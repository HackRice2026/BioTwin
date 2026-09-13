import base64
import json

import httpx
import pytest

from core.config import Settings
from narration.transcription import transcribe


@pytest.mark.asyncio
async def test_recording_transcribes_only_audio_into_question():
    data = b"generated-test-audio"

    def mock(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        inline = body["contents"][0]["parts"][0]["inlineData"]
        assert base64.b64decode(inline["data"]) == data
        assert inline["mimeType"] == "audio/webm"
        assert "context" not in body
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps({"question": "What is my heart rate?"})}]},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        question = await transcribe(
            data,
            "audio/webm",
            Settings(_env_file=None, narration_api_key="test-key", allow_external_narration=True),
            client,
        )
    assert question == "What is my heart rate?"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "empty", "invalid_json", "too_large", "mime", "disabled"])
async def test_transcription_failures_are_actionable(failure):
    def mock(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("provider detail", request=request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "not json" if failure == "invalid_json" else '{"question":""}'}
                            ]
                        },
                    }
                ]
            },
        )

    data = b"x" * (5 * 1024 * 1024 + 1) if failure == "too_large" else b"audio"
    settings = Settings(
        _env_file=None, narration_api_key="test-key", allow_external_narration=failure != "disabled"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        with pytest.raises(ValueError, match="(Type|type|recording|recording format)"):
            await transcribe(data, "text/html" if failure == "mime" else "audio/webm", settings, client)
