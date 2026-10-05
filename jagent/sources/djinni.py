# Djinni adapter; LIST_URL cards and JSON-LD contain job fields and UTC dates.
import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from jagent.db import connect
from jagent.models import Posting

LIST_URL = "https://djinni.co/jobs/"
MAX_BOOTSTRAP_PAGES = 10


def parse_response(html: str) -> list[Posting]:
    soup = BeautifulSoup(html, "html.parser")
    jobs_by_id = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        jobs = data if isinstance(data, list) else [data]
        for job in jobs:
            if isinstance(job, dict) and job.get("@type") == "JobPosting":
                jobs_by_id[str(job.get("identifier", ""))] = job
    postings = []
    for card in soup.select(".job-item"):
        link = card.select_one("a.job_item__header-link[href]")
        title = card.select_one(".job-item__position")
        company = link.select_one("span.small") if link else None
        if link is None or title is None or company is None:
            continue
        url = urljoin(LIST_URL, link["href"])
        match = re.search(r"/jobs/(\d+)-", url)
        if not match:
            continue
        job = jobs_by_id.get(match.group(1), {})
        posted_at = None
        if job.get("datePosted"):
            posted_at = datetime.fromisoformat(job["datePosted"].replace("Z", "+00:00"))
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=UTC)
            else:
                posted_at = posted_at.astimezone(UTC)
        description = card.select_one(".js-original-text")
        postings.append(Posting(
            source="djinni", source_id=match.group(1), url=url,
            company=company.get_text(" ", strip=True),
            title=title.get_text(" ", strip=True),
            description=description.get_text("\n", strip=True) if description else None,
            posted_at=posted_at,
        ))
    return postings


def known_source_ids() -> set[str]:
    with connect() as connection:
        return {row[0] for row in connection.execute(
            "SELECT source_id FROM postings WHERE source = 'djinni'"
        )}


def fetch() -> list[Posting]:
    known_ids = known_source_ids()
    postings = []
    bootstrap = not known_ids
    page = 1
    while True:
        if page > 1:
            time.sleep(1)
        response = httpx.get(
            LIST_URL, params={"page": page}, timeout=30, follow_redirects=True,
        )
        response.raise_for_status()
        page_postings = parse_response(response.text)
        if not page_postings:
            break
        postings.extend(page_postings)
        page_ids = {posting.source_id for posting in page_postings}
        if known_ids & page_ids and not bootstrap:
            break
        if bootstrap and page >= MAX_BOOTSTRAP_PAGES:
            break
        page += 1
    return postings
