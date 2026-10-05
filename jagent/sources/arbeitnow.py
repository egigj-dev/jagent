# Arbeitnow adapter; API_URL returns jobs with stable slugs and Unix timestamps.
from datetime import UTC, datetime

import httpx

from jagent.models import Posting

API_URL = "https://www.arbeitnow.com/api/job-board-api"


def parse_response(data: dict) -> list[Posting]:
    return [
        Posting(
            source="arbeitnow", source_id=item["slug"], url=item["url"],
            company=item["company_name"], title=item["title"],
            locations=[item["location"]] if item.get("location") else [],
            remote=item["remote"],
            posted_at=datetime.fromtimestamp(item["created_at"], UTC),
            description=item["description"],
        )
        for item in data["data"]
    ]


def fetch() -> list[Posting]:
    response = httpx.get(API_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_response(response.json())
