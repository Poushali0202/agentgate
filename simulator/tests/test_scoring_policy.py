import copy
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from gateway import app as gw, db, policy
from gateway.scoring import evaluate
from gateway.signer import PAYER_TAG, sign_request


def event(**changes):
    return {"identity": "verified", "agent_keyid": "key", "consumer_id": "consumer",
            "card_fp": "card", "ship_to": "address", "decision": "allow", "reasons": [],
            "cart": [{"sku": "HP-100", "qty": 1, "price": 149.99}], **changes}


def test_first_purchase_and_label_independence():
    e = event()
    original = copy.deepcopy(e)
    assert evaluate(e) == (5, ["base"])
    for label in ("good", "spoof", "hijacked", "slow_low"):
        assert evaluate({**e, "scenario": label}) == evaluate(e)
    assert e == original


@pytest.mark.parametrize("prior,rule", [(2, None), (3, "burst"), (9, "burst"), (10, "heavy_burst")])
def test_velocity_boundaries(prior, rule):
    score, reasons = evaluate(event(), [event() for _ in range(prior)])
    assert (rule in reasons) if rule else reasons == ["base"]
    assert score == (65 if prior == 10 else 25 if prior >= 3 else 5)


def test_velocity_is_per_consumer_and_resolutions_excluded():
    history = [event(consumer_id="other") for _ in range(12)]
    history += [event(reasons=["human_approved"]) for _ in range(12)]
    assert evaluate(event(), history) == (5, ["base"])


def test_cards_tiny_orders_hoarding_and_timing():
    assert "card_testing" in evaluate(event(), [event(card_fp="a"), event(card_fp="b")])[1]
    assert "tiny_orders" in evaluate(event(cart=[{"sku": "CB-520", "qty": 1, "price": 3.99}]))[1]
    assert "hoarding" in evaluate(event(cart=[{"sku": "SN-DROP1", "qty": 3, "price": 220}]))[1]
    assert "too_fast" in evaluate(event(), now=1000, last_browse=998)[1]
    assert "too_fast" not in evaluate(event(), now=1000, last_browse=997)[1]
    assert "young_key" in evaluate(event(), now=1000, first_seen=701)[1]
    assert "young_key" not in evaluate(event(), now=1000, first_seen=700)[1]


@pytest.mark.parametrize("field", ["card_fp", "ship_to"])
def test_cluster_across_keys(field):
    rows = [event(agent_keyid=str(i), consumer_id=str(i), card_fp=str(i), ship_to=str(i)) for i in range(2)]
    for row in rows:
        row[field] = event()[field]
    score, reasons = evaluate(event(), rows)
    assert "cluster" in reasons and score == 40
    assert "burst" not in reasons


def test_drift_and_policy_override_at_high_score():
    changed = event(ship_to="new", cart=[{"sku": "GC-901", "qty": 2, "price": 500}])
    score, reasons = evaluate(changed, history=[event()])
    assert score == 85 and set(reasons) == {"new_address", "big_basket", "new_category"}
    assert policy.decide("verified", score, reasons) == "challenge"
    assert evaluate(changed, history=[event(decision="block")]) == (5, ["base"])


def test_cap_and_top_three():
    rows = [event(card_fp=str(i), agent_keyid="key") for i in range(11)]
    score, reasons = evaluate(event(cart=[{"sku": "SN-DROP1", "qty": 3, "price": 220}]), rows,
                              now=1000, last_browse=999, first_seen=999)
    assert score == 100 and reasons == ["heavy_burst", "card_testing", "hoarding"]


@pytest.mark.parametrize("identity,risk,reasons,expected", [
    ("invalid", 0, [], "block"), ("unverified", 0, [], "block"),
    ("verified", 0, ["replayed"], "block"), ("verified", 29, [], "allow"),
    ("verified", 30, [], "challenge"), ("verified", 69, [], "challenge"),
    ("verified", 70, [], "block"), ("verified", 100, ["new_address"], "challenge"),
])
def test_policy_order(identity, risk, reasons, expected):
    assert policy.decide(identity, risk, reasons) == expected


def test_gateway_integration(tmp_path, monkeypatch):
    original_init = db.init
    monkeypatch.setattr(db, "init", lambda: original_init(str(tmp_path / "events.db")))
    monkeypatch.setattr(gw, "challenges", {})
    monkeypatch.setattr(policy, "thresholds", {"challenge_at": 30, "block_at": 70})
    with TestClient(gw.app) as client:
        key = Ed25519PrivateKey.generate()
        gw.directory.register("integration", key.public_key())
        body = json.dumps({"consumer_id": "new", "card_fp": "card", "ship_to": "1 Main St",
                           "cart": [{"sku": "HP-100", "qty": 1}]}).encode()
        def checkout():
            return client.post("/checkout", content=body, headers=sign_request(
                key, "integration", "POST", "http://testserver/checkout", body, tag=PAYER_TAG))
        assert checkout().json()["decision"] == "allow"
        assert client.get("/events").json()[0]["risk_score"] == 15
        assert client.get("/").status_code == 200
        assert client.post("/policy", json={"challenge_at": 70, "block_at": 30}).status_code == 422
        assert client.post("/policy", json={"challenge_at": 1, "block_at": 70}).status_code == 200
        assert checkout().status_code == 202
