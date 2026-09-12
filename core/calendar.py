import hashlib
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from shared.schemas import BusyInterval, utcnow
from modeling.planning import overlaps


class CalendarService:
    def __init__(self, oauth, http, store):
        self.oauth, self.http, self.store = oauth, http, store

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
        token = self.oauth.token(uid, "google-calendar")
        headers = {"Authorization": f"Bearer {token}"}
        # Calendar-owned timezone takes precedence when configured; users can select it in preferences.
        ids = user["profile"].get("calendar_ids", ["primary"])
        response = await self.http.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            headers=headers,
            json={
                "timeMin": day.isoformat(),
                "timeMax": (day + timedelta(days=1)).isoformat(),
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
            raise ValueError("Sign into your own account and connect Google Calendar to add real events")
        if proposal.start <= utcnow():
            raise ValueError("This time has passed; refresh the plan")
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
