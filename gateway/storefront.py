"""Storefront guard: the merchant's own pages, scanned on Apify for instructions hidden for AI agents.

GET  /storefront-scan      summary of the scanner Actor's latest successful run (pulled from Apify, cached 30 s)
POST /storefront-scan/run  start a new crawl of STOREFRONT_URLS

Pull, not webhook: the gateway usually runs on a laptop that Apify can't reach. An hourly Apify Schedule keeps
the latest run fresh. Needs APIFY_API_TOKEN; without it the endpoint reports itself unconfigured.
"""

import os
import time

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()

API = "https://api.apify.com/v2"
DEFAULT_STOREFRONT = "https://raw.githubusercontent.com/Poushali0202/agentgate/main/trap-page/index.html"
CACHE_S = 30
MIN_RUN_GAP_S = 60

_cache: dict = {"at": 0.0, "value": None}
_last_trigger = 0.0


def _config() -> tuple[str | None, str, list[str]]:
    actor = os.environ.get("APIFY_SCANNER_ACTOR", "tangy_taste_poy~agent-prompt-injection-scanner")
    urls = [u.strip() for u in os.environ.get("STOREFRONT_URLS", DEFAULT_STOREFRONT).split(",") if u.strip()]
    return os.environ.get("APIFY_API_TOKEN"), actor, urls


def _api(method: str, path: str, **kw) -> httpx.Response:
    token, _, _ = _config()
    return httpx.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=20, **kw)


def summarize(run: dict, items: list[dict]) -> dict:
    pages = [i for i in items if i.get("risk") != "error"]
    flagged = [i for i in pages if i.get("risk") in ("high", "medium")]
    return {
        "configured": True,
        "run": {"id": run.get("id"), "finished_at": run.get("finishedAt"), "status": run.get("status")},
        "pages": len(pages),
        "errors": len(items) - len(pages),
        "counts": {r: sum(1 for i in pages if i.get("risk") == r) for r in ("high", "medium", "low")},
        "flagged": [{
            "url": i["url"],
            "risk": i["risk"],
            "sku": (i.get("product") or {}).get("sku"),
            "patterns": i.get("injection_patterns", []),
            "hidden_text": next((f["text"] for f in i.get("findings", []) if f.get("where") != "visible"), None),
            "technique": next((f["technique"] for f in i.get("findings", []) if f.get("where") != "visible"), None),
        } for i in flagged],
    }


@router.get("/storefront-scan")
def storefront_scan():
    token, actor, _ = _config()
    if not token:
        return {"configured": False, "detail": "set APIFY_API_TOKEN to show the storefront scan"}
    if _cache["value"] and time.time() - _cache["at"] < CACHE_S:
        return _cache["value"]
    try:
        run = _api("GET", f"/acts/{actor}/runs/last", params={"status": "SUCCEEDED"})
        if run.status_code == 404:
            return {"configured": True, "run": None, "pages": 0, "counts": {}, "flagged": [], "detail": "no successful scan yet"}
        run.raise_for_status()
        items = _api("GET", f"/acts/{actor}/runs/last/dataset/items", params={"status": "SUCCEEDED", "clean": "true"})
        items.raise_for_status()
        value = summarize(run.json()["data"], items.json())
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Apify unreachable: {e}")
    _cache.update(at=time.time(), value=value)
    return value


@router.post("/storefront-scan/run", status_code=202)
def run_storefront_scan():
    global _last_trigger
    token, actor, urls = _config()
    if not token:
        raise HTTPException(503, "APIFY_API_TOKEN not configured")
    if time.time() - _last_trigger < MIN_RUN_GAP_S:
        raise HTTPException(429, "a scan was started less than a minute ago")
    try:
        r = _api("POST", f"/acts/{actor}/runs", json={"startUrls": [{"url": u} for u in urls], "crawl": True, "maxPages": 50})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Apify unreachable: {e}")
    _last_trigger = time.time()
    _cache["at"] = 0.0
    run = r.json()["data"]
    return {"run_id": run["id"], "status": run["status"], "urls": urls}
