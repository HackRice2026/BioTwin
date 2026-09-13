"""Text embeddings via the same Gemini OpenAI-compatible endpoint narration/service.py
already calls, reusing narration_api_key/allow_external_narration -- no new secret."""

import httpx

EMBED_MODEL = "text-embedding-004"


async def embed_text(text, config, http):
    if not config or not config.allow_external_narration or not config.narration_api_key:
        return None
    base = config.narration_url.rsplit("/chat/completions", 1)[0]
    try:
        response = await http.post(
            f"{base}/embeddings",
            timeout=httpx.Timeout(15, connect=5),
            headers={"Authorization": f"Bearer {config.narration_api_key}"},
            json={"model": EMBED_MODEL, "input": text},
        )
        response.raise_for_status()
        embedding = response.json()["data"][0]["embedding"]
        return embedding if isinstance(embedding, list) else None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None
