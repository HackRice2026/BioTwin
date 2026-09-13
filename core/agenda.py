"""Named calendar events and optional tasks; free/busy still protects planner booking."""

import asyncio
import hashlib
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field

from core.calendar import DEMO_WEEKLY_SCHEDULE
from shared.schemas import utcnow

GOOGLE = "https://www.googleapis.com/calendar/v3"
TASKS = "https://tasks.googleapis.com/tasks/v1"


class EventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    start: str = Field(max_length=40)
    end: str = Field(max_length=40)
    all_day: bool = False
    calendar_id: str = Field(default="primary", max_length=1024)
    location: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=2000)
    reminder_minutes: int = Field(default=10, ge=0, le=10080)


def safe_link(value):
    return value if value and urlparse(value).scheme == "https" else None


def instant(value, tz):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
        if parsed.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != parsed.replace(tzinfo=None):
            raise ValueError(
                "This clock time does not exist because daylight saving time changes. Choose another time."
            )
    return parsed


class AgendaService:
    def __init__(self, calendar):
        self.calendar = calendar
        self.http, self.oauth, self.store = calendar.http, calendar.oauth, calendar.store

    async def pages(self, url, token, params=None, *, microsoft=False):
        rows, seen = [], set()
        params = dict(params or {})
        while True:
            response = await self.http.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
            response.raise_for_status()
            data = response.json()
            rows.extend(data.get("value" if microsoft else "items", []))
            following = data.get("@odata.nextLink" if microsoft else "nextPageToken")
            if not following:
                return rows
            if following in seen:
                raise ValueError("Calendar pagination could not finish. Please refresh.")
            seen.add(following)
            if microsoft:
                parsed = urlparse(following)
                if parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com":
                    raise ValueError("Calendar returned an invalid page link")
                url, params = following, {}
            else:
                params["pageToken"] = following

    async def google_calendars(self, uid):
        token = self.oauth.token(uid, "google-calendar")
        rows = await self.pages(
            f"{GOOGLE}/users/me/calendarList",
            token,
            {"maxResults": 250, "minAccessRole": "reader", "showHidden": "true"},
        )
        return [
            {
                "id": c["id"],
                "name": c.get("summaryOverride") or c.get("summary", "Calendar"),
                "primary": c.get("primary", False),
                "writable": c.get("accessRole") in ("owner", "writer"),
                "color": c.get("backgroundColor", "#8bc5a6"),
                "provider": "google-calendar",
            }
            for c in rows
            if not c.get("deleted")
        ]

    async def google_events(self, uid, cal, start, end, tz):
        token = self.oauth.token(uid, "google-calendar")
        events = await self.pages(
            f"{GOOGLE}/calendars/{quote(cal['id'], safe='')}/events",
            token,
            {
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "timeZone": str(tz),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 2500,
                "showDeleted": "false",
            },
        )
        result = []
        for e in events:
            if e.get("status") == "cancelled" or not e.get("start") or not e.get("end"):
                continue
            result.append(
                {
                    "id": f"google:{cal['id']}:{e['id']}",
                    "title": e.get("summary") or "Private event",
                    "start": e["start"].get("dateTime") or e["start"]["date"],
                    "end": e["end"].get("dateTime") or e["end"]["date"],
                    "all_day": "date" in e["start"],
                    "calendar_id": cal["id"],
                    "calendar_name": cal["name"],
                    "color": cal["color"],
                    "provider": "google-calendar",
                    "location": e.get("location", ""),
                    "description": e.get("description", ""),
                    "url": safe_link(e.get("htmlLink")),
                    "recurring": bool(e.get("recurringEventId")),
                    "busy": e.get("transparency") != "transparent",
                    "status": e.get("status", "confirmed"),
                }
            )
        return result

    async def google_tasks(self, uid):
        token = self.oauth.token(uid, "google-calendar")
        lists = await self.pages(f"{TASKS}/users/@me/lists", token, {"maxResults": 1000})
        result = []
        for tasklist in lists:
            rows = await self.pages(
                f"{TASKS}/lists/{quote(tasklist['id'], safe='')}/tasks",
                token,
                {"maxResults": 100, "showCompleted": "true", "showHidden": "true", "showAssigned": "true"},
            )
            for task in rows:
                if task.get("deleted"):
                    continue
                result.append(
                    {
                        "id": f"task:{tasklist['id']}:{task['id']}",
                        "title": task.get("title", "Task"),
                        "due": task.get("due", "")[:10] or None,
                        "list_name": tasklist.get("title", "Tasks"),
                        "completed": task.get("status") == "completed",
                        "notes": task.get("notes", ""),
                        "url": safe_link(task.get("webViewLink")),
                    }
                )
        return result

    async def microsoft_events(self, uid, start, end, tz):
        token = self.oauth.token(uid, "microsoft-calendar")
        rows = await self.pages(
            "https://graph.microsoft.com/v1.0/me/calendarView",
            token,
            {
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$top": 250,
                "$select": "id,subject,start,end,isAllDay,location,bodyPreview,webLink,showAs,isCancelled,type",
            },
            microsoft=True,
        )
        return [
            {
                "id": f"outlook:{e['id']}",
                "title": e.get("subject") or "Private event",
                "start": instant(e["start"]["dateTime"], timezone.utc).isoformat(),
                "end": instant(e["end"]["dateTime"], timezone.utc).isoformat(),
                "all_day": e.get("isAllDay", False),
                "calendar_id": "outlook-primary",
                "calendar_name": "Outlook",
                "color": "#86bafa",
                "provider": "microsoft-calendar",
                "location": e.get("location", {}).get("displayName", ""),
                "description": e.get("bodyPreview", ""),
                "url": safe_link(e.get("webLink")),
                "recurring": e.get("type") in ("occurrence", "exception"),
                "busy": e.get("showAs") in ("busy", "oof"),
                "status": "confirmed",
            }
            for e in rows
            if not e.get("isCancelled")
        ]

    async def list(self, user, start=None, end=None):
        tz = ZoneInfo(user["profile"].get("timezone", "UTC"))
        start = start or utcnow().astimezone(tz).date()
        end = end or start + timedelta(days=7)
        if not 1 <= (end - start).days <= 62:
            raise ValueError("Choose a calendar range between 1 and 62 days")
        a, b = datetime.combine(start, time.min, tz), datetime.combine(end, time.min, tz)
        result = {
            "start": str(start),
            "end": str(end),
            "timezone": str(tz),
            "events": [],
            "tasks": [],
            "calendars": [],
            "warnings": [],
            "status": "disconnected",
            "tasks_status": "disconnected",
            "fetched_at": utcnow().isoformat(),
        }
        uid = user["id"]
        if uid == "demo":
            result["status"] = "demo"
            for i in range((end - start).days):
                day = a + timedelta(days=i)
                for j, (s, e, title) in enumerate(DEMO_WEEKLY_SCHEDULE[day.weekday()]):
                    result["events"].append(
                        {
                            "id": f"demo:{i}:{j}",
                            "title": title,
                            "start": (day + s).isoformat(),
                            "end": (day + e).isoformat(),
                            "all_day": False,
                            "calendar_name": "Example calendar",
                            "calendar_id": "demo",
                            "color": "#8bc5a6",
                            "provider": "demo",
                            "busy": True,
                        }
                    )
            return result
        providers = self.calendar.connected_providers(uid)
        result["status"] = "connected" if providers else "disconnected"
        if "google-calendar" in providers:
            try:
                calendars = await self.google_calendars(uid)
                result["calendars"].extend(calendars)
                # Bound concurrency, but consume every provider page for every readable calendar.
                sem = asyncio.Semaphore(4)

                async def fetch(cal):
                    async with sem:
                        return await self.google_events(uid, cal, a, b, tz)

                groups = await asyncio.gather(*(fetch(c) for c in calendars), return_exceptions=True)
                for cal, rows in zip(calendars, groups):
                    if isinstance(rows, Exception):
                        result["warnings"].append(
                            f"Could not load {cal['name']}. Reconnect or refresh to see its events."
                        )
                        result["status"] = "partial"
                    else:
                        result["events"].extend(rows)
            except (httpx.HTTPError, ValueError):
                result["status"] = "partial"
                result["warnings"].append(
                    "Google Calendar could not refresh. Reconnect Google and try again."
                )
            try:
                result["tasks"] = await self.google_tasks(uid)
                result["tasks_status"] = "connected"
            except (httpx.HTTPError, ValueError):
                result["tasks_status"] = "unavailable"
                result["warnings"].append(
                    "Google Tasks could not be loaded. Check Tasks access in Connections, then try again."
                )
        if "microsoft-calendar" in providers:
            try:
                result["events"].extend(await self.microsoft_events(uid, a, b, tz))
                result["calendars"].append(
                    {
                        "id": "outlook-primary",
                        "name": "Outlook",
                        "color": "#86bafa",
                        "writable": False,
                        "primary": False,
                        "provider": "microsoft-calendar",
                    }
                )
            except (httpx.HTTPError, ValueError):
                result["status"] = "partial"
                result["warnings"].append("Outlook could not refresh. Reconnect Outlook and try again.")
        result["events"].sort(key=lambda e: (instant(e["start"], tz), e["title"]))
        result["tasks"].sort(key=lambda t: (t["due"] or "9999", t["title"]))
        return result

    async def draft(self, user, data):
        if user["id"] == "demo":
            raise ValueError("Sign in and connect Google Calendar to add an event")
        data = EventDraft.model_validate(data).model_dump()
        data["title"] = data["title"].strip()
        if not data["title"]:
            raise ValueError("Give your event a title")
        tz = ZoneInfo(user["profile"].get("timezone", "UTC"))
        if data["all_day"]:
            start, end = date.fromisoformat(data["start"]), date.fromisoformat(data["end"])
            a, b = datetime.combine(start, time.min, tz), datetime.combine(end, time.min, tz)
            if end <= start:
                raise ValueError("An all-day event's end date is exclusive and must follow its start")
        else:
            a, b = instant(data["start"], tz), instant(data["end"], tz)
            data["start"], data["end"] = a.isoformat(), b.isoformat()
        if b <= a or b - a > timedelta(days=31):
            raise ValueError("Choose an end after the start, within 31 days")
        if b <= utcnow():
            raise ValueError("This event is in the past. Choose an upcoming time")
        calendars = await self.google_calendars(user["id"])
        selected = next(
            (
                c
                for c in calendars
                if c["id"] == data["calendar_id"] or (data["calendar_id"] == "primary" and c["primary"])
            ),
            None,
        )
        if not selected or not selected["writable"]:
            raise ValueError("Choose a Google calendar you can add events to")
        data.update(
            calendar_id=selected["id"],
            calendar_name=selected["name"],
            timezone=str(tz),
            id=secrets.token_hex(16),
            expires=utcnow().timestamp() + 3600,
        )
        self.store.put(user["id"], "calendar_draft", data, data["id"])
        return data

    async def confirm(self, user, draft_id):
        uid = user["id"]
        data = self.store.get(uid, "calendar_draft", draft_id)
        if not data:
            raise ValueError("This draft is not available. Ask your twin to prepare it again.")
        if data.get("created"):
            return data["created"]
        if data["expires"] < utcnow().timestamp():
            raise ValueError("This draft expired. Review a new draft before adding it.")
        token = self.oauth.token(uid, "google-calendar")
        event_id = hashlib.sha256(f"{uid}:draft:{draft_id}".encode()).hexdigest()[:40]
        url = f"{GOOGLE}/calendars/{quote(data['calendar_id'], safe='')}/events"
        headers = {"Authorization": f"Bearer {token}"}
        # Provider ID also prevents duplicates after a timeout or concurrent confirmation.
        existing = await self.http.get(f"{url}/{event_id}", headers=headers)
        if existing.status_code == 200:
            created = existing.json()
        else:
            if existing.status_code != 404:
                existing.raise_for_status()
            tz = ZoneInfo(data["timezone"])
            a, b = instant(data["start"], tz), instant(data["end"], tz)
            if b <= utcnow():
                raise ValueError("This event is in the past. Prepare a new draft.")
            availability = await self.http.post(
                f"{GOOGLE}/freeBusy",
                headers=headers,
                json={
                    "timeMin": a.isoformat(),
                    "timeMax": b.isoformat(),
                    "timeZone": str(tz),
                    "items": [{"id": data["calendar_id"]}],
                },
            )
            availability.raise_for_status()
            calendars = availability.json().get("calendars", {})
            target = calendars.get(data["calendar_id"])
            if target is None or target.get("errors"):
                raise ValueError("Calendar availability could not be checked. Please try again.")
            if target.get("busy"):
                raise ValueError("This time overlaps an event on the selected calendar. Choose another time.")
            key = "date" if data["all_day"] else "dateTime"
            body = {
                "id": event_id,
                "summary": data["title"],
                "location": data["location"],
                "description": data["notes"],
                "start": {key: data["start"]},
                "end": {key: data["end"]},
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": data["reminder_minutes"]}],
                },
            }
            if not data["all_day"]:
                body["start"]["timeZone"] = body["end"]["timeZone"] = str(tz)
            response = await self.http.post(url, headers=headers, params={"sendUpdates": "none"}, json=body)
            if response.status_code == 409:
                response = await self.http.get(f"{url}/{event_id}", headers=headers)
            response.raise_for_status()
            created = response.json()
        result = {"id": created["id"], "url": safe_link(created.get("htmlLink")), "status": "created"}
        self.store.put(uid, "calendar_draft", {**data, "created": result}, draft_id)
        self.store.remove_doc(uid, "calendar")
        return result


def calendar_question(question):
    return bool(
        re.search(
            r"\b(calendar|agenda|meetings?|appointments?|events?|tasks?|schedule|book)\b", question, re.I
        )
    )
