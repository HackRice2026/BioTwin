#!/usr/bin/env python3
"""Generate Monkey C constants without executing .env contents or printing secrets."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def generate(env_file=ROOT / ".env", output=ROOT / "source" / "ApiConfig.mc"):
    values = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if not sep:
            raise ValueError("Expected KEY=value in watch .env")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key.strip()] = val
    url = values.get("API_URL", "")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/api/ingest/watch"
    ):
        raise ValueError(
            "API_URL must be an HTTPS URL ending in /api/ingest/watch, without credentials or query"
        )
    key = values.get("API_KEY", "")
    if not 40 <= len(key) <= 160 or any(c.isspace() for c in key) or "replace-with" in key:
        raise ValueError("Set API_KEY to the pairing token from BioTwin Connections")
    interval = int(values.get("SEND_INTERVAL_SECONDS", "5"))
    if not 5 <= interval <= 30:
        raise ValueError("SEND_INTERVAL_SECONDS must be between 5 and 30")
    content = (
        "// Generated from .env; contains a private ingestion token. Do not commit.\n"
        "class ApiConfig {\n"
        f"    static const API_URL = {json.dumps(url)};\n"
        f"    static const API_KEY = {json.dumps(key)};\n"
        f"    static const SEND_INTERVAL_SECONDS = {interval};\n"
        "}\n"
    )
    # Restrict permissions before writing credentials, including on an existing file.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(content)


if __name__ == "__main__":
    try:
        generate()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
    print("Generated private watch configuration.")
