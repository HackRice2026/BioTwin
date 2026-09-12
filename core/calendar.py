import hashlib
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from shared.schemas import BusyInterval, utcnow
from modeling.planning import overlaps

CALENDAR_PROVIDERS = ("google-calendar", "microsoft-calendar")


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
                BusyInterval(start=day + timedelta(hours=a), end=day + timedelta(hours=b), title=title)
                for a, b, title in [
                    (9, 10, "Focus time"),
                    (11, 12, "Team catch-up"),
                    (15, 16, "Project work"),
                ]
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
