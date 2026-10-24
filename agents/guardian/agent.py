"""The Guardian agent.

The consumer's trusted channel. The gateway POSTs every challenge here (never to the Shopper), the Guardian shows it to
the human in ASI:One with the item, amount and risk reasons, and the human replies approve or deny. The Guardian then
resolves the challenge with the shared GUARDIAN_TOKEN the Shopper never has. A hijacked Shopper can't approve itself.
"""

import httpx
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, StartSessionContent, chat_protocol_spec

from agents import common
from agents.common import ack_for, env, message_text, reasons_text, text_message
from agents.guardian import webhook

common.load_env()

GATEWAY_URL = env("GATEWAY_URL", "http://localhost:8000").rstrip("/")
GUARDIAN_TOKEN = env("GUARDIAN_TOKEN")
WEBHOOK_PORT = int(env("GUARDIAN_WEBHOOK_PORT", "8001"))
OWNER = env("GUARDIAN_OWNER")  # optional: pin the human's agent address; otherwise the first person to talk to it

agent = Agent(
    name="agentgate-guardian",
    seed=env("GUARDIAN_SEED", "agentgate-guardian-dev-seed-change-me"),
    port=int(env("GUARDIAN_PORT", "8003")),
    mailbox=True,
)
chat = Protocol(spec=chat_protocol_spec)
http = httpx.AsyncClient()
_names: dict[str, str] = {}

HELP = (
    "I'm your AgentGate Guardian. When your Shopper tries something the store finds unusual, the store asks me, "
    "and I ask you. Reply \"approve\" or \"deny\" (optionally with the request id, e.g. \"approve 3f9a\"). "
    "Say \"pending\" to see open requests."
)


def _auth() -> dict:
    return {"Authorization": f"Bearer {GUARDIAN_TOKEN}"} if GUARDIAN_TOKEN else {}


def _owner(ctx: Context) -> str | None:
    return OWNER or ctx.storage.get("owner")


def _item_line(event: dict) -> str:
    parts = []
    total = 0.0
    for c in event.get("cart") or []:
        name = _names.get(c.get("sku"), c.get("sku"))
        price = float(c.get("price") or 0)
        qty = int(c.get("qty") or 1)
        total += price * qty
        parts.append(f"{name} ×{qty}")
    return f"{', '.join(parts) or 'unknown item'} — ${total:,.2f}"


def _ship_line(event: dict) -> str:
    # The gateway hashes ship_to before logging it, so the Guardian sees an address id, not the street.
    reasons = event.get("reasons") or []
    ref = str(event.get("ship_to") or "")[-6:]
    if "new_address" in reasons:
        return f"a NEW address, never used on your account (ref …{ref})"
    return f"your usual address (ref …{ref})"


def card_text(event: dict) -> str:
    cid = event.get("challenge_id", "")
    return (
        "🔒 Guardian check — your Shopper wants to buy:\n"
        f"• {_item_line(event)}\n"
        f"• Ship to: {_ship_line(event)}\n"
        f"• Risk {event.get('risk_score', '?')}/100 — flagged: {reasons_text(event.get('reasons'))}\n"
        f"Reply \"approve\" or \"deny\".  (request {cid[:8]})"
    )


async def load_names():
    try:
        r = await http.get(f"{GATEWAY_URL}/store/products", timeout=10)
        r.raise_for_status()
        _names.update({p["sku"]: p["name"] for p in r.json()})
    except (httpx.HTTPError, ValueError, KeyError):
        pass


async def resolve(cid: str, approved: bool) -> str:
    r = await http.post(f"{GATEWAY_URL}/challenge/{cid}/resolve", json={"approved": approved}, headers=_auth(), timeout=10)
    if r.status_code in (200, 201):
        return "ok"
    if r.status_code == 401:
        return "the gateway rejected my token (GUARDIAN_TOKEN mismatch)"
    if r.status_code == 404:
        return "the gateway doesn't know that challenge any more"
    if r.status_code == 409:
        return "that challenge was already resolved"
    if r.status_code == 503:
        return "the gateway has no GUARDIAN_TOKEN configured"
    return f"gateway returned {r.status_code}"


