# Himalayas adapter; known_ids stops incremental paging; cutoff bounds the first sync.
from datetime import UTC, datetime, timedelta
import time

import httpx

from jagent.models import Posting
from jagent.db import connect

API_URL = "https://himalayas.app/jobs/api"


def parse_response(data: dict) -> list[Posting]:
    return [
        Posting(
            source="himalayas", source_id=item["guid"], url=item["guid"],
            company=item["companyName"], title=item["title"],
            locations=item.get("locationRestrictions", []), remote=True,
            posted_at=datetime.fromtimestamp(item["pubDate"], UTC),
            description=item["description"],
        )
        for item in data["jobs"]
    ]


def known_source_ids() -> set[str]:
    with connect() as connection:
        return {row[0] for row in connection.execute(
            "SELECT source_id FROM postings WHERE source = 'himalayas'"
        )}


def fetch() -> list[Posting]:
    known_ids = known_source_ids()
    now = datetime.now(UTC)
    cutoff = None if known_ids else now - timedelta(days=7)
    postings = {}
    params = {"limit": 20}
    cursors = set()
    while True:
        response = httpx.get(API_URL, params=params, timeout=30, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        page = parse_response(data)
        for posting in page:
            if cutoff is None or cutoff <= posting.posted_at <= now:
                postings[posting.source_id] = posting
        # The feed is newest first; finish the boundary page before stopping.
        if (not page
                or any(posting.source_id in known_ids for posting in page)
                or (cutoff is not None and any(posting.posted_at < cutoff for posting in page))):
            break
        cursor = data.get("nextCursor")
        if not cursor:
            break
        if cursor in cursors:
            raise ValueError("Himalayas returned a repeated pagination cursor")
        cursors.add(cursor)
        params["cursor"] = cursor
        time.sleep(1)
    return list(postings.values())
