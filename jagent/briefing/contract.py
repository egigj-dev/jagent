# Briefing records; packets identify inputs, drafts carry citations, and claims carry application status.
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InputPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_id: int
    job_snapshot_id: str
    profile_version: str
    model: str


class ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["strength", "not_demonstrated", "shared_mention", "explicit_limitation", "uncertain_requirement"]
    skill: str
    job_excerpt_id: str
    profile_excerpt_id: str | None


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: Literal["job", "profile"]
    version: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=600)

    @property
    def excerpt_id(self) -> str:
        return f"{self.source}:{self.version}:{self.start}:{self.end}"


class Claim(ClaimDraft):
    status: Literal["passed_checks", "flagged", "manual_override"]
    verdict: Literal["supported", "contradicted", "insufficient_evidence"] | None = None
    reason: str | None = None
    job_span: SourceSpan | None = None
    profile_span: SourceSpan | None = None
    requirement: Literal["required", "preferred", "example", "title", "not_required", "unclear"] | None = None
    support: Literal["demonstrated", "partially_demonstrated", "not_demonstrated_in_profile",
                     "explicit_limitation", "uncertain"] | None = None


class Briefing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    packet: InputPacket
    engine_version: str | None = None
    claims: list[Claim]
