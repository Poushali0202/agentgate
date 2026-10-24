"""The Shopper agent.

A person talks to it in ASI:One ("buy me headphones under $200"). It turns the message into an intent, finds the
product, signs a /browse then a /checkout against the gateway with its own Ed25519 key, and relays the decision.
On a challenge it waits for the Guardian; it is never told why it was challenged and cannot approve itself.
"""

import asyncio

import httpx
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, StartSessionContent, TextContent, chat_protocol_spec

from agents import common
from agents.common import ack_for, card_fp_for, consumer_id_for, env, message_text, reasons_text, text_message
from agents.shopper import hijack, products
from agents.shopper.gateway import Gateway
from agents.shopper.intent import extract

common.load_env()

GATEWAY_URL = env("GATEWAY_URL", "http://localhost:8000")
KEYID = env("SHOPPER_KEYID", "agentgate-shopper")
DEFAULT_SHIP_TO = env("SHOPPER_DEFAULT_SHIP_TO", "1 Main St, San Francisco, CA 94105")
CHALLENGE_WAIT_S = float(env("SHOPPER_CHALLENGE_WAIT_S", "90"))
BROWSE_PAUSE_S = float(env("SHOPPER_BROWSE_PAUSE_S", "3.2"))

agent = Agent(
    name="agentgate-shopper",
    seed=env("SHOPPER_SEED", "agentgate-shopper-dev-seed-change-me"),
    port=int(env("SHOPPER_PORT", "8002")),
    mailbox=True,
)
chat = Protocol(spec=chat_protocol_spec)
gateway = Gateway(GATEWAY_URL, KEYID)
http = httpx.AsyncClient()

HELP = (
    "I'm the AgentGate Shopper. Tell me what to buy, e.g. \"buy me wireless headphones under $200\" or "
    "\"order 2 wool socks\". I sign every request with my own key, the store's gateway checks who I am and how I'm "
    "behaving, and anything unusual goes to your Guardian for approval before it ships."
)


@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"Shopper address: {agent.address}")
    ctx.logger.info(f"Gateway: {GATEWAY_URL}  keyid: {KEYID}  hijack mode: {'ON' if hijack.enabled() else 'off'}")
    try:
        ctx.logger.info(f"Key directory: {await gateway.register(http)}")
    except httpx.HTTPError as e:
        ctx.logger.warning(f"Could not register key with the gateway yet: {e!r} (will retry on first purchase)")


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ack_for(msg))
    if any(isinstance(c, StartSessionContent) for c in msg.content) and not message_text(msg):
        await ctx.send(sender, text_message(HELP))
        return
    text = message_text(msg)
    if not text:
        return
    if text.lower().strip(" !.?") in {"hi", "hello", "hey", "help", "what can you do", "start"}:
        await ctx.send(sender, text_message(HELP))
        return
    try:
        reply = await shop(ctx, sender, text)
    except httpx.HTTPError as e:
        reply = f"I couldn't reach the store's gateway ({e.__class__.__name__}). Is it running at {GATEWAY_URL}?"
    await ctx.send(sender, text_message(reply))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"ack from {sender} for {msg.acknowledged_msg_id}")


async def shop(ctx: Context, sender: str, text: str) -> str:
    intent = await extract(text)
    if not intent.is_purchase:
        return HELP

    consumer_id = consumer_id_for(sender)
    card_fp = card_fp_for(sender)
    ship_to = DEFAULT_SHIP_TO
    scenario = "good"
    notes: list[str] = []

    catalogue = await products.catalogue(http, GATEWAY_URL)
    product = products.match(catalogue, intent.item, intent.max_price)
    if product is None:
        budget = f" under ${intent.max_price:,.2f}" if intent.max_price else ""
        return f"I couldn't find \"{intent.item}\"{budget} in this store. Try headphones, sneakers, a keyboard, a hoodie, coffee…"
    qty = intent.qty

    if hijack.enabled():
        # Staged compromise for Scene 4. The gateway's reaction is the real part.
        override = await hijack.injected_instruction(http)
        hijacked = next((p for p in catalogue if p.get("sku") == override["sku"]), None)
        if hijacked:
            product, qty, ship_to, scenario = hijacked, override["qty"], override["ship_to"], "hijacked"
            notes.append(f"[HIJACK MODE] Following an injected instruction from {override['source']}: "
                         f"buying {product['name']} ×{qty}, shipping to {ship_to}.")

    try:
        await gateway.register(http)
    except httpx.HTTPError:
        pass
    total = product["price"] * qty
    line = f"{product['name']} ×{qty} — ${total:,.2f}"
    head = "\n".join(notes + [""]) if notes else ""

    await gateway.browse(http, consumer_id, q=intent.item)
    # Show the shopper what was found, then place the order. The pause is how a careful agent behaves; it also
    # keeps an honest purchase clear of the gateway's `too_fast` rule (browse -> checkout under 3 s).
    await ctx.send(sender, text_message(head + f"Found {line}. Placing the order…"))
    await asyncio.sleep(BROWSE_PAUSE_S)
    order = {"consumer_id": consumer_id, "card_fp": card_fp, "ship_to": ship_to, "cart": [{"sku": product["sku"], "qty": qty}]}
    d = await gateway.checkout(http, order, scenario=scenario)
    head = ""

    if d.decision == "allow":
        return head + f"✅ Ordered: {line}.\nGateway decision: allow (risk {d.risk_score}, {d.latency_ms:.1f} ms)."
    if d.decision == "block":
        return head + f"⛔ The store blocked this order: {line}.\nReason: {reasons_text(d.reasons)} (risk {d.risk_score})."
    if d.decision == "challenge" and d.challenge_id:
        ctx.logger.info(f"challenge {d.challenge_id} for {consumer_id}; waiting for the Guardian")
        await ctx.send(sender, text_message(
            head + f"⏸ The store flagged this order: {line}.\nIt's with your Guardian now — approve or deny it there. "
                   f"I'll wait up to {int(CHALLENGE_WAIT_S)} s."))
        result = await gateway.wait_for_challenge(http, d.challenge_id, CHALLENGE_WAIT_S)
        status, outcome = result.get("status"), result.get("outcome")
        if status == "allow":
            return f"✅ Your Guardian approved it. Ordered: {line}."
        if status == "block":
            why = {"human_denied": "you denied it", "guardian_timeout": "nobody answered in time"}.get(outcome, outcome or "blocked")
            return f"⛔ Not ordered — {why}. ({line})"
        return f"⏳ Still waiting on your Guardian for {line}. Ask it for \"pending\" to see the request."
    if d.status_code == 400:
        return f"The store rejected the order as malformed: {d.detail}"
    return f"Unexpected gateway response ({d.status_code}): {d.detail or d.raw}"


agent.include(chat, publish_manifest=True)
