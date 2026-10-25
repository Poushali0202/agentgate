"""AgentGate gateway: verify -> score -> decide on every agent checkout.

Run:  uvicorn gateway.app:app --port 8000      (reads .env from the working directory)
"""

import asyncio
import hashlib
import importlib
import logging
import os
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

from gateway import envfile

envfile.load()  # before the imports below read their config from os.environ

from gateway import db, latency, security_tests, store  # noqa: E402
from gateway.directory import Directory  # noqa: E402
from gateway.verify import Verifier  # noqa: E402

log = logging.getLogger("agentgate")


def _optional_module(name: str):
    """Import a teammate's module if it exists yet. Errors *inside* it still raise, so a broken
    scoring.py fails loudly instead of silently falling back to allow-everything."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name != name:
            raise
        log.warning("%s not present yet; using placeholder", name)
        return None


# Samhita's scoring/policy. Placeholders keep the gateway running until they merge.
_scoring = _optional_module("gateway.scoring")
_policy = _optional_module("gateway.policy")
_simulator = _optional_module("simulator")

if _scoring:
    score = _scoring.score
else:
    def score(event: dict) -> tuple[int, list[str]]:
        return 5, ["base"]

if _policy:
    decide = _policy.decide
else:
    def decide(identity: str, risk_score: int, reasons: list[str]) -> str:
        return "allow" if risk_score < 30 else "challenge" if risk_score < 70 else "block"

CHALLENGE_WEBHOOK_URL = os.environ.get("CHALLENGE_WEBHOOK_URL")
# Shared secret between gateway and Guardian. The shopper never has it, so it can't approve its own challenge.
GUARDIAN_TOKEN = os.environ.get("GUARDIAN_TOKEN")
CHALLENGE_TTL_S = float(os.environ.get("CHALLENGE_TTL_S", "900"))
WEBHOOK_ATTEMPTS = 3
MAX_QTY = 100
DIRECTORY_PATH = os.environ.get("GATEWAY_DIRECTORY_PATH", "gateway/data/directory.json")
DASHBOARD = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")

directory = Directory(DIRECTORY_PATH)
verifier = Verifier(directory)
# challenge_id -> {"event", "status": pending|allow|block, "created", "webhook": pending|delivered|failed|disabled, "final"}
challenges: dict[str, dict] = {}
_challenge_lock = threading.Lock()
_webhook_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    if not GUARDIAN_TOKEN:
        log.warning("GUARDIAN_TOKEN not set: challenges can't be resolved until it is")
    yield


app = FastAPI(title="AgentGate", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Samhita's routers: GET/POST /policy and POST /sim/run/{scenario}.
for _mod in (_policy, _simulator):
    if _mod is not None and hasattr(_mod, "router"):
        app.include_router(_mod.router)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def hash_address(address: str) -> str:
    return "addr_" + hashlib.sha256(address.strip().lower().encode()).hexdigest()[:12]


def _verify(request: Request, body: bytes):
    return verifier.verify(request.method, request.headers.get("host", ""), request.url.path, dict(request.headers), body)


def require_guardian(authorization: str | None = Header(None)) -> None:
    if not GUARDIAN_TOKEN:
        raise HTTPException(503, "GUARDIAN_TOKEN not configured on the gateway")
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {GUARDIAN_TOKEN}"):
        raise HTTPException(401, "Guardian token required")


async def _fire_webhook(event: dict) -> None:
    """POST the challenge to the Guardian, retrying with backoff. Outcome is visible on GET /challenges."""
    ch = challenges[event["challenge_id"]]
    if not CHALLENGE_WEBHOOK_URL:
        ch["webhook"] = "disabled"
        return
    headers = {"Authorization": f"Bearer {GUARDIAN_TOKEN}"} if GUARDIAN_TOKEN else {}
    for attempt in range(WEBHOOK_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                (await client.post(CHALLENGE_WEBHOOK_URL, json=event, headers=headers)).raise_for_status()
            ch["webhook"] = "delivered"
            return
        except Exception as e:  # any failure (bad URL, refused, 5xx) must end in "failed", never stuck "pending"
            log.warning("challenge webhook attempt %d failed: %r", attempt + 1, e)
            await asyncio.sleep(0.5 * 2 ** attempt)
    ch["webhook"] = "failed"


def _resolve(challenge_id: str, decision: str, first_reason: str, t0: float) -> dict:
    """Close a challenge: log a follow-up event with the same challenge_id and the final decision.
    Caller holds _challenge_lock and has checked the challenge is pending."""
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
    ch.update(status=decision, final=event, resolved=time.time())
    return event


def _expire_stale() -> None:
    """Block challenges nobody answered within CHALLENGE_TTL_S; forget resolved ones after another TTL."""
    now = time.time()
    with _challenge_lock:
        for cid, ch in list(challenges.items()):
            if ch["status"] == "pending" and ch["created"] < now - CHALLENGE_TTL_S:
                _resolve(cid, "block", "guardian_timeout", time.perf_counter())
            elif ch["status"] != "pending" and ch["resolved"] < now - CHALLENGE_TTL_S:
                del challenges[cid]


# --- Directory & store -------------------------------------------------------

@app.get("/.well-known/http-message-signatures-directory")
def key_directory():
    return directory.jwks()


@app.post("/directory/keys")
def register_key(jwk: dict):
    """Mock-directory registration: body is an Ed25519 public JWK {kty, crv, kid, x}.
    Re-registering the same key is fine; a different key for an existing kid is refused."""
    try:
        directory.register_jwk(jwk)
    except KeyError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"registered": jwk["kid"]}


@app.get("/store/products")
def products():
    return store.PRODUCTS


# --- Agent traffic -----------------------------------------------------------

class CartItem(BaseModel):
    sku: str
    qty: int = Field(1, ge=1, le=MAX_QTY)


class Order(BaseModel):
    consumer_id: str
    card_fp: str | None = None
    ship_to: str | None = None
    cart: list[CartItem] = Field(min_length=1)


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

    # Validate the order before verifying, so a malformed body doesn't burn the signature's nonce.
    try:
        order = Order.model_validate_json(body or b"{}")
    except ValidationError as e:
        raise HTTPException(400, f"body must be {{consumer_id, card_fp, ship_to, cart: [{{sku, qty 1-{MAX_QTY}}}]}}: "
                                 f"{e.errors()[0]['msg']}")
    cart = []
    for item in order.cart:
        product = store.get_product(item.sku)
        if product is None:
            raise HTTPException(400, f"unknown sku {item.sku}")
        cart.append({"sku": product["sku"], "qty": item.qty, "price": product["price"]})

    v = _verify(request, body)
    event = {
        "request_id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "agent_keyid": v.keyid,
        "tag": v.tag,
        "identity": v.identity,
        "consumer_id": order.consumer_id,
        "card_fp": order.card_fp,
        "ship_to": hash_address(order.ship_to) if order.ship_to else None,
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
        with _challenge_lock:
            challenges[event["challenge_id"]] = {"event": event, "status": "pending", "created": time.time(),
                                                 "webhook": "pending", "final": None, "resolved": None}

    event["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    db.insert_event(event)

    if event["decision"] == "challenge":
        task = asyncio.create_task(_fire_webhook(event))
        _webhook_tasks.add(task)
        task.add_done_callback(_webhook_tasks.discard)
        # The shopper agent is not told why; only the Guardian gets the details.
        return JSONResponse({"decision": "challenge", "challenge_id": event["challenge_id"]}, status_code=202)
    return JSONResponse(event, status_code=200 if event["decision"] == "allow" else 403)


class Resolution(BaseModel):
    approved: bool


@app.post("/challenge/{challenge_id}/resolve", dependencies=[Depends(require_guardian)])
def resolve_challenge(challenge_id: str, resolution: Resolution):
    """Guardian's answer (needs Authorization: Bearer GUARDIAN_TOKEN).
    Logs a follow-up event with the same challenge_id: allow on approve, block on deny."""
    t0 = time.perf_counter()
    _expire_stale()
    with _challenge_lock:
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
    """For the shopper agent to poll: pending until the Guardian answers, then allow or block.
    Only the outcome is returned, never the risk reasons."""
    _expire_stale()
    with _challenge_lock:
        ch = challenges.get(challenge_id)
        if ch is None:
            raise HTTPException(404, "unknown challenge")
        outcome = ch["final"]["reasons"][0] if ch["final"] else None
        return {"challenge_id": challenge_id, "status": ch["status"], "outcome": outcome}


@app.get("/challenges", dependencies=[Depends(require_guardian)])
def list_challenges(status: str | None = None):
    """Guardian fallback if the webhook can't reach it: poll ?status=pending. Newest first."""
    _expire_stale()
    with _challenge_lock:
        return [{"challenge_id": cid, "status": ch["status"], "webhook": ch["webhook"], "event": ch["event"]}
                for cid, ch in reversed(challenges.items()) if status is None or ch["status"] == status]


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
