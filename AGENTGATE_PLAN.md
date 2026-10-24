# AgentGate — Build Plan

Written Sat 2026-10-24 09:40 PDT. Four people: A, B, C, D. Each person reads only their own section plus "Shared contract" and "Gates".

| Fact | Value |
|---|---|
| Feature freeze | Sat 20:00 |
| Submit target | Sun 08:30 |
| Hard deadline | Sun 09:00 (Devpost) |
| Judging | Sun 10:30–12:30, at table, all four present |
| Pitch opener | "Visa built the ID check. We built the bouncer." |

---

## Shared contract (everyone reads, nobody changes without telling all four)

### Repo layout and file ownership

```
gateway/app.py          A   FastAPI app, routes, store, key directory
gateway/verify.py       A   RFC 9421-style Ed25519 verification
gateway/db.py           A   SQLite event log
gateway/scoring.py      B   score(event) -> (risk_score, reasons[3])
gateway/policy.py       B   decide(identity, risk_score, reasons) -> decision; thresholds
simulator/              B   scenario scripts
dashboard/index.html    B   live feed, counters, panels, sliders
model/                  B   logreg / lightgbm
agents/shopper/         C   uAgent, chat protocol, Claude intent, signed requests, card
agents/guardian/        C   uAgent, receives challenge webhook, shows card, resolves
apify/                  D   product Actor, swarm Actor (stretch)
trap-page/              D   GitHub Pages page with hidden injection
investigator/           D   Claude + one read-only tool over /events
devpost/                D   write-ups, pitch script, video
README.md               A   setup, architecture, signature flow, agent addresses, badges
```

### Event record — one JSON object per decision

```json
{
  "request_id": "uuid",
  "ts": "2026-10-24T14:03:11.204Z",
  "agent_keyid": "string",
  "tag": "agent-browser-auth | agent-payer-auth",
  "identity": "verified | unverified | invalid",
  "consumer_id": "string",
  "card_fp": "string",
  "ship_to": "string (address hash)",
  "cart": [{"sku": "string", "qty": 1, "price": 49.99}],
  "risk_score": 0,
  "reasons": ["string", "string", "string"],
  "decision": "allow | challenge | block",
  "challenge_id": "uuid | null",
  "latency_ms": 0.0,
  "scenario": "good | spoof | scalper | hijacked | slow_low"
}
```

`scenario` is simulator ground truth. `scoring.py` and `policy.py` never read it.

### Gateway endpoints

| Method | Path | Owner | Purpose |
|---|---|---|---|
| GET | `/.well-known/http-message-signatures-directory` | A | JWKS of agent public keys (mock directory) |
| GET | `/store/products` | A | ~20 SKUs, two flagged `limited: true` |
| GET | `/browse` | A | Signed; tag `agent-browser-auth` or `agent-payer-auth` |
| POST | `/checkout` | A | Signed; tag must be `agent-payer-auth`; returns event |
| POST | `/challenge/{id}/resolve` | A | Body `{"approved": true\|false}`; on true, checkout completes |
| GET | `/events?limit=N` | A | Recent events, newest first |
| GET | `/policy` · POST `/policy` | B | Read / set thresholds `{"challenge_at": 30, "block_at": 70}` |
| GET | `/security-tests` | A | Five cases with pass/fail |
| POST | `/sim/run/{scenario}` | B | Runs one scenario |
| GET | `/` | B | Dashboard |

**Challenge webhook (A → C):** when a decision is `challenge`, the gateway POSTs the full event to `CHALLENGE_WEBHOOK_URL` (env var). The Guardian agent listens there. Shopper agent is *not* told the challenge details — it only gets `{"decision": "challenge", "challenge_id": ...}`.

### Decision policy (`policy.py`)

Evaluated top to bottom; first match wins.

| Condition | Decision |
|---|---|
| `identity == invalid` or replayed nonce | block |
| `identity == unverified` on `/checkout` | block (403, "unsigned checkout not accepted") |
| verified and any top reason in `{new_address, new_category, big_basket}` | **challenge** (regardless of score) |
| verified, `risk_score < challenge_at` | allow |
| verified, `challenge_at <= risk_score < block_at` | challenge |
| verified, `risk_score >= block_at` | block |

Defaults: `challenge_at = 30`, `block_at = 70`.

### Scoring rules (`scoring.py`)

Velocity rules are keyed on `(agent_keyid, consumer_id)`, **not** `agent_keyid` alone. Cluster rule looks across keys.

