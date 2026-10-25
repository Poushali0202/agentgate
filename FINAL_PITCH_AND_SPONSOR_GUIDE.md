# AgentGate — final pitch and sponsor guide

Prepared October 25, 2026. This is a preparation pack, not a submitted entry.
Use the checked items as evidence; unchecked items still need a person to complete them.

## Start here

**One line:** AgentGate helps merchants accept shopping agents while checking whether each purchase should proceed, ask the buyer, or stop.

**Tagline:** Verified agent. Accountable purchase.

**Core story:** A valid signature establishes control of an agent key. It does not establish that a purchase matches the buyer's wishes. AgentGate combines request verification, behavior rules, and a separate Guardian approval channel.

**Submission deadline:** the [live Cal Hacks Devpost](https://cal-hacks-13-0.devpost.com/) lists **October 25, 2026, 9:00 AM PDT**. The live pitch is three minutes with two minutes of questions. Treat the team's 8:30 AM submission target as the working deadline. Any plan to finish “tomorrow” must be checked against this date.

| Resource | Link |
|---|---|
| Public repository | https://github.com/Poushali0202/agentgate |
| Merchant dashboard, login required | https://agentgate.149-28-201-108.sslip.io/ |
| Editable Figma design | https://www.figma.com/design/Ouys91iuPBUqW5Jvu56Ie7 |
| Public Apify Actor | https://apify.com/tangy_taste_poy/agent-prompt-injection-scanner |
| Agent setup and commands | [agents/README.md](agents/README.md) |
| Architecture and shared contract | [AGENTGATE_PLAN.md](AGENTGATE_PLAN.md) |
| Team responsibilities | [TEAM.md](TEAM.md) |

Never put dashboard passwords, API keys, seeds, or the Guardian token in a submission, recording, screenshot, or this file.

## Release and ASI:One status

The latest reviewed team main is `f5da37b`, including Poushali's ASI:One work through PR #14. The merchant UX was merged in [PR #9](https://github.com/Poushali0202/agentgate/pull/9); timing correlation in [PR #7](https://github.com/Poushali0202/agentgate/pull/7).

| Component | Evidence and status |
|---|---|
| Shopper and Guardian | Implemented as Fetch.ai uAgents using the Agent Chat Protocol; merged on main. |
| Chat hijack switch | `hijack on`, `hijack off`, and `hijack status` are implemented. The switch is explicitly staged. |
| ASI:One Interactive Card | Approve/Deny metadata payload and text fallback are implemented in Guardian; [PR #12](https://github.com/Poushali0202/agentgate/pull/12). |
| ASI:One routing fixes | Latest-chat routing, stricter selection parsing, and reply handling are merged through [PR #14](https://github.com/Poushali0202/agentgate/pull/14). PR notes describe behavior observed in ASI:One. |
| Complete live ASI:One demonstration | **Needs final independent verification:** stable addresses, discoverability, normal purchase, challenge, deliberate human answer, and matching gateway outcome. A code merge alone does not establish this. |
| Latest Vultr deployment | Last successful verification was `07515d6`. A fresh SSH/HTTPS check during preparation of this guide timed out; current availability and deployment revision are unconfirmed. |

The agent code is already integrated with the gateway API; no new checkout endpoint is needed. Poushali's running agents must target the deployed `GATEWAY_URL`, and Guardian must use the server's matching `GUARDIAN_TOKEN`. Public agent routes and Guardian authorization were verified in the earlier deployment. Guardian can poll pending challenges if a webhook cannot reach it.

The agent README still has address placeholders and an older statement that cards are text only. For the implementation, refer to `agents/guardian/agent.py::card_message`; do not present that older README sentence as current evidence.

**Important trust limit:** PR #14 narrows accepted reply formats after an ASI:One personal AI answered a challenge. Short replies and planner narration remain accepted. This is a prototype interaction filter, not cryptographic proof of a deliberate human click. Default Guardian routing also requires careful single-user demo setup; production needs authenticated owner binding and isolation.

### ASI:One handoff fields

Fill these with the actual running agents; never derive an address from a development seed and claim it is registered.

| Field | Value to add |
|---|---|
| Shopper name | `agentgate-shopper` |
| Shopper Agentverse address and public profile | **Poushali to supply** |
| Guardian name | `agentgate-guardian` |
| Guardian Agentverse address and public profile | **Poushali to supply** |
| Running process owner / machine | **Poushali to confirm** |
| Gateway URL used by both agents | **Confirm actual value** |
| Successful live demo recording / timestamp | **Add after verification** |
| CalHacks ASI:One Submission Agent receipt | **Add after registration** |

## Three-minute pitch and demo

Rehearse with two people: one narrates and operates ASI:One, one watches the merchant dashboard. Keep the dashboard ready on Decision Log and the correct consumer visible. Use a recording if the live transport is unreliable; label recordings and simulator traffic accurately.

| Time | Say | Show |
|---|---|---|
| 0:00–0:25 | “You ask your shopping agent for headphones. It has a valid identity and permission to shop. But what happens if a webpage steers it toward gift cards and a different shipping address? The signature can still be valid.” | Normal request and the suspicious purchase side by side. |
| 0:25–0:45 | “AgentGate checks both the signed request and the purchase behavior. It can allow, ask the buyer, or block. Authentication alone doesn't settle purchase authorization.” | Dashboard legend and one decision detail. |
| 0:45–1:10 | “First, an ordinary purchase. Our Shopper signs its request; the gateway verifies it and allows the order.” | ASI:One normal purchase, then its matching allowed gateway event. |
| 1:10–1:55 | “Now we enable our clearly labeled compromise simulation. The same agent requests an unusual gift-card order. The gateway asks for confirmation. A separate Guardian shows the reasons, and I deny it. The gateway records the block.” | `hijack on`, purchase, Guardian card, explicit denial, matching resolution event. |
| 1:55–2:15 | “We also look across agent keys. Our slow-and-low simulation spreads requests across keys to avoid per-key velocity signals; shared payment or address information still links them.” | Slow-and-low panel with actual rule results. |
| 2:15–2:35 | “Merchants can inspect a decision or ask AI for a plain-language explanation. Our Apify Actor also reports suspicious instructions on storefront pages.” | One prepared AI answer and one actual scanner finding. |
| 2:35–3:00 | “We built real signing, rules, escalation, an event log, and a deployed merchant console. Identity onboarding and payment credentials are simulated. Our next step is provider-backed identity and authenticated, durable human approvals. AgentGate makes delegated shopping accountable at checkout.” | Architecture and clearly labeled real/simulated boundaries. |

If ASI:One is not verified in time, use the gateway simulator for the core demonstration and explicitly say so. That fallback demonstrates gateway behavior; it does **not** satisfy Fetch's ASI:One workflow requirement.

### Exact ASI:One rehearsal

1. Confirm Poushali's actual agent addresses, mailbox connections, running processes, and shared gateway URL.
2. Check the public store endpoint and agent key registration; confirm the merchant dashboard loads with login.
3. Speak to Guardian first: `hi`. Use the intended human's conversation.
4. Tell Shopper `hijack off`, then `buy me wireless headphones under $200`.
5. Find the resulting allowed event in the merchant log. A completed normal purchase establishes the drift baseline.
6. Tell Shopper `hijack on`, then `buy me headphones`. Explain aloud that the compromise is staged.
7. Wait for Guardian's challenge. Inspect the item, destination, reasons, and request identifier. Polling fallback can add up to about 15 seconds before pickup.
8. The person deliberately selects Deny, or uses the explicit short deny command with the request ID if the card renderer fails. Check that no answer occurred automatically.
9. Match the challenge and final blocked resolution in the gateway log. A message saying “denied” alone is insufficient evidence.
10. Tell Shopper `hijack off`. Capture the successful workflow without secrets.

Do not restart the gateway mid-demo: pending challenges are in memory. The configured timeout is 15 minutes; that timeout is not a human denial. For clean repetition, use an agreed fresh demo consumer or a clean rehearsal gateway rather than deleting the live event log.

### Sixty-second version

“AgentGate gives merchants a control point for AI shopping. A valid agent signature proves control of a key, but an authenticated agent can still make an unwanted purchase. We verify requests, apply twelve behavior rules, and choose allow, challenge, or block. In our demo, a normal headphone order succeeds. A labeled compromise simulation changes the order to gift cards and a new address. The gateway escalates it to a separate Guardian, the buyer denies it, and the event log records the block. Merchants get understandable reasons, coordination signals across agent keys, storefront scanning, and a read-only AI investigator. The cryptography and decisions are real; identity onboarding and payment credentials are simulated.”

## Copy-ready Devpost draft

### Inspiration

Shopping agents make delegation convenient, but merchants still need to decide whether a particular purchase is appropriate. A signed request can come from a legitimate agent whose behavior has changed. We wanted a merchant to recognize that uncertainty and ask the buyer before completing an unusual purchase.

### What it does

AgentGate verifies signed shopping requests, evaluates twelve behavior rules, and returns allow, challenge, or block. A separate Guardian agent can present an unusual purchase for approval or denial. The merchant console shows decisions, reasons, identity status, latency, and event details. An Apify Actor scans storefront pages for prompt-injection patterns, while a Claude investigator explains recorded decisions in merchant language.

### How we built it

The gateway uses FastAPI, Ed25519 HTTP-message-signature verification, a mock key directory, deterministic behavior rules, and SQLite event storage. Shopper and Guardian use Fetch.ai uAgents and the Agent Chat Protocol. The merchant frontend includes distinct overview, decision, policy, investigation, security, and learning views. The gateway and investigator were deployed behind Caddy HTTPS on Vultr. Figma records our design reasoning, dashboard concepts, and human challenge experience.

### Challenges and learning

We separated agent authentication from purchase authorization. Behavior that departs from a consumer's established history can warrant a challenge even when the score is high. We also found that a conversational platform's personal AI can respond to an approval prompt; narrowing reply formats helps the demo, while strong human authorization requires a dedicated authenticated interaction boundary. Our experiments distinguish synthetic attack labels from the signals used by the policy.

### Accomplishments

We implemented a signed purchase path, cross-key clustering, a human-escalation path, an inspectable merchant console, a public scanner Actor, and a real Claude investigation request. The dashboard explains colors, risk, timing, and metrics, with short paginated tables and accessible contextual help. Latest ASI:One card and chat improvements are merged; attach the final live workflow evidence before claiming full ASI:One completion.

### What's next

Provider-backed agent credentials, verified consumer binding, durable challenge recovery, stronger human approval authentication, merchant validation, and calibrated fraud evaluation. Per-person inventory fairness needs a trustworthy identity layer and shared reservation accounting. Tiger Data, x402, and a custom domain remain deferred.

**Suggested built-with tags:** Python, FastAPI, Ed25519, SQLite, Fetch.ai uAgents, Agent Chat Protocol, Anthropic Claude, Apify, Vultr, Caddy, Figma, HTML, CSS, JavaScript. Add ASI:One as demonstrated technology once the live workflow is captured. Do not tag a real Visa payment API as implemented.

## Sponsor priorities and materials

These are fit assessments, not guarantees of eligibility or prizes. Final track selection and forms need the team's submission owner. Check linked sponsor instructions for amendments.

| Track | Fit / readiness | Remaining submission work |
|---|---|---|
| Visa — Reimagining Shopping | Strong shopping and trust story | Show normal purchase, changed purchase, buyer decision; disclose simulated credentials. |
| Fetch.ai | Agent implementation merged; live completion pending evidence | Addresses, ASI:One workflow recording, registration, public run instructions. |
| Microsoft — Built for the Real World / Customer Impact | Strong engineering story; impact validation incomplete | Explain merchant workflow, evidence, reliability limits, and validation plan. |
| Armadin — Best Security Hack | Strong security fit | Demo tampering/replay and coordination; verify any extra sponsor rules. |
| Atlassian — Best Security Solution for Agents | Strong fit; full challenge requirements need confirmation | Name the chosen category and review the linked challenge document. |
| Most Technically Complex Hack | Strong architecture story | Explain one request across components and show measured evidence. |
| Most Creative Hack | Strong authentication/behavior distinction | Center the challenge design and slow-and-low example. |
| Apify — Best Use / Best Actor | Real Actor and dashboard integration verified previously | Public Actor link, dataset evidence, relevant scan finding. |
| Figma — Best Figma Workflow Hack | Editable workflow artifact exists | Walk through reasoning, components, and implemented result. |
| MLH — Best Use of Vultr | Actual deployment verified previously | Restore/check current reachability and record deployment evidence. |
| Anthropic — Claude for Public Benefit | Working Claude feature; public-benefit case conditional | Specific community, actual validation if available, demonstrated explanation. |
| MLH — Commit Fellowship | Conditional on team intent | Opt in and complete the supplemental form. |
| Hyphenate | Conditional finance/workflow fit | Confirm sponsor fit; show the failure-handling moment and real/simulated evidence. |
| Notability | Conditional on actual use | Include genuine build-process notes and feature usage. |
| People-First Social Impact | Lower priority | Enter only with a substantiated community benefit. |
| Tiger Data / Coinbase x402 / GoDaddy domain | Deferred by team choice | No claim of implementation or entry based on planned work. |

### Visa — Reimagining Shopping

**Description:** AgentGate supports shopping delegation while preserving a buyer's control over unusual purchases. TAP-inspired signed requests establish agent-key identity in our prototype; behavior checks then evaluate the transaction. A normal purchase proceeds, while a changed address, category, or unusually large basket can trigger a Guardian challenge. The buyer's answer determines the final outcome. This separates the identity of a shopping agent from authorization for a particular purchase.

**Demo:** normal purchase → labeled hijack → challenge reasons → deliberate denial → gateway block. Explain how a merchant could integrate a provider-backed trust directory and actual payment credentials later.

**Boundary:** real Ed25519 signing with a mock directory and simulated payment fingerprints. No live Visa-issued agent credential, KYC, Visa payment authorization, or proof of personhood. The policy does not implement a fair queue or a per-person ticket quota across agents.

### Fetch.ai — ASI:One agent challenge

**Description:** AgentGate coordinates a Shopper and a separate Guardian using Fetch.ai uAgents and the Agent Chat Protocol. Shopper turns a purchase request into signed gateway calls. When purchase behavior is unusual, Guardian presents a confirmation request through the conversation and sends the resolution to the gateway. The merchant dashboard is an operations view; the intended buyer workflow remains within ASI:One.

**Demo:** use the exact ASI:One rehearsal above. Show discoverable agents, tool execution, the normal purchase, the card or explicit text fallback, and the matching final outcome. A direct-handler rehearsal is useful engineering evidence but does not prove Agentverse transport.

**Required checklist from the supplied Fetch guide:**

- [ ] At least one actual Agentverse registration; include stable agent names and addresses.
- [x] Agent Chat Protocol handlers implemented in the repository.
- [ ] Discoverable and usable in ASI:One, with the complete primary workflow demonstrated there.
- [ ] Meaningful execution/orchestration captured in the demo.
- [x] Public GitHub repository and agent run instructions exist; address placeholders still need completion.
- [ ] Confirm Innovation Lab category/tags and required public metadata.
- [ ] Add the requested demo video; check the guide's 3–5 minute format separately from the three-minute live pitch.
- [ ] Submit on Devpost **and** register through the CalHacks ASI:One Submission Agent.

Interactive Cards and Payment Protocol are bonus opportunities in the supplied requirements; the payment protocol is not implemented here. Card payload support is merged, but successful rendering and deliberate interaction still need a live capture.

### Microsoft — Built for the Real World / Customer Impact

**Description:** AgentGate targets the merchant operator responsible for accepting automated purchases without losing control over unusual orders. It combines explicit outcomes, understandable reasons, human escalation, and an inspectable event log in a deployed prototype. The interface supports investigation without requiring the operator to decode security rule IDs. Our production plan prioritizes trustworthy identity binding, durable approvals, operational recovery, and evaluation with merchant feedback.

**Demo:** follow a merchant from overview → filtered decision → plain-language explanation → technical evidence when needed. Show policy preview as an intentional change before saving. Cite sample sizes and synthetic-data context for every metric.

**Evidence gap:** no customer interviews, deployment SLA, or demonstrated commercial impact are established by this pack. Describe those as validation work. Do not invent Microsoft platform usage.

### Armadin — Best Security Hack

**Description:** AgentGate applies security checks at a consequential action boundary: merchant checkout. Signature verification rejects invalid requests, while behavior rules identify suspicious activity by authenticated keys. Shared card/address signals expose coordination across keys; consumer drift can trigger escalation to a separate approval channel. Operators can inspect the evidence and reproduce labeled attacks.

**Demo:** one digest-tampering or replay rejection, then slow-and-low clustering, then Guardian escalation. Explain which control caught each case. Review any sponsor-specific requirements before entry; the supplied guide had incomplete Armadin details.

### Atlassian — Best Security Solution for Agents

**Description:** AgentGate is a security control for agent actions, with signed-request verification, behavior policy, escalation, and an audit trail. It makes the difference between authenticated identity and authorized behavior visible to an operator. The Guardian channel separates the shopping executor from the approval credential, while the read-only investigator helps explain a decision.

**Demo:** show the agent's attempted action, policy reason, separate Guardian response, and recorded outcome. Explain limited authority for each component. Include the selected category explicitly in the project description.

**Still required:** review the full [Atlassian challenge document](https://docs.google.com/document/d/12Y2Vamxbm9W_l2Eo4AM530R7HfNAYCXI-UI6F6Xnggw/edit). The category name alone does not prove compliance with its full instructions.

### Apify — Best Use of Apify / Best Actor

**Description:** Our public Actor scans storefront pages for instructions aimed at shopping agents, including hidden content, instruction overrides, gift-card pushes, quantity changes, and shipping redirection. The merchant dashboard displays the actual scan output so an operator can investigate a suspicious page alongside purchase behavior. The last successful verified scan covered three pages: one high risk and two low risk, with no scan errors.

**Demo:** open the public Actor and a successful dataset; show the poisoned page, the recorded patterns/hiding technique, and its dashboard finding. Explain the practical operator action: inspect the listing and review related purchase events.

**Boundary:** this is pattern-based detection. A low result is not proof a page is safe. Dashboard visibility does not establish automatic prevention of agent browsing. Attach the actual run link and dataset link before submission; do not invent identifiers.

### Figma — Best Figma Workflow Hack

**Description:** Our Figma workflow made a product decision visible: an authenticated but unusual purchase deserves an understandable human challenge. The editable file contains the problem sketch, merchant desktop/mobile concepts, a visual Challenge Card, and the evolution from threshold-only reasoning toward human escalation. The implementation adds clearer navigation, compact tables, visible color meanings, progressive technical detail, and contextual help.

**Demo:** open the editable file → early decision sketch → Challenge Card and its rationale → desktop/mobile concepts → implemented dashboard. Show components and tokens where useful. Explain why Challenge preserves a buyer's agency when behavior is uncertain.

**Accuracy:** threshold-only versus escalation is design reasoning; do not fabricate shipped version history. The Figma dashboard is an earlier artifact, and the implemented interface has evolved. The visual card is a design artifact; the current Guardian separately implements ASI:One card metadata with text fallback. Do not claim pixel-identical rendering without checking it.

Review the current [Figma challenge instructions](https://docs.google.com/document/d/1HjzThDGveSLiilIdEPEHq12ZVLZ5eS0T8CQC5_m_-rg/edit) and provide the editable link plus a short workflow recording.

### MLH — Best Use of Vultr

**Description:** AgentGate's gateway and investigator run on a Vultr Ubuntu VM behind Caddy HTTPS. The deployment separates public agent endpoints from authenticated merchant tools, supervises processes with systemd, and persists the event log outside the release checkout. It provides a real hosted integration target for shopping agents.

**Demo:** show the live HTTPS dashboard, a signed checkout appearing there, and the Vultr instance overview without credentials. Confirm gateway, investigator, and Caddy health first. The current timeout must be resolved or reported honestly; an earlier successful deployment does not prove current availability.

### Anthropic — Claude for Public Benefit

**Description:** AgentGate uses Claude as a read-only merchant investigator. It turns recorded purchase decisions into a short explanation of what happened, why it was flagged, and what the operator can do next. Technical evidence stays available for investigation. The proposed public benefit is making agent-assisted commerce more understandable and giving buyers a chance to reject unusual purchases.

**Demo:** ask “Why was the last purchase blocked?” Show the plain-language answer, expand the recorded evidence, and compare its reason to the underlying event. Explain that the provided investigation tool reads events and cannot approve an order or change policy.

**Evidence:** an actual Claude Sonnet 5.5 request through the hosted investigator returned successfully in earlier verification. AI explanations remain advisory and may contain inference or chronology errors; the event log is the authoritative record.

**Eligibility/impact gap:** identify a specific community the team actually studied and report only genuine validation. Small merchants or people who rely on delegated shopping are candidate beneficiaries, not validated users. A generic benefit statement alone is a weak entry. Shopper intent extraction can also use Claude when configured; its regex fallback must not be represented as a model call.

### Hyphenate — Autonomous Systems for Finance

**Description:** AgentGate demonstrates a merchant risk-review workflow with limited component authority and escalation at uncertainty. The Shopper executes purchases, the gateway evaluates behavior, Guardian seeks an answer, and the investigator explains the record. The proposed seats are purchase-risk triage and merchant investigation support.

**Demo:** open with the failure-handling moment: an authenticated agent attempts an unwanted order, and the approval path stops it. Be prepared to try a judge-provided scenario. Show the action record and name exactly what is real versus simulated.

**Still required:** confirm with the sponsor that this commerce-security workflow fits the finance track. Do not claim autonomous settlement, accounting, or real fraud-loss reduction.

### Commit Fellowship, Notability, and general awards

**Commit Fellowship:** describe the working prototype, intended customer, and genuine post-hackathon commitment. A useful proposed discovery plan is merchant interviews followed by a small sandbox pilot. Opt into the category and complete its supplemental form using the current organizer-provided link. Do not invent team commitments, customer traction, or a form submission.

**Notability:** submit only if the team actually documented its build there. Show dated notes, decisions, sketches, or recordings and explain the features used. A newly reconstructed narrative is not evidence that Notability supported the build.

**Most Technically Complex:** trace one signed request through verification, behavior rules, challenge resolution, event storage, dashboard, and investigation. Explain replay/digest defenses, cross-key clustering, and the separate approval credential. Use measured results with their limitations.

**Most Creative:** focus on the product choice to challenge behavioral uncertainty and the coordination example that ordinary velocity checks miss.

**People-First:** consider only with a substantiated beneficiary story; the presence of a human confirmation button alone does not establish social impact.

## Evidence and claim boundaries

| Safe claim | Limit to say when asked |
|---|---|
| Real Ed25519 signing and verification | Mock trust directory; registration does not prove a unique person or Visa onboarding. |
| Twelve behavior rules | Heuristic scores, not calibrated fraud probabilities; up to three highest-scoring reasons are returned. |
| Allow / challenge / block | Consumer-drift override applies when a drift reason is among the returned reasons. |
| Velocity and hoarding signals | Hoarding is a per-order quantity signal; no cross-agent per-person quota or fair queue. |
| Cross-key clustering | Three or more keys sharing a card/address within ten minutes; those identifiers are client-supplied demo values. |
| Millisecond correlation diagnostic | Three distinct verified keys sharing a card/address within an inclusive 100 ms window; observational gateway timestamps, not proof of simultaneous client action. It does not alter policy decisions. |
| Separate Guardian approval credential | Prototype owner routing/reply parsing is not strong human authentication or audited multi-user isolation. |
| AI investigator | Real Claude call verified; read-only tools, advisory explanation, possible factual/inference errors. |
| Public Apify Actor and successful scan | Pattern detection; neither universal injection detection nor automatic prevention. |
| Vultr-hosted prototype | Last successful deployment verified earlier; current reachability needs a fresh check. |
| Editable Figma workflow | Distinguish proposed designs, implemented interface, and actual recorded history. |

Avoid “enterprise ready,” “KYC verified human,” “live Visa integration,” “two tickets per person,” “zero false positives,” “every malicious agent caught,” and “human approval cannot be spoofed.” Those claims are not supported.

### Metrics and test evidence

- Gateway, simulator, and scanner validation passed **68 automated tests** on the integrated `f5da37b` code baseline during this final preparation. This documentation-only addition does not change application behavior. The suite does not verify Agentverse transport or ASI:One card rendering.
- Precision/recall panels use labeled simulator traffic. In this evaluation, challenge or block counts as detection; an allow on a bad labeled scenario counts as a miss. The metrics do not measure real merchant fraud performance.
- Record sample count, timestamp, scenario distribution, thresholds, and whether resolutions are excluded before quoting a percentage. Mixed live/demo logs are not a clean benchmark.
- Label request-decision latency separately from the time a human takes to answer a challenge. Do not quote a p95 without its measured population.
- Previously verified scanner result: three pages, one high risk, two low risk, zero errors. Attach the run timestamp/link if showing it as evidence.
- Browser checks previously covered separate views, pagination/pause, policy preview, contextual help, learning navigation, and literal rendering of HTML in AI output.

## Judge questions

**How is an agent different from a scalper bot?** Its declared purpose does not establish safety. We constrain observable requests and behavior. Our prototype does not solve unique-person verification; a real fairness system would need trustworthy person binding and shared purchase accounting.

**Why challenge a high-risk verified purchase?** A new destination or large basket can be legitimate. Where the policy sees consumer drift, it gives the buyer a chance to decide. Invalid identity and request-integrity failures are handled earlier.

**Is this actual Visa integration?** It is a TAP-inspired signing prototype with a mock directory. We implemented real cryptography, not Visa-issued credentials or live payments. Provider-backed onboarding is a next integration step.

**Does the hijack happen naturally?** The demonstration uses an explicit switch to stage the changed agent behavior. The gateway receives signed requests and applies its normal checks. We do not claim the language model was independently induced to follow the injection in this demo.

**Can the Shopper approve itself?** The Shopper process drops the Guardian token; the gateway requires that credential for resolution. Stronger human-authenticated approval and multi-user owner binding remain production work. The chat reply filter alone is not a proof of human intent.

**What catches slow-and-low activity?** Cross-key shared-card/address clustering within ten minutes. The separate 100 ms diagnostic is for investigation and does not drive blocking.

**What happens after a restart?** Events persist in SQLite, but pending challenges and policy thresholds are process-local. Durable challenge recovery and persisted policy configuration are required before production use.

**Why use AI in the risk system?** Checkout decisions are deterministic rules. Claude helps operators interpret recorded evidence and can parse Shopper intent when configured. The investigator cannot authorize transactions through its tool.

**What is Samhita's contribution?** Scoring and decision policy, labeled simulator scenarios, cross-key coordination evaluation, the timing diagnostic, merchant dashboard and UX, plus deployment/design coordination and this pitch pack. Attribute the gateway, agents, scanner, and investigator to the team members in TEAM.md; don't present teammates' implementation as solo work.

## Submission and recording checklist

- [x] Core dashboard, policy, correlation diagnostic, and agent changes merged into team main through the reviewed baseline.
- [x] Compact merchant UX, Ask AI wording, contextual help, color meanings, and distinct views implemented.
- [x] Editable Figma artifact and public Apify Actor exist.
- [x] Real Claude investigator request verified earlier.
- [x] Test the integrated `f5da37b` baseline: 68 gateway, simulator, and scanner tests passed.
- [ ] Restore/verify current Vultr HTTPS and service health; record actual deployed revision.
- [ ] Poushali: provide stable agent addresses, running process details, and the full ASI:One capture.
- [ ] Confirm no automatic approval/denial occurs before the human's deliberate answer.
- [ ] Add video URL, project image, agent profiles, and Actor run/dataset links.
- [ ] Review full Atlassian, Figma, and any amended sponsor instructions.
- [ ] Enter all four teammates and select only supported tracks in Devpost.
- [ ] Fetch: complete the separate ASI:One Submission Agent registration.
- [ ] Fellowship: complete the supplemental form if the team wants to enter.
- [ ] Check that public links work for a judge; provide merchant access privately if needed.
- [ ] Submit before the deadline; save the receipt. Preparing this file does not submit anything.
- [ ] After the demo, rotate the previously exposed Apify token and update runtime settings.

### Final evidence to fill in

| Evidence | Value |
|---|---|
| Tested application baseline | `f5da37b`; pitch-pack addition is documentation only |
| Test result / command | `68 passed` — `.venv/bin/python -m pytest gateway/tests simulator/tests apify/actor/tests -q` |
| Actual deployed revision / health time | Add after fresh server check |
| General demo video | Add URL |
| Fetch workflow video | Add URL |
| Project image | Add URL or repository path |
| Actor run / dataset | Add actual URLs |
| Devpost submission | Add receipt / URL |
| ASI:One submission | Add receipt |

## Deferred work and tomorrow's handoff

Keep Tiger Data, x402, and a custom domain out of the current feature claims. These estimates assume account access and credentials are ready; they are engineering estimates, not provider guarantees.

| Work | Estimated effort | Approach |
|---|---|---|
| Custom domain | 30–60 minutes plus DNS propagation | Point DNS to the existing VM, update Caddy, and verify signature authority/host behavior. |
| x402 testnet prototype | Half a day; 1–3 days for reliable behavior | Start with one paid read-only report, then verify settlement, retries, and failure handling. |
| Tiger Data analytics mirror | Half to one day | Export events to a separate analytics consumer while SQLite remains authoritative. |
| Tiger Data primary store | 1–3 days | Port queries and connection handling, migrate data, and test ordering, restart, retention, and rollback. |

Next work in order: confirm the actual submission deadline → check hosted availability → collect ASI:One addresses and workflow evidence → finish missing forms/assets → stronger owner-bound approval → durable challenge recovery → merchant validation. Revisit deferred integrations after the submission is safe.

## Sources and interpretation

- [Live Cal Hacks Devpost](https://cal-hacks-13-0.devpost.com/): current deadline, live pitch format, track names, and submission overview; checked October 25, 2026.
- Supplied **13.0 Hacker Guide.pdf**, sponsor descriptions and judging criteria. Its older Figma title is superseded by the live listing. Some sponsor details were incomplete.
- Supplied **fetchai.pdf**, especially pages 4–6: mandatory ASI:One/Agentverse/ACP workflow, deliverables, registration, and bonus features.
- Repository implementation, TEAM.md, and linked PRs: technical behavior and ownership.
- Prior recorded deployment checks: hosted services, access controls, scanner run, Claude call, and UX verification. Fresh server checks timed out during this preparation; earlier evidence is labeled accordingly.

Track descriptions above are original drafts based on our implementation and the supplied guidance. They do not assert organizer approval. External submissions and messages require the team's actual submission action.
