# Remotive adapter; API_URL requests software jobs and publication dates use UTC.
from datetime import UTC, datetime

import httpx

from jagent.models import Posting

API_URL = "https://remotive.com/api/remote-jobs?category=software-dev"


def parse_response(data: dict) -> list[Posting]:
    postings = []
    for item in data["jobs"]:
        posted_at = datetime.fromisoformat(item["publication_date"])
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=UTC)
        location = item.get("candidate_required_location", "").strip()
        postings.append(Posting(
            source="remotive", source_id=str(item["id"]), url=item["url"],
            company=item["company_name"].strip(), title=item["title"],
            locations=[location] if location else [], remote=True,
            posted_at=posted_at, description=item["description"],
        ))
    return postings


def fetch() -> list[Posting]:
    # The API's default limit is all matching jobs; there are no pages to follow.
    response = httpx.get(API_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_response(response.json())
