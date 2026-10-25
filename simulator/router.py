"""POST /sim/run/{scenario}, GET /sim/runs, GET /sim/metrics. Included by gateway/app.py."""

import os
import threading
import time
from collections import OrderedDict

import httpx
from fastapi import APIRouter, HTTPException, Request

from gateway import db
from gateway.latency import is_resolution
from simulator.correlation import correlate
from simulator.scenarios import SCENARIOS, Run

router = APIRouter()
_runs: "OrderedDict[str, Run]" = OrderedDict()
_lock = threading.Lock()

BAD = {"spoof", "scalper", "hijacked", "slow_low"}
VELOCITY_RULES = {"burst", "heavy_burst", "card_testing", "tiny_orders"}


def _self_url(request: Request) -> str:
    """The simulator talks to this gateway over loopback HTTP, signing exactly what it sends."""
    if url := os.environ.get("SIM_GATEWAY_URL"):
        return url.rstrip("/")
    return f"http://127.0.0.1:{request.scope['server'][1]}"


def _execute(run: Run, base: str) -> None:
    try:
        with httpx.Client(timeout=15) as http:
            SCENARIOS[run.scenario](run, base, http)
        run.status = "done"
    except Exception as e:  # surface failures on the dashboard instead of a silent thread death
        run.log(f"ERROR: {e!r}")
        run.status = "error"
    run.finished = time.time()


@router.post("/sim/run/{scenario}", status_code=202)
def run_scenario(scenario: str, request: Request):
    if scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario; choose one of {sorted(SCENARIOS)}")
    with _lock:
        if any(r.status == "running" for r in _runs.values()):
            raise HTTPException(409, "a scenario is already running")
        run = Run(scenario)
        _runs[run.id] = run
        while len(_runs) > 20:
            _runs.popitem(last=False)
    threading.Thread(target=_execute, args=(run, _self_url(request)), daemon=True, name=f"sim-{scenario}").start()
    return run.as_dict()


@router.get("/sim/runs")
def list_runs():
    """Newest first."""
    with _lock:
        return [r.as_dict() for r in reversed(_runs.values())]


def metrics(events: list[dict]) -> dict:
    """Precision/recall from simulator ground truth. A bad request is caught if the gateway's first decision
    was challenge or block; a good one is a false alarm if it was. Challenge resolutions are not counted."""
    decisions = [e for e in events if e.get("scenario") and not is_resolution(e)]
    per = {}
    for e in decisions:
        s = per.setdefault(e["scenario"], {"n": 0, "allow": 0, "challenge": 0, "block": 0})
        s["n"] += 1
        s[e["decision"]] = s.get(e["decision"], 0) + 1
    flagged = lambda e: e["decision"] in ("challenge", "block")  # noqa: E731
    tp = sum(1 for e in decisions if e["scenario"] in BAD and flagged(e))
    fn = sum(1 for e in decisions if e["scenario"] in BAD and not flagged(e))
    fp = sum(1 for e in decisions if e["scenario"] == "good" and flagged(e))
    tn = sum(1 for e in decisions if e["scenario"] == "good" and not flagged(e))

    slow = [e for e in decisions if e["scenario"] == "slow_low"]
    return {
        "per_scenario": per,
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "false_alarm_rate": round(fp / (fp + tn), 3) if fp + tn else None,
        "timing_correlation": correlate(events),
        "slow_low": {
            "n": len(slow),
            "velocity_fired": sum(1 for e in slow if VELOCITY_RULES.intersection(e["reasons"])),
            "cluster_fired": sum(1 for e in slow if "cluster" in e["reasons"]),
            "caught": sum(1 for e in slow if flagged(e)),
        },
    }


@router.get("/sim/metrics")
def get_metrics():
    return metrics(db.all_events())
