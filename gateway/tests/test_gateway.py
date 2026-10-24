import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from gateway import app as gw
from gateway import db, security_tests
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

    r = client.post(f"/challenge/{cid}/resolve", json={"approved": approved})
    assert r.json()["decision"] == final
    assert r.json()["challenge_id"] == cid
    assert client.post(f"/challenge/{cid}/resolve", json={"approved": approved}).status_code == 404


def test_security_tests_endpoint(client):
    assert client.get("/security-tests").json()["passed"] == 5
