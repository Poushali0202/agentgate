"""Mock agent key directory, standing in for Visa's TAP key directory.

Keys come from three places:
  - gateway/data/directory.json (persisted registrations, e.g. the shopper and guardian agents)
  - POST /directory/keys at runtime (persisted)
  - Directory.register() in-process (simulator keys; not persisted)
"""

import base64
import json
import os
import threading
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from gateway.signer import public_jwk


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Directory:
    def __init__(self, path: str | None = None):
        self.path = path
        self._keys: dict[str, Ed25519PublicKey] = {}
        self._first_seen: dict[str, float] = {}
        self._persisted: dict[str, dict] = {}
        self._lock = threading.Lock()
        if path and os.path.exists(path):
            with open(path) as f:
                for jwk in json.load(f).get("keys", []):
                    self.register_jwk(jwk, persist=False)
                    self._persisted[jwk["kid"]] = jwk

    def register(self, keyid: str, public_key: Ed25519PublicKey) -> None:
        with self._lock:
            self._keys[keyid] = public_key
            self._first_seen.setdefault(keyid, time.time())

    def register_jwk(self, jwk: dict, persist: bool = True) -> None:
        """Raises ValueError for a malformed JWK, KeyError if the kid is already bound to a different key."""
        if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519" or not jwk.get("kid") or not jwk.get("x"):
            raise ValueError("expected an Ed25519 OKP JWK with kid and x")
        try:
            new_key = Ed25519PublicKey.from_public_bytes(_b64url_decode(jwk["x"]))
        except Exception:
            raise ValueError("x is not a valid Ed25519 public key")
        existing = self._keys.get(jwk["kid"])
        if existing is not None and public_jwk(existing, jwk["kid"])["x"] != public_jwk(new_key, jwk["kid"])["x"]:
            raise KeyError(f"kid {jwk['kid']} is already registered to a different key")
        self.register(jwk["kid"], new_key)
        if persist and self.path:
            with self._lock:
                self._persisted[jwk["kid"]] = public_jwk(self._keys[jwk["kid"]], jwk["kid"])
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                with open(self.path, "w") as f:
                    json.dump({"keys": list(self._persisted.values())}, f, indent=2)

    def get(self, keyid: str) -> Ed25519PublicKey | None:
        return self._keys.get(keyid)

    def first_seen(self, keyid: str) -> float | None:
        """When this key was first registered (unix seconds). Used by the young_key rule."""
        return self._first_seen.get(keyid)

    def jwks(self) -> dict:
        with self._lock:
            return {"keys": [public_jwk(k, kid) for kid, k in self._keys.items()]}
