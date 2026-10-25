from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from investigator import DecisionLog
from claude_client import investigate_event


BASE_DIR = Path(__file__).parent
LOG = DecisionLog(str(BASE_DIR / "events.json"))

app = FastAPI(title="AgentGate Investigator")


class InvestigationRequest(BaseModel):
    event_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/investigate")
def investigate(request: InvestigationRequest):
    event = LOG.get_event(request.event_id)

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found",
        )

    explanation = investigate_event(event)

    return {
        "event_id": request.event_id,
        "decision": event.get("decision"),
        "explanation": explanation,
        "read_only": True,
    }