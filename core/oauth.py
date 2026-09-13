import asyncio
import base64
import hashlib
import secrets
from urllib.parse import urlencode
from shared.schemas import utcnow
from core.security import TokenVault

GOOGLE_SCOPES = " ".join(
    "https://www.googleapis.com/auth/googlehealth." + s + ".readonly"
    for s in ["activity_and_fitness", "sleep", "health_metrics_and_measurements"]
)
CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/tasks.readonly"
)
# offline_access is what earns a refresh token from Microsoft's identity
# platform -- there's no separate access_type=offline param like Google's.
MICROSOFT_CALENDAR_SCOPES = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"


class OAuth:
    def __init__(self, config, store, http):
        self.config, self.store, self.http = config, store, http
        self.vault = TokenVault(config.token_encryption_key)

    def credentials(self, provider):
        if provider not in ["fitbit", "garmin", "google-calendar", "microsoft-calendar"]:
            raise ValueError("Unknown provider")
        prefix = "garmin" if provider == "garmin" else "microsoft" if provider == "microsoft-calendar" else "google"
        return getattr(self.config, prefix + "_client_id"), getattr(self.config, prefix + "_client_secret")

    def start(self, provider, user_id, return_to=None):
        client_id, secret = self.credentials(provider)
        if not client_id or not secret or not self.config.token_encryption_key:
            raise ValueError(
                f"{provider} needs client credentials and TOKEN_ENCRYPTION_KEY in the server .env; see docs/INTEGRATIONS.md"
            )
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        # return_to records which of the allowed origins the flow began at, so
        # consent returns the browser to the app it left rather than to whichever
        # origin the server happens to call its frontend. The caller validates it
        # against the allowlist; anything else is dropped here.
        self.store.put(
            user_id,
            "oauth_state",
            {
                "provider": provider,
                "verifier": verifier,
                "expires": utcnow().timestamp() + 600,
                "return_to": return_to or "",
            },
            state,
        )
        params = {
            "client_id": client_id,
            "redirect_uri": f"{self.config.public_url}/auth/{provider}/callback",
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if provider == "garmin":
            url = "https://connect.garmin.com/oauth2Confirm"
        elif provider == "microsoft-calendar":
            url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
            params.update(scope=MICROSOFT_CALENDAR_SCOPES, response_mode="query")
        else:
            url = "https://accounts.google.com/o/oauth2/v2/auth"
            params.update(
                scope=CALENDAR_SCOPES if provider == "google-calendar" else GOOGLE_SCOPES,
                access_type="offline",
                prompt="consent",
            )
        return url + "?" + urlencode(params)

    async def callback(self, provider, user_id, state, code):
        data = self.store.take(user_id, "oauth_state", state)
        if not data or data["provider"] != provider or data["expires"] < utcnow().timestamp():
            raise ValueError("OAuth state is invalid or expired. Start the connection again.")
        cid, secret = self.credentials(provider)
        r = await self.http.post(
            self.token_url(provider),
            data={
                "grant_type": "authorization_code",
                "client_id": cid,
                "client_secret": secret,
                "code": code,
                "code_verifier": data["verifier"],
                "redirect_uri": f"{self.config.public_url}/auth/{provider}/callback",
            },
        )
        r.raise_for_status()
        token = r.json()
        if "access_token" not in token:
            raise ValueError("Provider did not issue an access token")
        # Calendar-only connections have nothing to reverse-map a vendor
        # webhook to (no inbound push from either vendor for these) --
        # unlike garmin/fitbit, which need vendor_id -> user_id for that.
        if provider not in ("google-calendar", "microsoft-calendar"):
            url = (
                "https://apis.garmin.com/wellness-api/rest/user/id"
                if provider == "garmin"
                else "https://health.googleapis.com/v4/users/me/identity"
            )
            identity = await self.http.get(url, headers={"Authorization": f"Bearer {token['access_token']}"})
            identity.raise_for_status()
            vendor_id = identity.json()["userId" if provider == "garmin" else "healthUserId"]
            self.store.put(
                user_id,
                "identity",
                {"vendor_id": vendor_id, "user_id": user_id, "provider": provider},
                provider,
            )
        self.save(user_id, provider, token)
        return data.get("return_to") or ""

    def token_url(self, provider):
        if provider == "garmin":
            return "https://connectapi.garmin.com/di-oauth2-service/oauth/token"
        if provider == "microsoft-calendar":
            return "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        return "https://oauth2.googleapis.com/token"

    def save(self, user_id, provider, token):
        token = {
            **token,
            "refresh_at": utcnow().timestamp() + float(token.get("expires_in", 3600)) * 0.8,
            "expires_at": utcnow().timestamp() + float(token.get("expires_in", 3600)),
            "user_id": user_id,
            "provider": provider,
        }
        self.store.put(user_id, "token", self.vault.seal(token), provider)
        self.store.put(
            user_id,
            "connection",
            {
                "user_id": user_id,
                "provider": provider,
                "status": "connected",
                "refresh_at": token["refresh_at"],
            },
            provider,
        )

    def token(self, user_id, provider):
        sealed = self.store.get(user_id, "token", provider)
        if not sealed:
            raise ValueError(f"Connect {provider} first")
        token = self.vault.open(sealed)
        if token["expires_at"] <= utcnow().timestamp():
            raise ValueError(f"{provider} access expired; reconnect if background refresh fails")
        return token["access_token"]

    async def refresh_due(self):
        connections = await asyncio.to_thread(self.store.docs, None, "connection")
        for provider, connection in connections:
            uid = connection["user_id"]
            if connection.get("refresh_at", 0) > utcnow().timestamp() or connection["status"] == "reconnect":
                continue
            try:
                sealed = await asyncio.to_thread(self.store.get, uid, "token", provider)
                token = self.vault.open(sealed)
                cid, secret = self.credentials(provider)
                r = await self.http.post(
                    self.token_url(provider),
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": token["refresh_token"],
                        "client_id": cid,
                        "client_secret": secret,
                    },
                )
                r.raise_for_status()
                await asyncio.to_thread(self.save, uid, provider, {**token, **r.json()})
            except Exception:
                await asyncio.to_thread(
                    self.store.put,
                    uid,
                    "connection",
                    {**connection, "status": "reconnect"},
                    provider,
                )
                # Failure is visible in connection status; secrets and provider response bodies never enter logs.

    async def disconnect(self, user_id, provider):
        token = self.token(user_id, provider)
        if provider == "garmin":
            r = await self.http.delete(
                "https://apis.garmin.com/wellness-api/rest/user/registration",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
        elif provider == "microsoft-calendar":
            # Microsoft's identity platform has no per-app token-revoke
            # endpoint the way Google does (/me/revokeSignInSessions kills
            # every session for every app, which is the wrong scope here).
            # Forgetting the stored token is the standard "disconnect this
            # app" move: it stops being refreshed and simply expires.
            pass
        else:
            r = await self.http.post("https://oauth2.googleapis.com/revoke", data={"token": token})
            r.raise_for_status()
        for kind in ["token", "connection", "identity"]:
            self.store.remove_doc(user_id, kind, provider)
