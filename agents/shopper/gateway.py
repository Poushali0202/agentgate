"""Signed client for the AgentGate gateway. Uses gateway/signer.py so the Shopper signs exactly what the gateway verifies."""

import asyncio
import json
import os
import time
from dataclasses import dataclass

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gateway.signer import BROWSER_TAG, PAYER_TAG, public_jwk, sign_request

KEY_DIR = "agents/data/keys"


def load_or_create_key(keyid: str) -> Ed25519PrivateKey:
    """One persistent key per keyid, so the Shopper keeps its identity (and its history with the gateway) across restarts."""
    path = os.path.join(KEY_DIR, f"{keyid}.pem")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(KEY_DIR, exist_ok=True)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(pem)
    return key


@dataclass
class Decision:
    status_code: int
    decision: str | None          # allow | challenge | block | None (bad request)
    challenge_id: str | None
    risk_score: int | None
    reasons: list[str]
    latency_ms: float | None
    detail: str | None
    raw: dict


class Gateway:
    def __init__(self, base_url: str, keyid: str):
        self.base = base_url.rstrip("/")
        self.keyid = keyid
        self.key = load_or_create_key(keyid)

    @property
    def jwk(self) -> dict:
        return public_jwk(self.key.public_key(), self.keyid)

    async def register(self, client: httpx.AsyncClient) -> str:
        """Put this agent's public key in the mock directory. 409 means the kid is bound to a different key."""
        r = await client.post(f"{self.base}/directory/keys", json=self.jwk, timeout=10)
        if r.status_code == 409:
            return "conflict"
        r.raise_for_status()
        return "registered"

    async def browse(self, client: httpx.AsyncClient, consumer_id: str, q: str = "") -> int:
        url = f"{self.base}/browse"
        headers = sign_request(self.key, self.keyid, "GET", url, tag=BROWSER_TAG)
        r = await client.get(url, params={"consumer_id": consumer_id, "q": q}, headers=headers, timeout=10)
        return r.status_code

    async def checkout(self, client: httpx.AsyncClient, order: dict, scenario: str | None = None) -> Decision:
        url = f"{self.base}/checkout"
        body = json.dumps(order).encode()
        headers = {"Content-Type": "application/json", **sign_request(self.key, self.keyid, "POST", url, body, tag=PAYER_TAG)}
        if scenario:
            headers["X-AgentGate-Scenario"] = scenario
        r = await client.post(url, content=body, headers=headers, timeout=15)
        try:
            data = r.json()
        except ValueError:
            data = {"detail": r.text}
        return Decision(
            status_code=r.status_code,
            decision=data.get("decision"),
            challenge_id=data.get("challenge_id"),
            risk_score=data.get("risk_score"),
            reasons=list(data.get("reasons") or []),
            latency_ms=data.get("latency_ms"),
            detail=str(data.get("detail")) if data.get("detail") is not None else None,
            raw=data,
        )

    async def wait_for_challenge(self, client: httpx.AsyncClient, challenge_id: str, timeout_s: float = 90) -> dict:
        """Poll GET /challenge/{id} until it is no longer pending. The shopper is never told the risk reasons."""
        deadline = time.monotonic() + timeout_s
        last = {"status": "pending", "outcome": None}
        while time.monotonic() < deadline:
            r = await client.get(f"{self.base}/challenge/{challenge_id}", timeout=10)
            if r.status_code == 200:
                last = r.json()
                if last.get("status") != "pending":
                    return last
            await asyncio.sleep(1)
        return last
