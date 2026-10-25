"""Observational correlation of gateway event times; never a policy input.

Timestamps measure gateway observation, not when separate clients sent requests.
Shared card/address values are demo claims, not independently verified identities.
"""

from collections import Counter, defaultdict, deque
from datetime import datetime, timezone

RESOLUTIONS = {"human_approved", "human_denied", "guardian_timeout"}


def correlate(events, *, window_ms=100, min_agents=3):
    """Find overlapping windows linking distinct verified agent keys.

Deduplicate request IDs, ignore resolutions, and require a shared nonempty card
or address. Count each matched request once even if both links match. Evidence
contains no card/address values and is capped to the latest twenty windows.
"""
    if window_ms <= 0 or min_agents < 2:
        raise ValueError("positive window and at least two agents required")
    groups = defaultdict(list)
    seen = set()
    for event in events:
        request_id, agent = event.get("request_id"), event.get("agent_keyid")
        if (not request_id or not agent or request_id in seen
                or event.get("identity") != "verified"
                or RESOLUTIONS.intersection(event.get("reasons", []))):
            continue
        try:
            timestamp = datetime.fromisoformat(event.get("ts", "").replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                continue
            timestamp = timestamp.astimezone(timezone.utc)
        except (ValueError, TypeError, AttributeError):
            continue
        seen.add(request_id)
        for field in ("card_fp", "ship_to"):
            if value := event.get(field):
                groups[(field, value)].append((timestamp, request_id, agent))

    matched = set()
    evidence = []
    windows = 0
    for (field, _), rows in groups.items():
        active, counts = deque(), Counter()
        for row in sorted(rows):
            timestamp, request_id, agent = row
            while active and (timestamp - active[0][0]).total_seconds() * 1000 > window_ms:
                old = active.popleft()
                counts[old[2]] -= 1
                if not counts[old[2]]:
                    del counts[old[2]]
            active.append(row)
            counts[agent] += 1
            if len(counts) >= min_agents:
                windows += 1
                matched.update(item[1] for item in active)
                evidence.append({"end": timestamp.isoformat(), "link": field,
                                 "agents": len(counts), "requests": len(active),
                                 "span_ms": round((timestamp - active[0][0]).total_seconds() * 1000, 3)})
    return {"window_ms": window_ms, "min_agents": min_agents,
            "matched_requests": len(matched), "overlapping_windows": windows,
            "evidence": sorted(evidence, key=lambda row: row["end"])[-20:]}
