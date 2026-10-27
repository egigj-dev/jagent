# Briefing records; packets identify inputs, drafts carry citations, and claims carry application status.
from typing import Literal

from pydantic import BaseModel, ConfigDict


class InputPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_id: int
    job_snapshot_id: str
    profile_version: str
    model: str


class ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["strength", "not_demonstrated"]
    skill: str
    job_excerpt_id: str
    profile_excerpt_id: str | None


class Claim(ClaimDraft):
    status: Literal["passed_checks", "flagged", "manual_override"]


class Briefing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    packet: InputPacket
    claims: list[Claim]
