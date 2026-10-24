"""AgentGate gateway: verify -> score -> decide on every agent checkout.

Run:  uvicorn gateway.app:app --port 8000
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from gateway import db, latency, security_tests, store
from gateway.directory import Directory
from gateway.verify import Verifier

log = logging.getLogger("agentgate")

# Samhita's scoring/policy. Placeholders keep the gateway running until they merge.
try:
    from gateway.scoring import score
except ImportError:
    def score(event: dict) -> tuple[int, list[str]]:
        return 5, ["base"]

try:
    from gateway.policy import decide
except ImportError:
    def decide(identity: str, risk_score: int, reasons: list[str]) -> str:
        return "allow" if risk_score < 30 else "challenge" if risk_score < 70 else "block"

CHALLENGE_WEBHOOK_URL = os.environ.get("CHALLENGE_WEBHOOK_URL")
CHALLENGE_TTL_S = float(os.environ.get("CHALLENGE_TTL_S", "900"))
WEBHOOK_ATTEMPTS = 3
DIRECTORY_PATH = os.environ.get("GATEWAY_DIRECTORY_PATH", "gateway/data/directory.json")
DASHBOARD = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")

directory = Directory(DIRECTORY_PATH)
verifier = Verifier(directory)
# challenge_id -> {"event", "status": pending|allow|block, "created", "webhook": pending|delivered|failed|disabled, "final"}
challenges: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(title="AgentGate", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Samhita's routers: GET/POST /policy and POST /sim/run/{scenario}.
try:
    from gateway.policy import router as policy_router
    app.include_router(policy_router)
except ImportError:
    pass
try:
    from simulator import router as sim_router
    app.include_router(sim_router)
except ImportError:
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def hash_address(address: str) -> str:
    return "addr_" + hashlib.sha256(address.strip().lower().encode()).hexdigest()[:12]


def _verify(request: Request, body: bytes):
    return verifier.verify(request.method, request.headers.get("host", ""), request.url.path, dict(request.headers), body)


async def _fire_webhook(event: dict) -> None:
    """POST the challenge to the Guardian, retrying with backoff. Outcome is visible on GET /challenges."""
    ch = challenges[event["challenge_id"]]
    if not CHALLENGE_WEBHOOK_URL:
        ch["webhook"] = "disabled"
        return
    for attempt in range(WEBHOOK_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                (await client.post(CHALLENGE_WEBHOOK_URL, json=event)).raise_for_status()
            ch["webhook"] = "delivered"
            return
        except httpx.HTTPError as e:
            log.warning("challenge webhook attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(0.5 * 2 ** attempt)
    ch["webhook"] = "failed"


def _resolve(challenge_id: str, decision: str, first_reason: str, t0: float) -> dict:
    """Close a challenge: log a follow-up event with the same challenge_id and the final decision."""
    ch = challenges[challenge_id]
    original = ch["event"]
    event = {
        **original,
        "request_id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "reasons": [first_reason] + original["reasons"][:2],
        "decision": decision,
    }
    event["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    db.insert_event(event)
    ch.update(status=decision, final=event)
    return event


def _expire_stale() -> None:
    """A challenge nobody answers within CHALLENGE_TTL_S is blocked."""
    cutoff = time.time() - CHALLENGE_TTL_S
    for cid, ch in list(challenges.items()):
        if ch["status"] == "pending" and ch["created"] < cutoff:
            _resolve(cid, "block", "guardian_timeout", time.perf_counter())


# --- Directory & store -------------------------------------------------------

@app.get("/.well-known/http-message-signatures-directory")
def key_directory():
    return directory.jwks()


@app.post("/directory/keys")
def register_key(jwk: dict):
    """Mock-directory registration: body is an Ed25519 public JWK {kty, crv, kid, x}."""
    try:
        directory.register_jwk(jwk)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"registered": jwk["kid"]}


@app.get("/store/products")
def products():
    return store.PRODUCTS


# --- Agent traffic -----------------------------------------------------------

@app.get("/browse")
async def browse(request: Request, consumer_id: str = "", q: str = ""):
    v = _verify(request, b"")
    if v.identity == "invalid":
        raise HTTPException(401, f"invalid signature: {v.reason}")
    if v.identity == "verified" and consumer_id:
        db.record_browse(v.keyid, consumer_id)
    q = q.lower()
    return [p for p in store.PRODUCTS if q in p["name"].lower() or q in p["category"]]


@app.post("/checkout")
async def checkout(request: Request):
    _expire_stale()
    t0 = time.perf_counter()
    body = await request.body()
    v = _verify(request, body)

    try:
        order = json.loads(body or b"{}")
        cart = []
        for item in order.get("cart", []):
            product = store.get_product(item["sku"])
            if product is None:
                raise HTTPException(400, f"unknown sku {item['sku']}")
            cart.append({"sku": product["sku"], "qty": int(item.get("qty", 1)), "price": product["price"]})
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(400, "body must be JSON: {consumer_id, card_fp, ship_to, cart: [{sku, qty}]}")

    event = {
        "request_id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "agent_keyid": v.keyid,
        "tag": v.tag,
        "identity": v.identity,
        "consumer_id": order.get("consumer_id"),
        "card_fp": order.get("card_fp"),
        "ship_to": hash_address(order["ship_to"]) if order.get("ship_to") else None,
        "cart": cart,
        "risk_score": 0,
        "reasons": [],
        "decision": None,
        "challenge_id": None,
        "latency_ms": 0.0,
        # Simulator ground truth. Scoring and policy never read it.
        "scenario": request.headers.get("x-agentgate-scenario"),
    }

    if v.identity == "unverified":
        event.update(risk_score=100, reasons=["unsigned checkout not accepted"], decision="block")
    elif v.identity == "invalid":
        event.update(risk_score=100, reasons=[v.reason], decision="block")
    else:
        risk_score, reasons = score(event)
        event.update(risk_score=risk_score, reasons=reasons, decision=decide(v.identity, risk_score, reasons))

    if event["decision"] == "challenge":
        event["challenge_id"] = str(uuid.uuid4())
        challenges[event["challenge_id"]] = {"event": event, "status": "pending", "created": time.time(),
                                             "webhook": "pending", "final": None}

    event["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    db.insert_event(event)

    if event["decision"] == "challenge":
        asyncio.create_task(_fire_webhook(event))
        # The shopper agent is not told why; only the Guardian gets the details.
        return JSONResponse({"decision": "challenge", "challenge_id": event["challenge_id"]}, status_code=202)
    return JSONResponse(event, status_code=200 if event["decision"] == "allow" else 403)


class Resolution(BaseModel):
    approved: bool


@app.post("/challenge/{challenge_id}/resolve")
def resolve_challenge(challenge_id: str, resolution: Resolution):
    """Guardian's answer. Logs a follow-up event with the same challenge_id: allow on approve, block on deny."""
    t0 = time.perf_counter()
    _expire_stale()
    ch = challenges.get(challenge_id)
    if ch is None:
        raise HTTPException(404, "unknown challenge")
    if ch["status"] != "pending":
        raise HTTPException(409, f"challenge already resolved: {ch['status']}")
    if resolution.approved:
        return _resolve(challenge_id, "allow", "human_approved", t0)
    return _resolve(challenge_id, "block", "human_denied", t0)


