from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/biotwin.db"
    public_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:5173"
    # Optional third allowed origin, additive to public_url/frontend_origin --
    # for reaching this server from another device on the same LAN (e.g. a
    # phone) without changing public_url itself, which stays the registered
    # Google/Microsoft OAuth redirect_uri host. Empty means "not enabled".
    lan_origin: str = ""
    demo_enabled: bool = True
    # Opt-in only -- the project's own default is an explicitly synthetic
    # demo workspace (see README). When true, the unauthenticated "demo"
    # fallback account is instead continuously live-synced from a local
    # garmin viz dashboard InfluxDB, never synthetic. A real tradeoff, not
    # a free convenience: it means anyone who can reach this server sees
    # that real data with zero login. Fine on 127.0.0.1; reconsider before
    # exposing an instance with this set beyond localhost.
    demo_uses_real_data: bool = False
    retention_days: int = 90
    cookie_secure: bool = False
    token_encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_project_number: str = ""
    google_webhook_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    garmin_client_id: str = ""
    garmin_client_secret: str = ""
    garmin_webhook_secret: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_model_id: str = "eleven_flash_v2_5"
    narration_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    narration_api_key: str = ""
    narration_model: str = "gemini-3.1-flash-lite"
    allow_external_narration: bool = False
    # Gemini Live: a direct AI Studio API key, no Vertex ADC and no OpenAI-compatible
    # shim. The model speaks to the user itself over a WebSocket, so the numeric
    # guard in narration/service.py cannot sit between it and the listener -- the
    # grounding is carried in a locked system instruction instead. Off unless a key
    # is present AND this is true, like every other external path here.
    gemini_api_key: str = ""
    use_gemini_live: bool = False
    gemini_live_model: str = "gemini-3.1-flash-live-preview"
    gemini_live_voice: str = "Aoede"
    # How long a browser may hold a minted session token before it must ask again.
    gemini_live_token_minutes: int = 10
    # Opt-in alternate narration path: Vertex AI instead of the AI Studio key
    # above. Genuinely different auth (OAuth2 Application Default Credentials,
    # refreshed access tokens -- from `gcloud auth application-default login`
    # on this machine) and a different billing bucket than an AI Studio key's
    # "prepay credits" -- useful when that prepay balance is the thing
    # blocked, since Vertex bills through the project's normal Cloud Billing
    # account instead. Requires vertex_project_id; still needs
    # allow_external_narration=true.
    use_vertex_narration: bool = False
    vertex_project_id: str = ""
    vertex_region: str = "us-central1"
    vertex_model: str = "gemini-2.5-flash"
    # A stronger, slower model that periodically curates the fast conversational
    # model's per-account context into a short briefing (Runtime._refresh_briefing).
    # Off the live request path -- it runs in the background on a throttle, not once
    # per turn -- so it can afford to be the bigger of the two models. Two names
    # because the AI Studio and Vertex catalogs don't match: AI Studio stopped
    # serving gemini-2.5-pro to new callers (redirects to gemini-3.1-pro-preview),
    # while that same "3.1" name 404s on Vertex, which still serves 2.5-pro directly.
    insight_model: str = "gemini-3.1-pro-preview"
    vertex_insight_model: str = "gemini-2.5-pro"
