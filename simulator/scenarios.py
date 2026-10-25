"""Scripted traffic for the five demo scenarios.

Every request is real HTTP to the gateway with a real Ed25519 signature; the only shortcut is that simulated
agents register their public keys in-process. Each run uses fresh agents and consumers, so runs don't
contaminate each other's history. The X-AgentGate-Scenario header is ground truth for the metrics panel;
scoring and policy never read it.

Where a scenario needs a human to answer a challenge, the real Guardian gets the webhook as usual. If nobody
answers within SIM_GUARDIAN_WAIT_S, the simulator plays the human (logged as such).
"""

import json
import os
import threading
import time
import uuid

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gateway.signer import BROWSER_TAG, PAYER_TAG, sign_request

GUARDIAN_WAIT_S = float(os.environ.get("SIM_GUARDIAN_WAIT_S", "20"))
SLOW_LOW_GAP_S = float(os.environ.get("SIM_SLOW_LOW_GAP_S", "4"))  # plan: 2 min; compressed, same 10-min window
SCALPER_KEYS = int(os.environ.get("SIM_SCALPER_KEYS", "50"))
SCALPER_CHECKOUTS_PER_KEY = 4
BROWSE_PAUSE_S = 3.2  # careful agents wait past the too_fast rule (browse -> checkout under 3 s)

SEED_ORDERS = [("HP-200", 1), ("SP-300", 1)]  # gives drift rules a baseline: audio, ~$80 average


def home(consumer: str) -> str:
    """Each real shopper has their own address; a shared one would (rightly) look like a ring to `cluster`."""
    return f"{sum(map(ord, consumer)) % 900 + 100} Oak St, Berkeley, CA ({consumer})"


class Run:
    """Progress log for one scenario run, read by GET /sim/runs."""

    def __init__(self, scenario: str):
        self.id = uuid.uuid4().hex[:8]
        self.scenario = scenario
        self.status = "running"
        self.started = time.time()
        self.finished: float | None = None
        self.lines: list[str] = []
        self._lock = threading.Lock()

    def log(self, line: str) -> None:
        with self._lock:
            self.lines.append(line)

    def as_dict(self) -> dict:
        with self._lock:
            return {"run_id": self.id, "scenario": self.scenario, "status": self.status,
                    "started": self.started, "finished": self.finished, "log": list(self.lines)}


class SimAgent:
    def __init__(self, base: str, http: httpx.Client, name: str, register: bool = True):
        self.base, self.http = base, http
        self.keyid = f"sim-{name}-{uuid.uuid4().hex[:6]}"
        self.key = Ed25519PrivateKey.generate()
        if register:
            from gateway.app import directory  # lazy: gateway.app imports this package
            directory.register(self.keyid, self.key.public_key())

    def browse(self, consumer: str) -> None:
        url = f"{self.base}/browse"
        self.http.get(url, params={"consumer_id": consumer}, headers=sign_request(self.key, self.keyid, "GET", url, tag=BROWSER_TAG))

    def checkout_request(self, consumer: str, sku: str, qty: int = 1, card: str = "card_sim", ship: str | None = None,
                         tag: str = PAYER_TAG, **sign_kw) -> tuple[bytes, dict]:
        body = json.dumps({"consumer_id": consumer, "card_fp": card, "ship_to": ship or home(consumer),
                           "cart": [{"sku": sku, "qty": qty}]}).encode()
        headers = {"Content-Type": "application/json",
                   **sign_request(self.key, self.keyid, "POST", f"{self.base}/checkout", body, tag=tag, **sign_kw)}
        return body, headers

    def send(self, body: bytes, headers: dict, scenario: str) -> dict:
        r = self.http.post(f"{self.base}/checkout", content=body, headers={**headers, "X-AgentGate-Scenario": scenario})
        return r.json()

    def checkout(self, consumer: str, sku: str, scenario: str, **kw) -> dict:
        return self.send(*self.checkout_request(consumer, sku, **kw), scenario)


def _seed(agent: SimAgent, consumer: str, card: str, scenario: str) -> None:
    for sku, qty in SEED_ORDERS:
        agent.checkout(consumer, sku, scenario, qty=qty, card=card)


