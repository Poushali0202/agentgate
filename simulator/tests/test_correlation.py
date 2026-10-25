from datetime import datetime, timedelta, timezone

from simulator.correlation import correlate
from simulator.router import metrics


def event(n, milliseconds, **changes):
    timestamp = datetime(2026, 10, 25, tzinfo=timezone.utc) + timedelta(milliseconds=milliseconds)
    return {"request_id": str(n), "agent_keyid": f"agent-{n}",
            "identity": "verified", "ts": timestamp.isoformat(),
            "card_fp": "demo-card", "ship_to": "", "reasons": [], **changes}


def test_cross_agent_boundary_and_reverse_input():
    events = [event(1, 0), event(2, 50), event(3, 100)]
    result = correlate(list(reversed(events)))
    assert result["matched_requests"] == 3
    assert result["evidence"][0]["span_ms"] == 100
    assert correlate([*events[:2], event(3, 100.001)])["matched_requests"] == 0
    assert metrics(events)["timing_correlation"] == result


def test_legitimate_coincident_traffic_and_single_agent_do_not_match():
    assert correlate([event(n, n, card_fp=f"card-{n}") for n in range(10)])["matched_requests"] == 0
    assert correlate([event(n, n, agent_keyid="one-agent") for n in range(10)])["matched_requests"] == 0


def test_ignore_resolution_duplicates_invalid_identities_and_timestamps():
    first = event(1, 0)
    events = [first, first.copy(), event(2, 1),
              event(3, 2, reasons=["human_approved"]),
              event(4, 3, identity="invalid"), event(5, 4, ts="bad"),
              event(6, 5, ts="2026-10-25T00:00:00")]
    assert correlate(events)["matched_requests"] == 0


def test_card_and_address_matches_count_request_only_once_and_hide_values():
    events = [event(n, n, ship_to="demo-address") for n in range(3)]
    result = correlate(events)
    assert result["matched_requests"] == 3
    assert result["overlapping_windows"] == 2
    assert {row["link"] for row in result["evidence"]} == {"card_fp", "ship_to"}
    assert "demo-card" not in str(result) and "demo-address" not in str(result)


def test_sliding_window_does_not_merge_long_chains_and_caps_evidence():
    assert correlate([event(n, n * 60) for n in range(10)])["matched_requests"] == 0
    result = correlate([event(n, n) for n in range(100)])
    assert result["matched_requests"] == 100
    assert len(result["evidence"]) == 20