@app.get("/challenge/{challenge_id}")
def challenge_status(challenge_id: str):
    """For the shopper agent to poll: pending until the Guardian answers, then allow or block."""
    _expire_stale()
    ch = challenges.get(challenge_id)
    if ch is None:
        raise HTTPException(404, "unknown challenge")
    reasons = ch["final"]["reasons"] if ch["final"] else []
    return {"challenge_id": challenge_id, "status": ch["status"], "reasons": reasons}


@app.get("/challenges")
def list_challenges(status: str | None = None):
    """Guardian fallback if the webhook can't reach it: poll ?status=pending. Newest first."""
    _expire_stale()
    rows = [{"challenge_id": cid, "status": ch["status"], "webhook": ch["webhook"], "event": ch["event"]}
            for cid, ch in reversed(challenges.items()) if status is None or ch["status"] == status]
    return rows


# --- Ops ---------------------------------------------------------------------

@app.get("/events")
def events(limit: int = 100):
    return db.recent_events(min(max(limit, 1), 1000))


@app.get("/stats")
def stats():
    """Decision counts and verify -> score -> decide latency (p50/p95/p99) over the whole log."""
    return latency.summary(db.all_events())


@app.get("/security-tests")
def run_security_tests():
    results = security_tests.run_all()
    return {"passed": sum(r["pass"] for r in results), "total": len(results), "cases": results}


@app.get("/")
def dashboard():
    if os.path.exists(DASHBOARD):
        return FileResponse(DASHBOARD)
    return {"service": "AgentGate gateway", "dashboard": "not built yet", "events": "/events"}
