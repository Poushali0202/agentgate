# AgentGate agents

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Two Fetch.ai uAgents, both on Agentverse, both speaking the Agent Chat Protocol, both reachable in ASI:One.

| Agent | Name | Address | Role |
|---|---|---|---|
| Shopper | `agentgate-shopper` | _printed on startup; set `SHOPPER_SEED` for a stable one_ | Buys on your behalf through the gateway. Signs every request with its own Ed25519 key. |
| Guardian | `agentgate-guardian` | _printed on startup; set `GUARDIAN_SEED` for a stable one_ | Your trusted channel. Receives the store's challenges and asks you to approve or deny. |

The whole shopping flow happens inside an ASI:One conversation. The merchant dashboard at the gateway is the store's ops console, not the shopper's UI.

## Why two agents

A signature proves *who* the agent is, not that it is behaving. When the gateway finds a purchase unusual it does not ask the Shopper — a hijacked Shopper would just say yes. It POSTs the challenge to the **Guardian**, which holds a token the Shopper never has, and the Guardian asks the human. Deny → the store blocks it.

## Run

From the repo root, with the gateway already running on `:8000`:

```bash
cp .env.example .env         # fill GUARDIAN_TOKEN (same value as the gateway), seeds, ANTHROPIC_API_KEY
python -m agents.guardian    # webhook on :8001, agent on :8003
python -m agents.shopper     # agent on :8002
```

Each prints an Agentverse inspector link on first start. Open it, connect the mailbox, and the agent becomes discoverable in ASI:One. Keep both terminals open during judging — the agents need internet for Agentverse; the gateway does not.

## Talk to them in ASI:One

1. Message the **Guardian** once ("hi") so it knows who to ask.
2. Message the **Shopper**: `buy me wireless headphones under $200` → verified, allowed.
3. Tell the Shopper `hijack on` (the labelled demo switch — no restart needed; `HIJACK=1` in the env does the same at startup), then `buy me headphones` → it follows the trap page instead (gift cards, new address) → the gateway challenges → the **Guardian** shows you the card → reply `deny` → blocked. `hijack off` restores normal shopping.

## Environment

| Variable | Default | Used by |
|---|---|---|
| `GATEWAY_URL` | `http://localhost:8000` | both |
| `GUARDIAN_TOKEN` | — | Guardian. Must equal the gateway's. |
| `GUARDIAN_WEBHOOK_PORT` | `8001` | Guardian. Must match the gateway's `CHALLENGE_WEBHOOK_URL`. |
| `SHOPPER_SEED`, `GUARDIAN_SEED` | dev seeds | stable agent addresses |
| `ANTHROPIC_API_KEY` | — | Shopper intent extraction (Claude Opus 5.5). Falls back to a regex parser if unset. |
| `AGENTVERSE_API_KEY` | — | optional, lets uAgents register the mailbox without the inspector click |
| `TRAP_PAGE_URL` | — | Shopper hijack mode: the page with the hidden instruction |
| `PRODUCTS_JSON` | — | Shopper: Apify product output (file or URL). Falls back to `/store/products`. |
| `HIJACK` | `0` | Shopper. `1` = demo-only compromise. Say so in the pitch. |
| `GUARDIAN_STRICT` | `0` | Guardian. `1` = show only the owner's own orders. Default: any order the Shopper placed for an ASI:One user; simulator and test traffic is never shown. |

**The Shopper never holds `GUARDIAN_TOKEN`.** Even if both agents share one `.env`, the Shopper drops the token at startup and logs that it did. Only the Guardian can approve or deny.

## Rehearse without ASI:One

`agents/rehearse.py` drives the real Shopper and Guardian handler code against a gateway, without Agentverse: say hi to the Guardian → normal purchase (allow) → simulator swarm (not shown to the human) → `HIJACK` purchase from the trap page (challenge) → Guardian card → "deny" → blocked.

```bash
CHALLENGE_WEBHOOK_URL=http://127.0.0.1:8011/challenge .venv/bin/uvicorn gateway.app:app --port 8010 &
GATEWAY_URL=http://localhost:8010 .venv/bin/python -m agents.rehearse
```

In the live demo, **make one normal purchase before the hijack.** The drift rules need a completed purchase as a baseline.

## What is real and what is staged

- Signing, verification, scoring, the challenge, the Guardian token check and the block are real.
- The hijack is a labelled switch (`HIJACK=1`). Claude would usually refuse the injected instruction, so the switch forces it. The detection side is untouched.
- Interactive Cards: the challenge is delivered as a text card with `approve` / `deny` replies. Swap in the ASI1 Interactive Card format in `agents/guardian/agent.py::card_text` once its schema is confirmed.
