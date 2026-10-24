import asyncio
import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from gateway import app as gw
from gateway import db, latency, security_tests
from gateway.signer import BROWSER_TAG, PAYER_TAG, public_jwk, sign_request

BASE = "http://testserver"
ORDER = {"consumer_id": "c-1", "card_fp": "card_abc", "ship_to": "1 Main St", "cart": [{"sku": "HP-100", "qty": 1}]}


@pytest.mark.parametrize("name", list(security_tests.CASES))
def test_security_case(name):
    expected, got = security_tests.CASES[name]()
    assert got == expected


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setattr(gw.directory, "path", str(tmp_path / "directory.json"))
    with TestClient(gw.app) as c:
        yield c


@pytest.fixture
def agent(client):
    key = Ed25519PrivateKey.generate()
    r = client.post("/directory/keys", json=public_jwk(key.public_key(), "shopper-test"))
    assert r.status_code == 200
    return key


def signed_checkout(client, key, order=ORDER, tag=PAYER_TAG):
    body = json.dumps(order).encode()
    headers = sign_request(key, "shopper-test", "POST", f"{BASE}/checkout", body, tag=tag)
    return client.post("/checkout", content=body, headers={**headers, "Content-Type": "application/json"})


def test_unsigned_checkout_blocked(client):
    r = client.post("/checkout", json=ORDER)
    assert r.status_code == 403
    assert r.json()["reasons"] == ["unsigned checkout not accepted"]


def test_signed_checkout_allowed_and_logged(client, agent):
    r = signed_checkout(client, agent)
    assert r.status_code == 200
    event = r.json()
    assert event["identity"] == "verified" and event["decision"] == "allow"
    assert event["cart"][0]["price"] == 149.99
    assert event["ship_to"].startswith("addr_")
    assert client.get("/events?limit=1").json()[0]["request_id"] == event["request_id"]


def test_browser_tag_cannot_checkout(client, agent):
    r = signed_checkout(client, agent, tag=BROWSER_TAG)
    assert r.status_code == 403 and r.json()["reasons"] == ["wrong_tag"]


def test_signed_browse(client, agent):
    headers = sign_request(agent, "shopper-test", "GET", f"{BASE}/browse", tag=BROWSER_TAG)
    r = client.get("/browse", params={"consumer_id": "c-1", "q": "headphones"}, headers=headers)
    assert r.status_code == 200 and r.json()[0]["sku"] == "HP-100"
    assert db.last_browse("shopper-test", "c-1") is not None


@pytest.mark.parametrize("approved,final", [(True, "allow"), (False, "block")])
def test_challenge_flow(client, agent, monkeypatch, approved, final):
    monkeypatch.setattr(gw, "decide", lambda identity, score, reasons: "challenge")
    sent = []

    async def fake_webhook(event):
        sent.append(event)
    monkeypatch.setattr(gw, "_fire_webhook", fake_webhook)

    r = signed_checkout(client, agent)
    assert r.status_code == 202
    assert set(r.json()) == {"decision", "challenge_id"}
    cid = r.json()["challenge_id"]
    assert sent and sent[0]["challenge_id"] == cid

    assert client.get(f"/challenge/{cid}").json()["status"] == "pending"
    assert any(c["challenge_id"] == cid for c in client.get("/challenges?status=pending").json())

    r = client.post(f"/challenge/{cid}/resolve", json={"approved": approved})
    assert r.json()["decision"] == final
    assert r.json()["challenge_id"] == cid
    assert client.get(f"/challenge/{cid}").json()["status"] == final
    assert client.post(f"/challenge/{cid}/resolve", json={"approved": approved}).status_code == 409
    assert client.post("/challenge/nope/resolve", json={"approved": True}).status_code == 404


def test_unanswered_challenge_times_out(client, agent, monkeypatch):
    monkeypatch.setattr(gw, "decide", lambda identity, score, reasons: "challenge")
    monkeypatch.setattr(gw, "_fire_webhook", lambda event: _noop())
    cid = signed_checkout(client, agent).json()["challenge_id"]
    monkeypatch.setattr(gw, "CHALLENGE_TTL_S", -1)
    status = client.get(f"/challenge/{cid}").json()
    assert status["status"] == "block" and status["reasons"][0] == "guardian_timeout"


async def _noop():
    pass


def test_webhook_retries_then_delivers(monkeypatch):
    calls = []

    class FlakyClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json):
            calls.append(url)
            status = 500 if len(calls) < 2 else 200
            return httpx.Response(status, request=httpx.Request("POST", url))

    monkeypatch.setattr(gw, "CHALLENGE_WEBHOOK_URL", "http://guardian.test/challenge")
    monkeypatch.setattr(gw.httpx, "AsyncClient", FlakyClient)
    monkeypatch.setattr(gw.asyncio, "sleep", lambda s: _noop())
    gw.challenges["cid-1"] = {"event": {}, "status": "pending", "created": 0, "webhook": "pending", "final": None}
    asyncio.run(gw._fire_webhook({"challenge_id": "cid-1"}))
    assert len(calls) == 2 and gw.challenges["cid-1"]["webhook"] == "delivered"


def test_stats_excludes_resolutions():
    events = [{"decision": "allow", "latency_ms": float(i), "reasons": ["base"]} for i in range(1, 101)]
    events.append({"decision": "block", "latency_ms": 9999.0, "reasons": ["human_denied"]})
    s = latency.summary(events)
    assert s["latency_ms"]["p95"] == 95.0 and s["latency_ms"]["max"] == 100.0
    assert s["decisions"] == {"allow": 100, "block": 1}


def test_security_tests_endpoint(client):
    assert client.get("/security-tests").json()["passed"] == 5
