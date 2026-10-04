# Remote OK adapter; API_URL supplies jobs and the first response item is metadata.
import httpx

from jagent.models import Posting

API_URL = "https://remoteok.com/api"


def parse_response(data: list[dict]) -> list[Posting]:
    return [
        Posting(
            source="remoteok",
            source_id=str(item["id"]),
            url=item["url"],
            company=item["company"],
            title=item["position"],
            locations=[item["location"].strip()] if item.get("location", "").strip() else [],
            remote=True,
            posted_at=item["date"],
            description=item["description"],
        )
        for item in data[1:]
    ]


def fetch() -> list[Posting]:
    response = httpx.get(API_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_response(response.json())
