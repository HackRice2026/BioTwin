import base64
import hashlib
import hmac
import json
import secrets
from cryptography.fernet import Fernet


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()


def verify_password(password, encoded):
    raw = base64.b64decode(encoded)
    return hmac.compare_digest(raw[16:], hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1))


class TokenVault:
    def __init__(self, key):
        self.key = key

    def seal(self, value):
        if not self.key:
            raise ValueError("TOKEN_ENCRYPTION_KEY is required before connecting accounts")
        dek = Fernet.generate_key()
        return {
            "wrapped_key": Fernet(self.key).encrypt(dek).decode(),
            "ciphertext": Fernet(dek).encrypt(json.dumps(value).encode()).decode(),
        }

    def open(self, value):
        dek = Fernet(self.key).decrypt(value["wrapped_key"])
        return json.loads(Fernet(dek).decrypt(value["ciphertext"]))
