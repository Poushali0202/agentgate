"""Turn a chat message into a structured shopping intent.

Claude does the understanding when ANTHROPIC_API_KEY is set. A deterministic parser is the fallback and the
safety net, so the demo never depends on the API being reachable. Purchase logic stays in plain Python either way.
"""

import json
import re
from dataclasses import dataclass

from agents.common import env

MODEL = "claude-opus-5-5"

SYSTEM = (
    "You extract a shopping intent from one user message for a small online store. "
    "Reply with a single JSON object and nothing else, shaped exactly like "
    '{"item": "<what they want, a few words>", "max_price": <number or null>, "qty": <integer, default 1>}. '
    "If the message is not a request to buy something, reply {\"item\": null, \"max_price\": null, \"qty\": 1}."
)

_PRICE = re.compile(r"(?:under|below|less than|max(?:imum)?|up to|budget(?: of)?|for)?\s*\$?\s*(\d{1,6}(?:\.\d{1,2})?)\s*(?:dollars|usd|bucks)?", re.I)
_QTY = re.compile(r"\b(\d{1,3})\s*(?:x|pcs?|pieces?|units?|of)\b|\b(?:x|qty)\s*(\d{1,3})\b|(?:^|\b(?:buy|order|get|want|need)\s+(?:me\s+)?)(\d{1,3})\b(?!\s*(?:\.\d|%|\$))", re.I)
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a pair of": 2}
_FILLER = re.compile(
    r"\b(please|can you|could you|i want|i'd like|i would like|buy|get|order|purchase|me|a|an|the|some|for|under|below|"
    r"less than|max|maximum|up to|budget|of|dollars|usd|bucks|cheapest|best)\b",
    re.I,
)


@dataclass
class Intent:
    item: str | None
    max_price: float | None
    qty: int = 1
    source: str = "fallback"

    @property
    def is_purchase(self) -> bool:
        return bool(self.item)


def parse_fallback(text: str) -> Intent:
    """Regex intent: price after a budget word, an explicit quantity, and whatever is left as the item."""
    lowered = text.lower()
    max_price = None
    m = re.search(r"(?:under|below|less than|max(?:imum)?|up to|budget(?: of)?)\s*\$?\s*(\d{1,6}(?:\.\d{1,2})?)", lowered)
    if not m:
        m = re.search(r"\$\s*(\d{1,6}(?:\.\d{1,2})?)", lowered)
    if m:
        max_price = float(m.group(1))
        lowered = lowered.replace(m.group(0), " ")

    qty = 1
    q = _QTY.search(lowered)
    if q:
        qty = int(q.group(1) or q.group(2) or q.group(3))
        lowered = lowered.replace(q.group(0), " ")
    else:
        for word, n in _WORDS.items():
            if re.search(rf"\b{word}\b", lowered):
                qty = n
                lowered = re.sub(rf"\b{word}\b", " ", lowered)
                break

    item = _FILLER.sub(" ", lowered)
    item = re.sub(r"[^a-z0-9\- ]", " ", item)
    item = re.sub(r"\s+", " ", item).strip()
    if not item or item in {"hi", "hello", "hey", "help", "status", "thanks"}:
        return Intent(item=None, max_price=None, qty=1, source="fallback")
    return Intent(item=item, max_price=max_price, qty=max(1, min(qty, 100)), source="fallback")


async def extract(text: str) -> Intent:
    """Claude first, regex if Claude is unavailable or returns something unusable."""
    if not env("ANTHROPIC_API_KEY"):
        return parse_fallback(text)
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(timeout=12.0, max_retries=1)
        response = await client.messages.create(
            model=MODEL,
            max_tokens=256,
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        if response.stop_reason == "refusal":
            return parse_fallback(text)
        raw = "".join(block.text for block in response.content if block.type == "text")
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return parse_fallback(text)
        data = json.loads(match.group(0))
        item = data.get("item")
        price = data.get("max_price")
        qty = data.get("qty") or 1
        return Intent(
            item=str(item).strip() if item else None,
            max_price=float(price) if price is not None else None,
            qty=max(1, min(int(qty), 100)),
            source="claude",
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return parse_fallback(text)
    except Exception as e:  # anthropic.APIStatusError, APIConnectionError, APITimeoutError and friends
        if type(e).__module__.startswith("anthropic"):
            return parse_fallback(text)
        raise
