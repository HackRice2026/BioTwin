import json
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from core.agenda import AgendaService
from core.api import approve_pending_calendar_event, create_app, propose_coach_calendar_draft
from core.calendar import CalendarService
from core.config import Settings
from core.store import Store
from narration.calendar import calendar_context, prepare_event
from narration.service import guard
from modeling.explanations import narration_context
from shared.schemas import DailyPlan, NarrationContext, Proposal, TwinState, utcnow


CAL = {
    "id": "me@example.test",
    "summary": "Personal",
    "primary": True,
    "accessRole": "owner",
    "backgroundColor": "#80bb9b",
}
EVENT = {
    "id": "meeting",
    "summary": "Design review",
    "start": {"dateTime": "2026-10-05T09:00:00-05:00"},
    "end": {"dateTime": "2026-10-05T10:00:00-05:00"},
    "location": "Studio",
    "recurringEventId": "weekly",
}
USER = {"id": "u", "profile": {"timezone": "America/Chicago"}}


class OAuth:
    def token(self, uid, provider):
        return "calendar-test-token"


@pytest.fixture
def store(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/agenda.db")
    store.create_user("u", "u@example.test", "test-hash", "Test", USER["profile"])
    store.put("u", "connection", {"status": "connected"}, "google-calendar")
    yield store
    store.engine.dispose()


async def test_all_calendars_event_pages_tasks_and_exclusive_all_day_dates(store):
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.path.endswith("calendarList"):
            return httpx.Response(
                200,
                json={"items": [{"id": "other", "summary": "Work", "accessRole": "reader"}]}
                if req.url.params.get("pageToken")
                else {"items": [CAL], "nextPageToken": "cal-2"},
            )
        if req.url.path.endswith("/events"):
            assert req.url.params["singleEvents"] == "true"
            assert req.url.params["timeMin"] == "2026-10-05T00:00:00-05:00"
            if "/other/" in req.url.path:
                return httpx.Response(200, json={"items": [{**EVENT, "summary": "Work review"}]})
            if req.url.params.get("pageToken"):
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": "trip",
                                "summary": "Trip",
                                "start": {"date": "2026-10-06"},
                                "end": {"date": "2026-10-08"},
                            },
                            {"id": "gone", "status": "cancelled"},
                        ]
                    },
                )
            return httpx.Response(200, json={"items": [EVENT], "nextPageToken": "events-2"})
        if req.url.path.endswith("/@me/lists"):
            return httpx.Response(200, json={"items": [{"id": "list", "title": "To do"}]})
        if req.url.path.endswith("/tasks"):
            if req.url.params.get("pageToken"):
                return httpx.Response(
                    200, json={"items": [{"id": "undated", "title": "Read notes", "status": "needsAction"}]}
                )
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "done",
                            "title": "Send slides",
                            "due": "2026-10-05T00:00:00.000Z",
                            "status": "completed",
                        }
                    ],
                    "nextPageToken": "tasks-2",
                },
            )
        raise AssertionError(str(req.url))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await AgendaService(CalendarService(OAuth(), http, store)).list(
            USER, date(2026, 10, 5), date(2026, 10, 12)
        )
    assert result["status"] == "connected" and result["warnings"] == []
    assert len(result["events"]) == 3 and len(result["tasks"]) == 2
    assert len({e["id"] for e in result["events"]}) == 3
    assert result["events"][0]["recurring"]
    assert result["events"][-1]["all_day"] and result["events"][-1]["end"] == "2026-10-08"
    facts = calendar_context(result)["facts"]
    assert any("2026-10-06 through 2026-10-07, all day" in f for f in facts)
    assert any("9:00 AM" in f for f in facts)
    assert any("no due date" in f for f in facts)


