# Jobicy adapter; API_URL supplies remote jobs and dates without offsets use UTC.
from datetime import UTC, datetime
from html import unescape

import httpx

from jagent.models import Posting

API_URL = "https://jobicy.com/api/v2/remote-jobs"


def parse_response(data: dict) -> list[Posting]:
    postings = []
    for item in data["jobs"]:
        posted_at = datetime.fromisoformat(item["pubDate"])
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=UTC)
        location = item.get("jobGeo", "").strip()
        postings.append(Posting(
            source="jobicy", source_id=str(item["id"]), url=item["url"],
            company=unescape(item["companyName"]), title=unescape(item["jobTitle"]),
            locations=[location] if location else [], remote=True,
            posted_at=posted_at, description=item["jobDescription"],
        ))
    return postings


def fetch() -> list[Posting]:
    response = httpx.get(API_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_response(response.json())
