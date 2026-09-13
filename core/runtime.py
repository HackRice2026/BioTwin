import asyncio
import json
import logging
import os
import time
from bisect import bisect_left, bisect_right, insort_right
from collections import defaultdict, deque, Counter
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
import httpx
import websockets
from shared.schemas import utcnow, TwinState, TwinFrame, Baseline, RecoveryPrediction, Provenance
from core.store import Store
from core.oauth import OAuth
from core.calendar import CalendarService
from ingestion.adapters.synthetic import SyntheticAdapter
from ingestion.adapters.fitbit import FitbitAdapter
from ingestion.adapters.garmin import GarminAdapter, parse_summary
from ingestion.adapters.influx_sync import InfluxSyncAdapter
from ingestion.normalizer import normalize, METRICS
from ingestion.webhooks import GoogleSignatureVerifier
from modeling.engine import baseline, readiness, reconcile, drivers
from modeling.recovery import issue_prediction, score_prediction
from modeling.planning import make_plan

log = logging.getLogger("biotwin")


class Runtime:
    def __init__(self, config):
        self.config = config
        self.store = Store(config.database_url)
        self.http = httpx.AsyncClient(timeout=20, follow_redirects=False)
        self.oauth = OAuth(config, self.store, self.http)
        self.calendar = CalendarService(self.oauth, self.http, self.store)
        self.verifier = GoogleSignatureVerifier(self.http)
        self.adapters = {
            "fitbit": FitbitAdapter(self.oauth, self.http),
            "garmin": GarminAdapter(self.oauth, self.http),
            "garmin_influx": InfluxSyncAdapter(self.http),
        }
        self.ble_bridge_tasks = {}
        self.ble_bridge_status = {}
        self.influx_sync_tasks = {}
        self.influx_sync_status = {}
        self.synthetic = SyntheticAdapter()
        self.history_cache = {}
        self.latest_index = {}
        self.readiness_inputs = {}
        self.states = {}
        self.buffers = defaultdict(lambda: deque(maxlen=500))
        self.subscribers = defaultdict(set)
        self.counters = Counter()
        self.tasks = []
        self.last_transition = {}
        self.refit_due = set()
        self.wakeup = asyncio.Event()
        self.errors = {}
        self.ingest_lock = asyncio.Lock()

    def history(self, uid):
        if uid not in self.history_cache:
            self.history_cache[uid] = self.store.history(
                uid, utcnow() - timedelta(days=self.config.retention_days)
            )
        return self.history_cache[uid]

    def index_frame(self, uid, frame):
        for metric in METRICS:
            if getattr(frame, metric) is not None:
                key = (metric, frame.provenance)
                prior = self.latest_index[uid].get(key)
                if prior is None or (frame.event_time, frame.sequence) >= (prior.event_time, prior.sequence):
                    self.latest_index[uid][key] = frame
        if frame.sleep is not None or frame.hrv_rmssd_ms is not None or frame.resting_hr_bpm is not None:
            self.readiness_inputs[uid].append(frame)

    def prediction_window(self, uid, prediction):
        history = self.history(uid)
        start = bisect_left(history, prediction.issued_at, key=lambda f: f.event_time)
        end = bisect_right(
            history,
            prediction.issued_at + timedelta(seconds=prediction.horizon_s),
            key=lambda f: f.event_time,
        )
        return history[start:end]

    def forget(self, uid):
        for cache in [
            self.history_cache,
            self.latest_index,
            self.readiness_inputs,
            self.states,
            self.buffers,
        ]:
            cache.pop(uid, None)

    async def start(self):
        if self.config.demo_enabled:
            if not self.store.user("demo"):
                self.store.create_user(
                    "demo",
                    "demo@biotwin.local",
                    "",
                    "Alex",
                    {
                        "timezone": "America/Chicago",
                        "bedtime": "23:00",
                        "target_sleep": 480,
                        "workout_minutes": 30,
                        "naps_enabled": True,
                    },
                )
            if self.config.demo_uses_real_data:
                # Opt-in (see config.py) -- the unauthenticated/no-session
                # fallback account (api.py's `user()` helper) IS "demo",
                # there's no separate "owner" slot. One-time purge of any
                # synthetic frames + the documents derived from them (stale
                # baselines/readiness/predictions computed while synthetic
                # data was mixed in) -- idempotent, matches zero rows once
                # already clean -- then "demo" becomes a normal live
                # Garmin-InfluxDB sync target like any other account, just
                # auto-started instead of waiting for a Connect click.
                self.store.purge_provenance("demo", Provenance.SYNTHETIC.value)
                self.history_cache.pop("demo", None)
                self.states.pop("demo", None)
                await self.start_influx_live_sync("demo")
            else:
                # Project default: an explicitly synthetic demo workspace.
                if not self.store.history("demo", limit=1):
                    generated = []
                    async for f in self.synthetic.backfill("demo", utcnow() - timedelta(days=7)):
                        generated.append(f)
                    for f in sorted(generated, key=lambda x: x.event_time):
                        # Prequential demo: issue predictions using only earlier sessions, then ingest later observations.
                        stamp = f.event_time
                        f = f.model_copy(update={"ingest_time": stamp + timedelta(milliseconds=50)})
                        committed = self.store.append(normalize(f))
                        self.history_cache.setdefault("demo", []).append(committed)
                        if f.activity_level == 0.03 and f.heart_rate_bpm and 131 < f.heart_rate_bpm < 140:
                            state = self.compute("demo", now=stamp, refit=True)
                            prediction = issue_prediction(stamp, state.latest, state.baseline_summary)
                            if prediction:
                                self.store.put(
                                    "demo",
                                    "prediction",
                                    prediction.model_dump(mode="json"),
                                    prediction.id,
                                    immutable=True,
                                )
                        if f.sleep:
                            self.compute("demo", now=stamp, refit=True)
                    self.states.pop("demo", None)
                self.compute("demo", refit=True)
                self.tasks.append(asyncio.create_task(self.demo_loop()))
        self.tasks.extend([asyncio.create_task(self.worker()), asyncio.create_task(self.maintenance())])

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.http.aclose()
        self.store.engine.dispose()

    def compute(self, uid, now=None, refit=False):
        historical = now is not None
        now = now or utcnow()
        user = self.store.user(uid)
        if not user:
            raise ValueError("Unknown account")
        history = self.history(uid)
        if historical:
            history = history[: bisect_right(history, now, key=lambda f: f.event_time)]
            recent, readiness_history = history, history
        else:
            if uid not in self.latest_index:
                self.latest_index[uid] = {}
                self.readiness_inputs[uid] = []
                for f in history:
                    self.index_frame(uid, f)
            recent = list(self.latest_index[uid].values())
            readiness_history = self.readiness_inputs[uid]
        previous = self.states.get(uid)
        stored = self.store.get(uid, "baseline")
        if (
            refit
            or uid in self.refit_due
            or not stored
            or (now - datetime.fromisoformat(stored["computed_at"])).total_seconds() > 300
        ):
            base = baseline(history, uid, now, user["profile"].get("timezone", "UTC"))
            self.store.put(uid, "baseline", base.model_dump(mode="json"))
            self.refit_due.discard(uid)
            self.counters["model_refits"] += 1
        else:
            base = Baseline.model_validate(stored)
        latest, quality = reconcile(recent, now)
        last = previous.readiness if previous else None
        if last:
            last = last.model_copy(update={"computed_at": self.last_transition.get(uid, last.computed_at)})
        score_history = [
            p["score"] for _, p in self.store.docs(uid, "readiness") if p.get("score") is not None
        ]
        ready = readiness(
            uid,
            readiness_history,
            base,
            now,
            quality,
            latest,
            previous=last,
            target_sleep=user["profile"].get("target_sleep", 480),
            timezone=user["profile"].get("timezone", "UTC"),
            scores=score_history[-60:],
        )
        if not previous or previous.readiness.state != ready.state:
            self.last_transition[uid] = now
        self.store.put(
            uid,
            "readiness",
            ready.model_dump(mode="json"),
            now.astimezone(ZoneInfo(user["profile"].get("timezone", "UTC"))).date().isoformat(),
        )
        provenance = latest.provenance if latest else Provenance.GARMIN_LIVE
        prediction = None
        candidates = self.store.docs(uid, "prediction")
        if candidates:
            issued = max(candidates, key=lambda x: x[1]["issued_at"])[1]
            original = RecoveryPrediction.model_validate(issued)
            prediction = score_prediction(original, self.prediction_window(uid, original))
            if prediction.rmse is not None:
                self.store.put(
                    uid,
                    "prediction_score",
                    {
                        "issued_at": issued["issued_at"],
                        "rmse": prediction.rmse,
                        "observed": [p.model_dump(mode="json") for p in prediction.observed],
                    },
                    prediction.id,
                )
        state = TwinState(
            sequence=user["sequence"],
            server_time=now,
            readiness=ready,
            latest=latest,
            baseline_summary=base,
            drivers=drivers(latest, ready, base, quality, now),
            quality=quality,
            provenance_banner=provenance,
            prediction=prediction.model_copy(update={"curve": [], "observed": []}) if prediction else None,
        )
        # A presentation estimate from already-computed signals. Readiness carries
        # sleep, HRV, resting HR and sleep debt; recovery adds a live rest component.
        # A missing live pulse is not evidence of zero recovery.
        if ready.score is not None:
            reserve = ready.score
            if state.drivers.pulse_hz is not None:
                reserve = .8 * reserve + 20 * state.drivers.recovery_progress
            state = state.model_copy(update={"energy_reserve_pct": round(max(0, min(100, reserve)))})
        self.states[uid] = state
        return state

    async def ingest(self, frame, broadcast=True):
        started = time.perf_counter()
        normalized = normalize(frame)
        if normalized.event_time > utcnow() + timedelta(minutes=5):
            raise ValueError("Measurement time is too far in the future")
        async with self.ingest_lock:
            existing = self.history(normalized.user_id)
            committed = self.store.append(normalized)
            if not committed:
                self.counters["duplicates_suppressed"] += 1
                return None
            uid = committed.user_id
            if existing and committed.event_time < existing[-1].event_time - timedelta(minutes=5):
                self.refit_due.add(uid)
                self.counters["late_frames"] += 1
            if not existing or committed.event_time >= existing[-1].event_time:
                existing.append(committed)
            else:
                insort_right(existing, committed, key=lambda f: (f.event_time, f.sequence))
            if uid in self.latest_index:
                self.index_frame(uid, committed)
            self.counters[f"frames_{committed.provenance.value}"] += 1
            if not broadcast:
                return committed
            state = self.compute(uid)
            if (
                state.latest
                and state.latest.heart_rate_bpm
                and state.drivers.exertion < 0.2
                and state.latest.heart_rate_bpm > state.baseline_summary.resting_hr.median + 25
            ):
                if not state.prediction or (utcnow() - state.prediction.issued_at).total_seconds() > 600:
                    pred = issue_prediction(utcnow(), state.latest, state.baseline_summary)
                    if pred:
                        self.store.put(
                            uid, "prediction", pred.model_dump(mode="json"), pred.id, immutable=True
                        )
                        state = state.model_copy(update={"prediction": pred})
            state = state.model_copy(update={"latency_ms": round((time.perf_counter() - started) * 1000, 2)})
            self.publish(uid, state)
            log.info(
                '{"event":"ingested","provenance":"%s","sequence":%d,"latency_ms":%.2f}',
                committed.provenance.value,
                committed.sequence,
                state.latency_ms,
            )
            return committed

    def publish(self, uid, state):
        if state.prediction:
            state = state.model_copy(
                update={"prediction": state.prediction.model_copy(update={"curve": [], "observed": []})}
            )
        self.states[uid] = state
        self.buffers[uid].append(state)
        for queue in self.subscribers[uid]:
            if queue.full():
                queue.get_nowait()
                self.counters["states_coalesced"] += 1
            queue.put_nowait(state)

    async def demo_loop(self):
        async for frame in self.synthetic.stream("demo"):
            try:
                await self.ingest(frame)
            except Exception as exc:
                self.errors["demo"] = type(exc).__name__
                log.error('{"event":"demo_failure","type":"%s"}', type(exc).__name__)

    async def get_plan(self, user, force=False):
        state = self.states.get(user["id"]) or self.compute(user["id"])
        try:
            busy, status = await self.calendar.availability(user, force)
        except (ValueError, httpx.HTTPError):
            busy, status = [], "unavailable"
            self.counters["calendar_unavailable"] += 1
        plan = make_plan(utcnow(), state.readiness, busy, user["profile"], status)
        self.store.put(user["id"], "plan", plan.model_dump(mode="json"))
        return plan

    async def sync(self, uid, provider, since=None):
        count = 0
        async for frame in self.adapters[provider].backfill(uid, since or utcnow() - timedelta(days=7)):
            if await self.ingest(frame, broadcast=False):
                count += 1
        self.publish(uid, self.compute(uid, refit=True))
        self.store.put(uid, "sync", {"at": utcnow().isoformat(), "count": count, "status": "ok"}, provider)

    async def start_ble_bridge(self, uid, ws_url=None):
        """Bridge live BLE heart-rate readings from the local
        `ble_hr_live.py` script's WebSocket into this user's live twin,
        the same way /api/ingest/bluetooth does for a browser's own Web
        Bluetooth connection -- just sourced from that terminal script
        instead of this tab's browser APIs, so it keeps running headless
        without needing the page to stay open or Web Bluetooth support.
        """
        existing = self.ble_bridge_tasks.get(uid)
        if existing and not existing.done():
            return {"status": "already_running"}
        ws_url = ws_url or os.environ.get("GARMIN_BLE_WS_URL", "ws://localhost:8765/ws")

        async def run():
            while True:
                try:
                    async with websockets.connect(ws_url, open_timeout=5) as ws:
                        self.ble_bridge_status[uid] = {"status": "connected", "url": ws_url}
                        async for message in ws:
                            data = json.loads(message)
                            hr = data.get("hr")
                            if hr is None:
                                continue
                            ts = data.get("ts")
                            event_time = datetime.fromisoformat(ts) if ts else utcnow()
                            await self.ingest(
                                TwinFrame(
                                    user_id=uid,
                                    event_time=event_time,
                                    provenance=Provenance.GARMIN_BLE_LIVE,
                                    heart_rate_bpm=hr,
                                )
                            )
                except asyncio.CancelledError:
                    self.ble_bridge_status[uid] = {"status": "stopped"}
                    raise
                except Exception as exc:
                    self.ble_bridge_status[uid] = {
                        "status": "error",
                        "detail": f"Could not reach {ws_url}: {exc}. Is ble_hr_live.py running?",
                    }
                    await asyncio.sleep(5)

        task = asyncio.create_task(run())
        self.ble_bridge_tasks[uid] = task
        self.tasks.append(task)
        self.ble_bridge_status[uid] = {"status": "connecting", "url": ws_url}
        return {"status": "starting"}

    async def stop_ble_bridge(self, uid):
        task = self.ble_bridge_tasks.pop(uid, None)
        if task:
            task.cancel()
        self.ble_bridge_status[uid] = {"status": "stopped"}
        return {"status": "stopped"}

    async def start_influx_live_sync(self, uid):
        """Keep following the InfluxDB garmin viz dashboard fills, instead
        of only pulling once per button click. Runs the initial backfill
        first (broadcast=False, same as a manual sync -- no point recomputing
        readiness hundreds of times for historical points), then switches to
        InfluxSyncAdapter.stream()'s rolling poll with broadcast=True so
        each new point updates the live twin/avatar as it lands, not just
        on the next page reload.
        """
        existing = self.influx_sync_tasks.get(uid)
        if existing and not existing.done():
            return {"status": "already_running"}

        async def run():
            # Retries the whole cycle (initial backfill + stream loop) on
            # any failure, not just within the stream -- this can now be
            # the app's always-on default data path (see Runtime.start()),
            # so a transient failure (e.g. InfluxDB/Docker not up yet when
            # this server starts) must recover on its own, the same way
            # the BLE bridge already retries its connection.
            while True:
                try:
                    await self.sync(uid, "garmin_influx")
                    self.influx_sync_status[uid] = {"status": "live"}
                    async for frame in self.adapters["garmin_influx"].stream(uid):
                        await self.ingest(frame)
                        self.influx_sync_status[uid] = {
                            "status": "live",
                            "last_frame_at": utcnow().isoformat(),
                        }
                except asyncio.CancelledError:
                    self.influx_sync_status[uid] = {"status": "stopped"}
                    raise
                except Exception as exc:
                    self.influx_sync_status[uid] = {"status": "retrying", "detail": str(exc)}
                    log.warning('{"event":"garmin_influx_live_retry","reason":"%s"}', exc)
                    await asyncio.sleep(10)

        task = asyncio.create_task(run())
        self.influx_sync_tasks[uid] = task
        self.tasks.append(task)
        self.influx_sync_status[uid] = {"status": "starting"}
        return {"status": "starting"}

    async def stop_influx_live_sync(self, uid):
        task = self.influx_sync_tasks.pop(uid, None)
        if task:
            task.cancel()
        self.influx_sync_status[uid] = {"status": "stopped"}
        return {"status": "stopped"}

    def lookup_identity(self, provider, vendor_id):
        return next(
            (
                d["user_id"]
                for _, d in self.store.docs(None, "identity")
                if d["provider"] == provider and d["vendor_id"] == vendor_id
            ),
            None,
        )

    async def worker(self):
        while True:
            job = self.store.claim()
            if not job:
                self.wakeup.clear()
                try:
                    await asyncio.wait_for(self.wakeup.wait(), 1)
                except TimeoutError:
                    pass
                continue
            try:
                provider, payload = job["provider"], job["payload"]
                if provider == "sync":
                    if self.store.user(payload["user_id"]):
                        await self.sync(payload["user_id"], payload["provider"])
                elif provider == "fitbit":
                    for notification in payload if isinstance(payload, list) else [payload]:
                        data = notification["data"]
                        uid = self.lookup_identity("fitbit", data["healthUserId"])
                        if not uid:
                            continue
                        if data["operation"] == "DELETE":
                            self.remove_vendor_data(uid, "fitbit", data)
                        else:
                            intervals = data.get("intervals", [])
                            stamps = [
                                x["physicalTimeInterval"]["startTime"]
                                for x in intervals
                                if "physicalTimeInterval" in x
                            ]
                            since = (
                                datetime.fromisoformat(min(stamps).replace("Z", "+00:00"))
                                if stamps
                                else utcnow() - timedelta(days=7)
                            )
                            async for f in self.adapters["fitbit"].fetch(
                                uid, since, [data["dataType"]], live=True
                            ):
                                await self.ingest(f)
                elif provider == "garmin":
                    for dataset, entries in payload.items():
                        for data in entries:
                            uid = self.lookup_identity("garmin", data["userId"])
                            if not uid:
                                continue
                            if "callbackURL" in data:
                                from urllib.parse import urlparse

                                target = urlparse(data["callbackURL"])
                                if (
                                    target.scheme != "https"
                                    or target.hostname != "apis.garmin.com"
                                    or not target.path.startswith("/wellness-api/")
                                ):
                                    raise ValueError("Untrusted Garmin callback URL")
                                response = await self.http.get(
                                    data["callbackURL"],
                                    headers={"Authorization": f"Bearer {self.oauth.token(uid, 'garmin')}"},
                                )
                                response.raise_for_status()
                                summaries = response.json()
                            else:
                                summaries = [data]
                            for summary in summaries:
                                for f in parse_summary(summary, uid):
                                    await self.ingest(f)
                self.store.finish(job)
            except Exception as exc:
                self.store.finish(job, type(exc).__name__)
                self.counters["worker_failures"] += 1
                self.errors["worker"] = type(exc).__name__

    def remove_vendor_data(self, uid, provider, payload):
        from core.store import frames, documents
        from sqlalchemy import delete, select
        from ingestion.adapters.fitbit import GOOGLE_TYPES

        # Vendor deletion is an explicit privacy exception to append-only measurement retention.
        with self.store.engine.begin() as c:
            metric = GOOGLE_TYPES.get(payload.get("dataType"), (None, None, None))[2]
            intervals = []
            tz = ZoneInfo(self.store.user(uid)["profile"].get("timezone", "UTC"))
            for item in payload.get("intervals", []):
                interval = item.get("physicalTimeInterval") or item.get("civilIso8601TimeInterval")
                if interval:
                    start = datetime.fromisoformat(interval["startTime"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(interval["endTime"].replace("Z", "+00:00"))
                    intervals.append(
                        (
                            start if start.tzinfo else start.replace(tzinfo=tz),
                            end if end.tzinfo else end.replace(tzinfo=tz),
                        )
                    )
            if not intervals and not payload.get("recordId"):
                raise ValueError("Vendor deletion lacks a target interval or record ID")
            target_ids = []
            for row in c.execute(
                select(frames).where(frames.c.user_id == uid, frames.c.provenance.like(provider + "%"))
            ).mappings():
                record = TwinFrame.model_validate(row["payload"])
                matches_id = bool(payload.get("recordId")) and (record.source_record_id or "").endswith(
                    "/" + payload["recordId"]
                )
                matches_interval = any(start <= record.event_time <= end for start, end in intervals)
                if matches_id or (matches_interval and metric and getattr(record, metric) is not None):
                    target_ids.append(row["id"])
            if target_ids:
                c.execute(delete(frames).where(frames.c.id.in_(target_ids)))
            c.execute(
                delete(documents).where(
                    documents.c.user_id == uid,
                    documents.c.kind.in_(["baseline", "readiness", "prediction", "prediction_score"]),
                )
            )
        self.forget(uid)
        self.publish(uid, self.compute(uid, refit=True))

    async def maintenance(self):
        iteration = 0
        while True:
            try:
                await self.oauth.refresh_due()
                if iteration % 5 == 0:
                    for provider, conn in self.store.docs(None, "connection"):
                        if conn["status"] != "connected":
                            continue
                        uid = conn["user_id"]
                        try:
                            if provider == "google-calendar":
                                await self.calendar.sync_events(self.store.user(uid))
                            else:
                                await self.sync(uid, provider, utcnow() - timedelta(minutes=10))
                        except Exception as exc:
                            self.store.put(
                                uid, "sync", {"status": "error", "error": type(exc).__name__}, provider
                            )
                if iteration % 60 == 0:
                    self.store.purge(self.config.retention_days)
                    cutoff = utcnow() - timedelta(days=self.config.retention_days)
                    for uid, history in self.history_cache.items():
                        self.history_cache[uid] = [f for f in history if f.event_time >= cutoff]
                    self.latest_index.clear()
                    self.readiness_inputs.clear()
                # Expired measurements stop driving live pulse even when the vendor is silent.
                for uid in list(self.states):
                    if uid != "demo" and self.store.user(uid):
                        self.publish(uid, self.compute(uid))
                iteration += 1
            except Exception as exc:
                self.errors["maintenance"] = type(exc).__name__
            await asyncio.sleep(60)
