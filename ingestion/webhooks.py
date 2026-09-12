"""Google's rotating Tink ECDSA signature, verified over the original request bytes."""

import base64
import struct
import time
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes


def proto_fields(data):
    i = 0

    def varint():
        nonlocal i
        n, shift = 0, 0
        while True:
            if i >= len(data) or shift > 63:
                raise ValueError("Invalid protobuf")
            b = data[i]
            i += 1
            n |= (b & 127) << shift
            if b < 128:
                return n
            shift += 7

    result = {}
    while i < len(data):
        tag = varint()
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            result[field] = varint()
        elif wire == 2:
            size = varint()
            if i + size > len(data):
                raise ValueError("Invalid protobuf length")
            result[field] = data[i : i + size]
            i += size
        else:
            raise ValueError("Unsupported public key encoding")
    return result


class GoogleSignatureVerifier:
    def __init__(self, http):
        self.http = http
        self.keys = None
        self.fetched = 0

    async def verify(self, raw, signature):
        signed = base64.b64decode(signature, validate=True)
        if len(signed) < 6 or signed[0] != 1:
            raise ValueError("Invalid signature prefix")
        kid = struct.unpack(">I", signed[1:5])[0]
        if (
            not self.keys
            or time.monotonic() - self.fetched > 3600
            or not any(k["keyId"] == kid for k in self.keys["key"])
        ):
            r = await self.http.get(
                "https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json"
            )
            r.raise_for_status()
            self.keys = r.json()
            self.fetched = time.monotonic()
        key = next((k for k in self.keys["key"] if k["keyId"] == kid and k["status"] == "ENABLED"), None)
        if not key:
            raise ValueError("Unknown signature key")
        params = proto_fields(base64.b64decode(key["keyData"]["value"]))
        public = ec.EllipticCurvePublicNumbers(
            int.from_bytes(params[3], "big"), int.from_bytes(params[4], "big"), ec.SECP256R1()
        ).public_key()
        public.verify(signed[5:], raw, ec.ECDSA(hashes.SHA256()))
