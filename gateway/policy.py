"""Ordered decision policy and live, process-local thresholds."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator

thresholds = {"challenge_at": 30, "block_at": 70}
router = APIRouter()
DRIFT_REASONS = {"new_address", "new_category", "big_basket"}


def decide(identity: str, risk_score: int, reasons: list[str]) -> str:
    if identity != "verified" or "replayed" in reasons:
        return "block"
    if DRIFT_REASONS.intersection(reasons):
        return "challenge"
    limits = thresholds.copy()
    if risk_score < limits["challenge_at"]:
        return "allow"
    if risk_score < limits["block_at"]:
        return "challenge"
    return "block"


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_at: int = Field(ge=0, le=100, strict=True)
    block_at: int = Field(ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.challenge_at >= self.block_at:
            raise ValueError("challenge_at must be below block_at")
        return self


@router.get("/policy")
def get_policy():
    return thresholds.copy()


@router.post("/policy")
def set_policy(value: Thresholds):
    global thresholds
    thresholds = value.model_dump()
    return thresholds.copy()
