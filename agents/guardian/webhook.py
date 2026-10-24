"""Webhook listener the gateway POSTs challenges to.

Runs as a small FastAPI app in a daemon thread next to the Guardian agent, on the port named in CHALLENGE_WEBHOOK_URL.
The gateway sends `Authorization: Bearer $GUARDIAN_TOKEN`; anything without it is refused, so only the gateway can
put a challenge in front of the human.
"""

import secrets
import threading
from collections import deque

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="AgentGate Guardian webhook")

_token: str | None = None
pending: dict[str, dict] = {}        # challenge_id -> event, until the human answers
inbox: deque[str] = deque()          # challenge_ids not yet shown to the human
_lock = threading.Lock()


def configure(token: str | None) -> None:
    global _token
    _token = token or None


def _check(authorization: str | None) -> None:
    if not _token:
        raise HTTPException(503, "GUARDIAN_TOKEN not configured on the guardian")
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {_token}"):
        raise HTTPException(401, "Guardian token required")


@app.post("/challenge")
async def challenge(request: Request, authorization: str | None = Header(None)):
    _check(authorization)
    event = await request.json()
    cid = event.get("challenge_id")
    if not cid:
        raise HTTPException(400, "event has no challenge_id")
    with _lock:
        if cid not in pending:
            pending[cid] = event
            inbox.append(cid)
    return {"ok": True, "challenge_id": cid}


@app.get("/health")
async def health():
    with _lock:
        return {"ok": True, "pending": len(pending), "unread": len(inbox)}


def add_pending(event: dict) -> bool:
    """Used by the fallback poller when the webhook couldn't be reached. Returns True if new."""
    cid = event.get("challenge_id")
    if not cid:
        return False
    with _lock:
        if cid in pending:
            return False
        pending[cid] = event
        inbox.append(cid)
        return True


def drain_inbox() -> list[dict]:
    with _lock:
        ids = list(inbox)
        inbox.clear()
        return [pending[c] for c in ids if c in pending]


def pop_pending(cid: str) -> dict | None:
    with _lock:
        return pending.pop(cid, None)


def list_pending() -> list[dict]:
    with _lock:
        return list(pending.values())


def start(port: int) -> threading.Thread:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, name="guardian-webhook", daemon=True)
    t.start()
    return t