| Rule id | Condition | Points |
|---|---|---|
| base | always | 5 |
| burst | >3 checkouts by (key, consumer) in 10 min | +20 |
| heavy_burst | >10 checkouts by (key, consumer) in 10 min | +40 |
| card_testing | ≥3 distinct `card_fp` by (key, consumer) in 10 min | +30 |
| tiny_orders | >50% of (key, consumer) orders under $5 | +20 |
| hoarding | qty ≥3 on a `limited` SKU | +25 |
| too_fast | browse → checkout under 3 s | +15 |
| new_address | `ship_to` never seen for this `consumer_id` | +25 |
| big_basket | order > 5× this consumer's average | +30 |
| new_category | category never bought by this consumer | +25 |
| cluster | ≥3 distinct keys sharing one `card_fp` or `ship_to` in 10 min | +35 |
| young_key | key first seen < 5 min ago | +10 |

Score capped at 100. `reasons` = the three highest-point rules that fired, as rule ids.

### Scenarios (`simulator/`)

| Scenario | What it sends | Expected decision |
|---|---|---|
| good | one verified agent buys headphones | allow |
| spoof | unsigned checkout, then a replayed signature | block, block |
| scalper | 200 keys hit a limited SKU in 10 s | block (burst, hoarding, cluster) |
| hijacked | verified agent, gift cards, new address | **challenge** → human denies → block |
| slow_low | 6 keys, one checkout each every 2 min, same `card_fp` | velocity rules miss; cluster catches |

---

## Gates (everyone)

| Time | Gate | Passes when |
|---|---|---|
| Sat 12:00 | GATE 1 | One signed request from the shopper agent → gateway → decision → appears on dashboard. Nothing below starts until this passes. |
| Sat 16:00 | GATE 2 | All five scenarios run from one button each. `hijacked` shows the card and ends deny → block. `slow_low` panel shows "rules missed / cluster caught". |
| Sat 17:00 | STRETCH GATE | Stretch items may start only if Gate 2 passed *and* the Guardian answers in ASI:One. |
| Sat 20:00 | FREEZE | Nothing new. Any stretch item not working is removed, not fixed. |
| Sun 08:30 | SUBMITTED | Devpost: four members, repo, video, every track opted in. |

Sleep: A and B sleep 00:30–05:00. C and D sleep 02:30–06:30. C's agent processes stay running unattended 02:30–05:00: plugged in, sleep disabled, terminal open. A sets a 05:00 alarm.

---

## Person A — Gateway & Security

**Owns:** `gateway/app.py`, `gateway/verify.py`, `gateway/db.py`, `README.md`, `docker-compose.yml` (stretch).

**Tasks, in order:**

1. [ ] `verify.py`: parse `Signature-Input` and `Signature`; check tag vs route; check `created`/`expires`; reject seen nonce (in-memory dict with TTL sweep); look up `keyid` in directory; verify Ed25519 over the signature base. Time-box an RFC 9421 library to 90 min, then hand-build.
2. [ ] Four tests pass: `valid`, `wrong_tag`, `expired`, `replayed`.
3. [ ] Unverified `/checkout` returns 403 with reason `unsigned checkout not accepted`.
4. [ ] `POST /challenge/{id}/resolve`. Store pending challenges in memory keyed by id.
5. [ ] Challenge webhook: on `decision == challenge`, POST the event to `CHALLENGE_WEBHOOK_URL`. Return only `{"decision": "challenge", "challenge_id": ...}` to the caller.
6. [ ] `tampered` test (fifth case: body modified after signing). `GET /security-tests` returns all five with pass/fail.
7. [ ] `latency_ms` measured with `time.perf_counter()` around verify → score → decide, written to every event.
8. [ ] Include B's policy router and B's `/sim` router in `app.py` (one line each; B supplies the files).
9. [ ] **Stretch (after 17:00 gate, only if Gate 2 passed and Guardian answers):** x402 on the allow path — the agent pays in USDC before the order completes. Remove entirely if not working by 19:30. Otherwise: `docker-compose.yml` for gateway only.
10. [ ] After freeze: compute p95 `latency_ms` from the SQLite log. Record the number.
11. [ ] Sun 05:00–08:30: README complete; repo public; `innovationlab` and `hackathon` badges; agent names and addresses from C.

**Done when:** `/security-tests` shows 5/5; a measured p95 exists; webhook fires on every challenge; README is complete.

