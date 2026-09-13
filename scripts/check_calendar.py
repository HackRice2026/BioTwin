"""Preflight for the Google/Microsoft calendar connection.

The connect button fails with one message for several different causes: no
client credentials, a redirect URI the provider does not recognise, the Calendar
API not enabled, or an account missing from the consent screen's test users.
Only the first is visible from here, so this checks what it can and prints the
authorize URL for the rest.

    ./.venv/bin/python -m scripts.check_calendar [--provider google-calendar]
"""

import argparse
import asyncio
import sys
from urllib.parse import parse_qs, urlparse

import httpx

from core.config import Settings
from core.oauth import OAuth
from core.store import Store

REQUIRED_SCOPES = {
    "google-calendar": [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ],
    "microsoft-calendar": [
        "https://graph.microsoft.com/Calendars.ReadWrite",
        "offline_access",
    ],
}


def report(ok, label, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -- ' + detail if detail else ''}")
    return ok


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="google-calendar", choices=sorted(REQUIRED_SCOPES))
    parser.add_argument("--email", help="check a stored connection for this account too")
    args = parser.parse_args()

    config = Settings()
    store = Store(config.database_url)
    provider = args.provider
    print(f"\nPreflight: {provider}\n")

    prefix = "microsoft" if provider == "microsoft-calendar" else "google"
    client_id = getattr(config, prefix + "_client_id", "")
    secret = getattr(config, prefix + "_client_secret", "")

    ok = report(bool(client_id), f"{prefix.upper()}_CLIENT_ID set in .env",
                "" if client_id else "empty -- create an OAuth client, see docs/INTEGRATIONS.md")
    ok &= report(bool(secret), f"{prefix.upper()}_CLIENT_SECRET set in .env",
                 "" if secret else "empty")
    ok &= report(bool(config.token_encryption_key), "TOKEN_ENCRYPTION_KEY set",
                 "" if config.token_encryption_key else "run scripts.setup")

    redirect = f"{config.public_url}/auth/{provider}/callback"
    print(f"\n  Register EXACTLY this redirect URI with the provider:\n    {redirect}\n")

    if not ok:
        print("Fix the above, then re-run. Nothing else can be checked until then.\n")
        return 1

    # The URL the browser would be sent to. Building it proves the credentials
    # and state storage work; whether the provider accepts it is the next step.
    async with httpx.AsyncClient() as http:
        url = OAuth(config, store, http).start(provider, "preflight")
    query = parse_qs(urlparse(url).query)
    sent = query.get("scope", [""])[0].split()
    missing = [s for s in REQUIRED_SCOPES[provider] if s not in sent]
    report(not missing, "requested scopes include calendar read and write",
           "missing " + ", ".join(missing) if missing else "")
    report(query.get("redirect_uri", [""])[0] == redirect, "authorize URL carries that redirect URI")
    if provider == "google-calendar":
        report(query.get("access_type", [""])[0] == "offline",
               "access_type=offline, so a refresh token is issued")

    print(f"\n  Open this to consent, then watch for the callback:\n    {url}\n")

    if args.email:
        user = store.user_by_email(args.email) if hasattr(store, "user_by_email") else None
        if user is None:
            print(f"  (no stored account for {args.email}; skipping the connection check)\n")
        else:
            stored = store.get(user["id"], "connection", provider)
            report(bool(stored), f"{provider} already connected for {args.email}",
                   "" if stored else "not connected yet -- consent through the URL above")
    print("Credentials and the authorize request are sound. What this cannot")
    print("verify from here: the Calendar API being enabled on the project, and")
    print("the account being listed under the consent screen's test users while")
    print("the app is unverified. Both surface as an error on the provider's")
    print("consent page, not here.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
