from simulator.router import metrics
from simulator.scenarios import SCENARIOS, home


def ev(scenario, decision, reasons=("base",)):
    return {"scenario": scenario, "decision": decision, "reasons": list(reasons)}


def test_precision_recall_counts_first_decision_only():
    events = [
        ev("good", "allow"), ev("good", "allow"), ev("good", "challenge"),
        ev("good", "allow", ["human_approved", "new_address"]),          # resolution: not counted
        ev("scalper", "block"), ev("scalper", "allow"),
        ev("hijacked", "challenge"), ev("hijacked", "block", ["human_denied"]),
        ev(None, "allow"),                                               # live traffic: no ground truth
    ]
    m = metrics(events)
    assert m["confusion"] == {"tp": 2, "fn": 1, "fp": 1, "tn": 2}
    assert m["precision"] == 0.667 and m["recall"] == 0.667
    assert m["per_scenario"]["good"]["n"] == 3


def test_slow_low_panel():
    events = [ev("slow_low", "allow", ["young_key", "base"])] * 2 + [ev("slow_low", "challenge", ["cluster", "young_key"])] * 4
    assert metrics(events)["slow_low"] == {"n": 6, "velocity_fired": 0, "cluster_fired": 4, "caught": 4}


def test_scenarios_and_unique_homes():
    assert set(SCENARIOS) == {"good", "spoof", "scalper", "hijacked", "slow_low"}
    assert home("c-a") != home("c-b")