async def test_tasks_denied_and_secondary_calendar_failure_are_explicit(store):
    def handler(req):
        if req.url.path.endswith("calendarList"):
            return httpx.Response(200, json={"items": [CAL, {**CAL, "id": "broken", "summary": "Work"}]})
        if "/broken/" in req.url.path or req.url.host == "tasks.googleapis.com":
            return httpx.Response(403)
        return httpx.Response(200, json={"items": [EVENT]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await AgendaService(CalendarService(OAuth(), http, store)).list(USER, date(2026, 10, 5))
    assert result["status"] == "partial" and result["tasks_status"] == "unavailable"
    assert len(result["events"]) == 1 and len(result["warnings"]) == 2


async def test_draft_confirmation_idempotency_and_conflicts(store):
    writes = []
    busy = False

    def handler(req):
        if req.url.path.endswith("calendarList"):
            return httpx.Response(200, json={"items": [CAL]})
        if req.url.path.endswith("freeBusy"):
            return httpx.Response(
                200,
                json={
                    "calendars": {
                        CAL["id"]: {
                            "busy": [{"start": EVENT["start"]["dateTime"], "end": EVENT["end"]["dateTime"]}]
                            if busy
                            else []
                        }
                    }
                },
            )
        if req.method == "GET":
            return httpx.Response(404)
        writes.append(json.loads(req.content))
        assert req.url.params["sendUpdates"] == "none"
        return httpx.Response(
            200, json={"id": writes[-1]["id"], "htmlLink": "https://calendar.google.com/event"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = AgendaService(CalendarService(OAuth(), http, store))
        draft = await service.draft(
            USER,
            {
                "title": "Study session",
                "start": "2026-10-05T15:00",
                "end": "2026-10-05T15:30",
                "reminder_minutes": 15,
            },
        )
        assert writes == [] and draft["start"].endswith("-05:00")
        result = await service.confirm(USER, draft["id"])
        assert await service.confirm(USER, draft["id"]) == result
        assert len(writes) == 1 and writes[0]["summary"] == "Study session"
        assert writes[0]["reminders"]["overrides"][0]["minutes"] == 15
        with pytest.raises(ValueError, match="not available"):
            await service.confirm({**USER, "id": "other"}, draft["id"])
        busy = True
        second = await service.draft(
            USER, {"title": "Another event", "start": "2026-10-05T16:00", "end": "2026-10-05T16:30"}
        )
        with pytest.raises(ValueError, match="overlaps"):
            await service.confirm(USER, second["id"])
        assert len(writes) == 1
        with pytest.raises(ValueError, match="after the start"):
            await service.draft(
                USER, {"title": "Invalid", "start": "2026-10-05T16:00", "end": "2026-10-05T15:30"}
            )
        with pytest.raises(ValueError, match="does not exist"):
            await service.draft(
                USER, {"title": "DST gap", "start": "2027-03-14T02:30", "end": "2027-03-14T03:30"}
            )


async def test_ai_adds_event_after_extracting_a_valid_draft(store):
    config = Settings(_env_file=None, allow_external_narration=True, narration_api_key="test")
    calls = []
    writes = []

    def handler(req):
        calls.append(req)
        if req.url.path.endswith("calendarList"):
            return httpx.Response(200, json={"items": [CAL]})
        if req.url.path.endswith("freeBusy"):
            return httpx.Response(200, json={"calendars": {CAL["id"]: {"busy": []}}})
        if req.method == "GET" and "/events/" in req.url.path:
            return httpx.Response(404)
        if req.method == "POST" and req.url.path.endswith("/events"):
            writes.append(json.loads(req.content))
            return httpx.Response(
                200,
                json={"id": writes[-1]["id"], "htmlLink": "https://calendar.google.com/event"},
            )
        result = {
            "intent": "create",
            "draft": {
                "title": "Study session",
                "start": "2026-10-05T15:00:00-05:00",
                "end": "2026-10-05T15:30:00-05:00",
            },
        }
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = AgendaService(CalendarService(OAuth(), http, store))
        agenda = {
            "calendars": [
                {
                    "id": CAL["id"],
                    "primary": True,
                    "name": "Personal",
                    "provider": "google-calendar",
                    "writable": True,
                }
            ],
            "timezone": "America/Chicago",
        }
        answer, draft, event = await prepare_event(
            "Add a study session October 5 at 3 pm for 30 minutes", agenda, USER, service, config, http
        )
    assert "Added Study session to your Google Calendar" in answer.answer
    assert draft is None
    assert event == {"id": writes[0]["id"], "url": "https://calendar.google.com/event", "status": "created"}
    assert len(writes) == 1 and writes[0]["summary"] == "Study session"


async def test_coach_recommendation_drafts_then_voice_approval_confirms(store):
    writes = []

    def handler(req):
        if req.url.path.endswith("calendarList"):
            return httpx.Response(200, json={"items": [CAL]})
        if req.url.path.endswith("freeBusy"):
            return httpx.Response(200, json={"calendars": {CAL["id"]: {"busy": []}}})
        if req.method == "GET" and "/events/" in req.url.path:
            return httpx.Response(404)
        if req.method == "POST" and req.url.path.endswith("/events"):
            writes.append(json.loads(req.content))
            return httpx.Response(
                200,
                json={"id": writes[-1]["id"], "htmlLink": "https://calendar.google.com/event"},
            )
        raise AssertionError(str(req.url))

    start = utcnow() + timedelta(days=1)
    proposal = Proposal(
        id="coach-draft",
        kind="workout",
        title="Light movement",
        start=start,
        end=start + timedelta(minutes=30),
        intensity="light",
        reason="Readiness supports an easy session in a free window.",
        score=0.8,
        terms={"free_slot": 1.0},
    )
    plan = DailyPlan(
        date=str(start.date()),
        timezone="America/Chicago",
        calendar_status="connected",
        proposals=[proposal],
        busy=[],
        explanation="Test plan",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        runtime = SimpleNamespace(store=store, calendar=CalendarService(OAuth(), http, store))
        answer, draft = await propose_coach_calendar_draft(runtime, USER["id"], USER, "What workout should I do?", plan)
        assert "Want me to add it" in answer.answer
        assert draft["title"] == "BioTwin · Light movement"
        assert store.get(USER["id"], "pending_calendar_draft")["id"] == draft["id"]
        approved = await approve_pending_calendar_event(runtime, USER["id"], USER)

    assert approved[1]["status"] == "created"
    assert writes[0]["summary"] == "BioTwin · Light movement"
    assert store.get(USER["id"], "pending_calendar_draft") is None


async def test_coach_calendar_draft_uses_the_model_reasoning_when_it_can_be_grounded(store):
    """Same drafting flow, but with ctx/config/http supplied (as ask() now does): the
    spoken answer should be the model's own grounded reasoning, not just the
    proposal's fields read back verbatim -- that verbatim recitation is what should
    only ever happen as a fallback, when the model's answer can't be verified."""
    writes = []

    def calendar_handler(req):
        if req.url.path.endswith("calendarList"):
            return httpx.Response(200, json={"items": [CAL]})
        if req.url.path.endswith("freeBusy"):
            return httpx.Response(200, json={"calendars": {CAL["id"]: {"busy": []}}})
        if req.method == "GET" and "/events/" in req.url.path:
            return httpx.Response(404)
        if req.method == "POST" and req.url.path.endswith("/events"):
            writes.append(json.loads(req.content))
            return httpx.Response(200, json={"id": writes[-1]["id"], "htmlLink": "https://calendar.google.com/event"})
        raise AssertionError(str(req.url))

    start = utcnow() + timedelta(days=1)
    proposal = Proposal(
        id="coach-draft",
        kind="workout",
        title="Light movement",
        start=start,
        end=start + timedelta(minutes=30),
        intensity="light",
        reason="Readiness supports an easy session in a free window.",
        score=0.8,
        terms={"free_slot": 1.0},
    )
    plan = DailyPlan(
        date=str(start.date()),
        timezone="America/Chicago",
        calendar_status="connected",
        proposals=[proposal],
        busy=[],
        explanation="Test plan",
    )
    from pathlib import Path

    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    ctx = narration_context(state, plan=plan)
    config = Settings(_env_file=None, allow_external_narration=True, narration_api_key="k")

    narration_calls = []

    def narration_handler(req):
        narration_calls.append(req)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "A light session fits nicely in your open window this morning -- your readiness supports it.",
                                    "evidence": ["plan.proposals.0.reason"],
                                }
                            )
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(calendar_handler)) as calendar_http:
        async with httpx.AsyncClient(transport=httpx.MockTransport(narration_handler)) as narration_http:
            runtime = SimpleNamespace(store=store, calendar=CalendarService(OAuth(), calendar_http, store))
            answer, draft = await propose_coach_calendar_draft(
                runtime, USER["id"], USER, "What workout should I do?", plan, ctx, config, narration_http
            )

    assert len(narration_calls) == 1
    assert "A light session fits nicely in your open window this morning" in answer.answer
    assert "Want me to add it" in answer.answer
    assert answer.mode == "language_service"
    assert draft["title"] == "BioTwin · Light movement"


def test_agenda_endpoint_account_isolation_and_calendar_context(tmp_path):
    config = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/api.db",
        demo_enabled=False,
        allow_external_narration=False,
    )

    def handler(req):
        if req.url.path.endswith("calendarList"):
            return httpx.Response(200, json={"items": [CAL]})
        if req.url.host == "tasks.googleapis.com":
            return httpx.Response(403)
        return httpx.Response(200, json={"items": [EVENT]})

    with TestClient(create_app(config)) as client:
        assert client.get("/api/calendar/agenda").status_code == 401
        uid = client.post(
            "/auth/session/register",
            json={"email": "agenda@example.test", "password": "calendar-test-password", "adult": True},
        ).json()["user"]["id"]
        rt = client.app.state.runtime
        client.portal.call(rt.http.aclose)
        rt.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        rt.calendar = CalendarService(OAuth(), rt.http, rt.store)
        rt.store.put(uid, "connection", {"status": "connected"}, "google-calendar")
        agenda = client.get("/api/calendar/agenda?start=2026-10-05&end=2026-10-12").json()
        assert agenda["events"][0]["title"] == "Design review"
        reply = client.post(
            "/api/twin/ask",
            json={
                "question": "What meetings are on my calendar?",
                "calendar_start": "2026-10-05",
                "calendar_end": "2026-10-12",
                "request_id": "calendar-question-0001",
            },
        ).json()
        assert "Design review" in reply["answer"] and "9:00 AM" in reply["answer"]
        row = rt.store.conversation(uid, "calendar-question-0001")
        ctx = NarrationContext.model_validate(row["context"])
        assert guard("Design review starts at 9:00 AM.", ctx, ["calendar.facts.0"])
        assert not guard("Design review starts at 17:45.", ctx, ["calendar.facts.0"])
        assert client.get("/api/calendar/agenda?start=2026-10-12&end=2026-10-05").status_code == 422
        client.post("/auth/session/logout")
        client.post(
            "/auth/session/register",
            json={"email": "other@example.test", "password": "calendar-test-password", "adult": True},
        )
        assert client.get("/api/calendar/agenda").json()["events"] == []


def test_calendar_drafts_expire_and_cannot_recreate_deleted_accounts(store):
    store.put("u", "calendar_draft", {"expires": 0}, "expired", require_user=True)
    store.put("u", "conversation_draft", {"expires": 0}, "expired", require_user=True)
    store.purge(7)
    assert store.get("u", "calendar_draft", "expired") is None
    assert store.get("u", "conversation_draft", "expired") is None
    with pytest.raises(ValueError, match="no longer available"):
        store.put("deleted-user", "calendar_draft", {"title": "private"}, "draft", require_user=True)
    assert store.get("deleted-user", "calendar_draft", "draft") is None