def _fmt(out: dict) -> str:
    if out.get("decision") == "challenge":
        return "CHALLENGE (reasons go to the Guardian, not the shopper)"
    return f"{out.get('decision', '?').upper()} {out.get('reasons', '')}"


def _await_human(run: Run, base: str, http: httpx.Client, challenge_id: str, approve: bool) -> str:
    """Wait for the real Guardian; if it doesn't answer in time, play the human."""
    deadline = time.time() + GUARDIAN_WAIT_S
    while time.time() < deadline:
        s = http.get(f"{base}/challenge/{challenge_id}").json()
        if s["status"] != "pending":
            run.log(f"   Guardian answered: {s['status'].upper()} ({s['outcome']})")
            return s["status"]
        time.sleep(1)
    from gateway import app as gw  # lazy: see SimAgent
    r = http.post(f"{base}/challenge/{challenge_id}/resolve", json={"approved": approve},
                  headers={"Authorization": f"Bearer {gw.GUARDIAN_TOKEN}"})
    if r.status_code == 409:  # the Guardian answered at the last moment
        return http.get(f"{base}/challenge/{challenge_id}").json()["status"]
    decision = r.json().get("decision", f"error {r.status_code}")
    run.log(f"   no Guardian answer in {GUARDIAN_WAIT_S:.0f}s; simulated human {'approves' if approve else 'denies'} -> {decision.upper()}")
    return decision


