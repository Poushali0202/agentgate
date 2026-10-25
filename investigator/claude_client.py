"""AgentGate Security Investigator: Claude with one read-only tool over the gateway's live decision log.

    python claude_client.py "why was the last block flagged?"

Needs ANTHROPIC_API_KEY (read from the repo's .env if not already set). Without it, falls back to a
plain summary of the most recent matching event, built from the same log.
"""

import json
import os
import sys
from pathlib import Path

import anthropic
import httpx
from anthropic import beta_tool


def _load_dotenv() -> None:
    """Read the repo's .env (ANTHROPIC_API_KEY, GATEWAY_URL) without overriding what is already set."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#") and value.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


_load_dotenv()

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000").rstrip("/")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
# Only what a decision explanation needs; keeps the tool result small.
EVENT_FIELDS = ("request_id", "ts", "decision", "identity", "agent_keyid", "tag", "consumer_id",
                "cart", "risk_score", "reasons", "challenge_id", "latency_ms")

SYSTEM_PROMPT = """
You are the AgentGate Security Investigator.

You investigate merchant decisions made by AgentGate, a firewall in front of a store's checkout API that
verifies AI shopping agents' signatures and scores their behaviour. Each event in the log is one decision:
allow, challenge (the consumer's Guardian asks the human), or block. A resolved challenge appears as a
second event with the same challenge_id whose first reason is human_approved, human_denied or guardian_timeout.

Use the get_events tool to read the log. It is read-only and is your only source of evidence.

You must:
- distinguish facts from inference;
- mention the exact rule IDs from the event's reasons;
- explain why a request was allowed, challenged, or blocked;
- identify whether the issue was identity (unsigned, unknown_key, wrong_tag, expired), replay
  (replayed_nonce), tampering (digest_mismatch), or behaviour (velocity, cluster, drift rules);
- never approve a purchase;
- never change a decision;
- never invent missing evidence.

Answer in a short case summary of plain English, at most five sentences.
"""

RULE_TEXT = {
    "unsigned checkout not accepted": "the checkout carried no signature",
    "replayed_nonce": "a previously used signature was replayed",
    "digest_mismatch": "the order body was changed after it was signed",
    "expired": "the signature had expired",
    "wrong_tag": "a browse-only agent tried to pay",
    "unknown_key": "the agent's key is not in the directory",
    "burst": "many checkouts in a short time",
    "heavy_burst": "an extremely high checkout rate",
    "card_testing": "many different cards tried",
    "tiny_orders": "mostly tiny test-sized orders",
    "hoarding": "bulk buying of a limited item",
    "too_fast": "checkout faster than a normal shopper",
    "new_address": "a shipping address this customer never used",
    "big_basket": "an order far larger than this customer's usual",
    "new_category": "a category this customer never buys",
    "cluster": "many agents sharing one card or address",
    "young_key": "a brand-new agent identity",
    "human_approved": "the account holder approved it",
    "human_denied": "the account holder denied it",
    "guardian_timeout": "the account holder never answered",
}


def fetch_events(limit: int) -> list[dict]:
    r = httpx.get(f"{GATEWAY_URL}/events", params={"limit": max(1, min(limit, 100))}, timeout=10)
    r.raise_for_status()
    return [{k: e.get(k) for k in EVENT_FIELDS} for e in r.json()]


@beta_tool
def get_events(limit: int = 20) -> str:
    """Read the most recent AgentGate decisions, newest first. Read-only.

    Args:
        limit: How many recent events to return, from 1 to 100.
    """
    try:
        return json.dumps(fetch_events(limit))
    except httpx.HTTPError as e:
        return f"Error: could not read the decision log at {GATEWAY_URL}/events ({e})."


def investigate(question: str) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return fallback_explanation(question)

    client = anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        tools=[get_events],
        messages=[{"role": "user", "content": question}],
        # On a safety decline, the API re-runs the request on a fallback model it picks.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    final = runner.until_done()
    if final.stop_reason == "refusal":
        return "The investigator declined to answer this question."
    return "\n".join(b.text for b in final.content if b.type == "text").strip()


def fallback_explanation(question: str) -> str:
    """No API key: describe the most recent event matching a decision named in the question."""
    try:
        events = fetch_events(100)
    except httpx.HTTPError as e:
        return f"Could not read the decision log at {GATEWAY_URL}/events ({e})."
    wanted = next((d for d in ("block", "challenge", "allow") if d in question.lower()), None)
    event = next((e for e in events if wanted is None or e["decision"] == wanted), None)
    if event is None:
        return f"No {wanted or ''} decisions in the log yet.".replace("  ", " ")
    why = "; ".join(RULE_TEXT.get(r, r) for r in event["reasons"] if r != "base") or "baseline only"
    return (f"{event['decision'].upper()} at {event['ts']} for agent {event['agent_keyid'] or '(unsigned)'}, "
            f"risk {event['risk_score']}. Reasons: {', '.join(event['reasons'])} ({why}).")


if __name__ == "__main__":
    print(investigate(" ".join(sys.argv[1:]) or "Why was the last block flagged?"))
