# AgentGate

**Visa built the ID check for AI agents. We built the bouncer.**

AgentGate is a merchant-side firewall for AI shopping agents. It sits in front of a checkout API and, on every request, verifies *who* the agent is and scores *how* it is behaving, then decides in real time: **allow**, **challenge** the human behind the agent, or **block**. Every decision comes with plain-English reasons a merchant can read.

Built at [Cal Hacks 13.0](https://calhacks.io), October 24–26 2026, San Francisco.

## The problem

Merchants are about to see a flood of AI agents buying on behalf of real people. Today they classify bots by user-agent string and IP address, both trivially spoofed. So they either block every agent and lose real sales, or let them all in and eat scalping, card testing and inventory hoarding.

## How it works

| Layer | What it checks | How |
|---|---|---|
| **Identity** | Is this agent who it claims to be? | Visa Trusted Agent Protocol: RFC 9421 HTTP Message Signatures with Ed25519 keys. The `tag` says whether the agent may only browse or may also pay. Replays and tampering are rejected. |
| **Behaviour** | Is a verified agent acting normally? | Rule-based risk score over velocity, card testing, cart patterns and drift from the consumer's own history. Includes a cluster rule that links many agent keys sharing one card or address. |
| **Decision** | What happens next? | `allow` / `challenge` / `block`. Unusual-but-possibly-legitimate purchases go to the consumer's **Guardian agent**, which asks the human to approve or deny — so a hijacked shopping agent cannot approve its own purchase. |

A signature proves who the agent is. It does not prove the agent is behaving. AgentGate checks both.

## Components

```
gateway/      FastAPI gateway: signature verification, scoring, policy, event log, mock store, key directory
agents/       Fetch.ai uAgents on Agentverse: the Shopper (buys on your behalf) and the Guardian (confirms with you)
simulator/    Scripted traffic: good agents, spoofed agents, a scalper swarm, a hijacked verified agent, a slow-and-low scalper
dashboard/    Live decision feed, security test matrix, precision/recall, threshold sliders
apify/        Product data and the prompt-injection trap page, fetched as real scraped content
investigator/ Claude with one read-only tool over the decision log: "why was the last block flagged?"
```

## Stack

Python · FastAPI · `cryptography` (Ed25519) · Fetch.ai uAgents + Agentverse + ASI:One · Anthropic Claude · Apify · SQLite

## Honest disclosures

- Training and test traffic is synthetic, produced by our simulator.
- The agent key directory is a mock standing in for Visa's; the verifier is spec-shaped and swaps to a real directory by configuration.
- Scoring is rule-first. A learned model, if present, is a demonstration that the features generalise, not the decision authority.
- The hijacked-agent scenario is triggered by a clearly labelled demo switch.
- Latency figures are measured on one laptop.

## License

MIT

## Agents

Both agents are on Agentverse, speak the Agent Chat Protocol and can be found in ASI:One. See [agents/README.md](agents/README.md) for how to run them.

| Agent | Name | Address |
|---|---|---|
| Shopper | `agentgate-shopper` | `agent1qgllwhxush0wyfdfa45pklq2pjax7rqjsqexa8j0ynmp7yzmcseu59qdp69` |
| Guardian | `agentgate-guardian` | `agent1qf46y538dkcd4edmwh4cc2kzf3x8xgay669dzj77ym2a9zqv8dcm6s3xzqv` |

The shopper's whole workflow happens inside an ASI:One conversation. The merchant dashboard at the gateway is the store's ops console, not the shopper's UI.

## Running the gateway

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env            # set GUARDIAN_TOKEN (same value as the Guardian); the gateway reads .env itself
.venv/bin/uvicorn gateway.app:app --port 8000
.venv/bin/python -m pytest -q gateway/tests
```

## Plugging into the gateway

**Signing requests** (shopper agent, simulator). Use `gateway/signer.py`. It needs only `cryptography`, so agents can copy the file.

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gateway.signer import sign_request, public_jwk, PAYER_TAG, BROWSER_TAG

key = Ed25519PrivateKey.generate()
httpx.post("http://localhost:8000/directory/keys", json=public_jwk(key.public_key(), "shopper-1"))  # register once; 409 if that kid has a different key

body = json.dumps({"consumer_id": "c-1", "card_fp": "card_abc", "ship_to": "1 Main St",
                   "cart": [{"sku": "HP-100", "qty": 1}]}).encode()
headers = sign_request(key, "shopper-1", "POST", "http://localhost:8000/checkout", body, tag=PAYER_TAG)
httpx.post("http://localhost:8000/checkout", content=body, headers={**headers, "Content-Type": "application/json"})
```

- `GET /browse?consumer_id=...&q=...` is signed with `BROWSER_TAG` or `PAYER_TAG`. `POST /checkout` must use `PAYER_TAG`.
- The checkout body gives `cart` as `[{sku, qty}]`, with `qty` from 1 to 100. Bad bodies get a 400 without using up the signature's nonce. Prices come from the store, never from the client. `ship_to` is a raw address; the gateway hashes it.
- Responses: `allow` → 200 + event; `block` → 403 + event; `challenge` → 202 + `{"decision": "challenge", "challenge_id"}` only.
- Simulator ground truth goes in the header `X-AgentGate-Scenario: good|spoof|scalper|hijacked|slow_low`. Scoring never sees it.

**Simulator keys.** Register in-process with `from gateway.app import directory; directory.register(keyid, public_key)`. These keys are not persisted.

**Scoring and policy** (`gateway/scoring.py`, `gateway/policy.py`). The gateway imports `score(event) -> (risk_score, reasons)` and `decide(identity, risk_score, reasons) -> decision`. Until they exist, placeholders keep it running. `decide` is called only for `verified` requests; the gateway itself blocks `unverified` and `invalid` ones. If `policy.py` exposes `router`, and `simulator/__init__.py` exposes `router`, `app.py` includes them automatically.

History helpers for scoring, in `gateway/db.py`:
- `events_since(seconds)`
- `consumer_events(consumer_id)`
- `last_browse(keyid, consumer_id)`, for the `too_fast` rule
- `clear()`

Also available: `gateway.app.directory.first_seen(keyid)` for `young_key`, and `gateway.store.get_product(sku)` for categories and `limited`.

**Challenges.** On `challenge`, the gateway POSTs the full event to `CHALLENGE_WEBHOOK_URL` (3 tries with backoff), with `Authorization: Bearer $GUARDIAN_TOKEN`. Guardian endpoints need the same header. The shopper never has the token, so a hijacked shopper can't approve its own purchase. Without `GUARDIAN_TOKEN` set, resolving returns 503.

| Who | Call | Purpose |
|---|---|---|
| Guardian (token) | `POST /challenge/{id}/resolve {"approved": bool}` | Answer the challenge. 401 without the token, 404 if the id is unknown, 409 if it is already resolved. |
| Guardian (token) | `GET /challenges?status=pending` | Fallback if the webhook can't reach you: poll for open challenges. Each row includes the full event and `webhook` delivery status. |
| Shopper | `GET /challenge/{id}` | Poll the outcome: `{"status": "pending" \| "allow" \| "block", "outcome": "human_approved" \| "human_denied" \| "guardian_timeout" \| null}`. Risk reasons are never shown to the shopper. |

Resolving logs a second event with the same `challenge_id` and decision `allow` or `block`, whose first reason is `human_approved` or `human_denied`. A challenge nobody answers within `CHALLENGE_TTL_S` (default 900 s) is blocked with `guardian_timeout`. So a challenge shows up as two events in `/events`; count them per `challenge_id`.

**Ops.**
- `GET /stats` gives decision counts and p50/p95/p99 `latency_ms` (verify → score → decide; resolutions excluded). Run `python -m gateway.latency` for the same numbers from the command line.
- `python -m gateway.cli_shopper --sku HP-100 [--unsigned] [--scenario good]` is a signed shopper you can run from the terminal, for testing without the Fetch.ai agent.
