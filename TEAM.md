# AgentGate — Team Split

Who does what for Cal Hacks 13.0. The full spec is in [AGENTGATE_PLAN.md](AGENTGATE_PLAN.md). This file maps the plan's roles A–D to people and branches, and sets the rules for working in parallel.

**If you are an AI agent working for one of us:** read this file, then in `AGENTGATE_PLAN.md` read **"Shared contract"**, **"Gates"** and **your person's section only**. Work only on your branch and only in the files you own.

## Assignments

| Person | Role in plan | Area | Branch | Owns |
|---|---|---|---|---|
| **Dipin** | A | Gateway & Security | `dipin/gateway` | `gateway/app.py`, `gateway/verify.py`, `gateway/db.py`, `README.md`, `docker-compose.yml` |
| **Samhita** | B | Scoring, Simulator & Dashboard | `samhita/scoring` | `gateway/scoring.py`, `gateway/policy.py`, `simulator/`, `dashboard/`, `model/` |
| **Poushali** | C | Fetch.ai Agents | `poushali/agents` | `agents/shopper/`, `agents/guardian/` |
| **Sanjana** | D | Apify, Investigator & Demo | `sanjana/demo` | `apify/`, `trap-page/`, `investigator/`, `devpost/` |

Wherever the plan says "A", "B", "C" or "D", read the name from this table.

## Key times (Sat 24 – Sun 25 Oct, PDT)

| Time | What |
|---|---|
| Sat 12:00 | **GATE 1**: one signed request goes shopper agent → gateway → decision → dashboard |
| Sat 14:00 | Dipin → Poushali: `/challenge/{id}/resolve` + webhook. Samhita → Dipin: `policy` and `sim` routers |
| Sat 14:30 | Poushali → Samhita: hijack switch working |
| Sat 16:00 | **GATE 2**: all five scenarios run from buttons |
| Sat 17:00 | Stretch gate |
| Sat 20:00 | **FREEZE** |
| Sun 08:30 | Submitted on Devpost |

## Handoffs

| From | To | What | By |
|---|---|---|---|
| Poushali | Dipin | Shopper + Guardian Ed25519 public keys for the key directory | now |
| Sanjana | Poushali | Apify product data location + trap page URL | Sat 12:00 |
| Dipin | Poushali | `POST /challenge/{id}/resolve` + `CHALLENGE_WEBHOOK_URL` webhook | Sat 14:00 |
| Samhita | Dipin | `policy.py` router + `simulator/` router (Dipin adds one `include_router` line each) | Sat 14:00 |
| Poushali | Samhita | `HIJACK=1` switch working end to end | Sat 14:30 |
| Samhita | Sanjana | Scenario buttons on the dashboard | Sat 16:00 |
| Dipin | Samhita | `GET /security-tests` for the dashboard | Sat 17:00 |
| Poushali | Sanjana | ASI:One card screenshots | Sat 20:00 |
| Poushali | Dipin | Agent names + Agentverse addresses for README | Sat 20:00 |

## Branch & merge rules

1. **Start from main:** `git fetch && git checkout <your-branch>`, or if it doesn't exist yet, `git checkout -b <your-branch> origin/main`.
2. **Touch only files you own.** To change something someone else owns, ask them; don't edit it on your branch.
3. **The shared contract is frozen:** event record fields, endpoint paths, policy table, scoring rule ids, scenario names. Changing any of them needs a message to all four people first, then the change goes to `AGENTGATE_PLAN.md` on main.
4. **Merge small and often.** Open a PR into `main` as soon as something works, and always before each gate. Don't hold a big branch until the evening.
5. **Rebase on main before opening a PR:** `git fetch && git rebase origin/main`.
6. **Shared files:** dependencies go in one root `requirements.txt` with exact versions, one per line, append only. On a merge conflict, keep both sides. Put env vars in `.env.example`; real secrets go in `.env` and are never committed.
7. **Shared base goes straight to `main`** (Dipin is pushing the gateway foundation there in small commits). Everything else: PR from your branch.

## Stubs so nobody blocks on anyone

Until the real piece lands on main, work against these:

- **Samhita** can build `scoring.py` / `policy.py` as pure functions over event dicts in the contract shape, with unit tests, without the gateway running.
- **Poushali** can sign requests against a local stub server that returns `{"decision": "allow"}` until Dipin's gateway merges.
- **Sanjana** can build the investigator against a JSON file of hand-written events in the contract shape until `/events` is live.
- **Dipin** can call a placeholder `score()` that returns `(5, ["base"])` and a `decide()` that allows everything, until Samhita's modules merge.

## Cut order and never-cut list

See `AGENTGATE_PLAN.md` → "Cut order". Cuts are announced to all four, never made silently.
