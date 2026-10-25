"""HTTP front for the investigator.

    cd investigator && uvicorn app:app --port 8020
    curl -X POST localhost:8020/investigate -H 'Content-Type: application/json' \
         -d '{"question": "why was the last block flagged?"}'
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from claude_client import GATEWAY_URL, MODEL, investigate

app = FastAPI(title="AgentGate Investigator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class InvestigationRequest(BaseModel):
    question: str = "Why was the last block flagged?"


@app.get("/health")
def health():
    return {"status": "ok", "gateway": GATEWAY_URL, "model": MODEL}


@app.post("/investigate")
def investigate_endpoint(request: InvestigationRequest):
    return {"question": request.question, "answer": investigate(request.question), "read_only": True}
