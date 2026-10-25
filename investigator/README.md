# AgentGate Investigator

Claude (`claude-sonnet-5-5`) with one read-only tool, `get_events(limit)`, over the gateway's live decision log (`GET /events`). Ask it about a decision in plain English. It reads the log, cites the rule IDs, and keeps facts apart from inference. It can never approve a purchase or change a decision.

```bash
# from the repo root; ANTHROPIC_API_KEY and optionally GATEWAY_URL come from .env
cd investigator
../.venv/bin/python claude_client.py "Why was the last block flagged?"

# or as an HTTP service
../.venv/bin/uvicorn app:app --port 8020
curl -X POST localhost:8020/investigate -H 'Content-Type: application/json' \
     -d '{"question": "Why was the last block flagged?"}'
```

Without `ANTHROPIC_API_KEY` it falls back to a plain summary of the most recent matching event. Set `CLAUDE_MODEL` to override the model.

`events.json` and `investigator.py` are the earlier offline sample. The live investigator doesn't use them.
