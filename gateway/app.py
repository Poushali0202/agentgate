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

from gateway import db, security_tests, store
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
DIRECTORY_PATH = os.environ.get("GATEWAY_DIRECTORY_PATH", "gateway/data/directory.json")
DASHBOARD = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")

directory = Directory(DIRECTORY_PATH)
verifier = Verifier(directory)
pending_challenges: dict[str, dict] = {}


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
    if not CHALLENGE_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(CHALLENGE_WEBHOOK_URL, json=event)
    except httpx.HTTPError as e:
        log.warning("challenge webhook failed: %s", e)


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
        pending_challenges[event["challenge_id"]] = event

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
    original = pending_challenges.pop(challenge_id, None)
    if original is None:
        raise HTTPException(404, "unknown or already resolved challenge")
    first = "human_approved" if resolution.approved else "human_denied"
    event = {
        **original,
        "request_id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "reasons": [first] + original["reasons"][:2],
        "decision": "allow" if resolution.approved else "block",
    }
    event["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    db.insert_event(event)
    return event


# --- Ops ---------------------------------------------------------------------

@app.get("/events")
def events(limit: int = 100):
    return db.recent_events(min(max(limit, 1), 1000))


@app.get("/security-tests")
def run_security_tests():
    results = security_tests.run_all()
    return {"passed": sum(r["pass"] for r in results), "total": len(results), "cases": results}


@app.get("/")
def dashboard():
    if os.path.exists(DASHBOARD):
        return FileResponse(DASHBOARD)
    return {"service": "AgentGate gateway", "dashboard": "not built yet", "events": "/events"}