def _pick(cid_prefix: str | None) -> dict | None:
    items = webhook.list_pending()
    if not items:
        return None
    if cid_prefix:
        for e in items:
            if str(e.get("challenge_id", "")).startswith(cid_prefix):
                return e
        return None
    return items[-1]


@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"Guardian address: {agent.address}")
    webhook.configure(GUARDIAN_TOKEN)
    webhook.start(WEBHOOK_PORT)
    ctx.logger.info(f"Webhook listening on http://127.0.0.1:{WEBHOOK_PORT}/challenge  gateway: {GATEWAY_URL}")
    if not GUARDIAN_TOKEN:
        ctx.logger.warning("GUARDIAN_TOKEN is not set: the gateway's webhooks will be refused and resolves will fail")
    await load_names()


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ack_for(msg))
    if not OWNER and not ctx.storage.get("owner"):
        ctx.storage.set("owner", sender)
        ctx.logger.info(f"owner set to {sender}")
    text = message_text(msg).strip()
    if any(isinstance(c, StartSessionContent) for c in msg.content) and not text:
        await ctx.send(sender, text_message(HELP))
        return
    if not text:
        return
    await ctx.send(sender, text_message(await handle(ctx, text)))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"ack from {sender} for {msg.acknowledged_msg_id}")


async def handle(ctx: Context, text: str) -> str:
    words = text.lower().strip(" !.?").split()
    verb = words[0] if words else ""
    prefix = words[1] if len(words) > 1 and len(words[1]) >= 4 else None

    if verb in {"approve", "yes", "ok", "allow", "confirm", "y"}:
        return await _answer(ctx, prefix, approved=True)
    if verb in {"deny", "no", "block", "reject", "decline", "n"}:
        return await _answer(ctx, prefix, approved=False)
    if verb in {"pending", "status", "open", "list"}:
        items = webhook.list_pending()
        if not items:
            return "No open requests. I'll message you the moment the store flags something."
        return "Open requests:\n\n" + "\n\n".join(card_text(e) for e in items)
    return HELP


async def _answer(ctx: Context, prefix: str | None, approved: bool) -> str:
    event = _pick(prefix)
    if event is None:
        return "There's nothing waiting for your answer right now." if not prefix else f"I don't have a request starting with {prefix}."
    cid = event["challenge_id"]
    outcome = await resolve(cid, approved)
    if outcome != "ok":
        return f"I couldn't send your answer: {outcome}."
    webhook.pop_pending(cid)
    if approved:
        return f"✅ Approved. The store will complete: {_item_line(event)}."
    return f"⛔ Denied. The store has blocked: {_item_line(event)}. Your Shopper has been told it was not ordered."


@agent.on_interval(period=1.0)
async def deliver(ctx: Context):
    """Push new challenges to the human as soon as the gateway sends them."""
    new = webhook.drain_inbox()
    if not new:
        return
    owner = _owner(ctx)
    for event in new:
        if owner:
            await ctx.send(owner, text_message(card_text(event)))
            ctx.logger.info(f"challenge {event.get('challenge_id')} shown to {owner}")
        else:
            ctx.logger.warning(f"challenge {event.get('challenge_id')} waiting: nobody has talked to the Guardian yet, so I don't know who to ask")


@agent.on_interval(period=15.0)
async def poll_fallback(ctx: Context):
    """If the gateway couldn't reach the webhook, pick up open challenges by polling."""
    if not GUARDIAN_TOKEN:
        return
    try:
        r = await http.get(f"{GATEWAY_URL}/challenges", params={"status": "pending"}, headers=_auth(), timeout=10)
        if r.status_code != 200:
            return
        rows = r.json()
        rows = rows.get("challenges", rows) if isinstance(rows, dict) else rows
        for row in rows:
            event = row.get("event", row) if isinstance(row, dict) else None
            if event and webhook.add_pending({**event, "challenge_id": row.get("challenge_id") or event.get("challenge_id")}):
                ctx.logger.info(f"picked up challenge {event.get('challenge_id')} by polling")
    except (httpx.HTTPError, ValueError, AttributeError):
        pass


agent.include(chat, publish_manifest=True)
