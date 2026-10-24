"""Verify Visa TAP-style agent signatures: RFC 9421 HTTP Message Signatures with Ed25519.

verify(...) returns a VerifyResult whose `identity` is:
  verified   - signature valid for a known key, tag allowed on this route, fresh, not replayed
  unverified - no signature headers at all
  invalid    - signature present but wrong in some way (`reason` says which)
"""

import base64
import re
import threading
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature

from gateway.directory import Directory
from gateway.signer import BROWSER_TAG, PAYER_TAG, content_digest, signature_base

MAX_WINDOW_S = 8 * 60  # TAP: expires - created must not exceed 8 minutes
CLOCK_SKEW_S = 30

ROUTE_TAGS = {
    "/browse": {BROWSER_TAG, PAYER_TAG},
    "/checkout": {PAYER_TAG},
}

_INPUT_RE = re.compile(r'^\s*([A-Za-z0-9_-]+)=\(([^)]*)\)(.*)$')
_PARAM_RE = re.compile(r';\s*([a-z]+)=(?:"([^"]*)"|(-?\d+))')
_SIG_RE = re.compile(r'^\s*([A-Za-z0-9_-]+)=:([A-Za-z0-9+/=]+):\s*$')


@dataclass
class VerifyResult:
    identity: str
    reason: str | None = None
    keyid: str | None = None
    tag: str | None = None


class NonceStore:
    """Remembers (keyid, nonce) until the signature expires; sweeps expired entries as it goes."""

    def __init__(self):
        self._seen: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def check_and_add(self, keyid: str, nonce: str, expires: float) -> bool:
        """True if this nonce is new (and records it); False if it is a replay."""
        now = time.time()
        with self._lock:
            if len(self._seen) > 10_000:
                self._seen = {k: exp for k, exp in self._seen.items() if exp > now}
            exp = self._seen.get((keyid, nonce))
            if exp is not None and exp > now:
                return False
            self._seen[(keyid, nonce)] = max(expires, now) + CLOCK_SKEW_S
            return True


class Verifier:
    def __init__(self, directory: Directory, nonces: NonceStore | None = None):
        self.directory = directory
        self.nonces = nonces or NonceStore()

    def verify(self, method: str, authority: str, path: str, headers: dict[str, str], body: bytes, now: float | None = None) -> VerifyResult:
        h = {k.lower(): v for k, v in headers.items()}
        sig_input, sig_header = h.get("signature-input"), h.get("signature")
        if not sig_input and not sig_header:
            return VerifyResult("unverified", "unsigned")
        if not sig_input or not sig_header:
            return VerifyResult("invalid", "malformed_signature")

        m = _INPUT_RE.match(sig_input)
        s = _SIG_RE.match(sig_header)
        if not m or not s or m.group(1) != s.group(1):
            return VerifyResult("invalid", "malformed_signature")
        label, comp_str, param_str = m.groups()
        components = re.findall(r'"([^"]+)"', comp_str)
        params = {k: (int(iv) if iv else sv) for k, sv, iv in _PARAM_RE.findall(param_str)}
        keyid, tag, nonce = params.get("keyid"), params.get("tag"), params.get("nonce")
        created, expires = params.get("created"), params.get("expires")
        res = lambda reason: VerifyResult("invalid", reason, keyid, tag)  # noqa: E731

        if not all(isinstance(v, str) for v in (keyid, tag, nonce)) or not all(isinstance(v, int) for v in (created, expires)):
            return res("missing_params")
        if params.get("alg", "ed25519") != "ed25519":
            return res("unsupported_alg")

        required = {"@method", "@authority", "@path"} | ({"content-digest"} if body else set())
        if not required.issubset(components):
            return res("missing_components")

        if tag not in ROUTE_TAGS.get(path, {BROWSER_TAG, PAYER_TAG}):
            return res("wrong_tag")

        now = time.time() if now is None else now
        if expires < now:
            return res("expired")
        if created > now + CLOCK_SKEW_S:
            return res("created_in_future")
        if expires - created > MAX_WINDOW_S:
            return res("window_too_long")

        public_key = self.directory.get(keyid)
        if public_key is None:
            return res("unknown_key")

        if "content-digest" in components or body:
            if h.get("content-digest") != content_digest(body or b""):
                return res("digest_mismatch")

        values = []
        for c in components:
            if c == "@method":
                values.append((c, method.upper()))
            elif c == "@authority":
                values.append((c, authority.lower()))
            elif c == "@path":
                values.append((c, path))
            elif c in h:
                values.append((c, h[c].strip()))
            else:
                return res("missing_components")

        try:
            # @signature-params must be the exact text from Signature-Input.
            public_key.verify(base64.b64decode(s.group(2)), signature_base(values, f"({comp_str}){param_str}"))
        except (InvalidSignature, ValueError):
            return res("bad_signature")

        # Only burn the nonce once the signature is proven, so forged requests can't block real ones.
        if not self.nonces.check_and_add(keyid, nonce, expires):
            return res("replayed_nonce")

        return VerifyResult("verified", None, keyid, tag)
