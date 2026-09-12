"""Create a private local environment file without displaying its encryption key."""

import os
from pathlib import Path
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; preserving it.")
else:
    text = (
        (root / ".env.example")
        .read_text()
        .replace("TOKEN_ENCRYPTION_KEY=\n", "TOKEN_ENCRYPTION_KEY=" + Fernet.generate_key().decode() + "\n")
    )
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    print("Created private .env with a local token-encryption key. Provider credentials remain unconfigured.")
