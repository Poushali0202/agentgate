import json
import os

from anthropic import Anthropic


SYSTEM_PROMPT = """
You are the AgentGate Security Investigator.

You investigate merchant decisions made by AgentGate.

You may explain decisions using only the event log provided by your read-only tool.

You must:
- distinguish facts from inference;
- mention the exact rule IDs;
- explain why a request was allowed, challenged, or blocked;
- identify whether the issue was identity, replay, tampering, behavior, or prompt injection;
- never approve a purchase;
- never change a decision;
- never invent missing evidence.

Use concise plain English.
"""


def investigate_event(event: dict) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        return fallback_explanation(event)

    client = Anthropic(api_key=api_key)

    response = client.messages.create(
        model=os.environ.get(
            "CLAUDE_MODEL",
            "claude-3-5-sonnet-latest",
        ),
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Explain this AgentGate decision:\n\n"
                    + json.dumps(event, indent=2)
                ),
            }
        ],
    )

    return response.content[0].text


def fallback_explanation(event: dict) -> str:
    decision = event.get("decision", "unknown").upper()
    reasons = event.get("reasons", [])

    reason_text = "; ".join(reasons)

    return (
        f"Decision: {decision}. "
        f"Reason: {reason_text or 'No reason recorded.'}"
    )