**Needs:** C's agent public keys for the directory (now). B's `policy.py` and `simulator/` routers (by 14:00).
**Gives:** `/challenge/{id}/resolve` + webhook to C by 14:00. `/security-tests` to B's dashboard by 17:00.

---

## Person B — Scoring, Simulator & Dashboard

**Owns:** `gateway/scoring.py`, `gateway/policy.py`, `simulator/`, `dashboard/index.html`, `model/`.

**Tasks, in order:**

1. [ ] `scoring.py`: implement the rule table. Velocity keyed on `(agent_keyid, consumer_id)`. Returns `(risk_score, reasons[3])`.
2. [ ] `policy.py`: implement the decision table exactly as written. Thresholds read from a module-level dict; `GET /policy` and `POST /policy` as a FastAPI router A includes.
3. [ ] `dashboard/index.html`: polls `/events?limit=100` every second. Live feed with coloured allow / challenge / block, score, reasons, `latency_ms`. Counters by decision.
4. [ ] `simulator/`: scenarios `good`, `spoof`, `scalper`, `hijacked`, each a function; `POST /sim/run/{scenario}` router. Each simulated agent has its own Ed25519 key pair; register them in A's directory.
5. [ ] Cluster rule working: `scalper` fires `cluster`.
6. [ ] `hijacked` scenario ends in `challenge`, not block (policy row 3).
7. [ ] `slow_low` scenario. Dashboard panel: for `slow_low` events, show which rules fired; label "velocity rules: missed / cluster: caught".
8. [ ] Precision/recall panel from `scenario` ground truth. Bad scenario is caught if decision is challenge or block; good scenario is a false alarm if decision is challenge or block.
9. [ ] Two sliders on the dashboard bound to `POST /policy` (`challenge_at`, `block_at`).
10. [ ] `model/logreg.py`: train on simulator rows with `slow_low` held out; reasons from top-3 coefficients. Show the model's score beside the rule score on the feed. Rules stay authoritative.
11. [ ] **Stretch (only if task 10 done by 18:00):** LightGBM + SHAP in place of logreg.
12. [ ] After freeze: measure P/R and `slow_low` miss-rate. Record only measured numbers.
13. [ ] Sun 05:00: run all five scenarios from a clean start; screenshot dashboard during `scalper` for the Devpost image.

**Done when:** five scenarios from buttons; `hijacked` → challenge; `slow_low` panel shows miss → catch; sliders move decisions live; measured P/R and holdout numbers exist.

**Needs:** C's hijack switch working by 14:30 so `hijacked` runs end to end. A's `/security-tests` by 17:00 to render.
**Gives:** `policy.py` and `simulator/` routers to A by 14:00. Scenario buttons to D by 16:00.

---

## Person C — Fetch.ai Agents

**Owns:** `agents/shopper/`, `agents/guardian/`.

Fetch.ai eligibility (all required): at least one agent on Agentverse; Agent Chat Protocol implemented; discoverable through ASI:One; primary workflow inside an ASI:One conversation. The merchant dashboard is the merchant's ops console, not the shopper UI — say so in README and pitch.

**Tasks, in order:**

