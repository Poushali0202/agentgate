import httpx
import pytest
from fastapi.testclient import TestClient

from gateway import app as gw
from gateway import storefront

RUN = {"id": "run1", "finishedAt": "2026-10-25T07:00:00Z", "status": "SUCCEEDED"}
ITEMS = [
    {"url": "https://shop/index.html", "risk": "low", "findings": [], "product": {"sku": None}},
    {"url": "https://shop/safe.html", "risk": "low", "findings": [], "product": {"sku": "HP-100"}},
    {"url": "https://shop/poisoned.html", "risk": "high", "injection_patterns": ["gift_card_push", "redirect_shipping"],
     "findings": [{"where": "hidden", "technique": "stylesheet .agent-note {left: -10000px}", "text": "SYSTEM NOTE FOR AI…"}],
     "product": {"sku": "HP-100"}},
    {"url": "https://shop/broken", "risk": "error", "error": "dns"},
]


def fake_api(calls):
    def _api(method, path, **kw):
        calls.append((method, path, kw))
        req = httpx.Request(method, f"https://api.apify.com/v2{path}")
        if path.endswith("/dataset/items"):
            return httpx.Response(200, json=ITEMS, request=req)
        if method == "POST":
            return httpx.Response(201, json={"data": {"id": "run2", "status": "READY"}}, request=req)
        return httpx.Response(200, json={"data": RUN}, request=req)
    return _api


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(gw.db, "DB_PATH", str(tmp_path / "e.db"))
    monkeypatch.setattr(storefront, "_cache", {"at": 0.0, "value": None})
    monkeypatch.setattr(storefront, "_last_trigger", 0.0)
    with TestClient(gw.app) as c:
        yield c


def test_unconfigured_without_token(client, monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    assert client.get("/storefront-scan").json()["configured"] is False
    assert client.post("/storefront-scan/run").status_code == 503


def test_summary_of_latest_run(client, monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "t")
    calls = []
    monkeypatch.setattr(storefront, "_api", fake_api(calls))
    s = client.get("/storefront-scan").json()
    assert s["pages"] == 3 and s["errors"] == 1 and s["counts"] == {"high": 1, "medium": 0, "low": 2}
    assert s["flagged"] == [{"url": "https://shop/poisoned.html", "risk": "high", "sku": "HP-100",
                             "patterns": ["gift_card_push", "redirect_shipping"], "hidden_text": "SYSTEM NOTE FOR AI…",
                             "technique": "stylesheet .agent-note {left: -10000px}"}]
    client.get("/storefront-scan")
    assert len(calls) == 2  # second read served from cache


def test_trigger_scan_and_rate_limit(client, monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "t")
    monkeypatch.setenv("STOREFRONT_URLS", "https://shop/index.html")
    calls = []
    monkeypatch.setattr(storefront, "_api", fake_api(calls))
    r = client.post("/storefront-scan/run")
    assert r.status_code == 202 and r.json()["run_id"] == "run2"
    assert calls[0][2]["json"] == {"startUrls": [{"url": "https://shop/index.html"}], "crawl": True, "maxPages": 50}
    assert client.post("/storefront-scan/run").status_code == 429