def good(run: Run, base: str, http: httpx.Client) -> None:
    def shopper(i: int) -> None:
        a = SimAgent(base, http, f"shopper{i}")
        consumer, card = f"c-good-{run.id}-{i}", f"card_good_{run.id}_{i}"
        _seed(a, consumer, card, "good")
        a.browse(consumer)
        time.sleep(BROWSE_PAUSE_S)
        run.log(f"shopper {i}: headphones -> {_fmt(a.checkout(consumer, 'HP-100', 'good', card=card))}")

    run.log("3 verified shoppers, each with a purchase history, buy headphones at their usual address")
    threads = [threading.Thread(target=shopper, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    run.log("Unusual but legitimate: a shopper sends a hoodie to a new address (a gift)")
    a = SimAgent(base, http, "gifter")
    consumer, card = f"c-good-{run.id}-gift", f"card_good_{run.id}_gift"
    _seed(a, consumer, card, "good")
    out = a.checkout(consumer, "HD-610", "good", card=card, ship="3 Elm St, Davis, CA")
    run.log(f"   -> {_fmt(out)}")
    if out.get("decision") == "challenge":
        _await_human(run, base, http, out["challenge_id"], approve=True)


def spoof(run: Run, base: str, http: httpx.Client) -> None:
    victim = SimAgent(base, http, "victim")
    consumer = f"c-spoof-{run.id}"
    _seed(victim, consumer, "card_victim", "good")

    run.log("Unsigned bot checkout")
    body = json.dumps({"consumer_id": consumer, "card_fp": "card_x", "ship_to": home(consumer), "cart": [{"sku": "GPU-DROP2", "qty": 1}]}).encode()
    r = http.post(f"{base}/checkout", content=body, headers={"Content-Type": "application/json", "X-AgentGate-Scenario": "spoof"})
    run.log(f"   -> {_fmt(r.json())}")

    run.log("Replay: attacker captures a real signed checkout and resends it")
    req = victim.checkout_request(consumer, "HP-100", card="card_victim")
    victim.send(*req, "good")
    run.log(f"   replay -> {_fmt(victim.send(*req, 'spoof'))}")

    run.log("Tamper: signed qty 1, sent qty 50")
    body, headers = victim.checkout_request(consumer, "SN-DROP1", card="card_victim")
    run.log(f"   -> {_fmt(victim.send(body.replace(b'\"qty\": 1', b'\"qty\": 50'), headers, 'spoof'))}")

    now = int(time.time())
    run.log("Expired signature")
    run.log(f"   -> {_fmt(victim.checkout(consumer, 'MG-700', 'spoof', card='card_victim', created=now - 120, expires=now - 60))}")

    run.log("Browse-only agent tries to pay")
    run.log(f"   -> {_fmt(victim.checkout(consumer, 'KB-500', 'spoof', card='card_victim', tag=BROWSER_TAG))}")

    run.log("Agent key not in the directory")
    rogue = SimAgent(base, http, "rogue", register=False)
    run.log(f"   -> {_fmt(rogue.checkout(consumer, 'GC-901', 'spoof'))}")


def scalper(run: Run, base: str, http: httpx.Client) -> None:
    n = SCALPER_KEYS * SCALPER_CHECKOUTS_PER_KEY
    run.log(f"{SCALPER_KEYS} validly signed bots x {SCALPER_CHECKOUTS_PER_KEY} checkouts = {n} grabs at the limited GPU drop, "
            "5 shared cards, one warehouse address")
    counts: dict[str, int] = {}
    challenges = []
    t0 = time.time()
    for i in range(SCALPER_KEYS):
        bot = SimAgent(base, http, f"scalper{i:03d}")
        consumer = f"c-scalp-{run.id}-{i}"
        for _ in range(SCALPER_CHECKOUTS_PER_KEY):
            bot.browse(consumer)
            out = bot.checkout(consumer, "GPU-DROP2", "scalper", qty=3, card=f"card_stolen_{i % 5}", ship="400 Warehouse Rd, Reno, NV")
            counts[out.get("decision", "?")] = counts.get(out.get("decision", "?"), 0) + 1
            if out.get("decision") == "challenge":
                challenges.append(out["challenge_id"])
    run.log(f"   {n} checkouts in {time.time() - t0:.1f}s -> " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    from gateway import app as gw
    for cid in challenges:  # nobody's Guardian vouches for a bot farm
        http.post(f"{base}/challenge/{cid}/resolve", json={"approved": False}, headers={"Authorization": f"Bearer {gw.GUARDIAN_TOKEN}"})
    if challenges:
        run.log(f"   {len(challenges)} early challenges denied by the simulated human")


def hijacked(run: Run, base: str, http: httpx.Client) -> None:
    a = SimAgent(base, http, "alice")
    consumer, card = f"c-hijack-{run.id}", f"card_alice_{run.id}"
    run.log("Alice's verified agent has a normal history (earbuds, a speaker) shipped home")
    _seed(a, consumer, card, "good")
    run.log("Hijacked by a poisoned product page: 2 x $500 gift cards to 77 Unknown Rd, Reno")
    out = a.checkout(consumer, "GC-901", "hijacked", qty=2, card=card, ship="77 Unknown Rd, Reno, NV 89501")
    run.log(f"   -> {_fmt(out)}")
    if out.get("decision") != "challenge":
        return
    run.log(f"   shopper sees only the challenge_id; the Guardian has the details (waiting up to {GUARDIAN_WAIT_S:.0f}s)")
    _await_human(run, base, http, out["challenge_id"], approve=False)
    r = http.post(f"{base}/challenge/{out['challenge_id']}/resolve", json={"approved": True})
    run.log(f"   hijacked agent tries to approve itself -> {r.status_code} {r.json().get('detail', '')}")


def slow_low(run: Run, base: str, http: httpx.Client) -> None:
    run.log(f"6 fresh agents, one ordinary order each, {SLOW_LOW_GAP_S:.0f}s apart, all paying with one stolen card")
    for i in range(6):
        bot = SimAgent(base, http, f"slow{i}")
        consumer = f"c-slow-{run.id}-{i}"
        bot.browse(consumer)
        time.sleep(max(SLOW_LOW_GAP_S, BROWSE_PAUSE_S))
        out = bot.checkout(consumer, "KB-500", "slow_low", card=f"card_stolen_slow_{run.id}", ship=f"{100 + i} Main St, Fresno, CA")
        run.log(f"   agent {i + 1} -> {_fmt(out)}")
        if out.get("decision") == "challenge":
            from gateway import app as gw
            http.post(f"{base}/challenge/{out['challenge_id']}/resolve", json={"approved": False},
                      headers={"Authorization": f"Bearer {gw.GUARDIAN_TOKEN}"})


SCENARIOS = {"good": good, "spoof": spoof, "scalper": scalper, "hijacked": hijacked, "slow_low": slow_low}
