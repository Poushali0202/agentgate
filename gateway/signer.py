"""Client-side signing for AgentGate requests (RFC 9421 style, Ed25519).

Used by the simulator, the shopper agent and the security tests. Only depends on
`cryptography`, so agents can copy this file if they don't import the gateway package.

    key = Ed25519PrivateKey.generate()
    headers = sign_request(key, "shopper-1", "POST", "http://localhost:8000/checkout",
                           body=json.dumps(order).encode(), tag=PAYER_TAG)
    httpx.post(url, content=body, headers={**headers, "Content-Type": "application/json"})
"""

import base64
import hashlib
import time
import uuid
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

BROWSER_TAG = "agent-browser-auth"
PAYER_TAG = "agent-payer-auth"
SIG_LABEL = "sig1"
DEFAULT_TTL_S = 60


def content_digest(body: bytes) -> str:
    return "sha-256=:" + base64.b64encode(hashlib.sha256(body).digest()).decode() + ":"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def public_jwk(public_key: Ed25519PublicKey, keyid: str) -> dict:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "kid": keyid, "alg": "ed25519", "x": b64url(raw)}


def signature_params(components: list[str], created: int, expires: int, keyid: str, nonce: str, tag: str) -> str:
    comps = " ".join(f'"{c}"' for c in components)
    return f'({comps});created={created};expires={expires};keyid="{keyid}";alg="ed25519";nonce="{nonce}";tag="{tag}"'


def signature_base(component_values: list[tuple[str, str]], params: str) -> bytes:
    lines = [f'"{name}": {value}' for name, value in component_values]
    lines.append(f'"@signature-params": {params}')
    return "\n".join(lines).encode()


def sign_request(
    private_key: Ed25519PrivateKey,
    keyid: str,
    method: str,
    url: str,
    body: bytes | None = None,
    tag: str = BROWSER_TAG,
    created: int | None = None,
    expires: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Return the headers to add to the request: Signature-Input, Signature and, with a body, Content-Digest."""
    parts = urlsplit(url)
    created = int(time.time()) if created is None else created
    expires = created + DEFAULT_TTL_S if expires is None else expires
    nonce = nonce or uuid.uuid4().hex

    values = [("@method", method.upper()), ("@authority", parts.netloc.lower()), ("@path", parts.path or "/")]
    headers = {}
    if body is not None:
        headers["Content-Digest"] = content_digest(body)
        values.append(("content-digest", headers["Content-Digest"]))

    params = signature_params([name for name, _ in values], created, expires, keyid, nonce, tag)
    sig = private_key.sign(signature_base(values, params))
    headers["Signature-Input"] = f"{SIG_LABEL}={params}"
    headers["Signature"] = f"{SIG_LABEL}=:{base64.b64encode(sig).decode()}:"
    return headers
