import hashlib
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from shared.schemas import BusyInterval, utcnow
from modeling.planning import overlaps

CALENDAR_PROVIDERS = ("google-calendar", "microsoft-calendar")


def _t(h, m=0):
    return timedelta(hours=h, minutes=m)


# A representative week, not the same three blocks repeated every day --
# 4 classes at scattered/irregular times (not a clean grid -- a real student
# schedule rarely is), ~20 campus-work hours split into weekday shifts inside
# 9-5, and 4 professor/club meetings. Keyed by Python's Monday=0 weekday();
# weekends are deliberately light, same as most students actually run.
DEMO_WEEKLY_SCHEDULE = {
    0: [  # Monday
        (_t(9), _t(9, 50), "Class · Data Structures"),
        (_t(10), _t(14), "Work · Campus IT help desk"),
        (_t(18), _t(19), "Club · Robotics club meeting"),
    ],
    1: [  # Tuesday
        (_t(9), _t(12, 30), "Work · Campus IT help desk"),
        (_t(13), _t(14, 15), "Class · Organic Chemistry"),
        (_t(16), _t(16, 45), "Office hours · Prof. Whitfield"),
    ],
    2: [  # Wednesday
        (_t(11), _t(11, 50), "Class · Microeconomics"),
        (_t(13), _t(17), "Work · Campus IT help desk"),
        (_t(17, 30), _t(18, 15), "Club · Data Science Club"),
    ],
    3: [  # Thursday
        (_t(9), _t(13), "Work · Campus IT help desk"),
        (_t(14, 30), _t(15, 15), "Office hours · Prof. Alvarez"),
        (_t(19), _t(20), "Club · Intramural soccer"),
    ],
    4: [  # Friday
        (_t(9), _t(13, 30), "Work · Campus IT help desk"),
        (_t(15), _t(16, 15), "Class · American Literature"),
    ],
    5: [],  # Saturday
    6: [],  # Sunday
}


