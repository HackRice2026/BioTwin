"""Shared Vertex AI auth for narration and transcription -- both bill through
a project's normal Cloud Billing account instead of an AI Studio key's
separate prepay-credits balance.
"""

_vertex_credentials = None  # lazy-loaded, module-level so the token is reused/refreshed across requests instead of re-authenticating every call


def vertex_token():
    """Blocking (google-auth has no native async transport) -- always call
    via asyncio.to_thread. Loads Application Default Credentials once
    (from `gcloud auth application-default login`'s local file) and
    refreshes the cached access token only when it's actually expired.
    """
    global _vertex_credentials
    import google.auth
    from google.auth.transport.requests import Request as GoogleAuthRequest

    if _vertex_credentials is None:
        _vertex_credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    if not _vertex_credentials.valid:
        _vertex_credentials.refresh(GoogleAuthRequest())
    return _vertex_credentials.token
