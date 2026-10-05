# HN hiring adapter; SEARCH_URL finds stories and ITEM_URL supplies their comments.
from html import unescape
import re

import httpx

from jagent.models import Posting

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
ITEM_URL = "https://hn.algolia.com/api/v1/items/"


def latest_story(hits: list[dict]) -> str:
    stories = [hit for hit in hits
               if hit.get("title", "").startswith("Ask HN: Who is hiring?")]
    if not stories:
        raise ValueError("No HN hiring story found")
    return str(max(stories, key=lambda hit: hit["created_at_i"])["objectID"])


def parse_response(data: dict) -> list[Posting]:
    postings = []
    for item in data["children"]:
        description = item.get("text")
        if not description or item.get("deleted") or item.get("dead"):
            continue
        text = re.sub(r"<\s*(?:p|br)\b[^>]*>", "\n", description, flags=re.I)
        text = unescape(re.sub(r"<[^>]+>", "", text))
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        company = None
        title = lines[0]
        locations = None
        if "|" in lines[0]:
            parts = [part.strip() for part in lines[0].split("|")]
            company, title = parts[:2]
            if len(parts) > 2:
                locations = [parts[2]] if parts[2] else []
        postings.append(Posting(
            source="hn_hiring", source_id=str(item["id"]),
            url=f"https://news.ycombinator.com/item?id={item['id']}",
            company=company, title=title, locations=locations,
            description=description, posted_at=item["created_at"],
        ))
    return postings


def fetch() -> list[Posting]:
    hits = []
    page = 0
    while True:
        response = httpx.get(SEARCH_URL, params={
            "tags": "story,author_whoishiring",
            "query": "Ask HN: Who is hiring?", "hitsPerPage": 1000, "page": page,
        }, timeout=30, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        hits.extend(data["hits"])
        page += 1
        if page >= data["nbPages"]:
            break
    response = httpx.get(ITEM_URL + latest_story(hits), timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_response(response.json())
