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

## Status

Day one. Repo initialised; build in progress. See `AGENTGATE_PLAN.md` once it lands for the build plan and ownership.

## Team

Four people. Names and roles to be added.

## Honest disclosures

- Training and test traffic is synthetic, produced by our simulator.
- The agent key directory is a mock standing in for Visa's; the verifier is spec-shaped and swaps to a real directory by configuration.
- Scoring is rule-first. A learned model, if present, is a demonstration that the features generalise, not the decision authority.
- The hijacked-agent scenario is triggered by a clearly labelled demo switch.
- Latency figures are measured on one laptop.

## License

MIT
