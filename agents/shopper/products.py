"""Product lookup. Source is Sanjana's Apify output (PRODUCTS_JSON: a file path or URL) when set, else the gateway's own store."""

import json
import os
import re

import httpx

from agents.common import env

# Words a shopper uses -> catalogue categories / names they mean.
SYNONYMS = {
    "headphone": ["headphones", "audio"],
    "headphones": ["headphones", "audio"],
    "earbud": ["earbuds", "audio"],
    "earbuds": ["earbuds", "audio"],
    "speaker": ["speaker", "audio"],
    "sneaker": ["sneaker", "footwear"],
    "sneakers": ["sneaker", "footwear"],
    "shoe": ["shoe", "footwear"],
    "shoes": ["shoe", "footwear"],
    "gpu": ["graphics", "electronics"],
    "graphics": ["graphics", "electronics"],
    "keyboard": ["keyboard", "electronics"],
    "mouse": ["mouse", "electronics"],
    "cable": ["cable", "electronics"],
    "charger": ["power bank", "electronics"],
    "battery": ["power bank", "electronics"],
    "tshirt": ["t-shirt", "apparel"],
    "shirt": ["t-shirt", "apparel"],
    "hoodie": ["hoodie", "apparel"],
    "socks": ["socks", "apparel"],
    "mug": ["mug", "home"],
    "coffee": ["coffee", "grocery"],
    "tea": ["tea", "grocery"],
    "book": ["novel", "books"],
    "novel": ["novel", "books"],
    "gift": ["gift card", "gift_cards"],
    "giftcard": ["gift card", "gift_cards"],
    "voucher": ["gift card", "gift_cards"],
    "backpack": ["backpack", "bags"],
    "bag": ["backpack", "bags"],
}


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


async def catalogue(client: httpx.AsyncClient, gateway_url: str) -> list[dict]:
    source = env("PRODUCTS_JSON")
    if source:
        if source.startswith("http://") or source.startswith("https://"):
            r = await client.get(source, timeout=15)
            r.raise_for_status()
            data = r.json()
        elif os.path.exists(source):
            with open(source, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = None
        if isinstance(data, dict):
            data = data.get("products") or data.get("items") or []
        if data:
            return [_normalise(p) for p in data if isinstance(p, dict)]
    r = await client.get(f"{gateway_url}/store/products", timeout=10)
    r.raise_for_status()
    return r.json()


def _normalise(p: dict) -> dict:
    """Apify output can use different field names; the gateway only needs sku/name/price/category."""
    return {
        "sku": p.get("sku") or p.get("id") or p.get("SKU"),
        "name": p.get("name") or p.get("title") or "",
        "price": float(p.get("price") or 0),
        "category": p.get("category") or "",
        "limited": bool(p.get("limited", False)),
    }


def match(products: list[dict], item: str, max_price: float | None = None) -> dict | None:
    """Best product for the words the shopper used. Ties go to the cheaper item; a budget filters first."""
    want = _tokens(item)
    expanded = list(want)
    for w in want:
        expanded.extend(_tokens(" ".join(SYNONYMS.get(w, []))))
        if w.endswith("s") and w[:-1] in SYNONYMS:
            expanded.extend(_tokens(" ".join(SYNONYMS[w[:-1]])))

    best, best_score = None, 0
    for p in products:
        if not p.get("sku"):
            continue
        if max_price is not None and p["price"] > max_price:
            continue
        hay = _tokens(f"{p.get('name', '')} {p.get('category', '')} {p.get('sku', '')}")
        score = sum(2 if t in want else 1 for t in expanded if t in hay)
        if score > best_score or (score == best_score and best and score and p["price"] < best["price"]):
            best, best_score = p, score
    return best if best_score > 0 else None
