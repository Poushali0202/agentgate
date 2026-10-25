"""Shared helpers for the Shopper and Guardian agents: env loading, chat-protocol message builders, reason text."""

import hashlib
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
)


def load_env(path: str = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ without overriding what is already set."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def text_message(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=utcnow(), msg_id=uuid4(), content=content)


def ack_for(msg: ChatMessage) -> ChatAcknowledgement:
    return ChatAcknowledgement(timestamp=utcnow(), acknowledged_msg_id=msg.msg_id)


_MENTION = re.compile(r"@?agent1q[0-9a-z]{20,}")


def message_text(msg: ChatMessage) -> str:
    """Concatenate the text parts of an incoming chat message.

    ASI:One keeps the @agent1q... mention inside the text it delivers, so strip agent addresses out: otherwise the
    Shopper searches the store for an address and the Guardian reads one as the approve/deny verb.
    """
    parts = []
    for item in msg.content:
        if isinstance(item, TextContent):
            parts.append(_MENTION.sub(" ", item.text))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def consumer_id_for(sender: str) -> str:
    """The human behind the chat is the consumer. Derive a stable, short id from their agent address."""
    return "c-" + hashlib.sha256(sender.encode()).hexdigest()[:10]


def card_fp_for(sender: str) -> str:
    return "card_" + hashlib.sha256(("card:" + sender).encode()).hexdigest()[:8]


# Rule ids from gateway/scoring.py, in the words a shopper or merchant would read.
REASON_TEXT = {
    "base": "baseline",
    "burst": "unusually many checkouts in a short time",
    "heavy_burst": "extremely high checkout rate",
    "card_testing": "many different cards tried by one agent",
    "tiny_orders": "mostly very small test-sized orders",
    "hoarding": "bulk buying of a limited-drop item",
    "too_fast": "checked out faster than a normal shopper",
    "new_address": "shipping to an address this customer has not used",
    "big_basket": "order far larger than this customer's usual",
    "new_category": "buying a category this customer never buys",
    "cluster": "many agents tied to the same card or address",
    "young_key": "brand-new agent identity",
    "human_approved": "approved by the account holder",
    "human_denied": "denied by the account holder",
    "guardian_timeout": "no answer from the account holder in time",
}


def reasons_text(reasons: list[str] | None) -> str:
    if not reasons:
        return "no specific flags"
    return "; ".join(REASON_TEXT.get(r, r) for r in reasons if r != "base") or "baseline only"
