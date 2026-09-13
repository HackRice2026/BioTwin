import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import httpx
from fastapi import (
    FastAPI,
    Request,
    Response,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlsplit
from fastapi.responses import RedirectResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.exc import IntegrityError, OperationalError
from shared.schemas import TwinFrame, utcnow, Provenance, DailyPlan, RecoveryPrediction, NarrationResponse
from core.config import Settings
from core.runtime import Runtime
from core.agenda import AgendaService, EventDraft, calendar_question
from narration.calendar import prepare_event, calendar_context
from core.security import hash_password, verify_password
from core.watch import issue_token, authenticate as authenticate_watch
from ingestion.adapters.watch import WatchBatch, watch_frames, WATCH_METRICS
from ingestion.adapters.garmin import parse_fit, parse_summary
from ingestion.adapters.replay import ReplayAdapter
from ingestion.normalizer import METRICS
from modeling.explanations import narration_context
from modeling.recovery import score_prediction
from modeling.outlook import daily_outlook
from narration.service import narrate
from narration.transcription import transcribe


def data_source_label(database_url: str) -> str:
    url = database_url.lower()
    if url.startswith("sqlite"):
        return "sqlite"
    if "supabase" in url:
        return "supabase"
    if url.startswith("postgres"):
        return "postgres"
    return "database"


class AuthInput(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default="", max_length=60)
    adult: bool = False


class ProfileInput(BaseModel):
    timezone: str = "America/Chicago"
    bedtime: str = "23:00"
    target_sleep: int = Field(default=480, ge=360, le=600)
    workout_minutes: int = Field(default=30, ge=10, le=120)
    naps_enabled: bool = True
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"], max_length=10)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    request_id: str = Field(default_factory=lambda: secrets.token_hex(16), pattern=r"^[a-zA-Z0-9_-]{16,64}$")
    calendar_start: date | None = None
    calendar_end: date | None = None
    calendar_mode: bool = False



class AddEvent(BaseModel):
    proposal_id: str
    reminder_minutes: int = Field(default=10, ge=0, le=10080)


APPROVAL_RE = re.compile(
    r"\b(yes|yeah|yep|go ahead|approve|confirm|book it|add it|do it|put it|sounds good|looks good)\b",
    re.I,
)
COACH_DRAFT_RE = re.compile(
    r"\b(recommend|suggest|draft|plan|when should|best window|find me|workout|movement|nap)\b",
    re.I,
)


def wants_pending_calendar_approval(question):
    return bool(APPROVAL_RE.search(question))


def wants_coach_calendar_draft(question):
    return bool(COACH_DRAFT_RE.search(question)) and not re.search(
        r"\b(add|create|book|put|remind)\b|\bschedule\s+(a|an|the|my|me)\b",
        question,
        re.I,
    )


async def approve_pending_calendar_event(runtime, owner, u):
    pending = runtime.store.get(owner, "pending_calendar_draft")
    if not pending:
        return None
    created = await AgendaService(runtime.calendar).confirm(u, pending["id"])
    runtime.store.remove_doc(owner, "pending_calendar_draft")
    title = pending.get("title", "that plan")
    return (
        NarrationResponse(
            answer=f"Done, I added {title} to your Google Calendar.",
            mode="template",
        ),
        created,
    )


async def propose_coach_calendar_draft(runtime, owner, u, question, plan):
    if not plan or not plan.proposals:
        return None
    q = question.lower()
    proposal = next((p for p in plan.proposals if p.kind in q), plan.proposals[0])
    draft = await AgendaService(runtime.calendar).draft(
        u,
        {
            "title": f"BioTwin · {proposal.title}",
            "start": proposal.start.isoformat(),
            "end": proposal.end.isoformat(),
            "calendar_id": "primary",
            "location": "",
            "notes": proposal.reason,
            "reminder_minutes": 10,
        },
    )
    runtime.store.put(owner, "pending_calendar_draft", draft, require_user=True)
    local_start = proposal.start.astimezone(ZoneInfo(plan.timezone))
    local_end = proposal.end.astimezone(ZoneInfo(plan.timezone))
    return (
        NarrationResponse(
            answer=(
                f"I'd recommend {proposal.title.lower()} from {local_start.strftime('%I:%M %p').lstrip('0')} "
                f"to {local_end.strftime('%I:%M %p').lstrip('0')}. {proposal.reason} "
                "Want me to add it to your Google Calendar?"
            ),
            mode="template",
        ),
        draft,
    )


class BroadcastSample(BaseModel):
    heart_rate_bpm: float = Field(ge=25, le=250)
    event_time: datetime | None = None
    # Beat-to-beat intervals, when the sensor reports them. A wrist optical
    # sensor usually does not; a chest strap does. Carried so RMSSD can be
    # derived from measured intervals rather than inferred from a rate.
    rr_ms: list[float] = Field(default_factory=list, max_length=32)
    # Standard heart-rate service contact bits: False means off-body, which is a
    # reading to distrust rather than a reading to drop silently.
    contact: bool | None = None


def create_app(config=None):
    config = config or Settings()

    @asynccontextmanager
    async def lifespan(app):
        runtime = Runtime(config)
        app.state.runtime = runtime
        await runtime.start()
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(title="BioTwin", version="1.0.0", lifespan=lifespan)
    cors_origins = [config.frontend_origin, config.public_url]
    if config.lan_origin:
        cors_origins.append(config.lan_origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    limits = defaultdict(deque)

    @app.middleware("http")
    async def protections(request, call_next):
        if request.method in ["POST", "PUT", "DELETE"] and not request.url.path.startswith("/webhooks/"):
            origin = request.headers.get("origin")
            allowed = [config.frontend_origin, config.public_url]
            if config.lan_origin:
                allowed.append(config.lan_origin)
            if origin and origin not in allowed:
                return Response("Origin not allowed", 403)
        if request.url.path.startswith(("/auth/session", "/api/twin/", "/api/voice")):
            key = (request.client.host if request.client else "unknown", request.url.path)
            q = limits[key]
            now = time.monotonic()
            while q and q[0] < now - 60:
                q.popleft()
            if len(q) >= 30:
                return Response("Too many requests. Try again shortly.", 429)
            q.append(now)
        if int(request.headers.get("content-length", "0")) > 20 * 1024 * 1024:
            return Response("Upload exceeds 20 MB", 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith(("/api/", "/auth/", "/sources", "/ops/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def bad_value(request, exc):
        return Response(json.dumps({"detail": str(exc)}), 422, media_type="application/json")

    @app.exception_handler(httpx.HTTPError)
    async def vendor_error(request, exc):
        return Response(
            json.dumps(
                {
                    "detail": "The connected service could not complete this request. Check its connection and try again."
                }
            ),
            502,
            media_type="application/json",
        )

    @app.exception_handler(OperationalError)
    async def db_error(request, exc):
        return Response(
            json.dumps(
                {
                    "detail": "Storage is unavailable. The offline demo remains available; personal writes are paused."
                }
            ),
            503,
            media_type="application/json",
        )

    def rt():
        return app.state.runtime

    def user(request, personal=False):
        found = rt().store.session_user(request.cookies.get("biotwin_session"))
        if found:
            return found
        if personal or not config.demo_enabled:
            raise HTTPException(401, "Sign in to your own BioTwin account")
        return rt().store.user("demo")

    def public_user(u):
        return {k: u[k] for k in ["id", "name", "email", "profile"]}

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/readyz")
    async def ready():
        rt().store.stats()
        return {"status": "ready"}

    @app.get("/api/session")
    async def session(request: Request):
        u = user(request)
        return {
            "user": public_user(u),
            "demo": u["id"] == "demo",
            "data_source": data_source_label(config.database_url),
            "voice_configured": bool(config.elevenlabs_api_key),
            "narration_configured": bool(config.allow_external_narration and config.narration_api_key),
            "retention_days": config.retention_days,
        }

    @app.post("/auth/session/register")
    async def register(data: AuthInput, response: Response):
        if not data.adult:
            raise HTTPException(422, "BioTwin accounts are for adults aged 18 or older")
        if "@" not in data.email:
            raise ValueError("Enter a valid email address")
        uid = secrets.token_hex(16)
        try:
            rt().store.create_user(
                uid,
                data.email.lower().strip(),
                hash_password(data.password),
                data.name.strip() or "Your twin",
                ProfileInput().model_dump(),
            )
        except IntegrityError:
            raise HTTPException(409, "An account with that email already exists")
        response.set_cookie(
            "biotwin_session",
            rt().store.create_session(uid),
            httponly=True,
            secure=config.cookie_secure,
            samesite="lax",
            max_age=604800,
        )
        return {"user": public_user(rt().store.user(uid))}

    @app.post("/auth/session/login")
    async def login(data: AuthInput, response: Response):
        u = rt().store.by_email(data.email.lower().strip())
        valid = verify_password(
            data.password,
            u["password"] if u and u["password"] else hash_password("dummy-password-for-timing"),
        )
        if not u or not u["password"] or not valid:
            raise HTTPException(401, "Email or password is incorrect")
        response.set_cookie(
            "biotwin_session",
            rt().store.create_session(u["id"]),
            httponly=True,
            secure=config.cookie_secure,
            samesite="lax",
            max_age=604800,
        )
        return {"user": public_user(u)}

    @app.post("/auth/session/logout")
    async def logout(request: Request, response: Response):
        rt().store.end_session(request.cookies.get("biotwin_session", ""))
        response.delete_cookie("biotwin_session")
        return {"status": "signed_out"}

    @app.put("/api/profile")
    async def profile(data: ProfileInput, request: Request):
        u = user(request, True)
        try:
            ZoneInfo(data.timezone)
            datetime.strptime(data.bedtime, "%H:%M")
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use a valid IANA timezone and bedtime in HH:MM format")
        rt().store.save_profile(u["id"], data.model_dump())
        rt().refit_due.add(u["id"])
        return data

    @app.get("/api/state")
    async def state(request: Request):
        uid = user(request)["id"]
        return rt().states.get(uid) or rt().compute(uid)

    @app.get("/api/metrics")
    async def metrics(request: Request, metric: str = "heart_rate_bpm", days: int = 7):
        if metric not in METRICS or not 1 <= days <= 90:
            raise ValueError("Unknown metric or invalid history range")
        uid = user(request)["id"]
        query = request.query_params
        since = (
            datetime.fromisoformat(query["from"].replace("Z", "+00:00"))
            if "from" in query
            else utcnow() - timedelta(days=days)
        )
        until = datetime.fromisoformat(query["to"].replace("Z", "+00:00")) if "to" in query else utcnow()
        if since.tzinfo is None or until.tzinfo is None or until - since > timedelta(days=90):
            raise ValueError("Use timezone-aware timestamps and a range of at most 90 days")
        rows = [
            {
                "time": f.event_time.isoformat(),
                "value": getattr(f, metric).model_dump(mode="json")
                if metric == "sleep"
                else getattr(f, metric),
                "provenance": f.provenance.value,
                "confidence": f.confidence,
            }
            for f in rt().history(uid)
            if getattr(f, metric) is not None and since <= f.event_time <= until
        ]
        if len(rows) > 2000 and metric != "sleep":
            # Min/max envelope preserves spikes while capping response size.
            size = max(2, len(rows) // 900)
            rows = [
                r
                for i in range(0, len(rows), size)
                for r in sorted(
                    {
                        x["time"]: x
                        for x in [
                            min(rows[i : i + size], key=lambda x: x["value"]),
                            max(rows[i : i + size], key=lambda x: x["value"]),
                        ]
                    }.values(),
                    key=lambda x: x["time"],
                )
            ]
        return {"metric": metric, "series": rows}

    @app.get("/api/forecast")
    async def forecast(request: Request):
        """One-hour Body Battery forecast from the exported ridge coefficients.

        Returns availability rather than a number when the current Body Battery
        reading is stale: the model leans on that level heavily enough that
        extrapolating from an old one would be confidently wrong.
        """
        u = user(request)
        from modeling.forecast import predict

        return predict(
            rt().history(u["id"]),
            utcnow(),
            u["profile"].get("timezone", "UTC"),
        )

    @app.get("/api/forecast/trajectory")
    async def forecast_trajectory(request: Request):
        """Body Battery at 1, 3 and 6 hours ahead.

        Each point comes from whichever predictor measured best at that horizon
        -- the ridge only at an hour, this person's own hour-of-day rhythm
        beyond it -- and carries the method and validation error that produced
        it, so the widening uncertainty is on the chart rather than implied.
        """
        u = user(request)
        from modeling.forecast import trajectory

        return trajectory(
            rt().history(u["id"]),
            utcnow(),
            u["profile"].get("timezone", "UTC"),
        )

    @app.get("/api/baseline")
    async def get_baseline(request: Request):
        return (await state(request)).baseline_summary

    @app.post("/api/baseline/recompute")
    async def refit(request: Request):
        return rt().compute(user(request)["id"], refit=True).baseline_summary

    @app.get("/api/readiness/history")
    async def readiness_history(request: Request):
        return [p for _, p in sorted(rt().store.docs(user(request)["id"], "readiness"))]

    @app.get("/api/predictions")
    async def predictions(request: Request, scored: bool = False):
        uid = user(request)["id"]
        values = [
            score_prediction(
                RecoveryPrediction.model_validate(p),
                rt().prediction_window(uid, RecoveryPrediction.model_validate(p)),
            )
            for _, p in rt().store.docs(uid, "prediction")
        ]
        return [
            p
            for p in sorted(values, key=lambda p: p.issued_at, reverse=True)
            if not scored or p.rmse is not None
        ][:30]

    @app.get("/api/plan/today")
    async def plan(request: Request):
        return await rt().get_plan(user(request))

    @app.get("/api/outlook")
    async def outlook(request: Request):
        return daily_outlook(await state(request), user(request)["profile"], utcnow())

    @app.post("/api/plan/refresh")
    async def refresh_plan(request: Request):
        return await rt().get_plan(user(request), True)

    @app.get("/api/calendar/agenda")
    async def calendar_agenda(request: Request, start: date | None = None, end: date | None = None):
        return await AgendaService(rt().calendar).list(user(request), start, end)

    @app.post("/api/calendar/drafts")
    async def calendar_draft(data: EventDraft, request: Request):
        return await AgendaService(rt().calendar).draft(user(request, True), data.model_dump())

    @app.post("/api/calendar/drafts/{draft_id}/confirm")
    async def calendar_confirm(draft_id: str, request: Request):
        return await AgendaService(rt().calendar).confirm(user(request, True), draft_id)

    @app.post("/api/calendar/events")
    async def calendar_add(data: AddEvent, request: Request):
        u = user(request, True)
        stored = rt().store.get(u["id"], "plan")
        if not stored:
            raise ValueError("Generate a plan first")
        planned = DailyPlan.model_validate(stored)
        proposal = next((p for p in planned.proposals if p.id == data.proposal_id), None)
        if not proposal:
            raise ValueError("This proposal is out of date. Refresh your plan.")
        # The server rebuilds hard constraints from current readiness, before checking live calendar availability.
        current = await rt().get_plan(u, True)
        if not any(p.id == proposal.id and p.intensity == proposal.intensity for p in current.proposals):
            # Idempotent repeats can still return an event already created by this exact proposal.
            existing = rt().store.get(u["id"], "added_event", proposal.id)
            if existing:
                return existing
            raise ValueError(
                "Readiness or availability changed. Review the refreshed plan before adding an event."
            )
        event = await rt().calendar.add(u, proposal, data.reminder_minutes)
        result = {
            "id": event["id"],
            "url": event.get("htmlLink"),
            "status": "created",
            "reminder_minutes": data.reminder_minutes,
        }
        rt().store.put(u["id"], "added_event", result, proposal.id)
        return result

    @app.post("/api/calendar/seed")
    async def calendar_seed(request: Request):
        u = user(request, True)
        return await rt().calendar.seed_if_empty(u)

    def conversation_owner(request, response=None):
        u = user(request)
        if u["id"] != "demo":
            return u["id"]
        token = request.cookies.get("biotwin_conversation", "")
        if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            if response is None:
                return None
            token = secrets.token_hex(32)
            response.set_cookie(
                "biotwin_conversation",
                token,
                httponly=True,
                secure=config.cookie_secure,
                samesite="lax",
                max_age=604800,
            )
        # The public demo's measurements are shared; visitors' questions never are.
        return "guest:" + hashlib.sha256(token.encode()).hexdigest()

    def transcript(row):
        return {
            **{key: row[key] for key in ["id", "question", "answer", "mode", "notice", "model"]},
            "created_at": datetime.fromtimestamp(row["created_at"], timezone.utc).isoformat(),
            "completed_at": datetime.fromtimestamp(row["completed_at"], timezone.utc).isoformat()
            if row["completed_at"]
            else None,
        }

    def speech_ticket(owner, row):
        if not row or not row["answer"]:
            raise HTTPException(404, "This conversation has no completed answer to speak.")
        reply_id = secrets.token_hex(16)
        rt().store.put(
            owner, "speech", {"answer": row["answer"], "expires": utcnow().timestamp() + 300}, reply_id
        )
        return {"reply_id": reply_id, "voice_configured": bool(config.elevenlabs_api_key)}

    @app.post("/api/twin/transcribe")
    async def transcribe_question(request: Request, audio: UploadFile = File(...)):
        user(request)
        recording = await audio.read(5 * 1024 * 1024 + 1)
        mime_type = (audio.content_type or "").split(";", 1)[0]
        try:
            question = await transcribe(recording, mime_type, config, rt().http)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return {"question": question}

    @app.get("/api/twin/conversations")
    async def conversation_history(
        request: Request, limit: int = Query(30, ge=1, le=100), before: str | None = None
    ):
        owner = conversation_owner(request)
        rows = rt().store.conversation_history(owner, limit + 1, before) if owner else []
        more = len(rows) > limit
        rows = rows[-limit:]
        return {
            "conversations": [transcript(row) for row in rows],
            "next_before": rows[0]["id"] if more else None,
        }

    @app.post("/api/twin/conversations/{conversation_id}/speech")
    async def replay_speech(conversation_id: str, request: Request):
        owner = conversation_owner(request)
        row = rt().store.conversation(owner, conversation_id) if owner else None
        return speech_ticket(owner, row)

    @app.post("/api/twin/ask")
    async def ask(data: Question, request: Request, response: Response):
        u = user(request)
        owner = conversation_owner(request, response)
        question = data.question.strip()
        if not question:
            raise HTTPException(422, "Enter a question for your twin.")
        current = await state(request)
        if current.prediction:
            stored_prediction = rt().store.get(u["id"], "prediction", current.prediction.id)
            if stored_prediction:
                stored_score = rt().store.get(u["id"], "prediction_score", current.prediction.id) or {}
                current = current.model_copy(
                    update={
                        "prediction": RecoveryPrediction.model_validate({**stored_prediction, **stored_score})
                    }
                )
        stored = rt().store.get(u["id"], "plan")
        plan = DailyPlan.model_validate(stored) if stored else None
        if plan is None and u["id"] != "demo" and wants_coach_calendar_draft(question):
            try:
                plan = await rt().get_plan(u)
            except (ValueError, httpx.HTTPError):
                plan = None
        outlook = daily_outlook(current, u["profile"], utcnow())
        energy_trajectory = None
        try:
            from modeling.forecast import trajectory

            energy_trajectory = trajectory(
                rt().history(u["id"]),
                utcnow(),
                u["profile"].get("timezone", "UTC"),
            )
        except (ValueError, OSError, KeyError, TypeError):
            energy_trajectory = None
        ctx = narration_context(
            current,
            plan,
            [p for _, p in rt().store.docs(u["id"], "readiness")],
            outlook,
            energy_trajectory,
        )
        agenda = None
        if data.calendar_mode or calendar_question(question):
            agenda = await AgendaService(rt().calendar).list(u, data.calendar_start, data.calendar_end)
            ctx = ctx.model_copy(update={"calendar": calendar_context(agenda)})
        row, created = rt().store.begin_conversation(
            owner, data.request_id, question, ctx.model_dump(mode="json")
        )
        if created:
            approved = (
                await approve_pending_calendar_event(rt(), owner, u)
                if u["id"] != "demo" and wants_pending_calendar_approval(question)
                else None
            )
            if approved:
                answer, calendar_event = approved
                rt().store.put(
                    owner, "conversation_calendar_event", calendar_event, data.request_id, require_user=True
                )
            else:
                prepared = (
                    await prepare_event(question, agenda, u, AgendaService(rt().calendar), config, rt().http)
                    if agenda
                    else None
                )
                recommended = None
                if not prepared and u["id"] != "demo" and wants_coach_calendar_draft(question):
                    try:
                        recommended = await propose_coach_calendar_draft(rt(), owner, u, question, plan)
                    except (ValueError, httpx.HTTPError):
                        recommended = None
                if recommended:
                    answer, draft = recommended
                    rt().store.put(owner, "conversation_draft", draft, data.request_id, require_user=True)
                    calendar_event = None
                elif prepared:
                    answer, draft, calendar_event = prepared
                    if draft:
                        rt().store.put(owner, "conversation_draft", draft, data.request_id, require_user=True)
                    if calendar_event:
                        rt().store.put(
                            owner, "conversation_calendar_event", calendar_event, data.request_id, require_user=True
                        )
                else:
                    answer = await narrate(question, ctx, config, rt().http)
                    calendar_event = None
            row = rt().store.complete_conversation(owner, data.request_id, answer)
        elif row["mode"] == "pending":
            raise HTTPException(409, "Your twin is still answering this question. Try again shortly.")
        if row is None:
            raise HTTPException(410, "This account or conversation was deleted.")
        return {
            **transcript(row),
            "grounded": True,
            **speech_ticket(owner, row),
            "calendar_draft": rt().store.get(owner, "conversation_draft", data.request_id),
            "calendar_event": rt().store.get(owner, "conversation_calendar_event", data.request_id),
        }

    @app.get("/api/voice/{reply_id}")
    async def voice(reply_id: str, request: Request, timestamps: bool = False):
        uid = conversation_owner(request)
        if not config.elevenlabs_api_key:
            raise HTTPException(
                503,
                "ElevenLabs needs ELEVENLABS_API_KEY in the server .env. Your text answer is still available.",
            )
        speech = rt().store.take(uid, "speech", reply_id) if uid else None
        if not speech or speech["expires"] < utcnow().timestamp():
            raise HTTPException(404, "Speech expired. Ask the twin again.")
        upstream = rt().http.build_request(
            "POST",
            f"https://api.elevenlabs.io/v1/text-to-speech/{config.elevenlabs_voice_id}/stream"
            + ("/with-timestamps" if timestamps else ""),
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": config.elevenlabs_api_key},
            json={"text": speech["answer"], "model_id": config.elevenlabs_model_id},
        )
        try:
            response = await rt().http.send(upstream, stream=True)
        except httpx.HTTPError:
            raise HTTPException(
                502, "ElevenLabs is unavailable. Your text answer is saved; try Listen again."
            ) from None
        if response.status_code != 200:
            await response.aclose()
            raise HTTPException(
                502,
                "The selected ElevenLabs voice requires a paid plan or more credits. Choose a voice available to your account. Your text answer is saved."
                if response.status_code == 402
                else "ElevenLabs could not generate speech. Check your API key, voice access, and credit balance. Your text answer is saved.",
            )

        stream = response.aiter_bytes()
        try:
            first = await anext(stream)
            if not first:
                raise StopAsyncIteration
        except (httpx.HTTPError, StopAsyncIteration):
            await response.aclose()
            raise HTTPException(
                502, "ElevenLabs returned no usable audio. Your text answer is saved."
            ) from None

        async def chunks():
            try:
                yield first
                async for chunk in stream:
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(
            chunks(),
            media_type="application/x-ndjson" if timestamps else "audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/sources")
    async def sources(request: Request):
        u = user(request)
        result = []
        for provider in ["garmin", "fitbit", "google-calendar", "microsoft-calendar"]:
            connection = rt().store.get(u["id"], "connection", provider)
            cid, secret = rt().oauth.credentials(provider)
            history = [f for f in rt().history(u["id"]) if f.provenance.value.startswith(provider)]
            result.append(
                {
                    "provider": provider,
                    "status": connection["status"] if connection else "not_connected",
                    "configured": bool(cid and secret and config.token_encryption_key),
                    "last_frame": max((f.event_time for f in history), default=None),
                    "sync": rt().store.get(u["id"], "sync", provider),
                }
            )
        return {
            "sources": result,
            "elevenlabs": {
                "configured": bool(config.elevenlabs_api_key),
                "model": config.elevenlabs_model_id,
            },
            "demo": u["id"] == "demo",
        }

    def origin_of(request):
        """Which allowed origin this request came from, or "" if it is not one
        of them. Consent has to return the browser somewhere it can actually
        reach: served from public_url, the Vite dev server, or the LAN address
        are all normal, and frontend_origin alone is only right for the second."""
        allowed = [o for o in (config.frontend_origin, config.public_url, config.lan_origin) if o]
        candidate = request.headers.get("origin") or ""
        if not candidate:
            referer = request.headers.get("referer") or ""
            if referer:
                parts = urlsplit(referer)
                candidate = f"{parts.scheme}://{parts.netloc}" if parts.scheme else ""
        return candidate if candidate in allowed else ""

    @app.get("/auth/{provider}/start")
    async def start_oauth(provider: str, request: Request):
        uid = user(request, True)["id"]
        return {"url": rt().oauth.start(provider, uid, origin_of(request))}

    @app.get("/auth/{provider}/callback")
    async def oauth_callback(provider: str, request: Request, state: str, code: str = "", error: str = ""):
        uid = user(request, True)["id"]
        if error or not code:
            raise ValueError("Connection was not approved; return to BioTwin and reconnect")
        return_to = await rt().oauth.callback(provider, uid, state, code)
        if provider in rt().adapters:
            rt().store.enqueue("sync", {"user_id": uid, "provider": provider})
            rt().wakeup.set()
        elif provider == "google-calendar":
            # Fetch the primary calendar timezone after consent. Google's
            # calendar timeZone is a real IANA name, the same shape stored
            # in profile.timezone and fed straight into ZoneInfo() elsewhere.
            r = await rt().http.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary",
                headers={"Authorization": f"Bearer {rt().oauth.token(uid, provider)}"},
            )
            r.raise_for_status()
            profile = rt().store.user(uid)["profile"]
            if r.json().get("timeZone"):
                rt().store.save_profile(uid, {**profile, "timezone": r.json()["timeZone"]})
        # microsoft-calendar: deliberately not auto-detected. Graph's own
        # mailboxSettings.timeZone comes back as a Windows timezone name
        # ("Pacific Standard Time"), not IANA -- saving that into
        # profile.timezone would break every ZoneInfo(...) call downstream
        # instead of just leaving the existing/default zone in place.
        return RedirectResponse((return_to or config.frontend_origin) + "/?connected=" + provider)

    @app.delete("/auth/{provider}")
    async def disconnect(provider: str, request: Request):
        await rt().oauth.disconnect(user(request, True)["id"], provider)
        return {"status": "disconnected"}

    @app.post("/api/sources/{provider}/sync")
    async def sync_source(provider: str, request: Request):
        uid = user(request, True)["id"]
        if provider not in rt().adapters:
            raise ValueError("Unknown source")
        rt().oauth.token(uid, provider)
        rt().store.enqueue("sync", {"user_id": uid, "provider": provider})
        rt().wakeup.set()
        return {"status": "queued"}

    @app.post("/api/watch/token")
    async def watch_token(request: Request):
        return issue_token(rt().store, user(request, True)["id"])

    @app.delete("/api/watch/token")
    async def revoke_watch(request: Request):
        rt().store.remove_doc(user(request, True)["id"], "watch_device")
        return {"status": "revoked"}

    @app.get("/api/watch")
    async def watch_status(request: Request):
        uid = user(request, True)["id"]
        device = rt().store.get(uid, "watch_device")
        if uid not in rt().latest_index:
            rt().compute(uid)
        readings = {}
        for wire_metric, stored_metric in WATCH_METRICS.items():
            frame = rt().latest_index[uid].get((stored_metric, Provenance.GARMIN_CIQ_LIVE))
            if frame is not None:
                readings[wire_metric] = {
                    "value": getattr(frame, stored_metric),
                    "event_time": frame.event_time,
                }
        return {
            "paired": bool(device and device["expires"] > utcnow().timestamp()),
            "expires_at": device["expires_at"] if device else None,
            "sync": rt().store.get(uid, "watch_sync"),
            "readings": readings,
        }

    @app.post("/api/ingest/watch")
    async def watch_ingest(data: WatchBatch, request: Request):
        uid = authenticate_watch(rt().store, request.headers.get("x-api-key"))
        if uid is None:
            raise HTTPException(401, "Invalid or expired watch token. Pair the watch in Connections.")
        # Bound load per credential; normal operation makes twelve requests/minute.
        q = limits[(uid, "watch")]
        now = time.monotonic()
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= 30:
            raise HTTPException(429, "Watch request limit exceeded", headers={"Retry-After": "5"})
        q.append(now)
        # Validate every row before the first write. Retries of partially committed
        # batches (e.g. after a storage outage) are safe through normal deduplication.
        records = watch_frames(data, uid, config.retention_days)
        added = 0
        for frame in records:
            added += bool(await rt().ingest(frame, broadcast=False))
        if added:
            rt().publish(uid, rt().compute(uid))
        rt().store.put(
            uid,
            "watch_sync",
            {
                "received_at": utcnow().isoformat(),
                "last_event_time": records[-1].event_time.isoformat(),
                "accepted": added,
                "duplicates": len(records) - added,
            },
        )
        return {
            "accepted": added,
            "duplicates": len(records) - added,
            "sequence": rt().store.user(uid)["sequence"],
        }

    @app.post("/api/connect/garmin-influx/sync")
    async def sync_garmin_influx(request: Request):
        # A local database pull, not an OAuth provider -- runs inline
        # (like /api/ingest/file) rather than through the OAuth-oriented
        # outbox queue sync_source() above, which requires a vendor token
        # this source doesn't have.
        uid = user(request, True)["id"]
        await rt().sync(uid, "garmin_influx")
        return rt().store.get(uid, "sync", "garmin_influx")

    @app.get("/api/connect/garmin-influx/health")
    async def garmin_influx_health():
        return await rt().adapters["garmin_influx"].health()

    @app.post("/api/connect/garmin-influx/live/start")
    async def start_garmin_influx_live(request: Request):
        uid = user(request, True)["id"]
        return await rt().start_influx_live_sync(uid)

    @app.post("/api/connect/garmin-influx/live/stop")
    async def stop_garmin_influx_live(request: Request):
        uid = user(request, True)["id"]
        return await rt().stop_influx_live_sync(uid)

    @app.get("/api/connect/garmin-influx/live/status")
    async def garmin_influx_live_status(request: Request):
        uid = user(request, True)["id"]
        return rt().influx_sync_status.get(uid, {"status": "stopped"})

    @app.post("/api/connect/garmin-ble-bridge/start")
    async def start_garmin_ble_bridge(request: Request):
        uid = user(request, True)["id"]
        return await rt().start_ble_bridge(uid)

    @app.post("/api/connect/garmin-ble-bridge/stop")
    async def stop_garmin_ble_bridge(request: Request):
        uid = user(request, True)["id"]
        return await rt().stop_ble_bridge(uid)

    @app.get("/api/connect/garmin-ble-bridge/status")
    async def garmin_ble_bridge_status(request: Request):
        uid = user(request, True)["id"]
        return rt().ble_bridge_status.get(uid, {"status": "stopped"})

    @app.post("/api/ingest/bluetooth")
    async def bluetooth(data: BroadcastSample, request: Request):
        uid = user(request, True)["id"]
        rmssd = rt().rr_rmssd(uid, data.rr_ms) if data.rr_ms else None
        f = TwinFrame(
            user_id=uid,
            event_time=data.event_time or utcnow(),
            provenance=Provenance.GARMIN_BLE_LIVE,
            heart_rate_bpm=data.heart_rate_bpm,
            hrv_rmssd_ms=rmssd,
            # Off-body contact is reported, not hidden: the measurement still
            # arrives and the model weighs it less.
            confidence=0.4 if data.contact is False else 1.0,
        )
        committed = await rt().ingest(f)
        return {
            "sequence": committed.sequence if committed else None,
            "hrv_rmssd_ms": rmssd,
            "rr_intervals": len(data.rr_ms),
        }

    @app.post("/api/ingest/file")
    async def import_file(request: Request, file: UploadFile = File(...)):
        uid = user(request, True)["id"]
        raw = await file.read(20 * 1024 * 1024 + 1)
        if len(raw) > 20 * 1024 * 1024:
            raise HTTPException(413, "Keep each import below 20 MB")
        if (file.filename or "").lower().endswith(".fit"):
            try:
                records = await asyncio.to_thread(parse_fit, raw, uid)
            except Exception as exc:
                raise ValueError(
                    "This FIT file could not be read. Export the original activity FIT file with heart-rate measurements."
                ) from exc
        else:
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                raise ValueError("Choose a Garmin .FIT file or a supported JSON export")
            rows = (
                payload
                if isinstance(payload, list)
                else payload.get("frames", payload.get("dailies", payload.get("sleeps", [])))
            )
            if not isinstance(rows, list) or not rows or len(rows) > 100000:
                raise ValueError(
                    "JSON must contain a nonempty frames, dailies, or sleeps array (up to 100,000 records)"
                )
            records = []
            for row in rows:
                if "startTimeInSeconds" in row:
                    records.extend(parse_summary(row, uid, Provenance.GARMIN_FIT_REPLAY))
                else:
                    records.append(
                        TwinFrame.model_validate(
                            {**row, "user_id": uid, "provenance": Provenance.REPLAY, "ingest_time": utcnow()}
                        )
                    )
        # Validate the entire import before committing any records.
        from ingestion.normalizer import normalize

        records = [normalize(f) for f in records]
        if any(f.event_time > utcnow() + timedelta(minutes=5) for f in records):
            raise ValueError("Import contains measurements in the future")
        added = 0
        for f in sorted(records, key=lambda f: f.event_time):
            added += bool(await rt().ingest(f, broadcast=False))
        rt().publish(uid, rt().compute(uid, refit=True))
        return {"imported": added, "duplicates": len(records) - added, "provenance": "recorded"}

    @app.post("/ingest/replay")
    async def replay(request: Request):
        uid = user(request, True)["id"]
        data = await request.json()
        adapter = ReplayAdapter(data.get("frames", []), float(data.get("speed", 1)))
        if not adapter.records or len(adapter.records) > 10000:
            raise ValueError("Supply between 1 and 10,000 recorded frames")
        # Validate before acknowledging the session.
        for row in adapter.records:
            TwinFrame.model_validate({**row, "user_id": uid, "provenance": Provenance.REPLAY})

        async def run():
            async for f in adapter.stream(uid):
                await rt().ingest(f)

        rt().tasks.append(asyncio.create_task(run()))
        return {"status": "replaying", "speed": adapter.speed}

    @app.post("/webhooks/google-health")
    async def google_webhook(request: Request):
        secret = config.google_webhook_secret
        if not secret or not hmac.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {secret}"
        ):
            rt().counters["webhook_verification_failures"] += 1
            raise HTTPException(401, "Invalid webhook authorization")
        raw = await request.body()
        if len(raw) > 1024 * 1024:
            raise HTTPException(413, "Webhook too large")
        data = json.loads(raw)
        if data == {"type": "verification"}:
            return Response(status_code=200)
        try:
            await rt().verifier.verify(raw, request.headers.get("google-health-api-signature", ""))
        except Exception:
            rt().counters["webhook_verification_failures"] += 1
            raise HTTPException(401, "Invalid webhook signature")
        rt().store.enqueue("fitbit", data)
        rt().wakeup.set()
        return Response(status_code=204)

    @app.post("/webhooks/garmin")
    async def garmin_webhook(request: Request):
        # Configure this shared authorization header in the approved partner webhook delivery setup.
        if not config.garmin_webhook_secret or not hmac.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {config.garmin_webhook_secret}"
        ):
            raise HTTPException(401, "Invalid Garmin webhook authorization")
        rt().store.enqueue("garmin", await request.json())
        rt().wakeup.set()
        return Response(status_code=204)

    @app.get("/api/data/export")
    async def export(request: Request):
        uid = user(request, True)["id"]
        return Response(
            json.dumps(
                {
                    "frames": [f.model_dump(mode="json") for f in rt().history(uid)],
                    "conversations": [transcript(row) for row in rt().store.conversation_history(uid)],
                }
            ),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=biotwin-data.json"},
        )

    @app.delete("/api/data")
    async def delete_account(request: Request, response: Response):
        uid = user(request, True)["id"]
        failures = []
        for provider, _ in rt().store.docs(uid, "connection"):
            try:
                await rt().oauth.disconnect(uid, provider)
            except Exception:
                failures.append(provider)
        rt().store.delete_user(uid)
        rt().forget(uid)
        for queue in rt().subscribers.pop(uid, set()):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(None)
        response.delete_cookie("biotwin_session")
        return {"status": "deleted", "provider_revocation_failed": failures}

    @app.get("/ops/status")
    async def ops(request: Request):
        u = user(request)
        return {
            "storage": data_source_label(config.database_url),
            "demo": u["id"] == "demo",
            "counters": dict(rt().counters),
            "clients": len(rt().subscribers[u["id"]]),
            "errors": rt().errors,
            "state_sequence": rt().states.get(u["id"]).sequence if u["id"] in rt().states else 0,
            "model_version": "recovery-1.0.0",
            "queue": rt().store.stats()["queue"],
        }

    @app.websocket("/ws/live")
    async def websocket(ws: WebSocket):
        allowed = [config.frontend_origin, config.public_url]
        if config.lan_origin:
            allowed.append(config.lan_origin)
        if ws.headers.get("origin") not in allowed:
            await ws.close(code=1008)
            return
        u = rt().store.session_user(ws.cookies.get("biotwin_session"))
        if not u and config.demo_enabled:
            u = rt().store.user("demo")
        if not u:
            await ws.close(code=1008)
            return
        await ws.accept()
        uid = u["id"]
        queue = asyncio.Queue(maxsize=1)
        rt().subscribers[uid].add(queue)
        try:
            hello = await asyncio.wait_for(ws.receive_json(), 10)
            if hello.get("type") != "hello":
                await ws.close(code=1008)
                return
            last = int(hello.get("last_sequence", 0))
            current = rt().states.get(uid) or rt().compute(uid)
            states = [s for s in rt().buffers[uid] if s.sequence > last]
            if last and states and rt().buffers[uid][0].sequence <= last + 1:
                await ws.send_json({"type": "resume", "from": states[0].sequence})
                for s in states[-500:]:
                    await ws.send_json({"type": "state", "payload": s.model_dump(mode="json")})
            else:
                await ws.send_json({"type": "state", "payload": current.model_dump(mode="json")})

            async def receive():
                while True:
                    message = await asyncio.wait_for(ws.receive_json(), 45)
                    if message.get("type") not in ["ack", "heartbeat"]:
                        raise ValueError("Unsupported socket message")

            receiver = asyncio.create_task(receive())
            try:
                while not receiver.done():
                    try:
                        s = await asyncio.wait_for(queue.get(), 15)
                        if s is None:
                            await ws.close(code=1008)
                            return
                        await asyncio.wait_for(
                            ws.send_json({"type": "state", "payload": s.model_dump(mode="json")}), 5
                        )
                    except TimeoutError:
                        await asyncio.wait_for(
                            ws.send_json({"type": "heartbeat", "t": utcnow().timestamp()}), 5
                        )
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
        except (WebSocketDisconnect, TimeoutError, ValueError, RuntimeError):
            rt().counters["ws_disconnects"] += 1
        finally:
            rt().subscribers[uid].discard(queue)

    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        async def spa(path: str):
            candidate = (dist / path).resolve()
            if candidate.is_relative_to(dist) and candidate.is_file():
                return FileResponse(candidate)
            if path.startswith(("api/", "auth/", "webhooks/")):
                raise HTTPException(404)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
