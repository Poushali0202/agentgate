# AgentGate frontend and hosting brief

## Deployment shape

Use one Vultr Linux VM for the current demo. Serve the dashboard and FastAPI
API from the same HTTPS origin through a reverse proxy. Keep SQLite and the
registered key directory on persistent disk. Run one Uvicorn worker: pending
challenges, nonce replay tracking, live thresholds and simulated key registrations
currently live in process memory and are not shared between workers.

The reverse proxy must preserve the original Host header and request path:
the request signatures cover those values. Configure the service to restart
automatically and keep port 8000 bound to localhost behind the HTTPS proxy.

Runtime settings:

- `GATEWAY_DB_PATH`: writable persistent SQLite file.
- `GATEWAY_DIRECTORY_PATH`: writable persistent public-key directory JSON.
- `GUARDIAN_TOKEN`: secret shared with the Guardian, supplied outside Git.
- `CHALLENGE_WEBHOOK_URL`: Guardian listener reachable from the VM;
  `localhost:8001` would refer to the VM, not a teammate's laptop.
- `CHALLENGE_TTL_S`: pending-challenge expiry, default 900 seconds.

Before public demo access, decide which merchant and administrative routes
need access restrictions. `/policy` changes live thresholds and `/events`
contains consumer identifiers and purchase details. Separate merchant access
from the signed agent checkout routes. Run the five signature security cases
through the deployed proxy as well as a normal signed checkout.

A Vultr server has been deployed in Silicon Valley: one vCPU, 2 GB RAM,
55 GB SSD, Ubuntu 24.04 LTS, with automatic backups ($12/month total).
Public HTTPS URL: https://agentgate.149-28-196-135.sslip.io/
Rebuilt October 25, 2026 after the original server became unreachable. The
gateway, investigator, and Caddy are enabled at boot and run independently of
any Vultr browser login. Running Shopper and Guardian processes must use this
new origin as `GATEWAY_URL`; repository changes do not update external processes.
Merchant routes require authentication. Credentials and deployment keys stay
outside this repository.

## Figma design brief

Audience: merchants monitoring AI-agent purchases. The shopper and Guardian
conversation remains in ASI:One; this frontend is the merchant console.

Design desktop and mobile frames with these components:

1. Header with AgentGate brand and live connection state.
2. Allow, challenge and block counters with explicit time/window labels.
3. Decision feed: time, agent, consumer, decision, risk, top reasons, latency.
4. Event detail with cart, identity and the challenge/resolution relationship.
5. Policy controls with current thresholds, validation and save feedback.
6. Scenario controls for good, spoof, scalper, hijacked and slow_low.
7. Slow-low explanation panel showing velocity misses and cluster detection.
8. Security-test results and measured precision/recall, with sample size.

Keep allow green, challenge amber and block red, with text labels so that
meaning never depends on color. Use readable tables, restrained motion,
visible keyboard focus and distinct loading, empty, disconnected and error
states. On phones, allow the decision table to scroll without clipping controls.

Implemented: live feed, event inspection, counters, policy controls, five
scenario buttons, measured detection metrics, slow-low comparison, security
checks, investigator integration and the Apify storefront scan panel.
Anthropic credentials are configured on the replacement server. Guardian can use its configured webhook or authenticated polling; verify the live agent flow separately.
Apify has been configured on the deployed server and a scanner run returned results.
The simulator and investigator provide explicitly labeled local fallbacks.
Do not present simulated example values as measured live results.

The implemented frontend is the reference for an editable Figma design.
An editable Figma file now exists at
https://www.figma.com/design/Ouys91iuPBUqW5Jvu56Ie7 . It contains the problem
sketch, desktop and mobile merchant dashboards, proposed visual Challenge Card,
and design evolution. The card is a design proposal; the real Guardian flow
must still be verified independently.

## Millisecond correlation diagnostic

`simulator/correlation.py` analyzes stored gateway event timestamps. The
dashboard displays its results from the additive `timing_correlation` field in
`GET /sim/metrics`. A match requires at least three distinct verified agent keys
sharing a nonempty card fingerprint or shipping address within an inclusive
100 ms sliding window. Duplicate request IDs and human resolution records are
excluded. Each matched request is counted once across both types of link;
evidence windows can overlap. This is historical analysis, not a live alert.

These are gateway observation timestamps, not synchronized client send times.
Shared identifiers are client-supplied demo values. Timing alone does not prove
malice, and the diagnostic does not change scores or checkout decisions. No
event fields, scoring rule IDs, endpoint paths, or scenario names were changed.

## Visa demo boundary

The demo uses real Ed25519 cryptography for TAP-shaped HTTP signatures and a
mock public-key directory. This is not Visa onboarding, Visa-issued consumer
identity, payment tokenization, KYC, or a live payment authorization. Present it
as a simulated integration boundary built around the public TAP concepts.
Synthetic consumer IDs and card fingerprints must not be described as verified
people or Visa payment credentials. Full consumer/payment-container integration
would require additional validation and the relevant provider access.

## Verification before handoff

- HTTPS loads the console and its same-origin API requests succeed.
- Valid signature succeeds; tampered, expired, replayed and wrong-tag requests fail.
- Guardian receives a challenge and its authorized denial produces a block.
- A service restart preserves logged events and registered public keys.
- Document that pending in-memory challenges and threshold edits reset on restart.
- Verify the actual Shopper flow before declaring Gate 1 complete.
