"""Gemini Live: the model talks to the user directly, over a WebSocket.

Different shape from narration/service.py, and the difference matters.

    service.py      question -> Gemini -> text -> guard() -> ElevenLabs -> ear
    this module     ear <-> Gemini Live <-> mouth, in one audio stream

Because the audio never passes back through the server, guard() cannot inspect what
is spoken. Nothing here can restore that check, so the grounding is moved earlier
instead: every number the model is allowed to say is written into the system
instruction, and that instruction is locked into the ephemeral token through
bidiGenerateContentSetup -- so a browser holding the token cannot swap it for a
friendlier one, change the model, or lift the restrictions.

The API key never reaches the browser. The server mints a short-lived, single-use
token; the browser connects to Google with that.
"""

import json
from datetime import timedelta

from shared.schemas import utcnow

TOKENS_URL = "https://generativelanguage.googleapis.com/v1beta/auth_tokens"
LIVE_WS = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

RULES = """You are BioTwin, speaking with the person whose body this data describes.

Everything you know is in CONTEXT below. It was computed before this conversation
started, from that person's own wearable measurements.

Speak like a sharp, warm coach: short sentences, no data dumps, no lists read aloud.
Answer the question that was actually asked, then stop.

Hard rules, because you are speaking aloud and nothing filters you:
- Every number you say must appear in CONTEXT, exactly as written there. Never
  round it, convert it, add to it, or compute a new one.
- If CONTEXT does not answer something, say you do not have it. Never estimate.
- A missing measurement is unknown, never zero and never fine.
- Describe readiness and forecasts as estimates, never as diagnoses or advice.
- You explain the plan that was already decided. You never invent a different
  time, duration or intensity than the one in CONTEXT.
- You are not a doctor. If asked about symptoms or illness, say that plainly and
  suggest a clinician.
"""


def system_instruction(ctx, briefing=None):
    """The whole of what the voice may say, assembled before a word is spoken.

    Facts arrive as already-formatted sentences carrying their own units, so they
    are passed through verbatim -- reformatting them here is how a number starts
    drifting from the measurement behind it.
    """
    blocks = [RULES]
    text = briefing if briefing is not None else getattr(ctx, "briefing", None)
    if text:
        blocks.append("CONTEXT — how this app works and where you stand today:\n" + text)
    facts = list(getattr(ctx, "facts", None) or [])
    if facts:
        blocks.append(
            "CONTEXT — measurements and model output, the only numbers you may speak:\n"
            + "\n".join(f"- {fact}" for fact in facts)
        )
    brief = getattr(ctx, "coach_brief", None)
    if brief:
        blocks.append(
            "CONTEXT — today's decision, already made. Lead with this when asked "
            "about timing, training or the plan:\n" + json.dumps(brief, default=str)
        )
    return "\n\n".join(blocks)


def live_config(config, instruction):
    """The setup Gemini is held to. Locked into the token, not sent by the browser."""
    return {
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.gemini_live_voice}}
            },
            "temperature": 0.3,
        },
        "systemInstruction": {"parts": [{"text": instruction}]},
    }


async def mint_session(config, http, instruction):
    """One single-use token for one conversation, constrained to one configuration.

    uses=1 so an intercepted token cannot open a second conversation.
    newSessionExpireTime bounds how long the browser may wait before connecting;
    expireTime bounds the conversation itself.
    """
    if not config.gemini_api_key:
        raise ValueError("Set GEMINI_API_KEY in the server .env to use the live voice")
    if not config.use_gemini_live:
        raise ValueError("Live voice is off. Set USE_GEMINI_LIVE=true to enable it")

    now = utcnow()
    body = {
        "uses": 1,
        "expireTime": _stamp(now + timedelta(minutes=config.gemini_live_token_minutes)),
        "newSessionExpireTime": _stamp(now + timedelta(minutes=2)),
        # bidiGenerateContentSetup, not the SDK's liveConnectConstraints: over REST
        # the constraint IS a setup message, model and all, and the wrapper name the
        # Python SDK uses is rejected with "Cannot find field".
        "bidiGenerateContentSetup": {
            "model": f"models/{config.gemini_live_model}",
            **live_config(config, instruction),
        },
    }
    response = await http.post(
        TOKENS_URL,
        headers={"x-goog-api-key": config.gemini_api_key, "content-type": "application/json"},
        json=body,
    )
    if response.status_code >= 400:
        # Surface Google's own reason (bad key, model not enabled) without ever
        # echoing the key itself.
        detail = _reason(response)
        raise ValueError(f"Gemini refused to start a live session: {detail}")
    token = response.json().get("name")
    if not token:
        raise ValueError("Gemini returned no session token")
    return {
        "token": token,
        "url": LIVE_WS,
        "model": config.gemini_live_model,
        "voice": config.gemini_live_voice,
        "expires_at": body["expireTime"],
        # 16 kHz in, 24 kHz out is what the Live API speaks; the browser needs both
        # to configure its capture and playback, so they are stated rather than
        # hardcoded twice.
        "input_sample_rate": 16000,
        "output_sample_rate": 24000,
        "input_mime_type": "audio/pcm;rate=16000",
    }


def _stamp(moment):
    return moment.isoformat().replace("+00:00", "Z")


def _reason(response):
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    error = payload.get("error") or {}
    return error.get("message") or f"HTTP {response.status_code}"
