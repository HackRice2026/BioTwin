import httpx
import pytest

from core.config import Settings
from narration.insights import retrieve_insight, wants_methodology_insight


def test_wants_methodology_insight_matches_forecast_accuracy_questions():
    assert wants_methodology_insight("How accurate is your 1 hour forecast?")
    assert wants_methodology_insight("What's your recovery time constant, tau?")
    assert not wants_methodology_insight("What's my heart rate right now?")


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def list_insights(self):
        return self.rows


@pytest.mark.asyncio
async def test_retrieve_insight_returns_closest_match_above_threshold():
    rows = [
        {"topic": "forecast_accuracy_1h", "content": "1-hour finding.", "embedding": [1.0, 0.0]},
        {"topic": "forecast_accuracy_6h", "content": "6-hour finding.", "embedding": [0.0, 1.0]},
    ]

    def mock(request):
        return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})

    config = Settings(_env_file=None, allow_external_narration=True, narration_api_key="test-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        result = await retrieve_insight("How accurate is the 1 hour forecast?", FakeStore(rows), config, client)
    assert result == ["1-hour finding."]


@pytest.mark.asyncio
async def test_retrieve_insight_skips_unrelated_questions_without_a_network_call():
    def mock(request):
        raise AssertionError("should not embed a question that isn't methodology-flavored")

    config = Settings(_env_file=None, allow_external_narration=True, narration_api_key="test-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        result = await retrieve_insight("What's my heart rate right now?", FakeStore([]), config, client)
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_insight_empty_when_narration_not_configured():
    config = Settings(_env_file=None, allow_external_narration=False)
    async with httpx.AsyncClient() as client:
        result = await retrieve_insight("How accurate is your forecast?", FakeStore([]), config, client)
    assert result == []
