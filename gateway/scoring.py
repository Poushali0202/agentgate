"""Contract risk rules. Simulator labels never participate in scoring.

Drift requires a completed, allowed purchase as a baseline; first purchases
have no established preferences. Count verified attempts for velocity, but
never count a challenge resolution as another checkout.
"""

import time

from gateway import db, store

RESOLUTION_REASONS = {"human_approved", "human_denied", "guardian_timeout"}


def _attempts(events):
    return [e for e in events if e.get("identity") == "verified"
            and not RESOLUTION_REASONS.intersection(e.get("reasons", []))]


def _total(event):
    return sum(i.get("qty", 0) * i.get("price", 0) for i in event.get("cart", []))


def _categories(event):
    return {p["category"] for i in event.get("cart", [])
            if (p := store.get_product(i["sku"]))}


def evaluate(event, recent=(), history=(), *, now=None, last_browse=None, first_seen=None):
    """Pure evaluator; recent is the preceding ten-minute checkout window.

    Current checkout participates in velocity, card and cluster counts.
    Equal-point reasons retain the shared contract's rule-table order.
    """
    now = time.time() if now is None else now
    recent = _attempts(recent)
    pair = (event.get("agent_keyid"), event.get("consumer_id"))
    orders = [e for e in recent if (e.get("agent_keyid"), e.get("consumer_id")) == pair] + [event]
    fired = [("base", 5)]

    def add(rule, condition, points):
        if condition:
            fired.append((rule, points))

    add("burst", len(orders) > 3, 20)
    add("heavy_burst", len(orders) > 10, 40)
    add("card_testing", len({e["card_fp"] for e in orders if e.get("card_fp")}) >= 3, 30)
    add("tiny_orders", sum(_total(e) < 5 for e in orders) > len(orders) / 2, 20)
    add("hoarding", any(i.get("qty", 0) >= 3 and (store.get_product(i["sku"]) or {}).get("limited")
                        for i in event.get("cart", [])), 25)
    add("too_fast", last_browse is not None and 0 <= now - last_browse < 3, 15)

    # Completed purchases only: blocked attempts must not teach the baseline.
    baseline = [e for e in history if e.get("consumer_id") == event.get("consumer_id")
                and e.get("identity") == "verified" and e.get("decision") == "allow"]
    if baseline:
        add("new_address", bool(event.get("ship_to")) and event["ship_to"] not in
            {e.get("ship_to") for e in baseline}, 25)
        average = sum(_total(e) for e in baseline) / len(baseline)
        add("big_basket", _total(event) > 5 * average, 30)
        categories = set().union(*(_categories(e) for e in baseline))
        add("new_category", bool(_categories(event) - categories), 25)

    cluster = any(event.get(field) and len({e.get("agent_keyid") for e in recent + [event]
                    if e.get(field) == event[field] and e.get("agent_keyid")}) >= 3
                  for field in ("card_fp", "ship_to"))
    add("cluster", cluster, 35)
    add("young_key", first_seen is not None and 0 <= now - first_seen < 300, 10)
    reasons = [rule for rule, _ in sorted(fired, key=lambda item: -item[1])[:3]]
    return min(100, sum(points for _, points in fired)), reasons


def score(event):
    """Gateway integration; imported lazily to avoid an app import cycle."""
    from gateway.app import directory

    return evaluate(event, db.events_since(600), db.consumer_events(event.get("consumer_id")),
                    last_browse=db.last_browse(event.get("agent_keyid"), event.get("consumer_id")),
                    first_seen=directory.first_seen(event.get("agent_keyid")))