1. [ ] Shopper uAgent: chat protocol, mailbox, registered on Agentverse. ASI:One finds it and it replies. **Do before anything else.**
2. [ ] Claude turns the user message into intent `{"item": str, "max_price": float}`. Purchase logic in plain Python, not Claude.
3. [ ] Tools: product search (D's Apify output), signed `GET /browse` then signed `POST /checkout` with the shopper's Ed25519 key. Give A the public key for the directory.
4. [ ] On `decision == allow`: tell the user the order went through. On `block`: relay the reasons. On `challenge`: tell the user "waiting for your Guardian to confirm".
5. [ ] Hijack switch: env var `HIJACK=1` makes the agent follow the hidden instruction on D's trap page (buy gift cards, ship to a new address). Clearly labelled. Tell B when it works.
6. [ ] Guardian uAgent: hello-world, chat protocol, mailbox, on Agentverse. ASI:One finds it.
7. [ ] Guardian HTTP listener on `CHALLENGE_WEBHOOK_URL` (local port; gateway is local). On a challenge event: send the user an ASI1 Interactive Card with item, amount, top reasons, Approve / Deny. Text fallback: ask the user to reply `approve` or `deny`.
8. [ ] On Approve → `POST /challenge/{id}/resolve {"approved": true}`. On Deny → `{"approved": false}`.
9. [ ] Both agents listed on Agentverse. Names and addresses to A for README.
10. [ ] After freeze: keep-alive and mailbox reconnect. Test the full `hijacked` flow from a second phone on a hotspot.
11. [ ] 00:30–02:30: run the agents while D records the video.
12. [ ] Sun 06:30–08:30: confirm both agents live; register the project through the Cal Hacks ASI:One submission agent.

**Done when:** `hijacked` flow shows the card in ASI:One via the Guardian, user denies, gateway blocks; both agents discoverable; submission agent confirms.

**Needs:** A's `/challenge/{id}/resolve` and webhook by 14:00. D's product data by 12:00. D's trap page URL by 12:00.
**Gives:** public keys to A now. Hijack switch to B by 14:30. Card screenshots to D by 20:00. Agent names/addresses to A by 20:00.

**Fallback if Guardian is cut:** shopper agent shows the card itself (task 7 logic inside the shopper). Scene 4 still shows the card.

---

## Person D — Apify, Investigator & Demo

**Owns:** `apify/`, `trap-page/`, `investigator/`, `devpost/`. Keeps the Notability log all day.

**Tasks, in order:**

1. [ ] Open the Notability log now. Sketch the architecture, record decisions as they happen. This is a prize entry on its own.
2. [ ] Apify Actor returns products (name, price, sku, category) as JSON. Source: a public test shop, or the mock store via a tunnel. Give C the output location by 12:00.
3. [ ] Trap page on GitHub Pages: a product page with hidden text instructing the agent to buy gift cards and ship to a new address. Fetched through Apify so the injection arrives as real scraped content. URL to C by 12:00.
4. [ ] Investigator: Claude with one read-only tool `get_events(limit)` over `/events`. Input "why was the last block flagged?" → short case summary. Runs on the dashboard or as a CLI.
5. [ ] Demo script (90 s table version). Opener: "Visa built the ID check. We built the bouncer." Scenes: good → spoof → scalper → hijacked (card, deny, block, investigator) → slow_low (miss, catch). Close on the same line.
6. [ ] Devpost project created; all four members added.
7. [ ] Track write-ups, one paragraph each, saved in `devpost/`: Visa, Fetch.ai, Apify, Anthropic (named community: *solo Shopify merchants running limited drops who can't afford a fraud team*), Hyphenate, Microsoft Grand Prize, Microsoft Customer Impact, Armadin, Notability.
8. [ ] Disclosures section: traffic is synthetic; key directory is a mock standing in for Visa's; scoring is rule-first with a learned model as demonstration; hijack is a labelled demo switch; latency measured on one laptop.
9. [ ] **Stretch (only if Devpost draft saved by 18:00):** publish the swarm script as an Apify Actor for Best Actor.
10. [ ] After freeze: pitch rehearsal ×2 with all four.
11. [ ] 00:30–02:30: record the video with C. Open on `hijacked`. Under 3 min. If Fetch.ai wants 3–5 min, record that cut in the same session.
12. [ ] Sun 06:30–08:30: video uploaded; Devpost final; every track opted in; submit by 08:30.

**Done when:** Devpost complete with one paragraph per track and the disclosures; video uploaded; pitch run three times by the full team.

**Needs:** B's scenario buttons by 16:00. C's card screenshots by 20:00.
**Gives:** product data and trap URL to C by 12:00.

---

## Cut order (first cut first)

1. x402 (A)
2. LightGBM (B) — keep logreg
3. Apify Actor publishing (D)
4. Docker Compose (A)
5. Sliders (B)
6. Logreg (B) — keep rules and `slow_low` scenario
7. Guardian (C) — card moves into the shopper agent
8. Investigator as separate agent — keep as tool

**Never cut:** signature verification; scoring with reasons; shopper agent in ASI:One; live decision feed; `hijacked` ending challenge → deny → block; `slow_low` miss-and-catch panel; the bouncer opener.

## Booth questions (first person free goes now)

- Visa: are TAP keys per agent platform or per agent instance? Sandbox directory available?
- Fetch.ai: is a merchant-side dashboard acceptable if the shopper flow is fully in ASI:One? 3–5 min video wanted?
- Apify: which sites may be scraped; how Best Actor is judged.
- Hyphenate, Armadin: does AgentGate fit? Twenty minutes of write-up each if yes.
- #ask-directors: cap on sponsor tracks per project?