class CalendarService:
    def __init__(self, oauth, http, store):
        self.oauth, self.http, self.store = oauth, http, store

    def connected_providers(self, uid):
        """Every calendar the user has connected, not just one -- the whole
        point of asking is "am I free", and a meeting sitting on a calendar
        this app never looks at is still a meeting."""
        return [p for p in CALENDAR_PROVIDERS if self.store.get(uid, "connection", p)]

    async def availability(self, user, force=False):
        uid = user["id"]
        tz = ZoneInfo(user["profile"].get("timezone", "UTC"))
        now = utcnow().astimezone(tz)
        day = datetime.combine(now.date(), time.min, tz)
        if uid == "demo":
            busy = [
                BusyInterval(start=day + a, end=day + b, title=title)
                for a, b, title in DEMO_WEEKLY_SCHEDULE[now.weekday()]
            ]
            return busy, "demo"
        cached = self.store.get(uid, "calendar")
        if (
            cached
            and not force
            and cached["expires"] > utcnow().timestamp()
            and cached["date"] == str(now.date())
        ):
            return [BusyInterval.model_validate(x) for x in cached["busy"]], "connected"
        providers = self.connected_providers(uid)
        if not providers:
            # Same "nothing connected" failure the old hardcoded
            # oauth.token(uid, "google-calendar") call used to raise.
            raise ValueError("Connect google-calendar first")
        window_start, window_end = day, day + timedelta(days=1)
        busy = []
        for provider in providers:
            fetch = self._google_busy if provider == "google-calendar" else self._microsoft_busy
            busy.extend(await fetch(uid, window_start, window_end, tz, user["profile"]))
        self.store.put(
            uid,
            "calendar",
            {
                "date": str(now.date()),
                "expires": utcnow().timestamp() + 120,
                "busy": [b.model_dump(mode="json") for b in busy],
            },
        )
        return busy, "connected"

    async def _google_busy(self, uid, window_start, window_end, tz, profile):
        token = self.oauth.token(uid, "google-calendar")
        # Calendar-owned timezone takes precedence when configured; users can select it in preferences.
        ids = profile.get("calendar_ids", ["primary"])
        response = await self.http.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "timeMin": window_start.isoformat(),
                "timeMax": window_end.isoformat(),
                "timeZone": str(tz),
                "items": [{"id": i} for i in ids],
            },
        )
        response.raise_for_status()
        busy = []
        for cal in response.json().get("calendars", {}).values():
            if cal.get("errors"):
                raise ValueError("A selected calendar could not be checked; availability is unverified")
            busy.extend(BusyInterval(start=b["start"], end=b["end"]) for b in cal.get("busy", []))
        return busy

    async def _microsoft_busy(self, uid, window_start, window_end, tz, profile):
        token = self.oauth.token(uid, "microsoft-calendar")
        # No `Prefer: outlook.timezone` header -- Graph's documented default
        # without it is UTC start/end values with no offset suffix, which is
        # simpler and less error-prone to parse correctly than juggling the
        # separate local-time/timeZone pair that header switches on.
        response = await self.http.get(
            "https://graph.microsoft.com/v1.0/me/calendarView",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "startDateTime": window_start.astimezone(timezone.utc).isoformat(),
                "endDateTime": window_end.astimezone(timezone.utc).isoformat(),
                "$select": "start,end,showAs",
                "$top": 250,
            },
        )
        response.raise_for_status()
        busy = []
        for e in response.json().get("value", []):
            # calendarView returns every event in range, not just busy ones
            # -- Google's freeBusy already filters this; match it here.
            if e.get("showAs") not in ("busy", "oof"):
                continue
            start = datetime.fromisoformat(e["start"]["dateTime"]).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(e["end"]["dateTime"]).replace(tzinfo=timezone.utc)
            busy.append(BusyInterval(start=start, end=end))
        return busy

    async def sync_events(self, user):
        """Incremental event cache, including cancellations; freeBusy remains conflict authority."""
        uid = user["id"]
        token = self.oauth.token(uid, "google-calendar")
        cached = self.store.get(uid, "calendar_events") or {"events": {}, "sync_token": None}
        params = {"maxResults": 2500, "singleEvents": "false"}
        if cached["sync_token"]:
            params["syncToken"] = cached["sync_token"]
        events = dict(cached["events"])
        while True:
            r = await self.http.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if r.status_code == 410 and "syncToken" in params:
                params = {"maxResults": 2500, "singleEvents": "false"}
                events = {}
                continue
            r.raise_for_status()
            payload = r.json()
            for e in payload.get("items", []):
                if e.get("status") == "cancelled":
                    events.pop(e["id"], None)
                else:
                    events[e["id"]] = {
                        k: e[k] for k in ["id", "summary", "start", "end", "recurrence"] if k in e
                    }
            if payload.get("nextPageToken"):
                params["pageToken"] = payload["nextPageToken"]
            else:
                self.store.put(
                    uid, "calendar_events", {"events": events, "sync_token": payload.get("nextSyncToken")}
                )
                return

    async def add(self, user, proposal, reminder_minutes=10):
        if user["id"] == "demo":
            raise ValueError("Sign into your own account and connect a calendar to add real events")
        if proposal.start <= utcnow():
            raise ValueError("This time has passed; refresh the plan")
        providers = self.connected_providers(user["id"])
        # One target, not both -- writing the same workout to two calendars
        # at once isn't "more agentic", it's a confusing double-book. Google
        # first since its idempotent PUT-by-id path is the more established
        # one here; Outlook only when Google isn't connected.
        if "google-calendar" in providers:
            return await self._add_google(user, proposal, reminder_minutes)
        if "microsoft-calendar" in providers:
            return await self._add_microsoft(user, proposal, reminder_minutes)
        raise ValueError("Connect Google Calendar or Outlook Calendar to add real events")

    async def seed_if_empty(self, user, days=7):
        """User-triggered, never automatic: if a connected calendar has
        nothing coming up in the next `days`, populate it with the same
        representative student week the demo account shows (DEMO_WEEKLY_
        SCHEDULE), so there's something real to navigate around instead of
        every slot reading as free. Refuses outright the moment anything is
        already on the calendar -- this only ever writes into empty space,
        never near existing events.
        """
        uid = user["id"]
        if uid == "demo":
            raise ValueError("The demo account already has a sample schedule built in")
        providers = self.connected_providers(uid)
        if not providers:
            raise ValueError("Connect Google Calendar or Outlook Calendar first")
        tz = ZoneInfo(user["profile"].get("timezone", "UTC"))
        now = utcnow().astimezone(tz)
        window_start = datetime.combine(now.date(), time.min, tz)
        window_end = window_start + timedelta(days=days)
        busy = []
        for provider in providers:
            fetch = self._google_busy if provider == "google-calendar" else self._microsoft_busy
            busy.extend(await fetch(uid, window_start, window_end, tz, user["profile"]))
        if busy:
            return {"seeded": False, "created": 0, "reason": "Your calendar already has events in the next week"}
        provider = "google-calendar" if "google-calendar" in providers else "microsoft-calendar"
        write = self._write_seed_google if provider == "google-calendar" else self._write_seed_microsoft
        created = 0
        for offset in range(days):
            day = window_start + timedelta(days=offset)
            for start_off, end_off, title in DEMO_WEEKLY_SCHEDULE[day.weekday()]:
                start, end = day + start_off, day + end_off
                if start <= now:
                    continue
                event_id = hashlib.sha256(f"{uid}:seed:{start.isoformat()}:{title}".encode()).hexdigest()[:40]
                await write(uid, event_id, title, start, end, tz)
                created += 1
        self.store.remove_doc(uid, "calendar")
        return {"seeded": True, "created": created}

    async def _write_seed_google(self, uid, event_id, title, start, end, tz):
        token = self.oauth.token(uid, "google-calendar")
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        existing = await self.http.get(f"{url}/{event_id}", headers=headers)
        if existing.status_code == 200:
            return existing.json()
        if existing.status_code != 404:
            existing.raise_for_status()
        response = await self.http.post(
            url,
            headers=headers,
            params={"sendUpdates": "none"},
            json={
                "id": event_id,
                "summary": title,
                "description": "Sample schedule added by BioTwin so there's something real to plan around.",
                "start": {"dateTime": start.isoformat(), "timeZone": str(tz)},
                "end": {"dateTime": end.isoformat(), "timeZone": str(tz)},
            },
        )
        if response.status_code == 409:
            response = await self.http.get(f"{url}/{event_id}", headers=headers)
        response.raise_for_status()
        return response.json()

    async def _write_seed_microsoft(self, uid, event_id, title, start, end, tz):
        token = self.oauth.token(uid, "microsoft-calendar")
        headers = {"Authorization": f"Bearer {token}"}
        ref = self.store.get(uid, "calendar_event_ref", event_id)
        if ref:
            existing = await self.http.get(
                f"https://graph.microsoft.com/v1.0/me/events/{ref['vendor_id']}", headers=headers
            )
            if existing.status_code == 200:
                return existing.json()
            if existing.status_code != 404:
                existing.raise_for_status()
        response = await self.http.post(
            "https://graph.microsoft.com/v1.0/me/events",
            headers=headers,
            json={
                "subject": title,
                "body": {
                    "contentType": "text",
                    "content": "Sample schedule added by BioTwin so there's something real to plan around.",
                },
                "start": {"dateTime": start.astimezone(tz).replace(tzinfo=None).isoformat(), "timeZone": str(tz)},
                "end": {"dateTime": end.astimezone(tz).replace(tzinfo=None).isoformat(), "timeZone": str(tz)},
            },
        )
        response.raise_for_status()
        created = response.json()
        self.store.put(uid, "calendar_event_ref", {"vendor_id": created["id"]}, event_id)
        return created

    async def _add_google(self, user, proposal, reminder_minutes):
        event_id = hashlib.sha256(f"{user['id']}:{proposal.id}".encode()).hexdigest()[:40]
        token = self.oauth.token(user["id"], "google-calendar")
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        existing = await self.http.get(f"{url}/{event_id}", headers=headers)
        if existing.status_code == 200:
            return existing.json()
        if existing.status_code != 404:
            existing.raise_for_status()
        busy, _ = await self.availability(user, force=True)
        if overlaps(proposal.start, proposal.end, busy):
            raise ValueError("Your calendar changed and this slot is now busy. Refresh the plan.")
        response = await self.http.post(
            url,
            headers=headers,
            params={"sendUpdates": "none"},
            json={
                "id": event_id,
                "summary": f"BioTwin · {proposal.title}",
                "description": "Personal wellness time planned in BioTwin.",
                "start": {
                    "dateTime": proposal.start.isoformat(),
                    "timeZone": user["profile"].get("timezone", "UTC"),
                },
                "end": {
                    "dateTime": proposal.end.isoformat(),
                    "timeZone": user["profile"].get("timezone", "UTC"),
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": reminder_minutes}],
                },
            },
        )
        if response.status_code == 409:
            response = await self.http.get(f"{url}/{event_id}", headers=headers)
        response.raise_for_status()
        self.store.remove_doc(user["id"], "calendar")
        return response.json()

    async def _add_microsoft(self, user, proposal, reminder_minutes):
        uid = user["id"]
        event_id = hashlib.sha256(f"{uid}:{proposal.id}".encode()).hexdigest()[:40]
        token = self.oauth.token(uid, "microsoft-calendar")
        headers = {"Authorization": f"Bearer {token}"}
        # Graph assigns its own event id on creation -- there's no
        # client-chosen-id PUT the way Google's path uses for idempotency,
        # so a local id -> vendor-event-id mapping stands in for it instead.
        ref = self.store.get(uid, "calendar_event_ref", event_id)
        if ref:
            existing = await self.http.get(
                f"https://graph.microsoft.com/v1.0/me/events/{ref['vendor_id']}", headers=headers
            )
            if existing.status_code == 200:
                return existing.json()
            if existing.status_code != 404:
                existing.raise_for_status()
        busy, _ = await self.availability(user, force=True)
        if overlaps(proposal.start, proposal.end, busy):
            raise ValueError("Your calendar changed and this slot is now busy. Refresh the plan.")
        # Graph's dateTimeTimeZone wants a *local, offset-free* clock time
        # paired with an explicit IANA zone -- unlike Google, which is happy
        # with an offset-inclusive ISO string next to the same zone name.
        # Sending proposal.start's own offset-suffixed isoformat() here
        # would double up the offset and land the event at the wrong hour.
        tz = ZoneInfo(user["profile"].get("timezone", "UTC"))
        response = await self.http.post(
            "https://graph.microsoft.com/v1.0/me/events",
            headers=headers,
            json={
                "subject": f"BioTwin · {proposal.title}",
                "body": {"contentType": "text", "content": "Personal wellness time planned in BioTwin."},
                "start": {
                    "dateTime": proposal.start.astimezone(tz).replace(tzinfo=None).isoformat(),
                    "timeZone": str(tz),
                },
                "end": {
                    "dateTime": proposal.end.astimezone(tz).replace(tzinfo=None).isoformat(),
                    "timeZone": str(tz),
                },
                "isReminderOn": True,
                "reminderMinutesBeforeStart": reminder_minutes,
            },
        )
        response.raise_for_status()
        created = response.json()
        self.store.put(uid, "calendar_event_ref", {"vendor_id": created["id"]}, event_id)
        self.store.remove_doc(uid, "calendar")
        return created
