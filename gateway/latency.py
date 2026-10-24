"""Latency and decision stats from the SQLite event log.

    python -m gateway.latency            # prints p50/p95/p99 for the Devpost write-up

Challenge resolutions are excluded from latency: they time the Guardian round-trip, not verify -> score -> decide.
"""

import json
from collections import Counter

from gateway import db

RESOLUTION_REASONS = {"human_approved", "human_denied", "guardian_timeout"}


def is_resolution(event: dict) -> bool:
    return bool(event.get("reasons")) and event["reasons"][0] in RESOLUTION_REASONS


def percentile(sorted_values: list[float], p: float) -> float | None:
    """Nearest-rank percentile."""
    if not sorted_values:
        return None
    rank = max(1, -(-len(sorted_values) * p // 100))  # ceil
    return sorted_values[int(rank) - 1]


def summary(events: list[dict]) -> dict:
    lat = sorted(e["latency_ms"] for e in events if not is_resolution(e))
    return {
        "events": len(events),
        "decisions": dict(Counter(e["decision"] for e in events)),
        "latency_ms": {
            "n": len(lat),
            "p50": percentile(lat, 50),
            "p95": percentile(lat, 95),
            "p99": percentile(lat, 99),
            "max": lat[-1] if lat else None,
        },
    }


if __name__ == "__main__":
    db.init()
    print(json.dumps(summary(db.all_events()), indent=2))
