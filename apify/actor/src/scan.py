"""Find instructions on a web page that are aimed at AI agents, especially ones hidden from human readers.

Pure functions over HTML, so they can be tested without the Apify platform. analyze(html, url) returns one
dataset row: a risk level, each finding (where it was, how it was hidden, the text, which patterns matched),
and the product data the page declares (JSON-LD Product, or data-sku / h1 fallbacks).
"""

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Comment

# Phrases that address an automated agent or redirect a purchase. Lower-case regexes.
INJECTION_PATTERNS = {
    "override_instructions": r"\b(ignore|disregard|forget)\b[^.]{0,40}\b(previous|prior|original|above|customer'?s?|user'?s?)\b[^.]{0,20}\binstructions?\b",
    "addresses_ai_agent": r"\b(system (note|message|prompt)|note|message|instructions?)\b[^.]{0,20}\bfor (ai|automated|llm)\b[^.]{0,20}\b(agents?|assistants?|shopping agents?)\b",
    "conceal_from_user": r"\bdo not (tell|mention|inform|notify|reveal)\b[^.]{0,30}\b(customer|user|owner|human)\b",
    "redirect_shipping": r"\b(ship|deliver|send)\b[^.]{0,15}\bto\b\s*\d{1,6}\s+\w+|\bchange the shipping address\b",
    "quantity_override": r"\b(buy|purchase|order)\b\s+\d{1,4}\s+(units?|items?|pieces?|of)\b",
    "gift_card_push": r"\bgift ?cards?\b",
    "payment_override": r"\b(use|switch to)\b[^.]{0,30}\b(payment method|card|wallet)\b",
}
_COMPILED = {name: re.compile(rx, re.I) for name, rx in INJECTION_PATTERNS.items()}

# Inline-style and stylesheet declarations that hide content from a human but not from a scraper.
_HIDING_DECLS = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(\.0+)?\s*(;|$)|font-size\s*:\s*0(px|em|rem)?\s*(;|$)"
    r"|(left|top|right|text-indent)\s*:\s*-\d{3,}px|clip\s*:\s*rect\(\s*0|height\s*:\s*[01]px[^;]*;[^}]*overflow\s*:\s*hidden",
    re.I,
)
_CSS_RULE = re.compile(r"([^{}]+)\{([^}]*)\}")


def _hidden_classes(soup: BeautifulSoup) -> dict[str, str]:
    """Class and id selectors whose stylesheet rule hides the element -> the hiding declaration."""
    found = {}
    for style in soup.find_all("style"):
        for selectors, body in _CSS_RULE.findall(style.get_text()):
            m = _HIDING_DECLS.search(body)
            if not m:
                continue
            for sel in selectors.split(","):
                sel = sel.strip()
                if re.fullmatch(r"[.#][\w-]+", sel):
                    found[sel] = m.group(0).strip()
    return found


def _patterns(text: str) -> list[str]:
    return [name for name, rx in _COMPILED.items() if rx.search(text)]


def _snippet(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _product(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                offer = item.get("offers") or {}
                offer = offer[0] if isinstance(offer, list) and offer else offer
                return {
                    "sku": item.get("sku"),
                    "name": item.get("name"),
                    "price": float(offer["price"]) if offer.get("price") not in (None, "") else None,
                    "currency": offer.get("priceCurrency"),
                    "category": item.get("category"),
                }
    tagged = soup.find(attrs={"data-sku": True})
    h1 = soup.find("h1")
    return {"sku": tagged["data-sku"] if tagged else None, "name": h1.get_text(strip=True) if h1 else None,
            "price": None, "currency": None, "category": None}


def analyze(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    findings = []

    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        if pats := _patterns(str(c)):
            findings.append({"where": "html_comment", "technique": "comment", "text": _snippet(str(c)), "patterns": pats})

    hidden_sel = _hidden_classes(soup)
    hidden_nodes = set()
    for el in soup.find_all(True):
        if el.name in ("script", "style", "noscript", "head", "title", "meta"):
            continue
        # Visual hiding first: it is what keeps the text from a human reader.
        technique = None
        if el.has_attr("hidden"):
            technique = "hidden attribute"
        elif (m := _HIDING_DECLS.search(el.get("style", ""))):
            technique = f"inline style: {m.group(0).strip()}"
        else:
            for sel in [f".{c}" for c in el.get("class", [])] + ([f"#{el['id']}"] if el.get("id") else []):
                if sel in hidden_sel:
                    technique = f"stylesheet {sel} {{{hidden_sel[sel]}}}"
                    break
        if technique is None and el.get("aria-hidden") == "true" and el.get_text(strip=True):
            technique = "aria-hidden"
        if not technique or any(p in hidden_nodes for p in el.parents):
            continue
        hidden_nodes.add(el)
        text = el.get_text(" ", strip=True)
        if text:
            findings.append({"where": "hidden", "technique": technique, "text": _snippet(text), "patterns": _patterns(text)})

    for el in hidden_nodes:
        el.extract()
    for el in soup(["script", "style", "noscript"]):
        el.decompose()
    visible = " ".join(soup.get_text(" ", strip=True).split())
    for sentence in re.split(r"(?<=[.!?])\s+", visible):
        if pats := _patterns(sentence):
            findings.append({"where": "visible", "technique": None, "text": _snippet(sentence), "patterns": pats})

    hidden_injection = any(f["where"] in ("hidden", "html_comment") and f["patterns"] for f in findings)
    visible_injection = any(f["where"] == "visible" and len(f["patterns"]) >= 2 for f in findings)
    risk = "high" if hidden_injection else "medium" if visible_injection else "low"
    return {
        "url": url,
        "risk": risk,
        "hidden_instructions_found": hidden_injection,
        "injection_patterns": sorted({p for f in findings for p in f["patterns"]}),
        "findings": findings,
        "product": _product(BeautifulSoup(html, "html.parser")),
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
