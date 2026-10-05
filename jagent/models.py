# Posting mirrors the postings columns; timestamps are normalized to UTC.
from datetime import UTC, datetime

from pydantic import BaseModel, field_validator


class Posting(BaseModel):
    id: int | None = None
    source: str
    source_id: str
    url: str | None = None
    company: str | None = None
    title: str | None = None
    locations: list[str] | None = None
    remote: bool | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    description: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    @field_validator("posted_at", "expires_at", "first_seen", "last_seen")
    @classmethod
    def utc_timestamp(cls, value):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamps must include a timezone")
        return value.astimezone(UTC)
