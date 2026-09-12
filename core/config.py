from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/biotwin.db"
    public_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:5173"
    demo_enabled: bool = True
    retention_days: int = 90
    cookie_secure: bool = False
    token_encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_project_number: str = ""
    google_webhook_secret: str = ""
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
