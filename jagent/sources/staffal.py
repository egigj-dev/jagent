# Staff.al adapter; listing URLs come from the sitemap and detail JSON supplies job fields.
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx

from jagent.db import connect
from jagent.models import Posting

LIST_URL = "https://staff.al/sq/job-list"
SITEMAP_URL = "https://staff.al/sitemap.xml"


def parse_response(html: str) -> list[Posting]:
    soup = BeautifulSoup(html, "html.parser")
    postings = []
    for card in soup.select(".job-card, [data-testid='job-card']"):
        link = card.select_one("a[href]")
        title = card.select_one("h1, h2, h3, [class*='title']")
        if link is None or title is None:
            continue
        url = link.get("href", "")
        match = re.search(r"/job-list/([a-f\d]+)", url)
        if not match:
            continue
        company = card.select_one("[class*='company']")
        description = card.select_one("[class*='description']")
        postings.append(Posting(
            source="staffal", source_id=match.group(1), url=url,
            title=title.get_text(" ", strip=True),
            company=company.get_text(" ", strip=True) if company else None,
            description=description.get_text("\n", strip=True) if description else None,
        ))
    return postings


def parse_sitemap(xml: str) -> list[Posting]:
    postings = []
    for node in ET.fromstring(xml).iter():
        if node.tag.rsplit("}", 1)[-1] != "loc" or not node.text:
            continue
        url = node.text.strip()
        match = re.search(r"/sq/job-list/([a-f\d]+)(?:/|$)", url)
        if not match:
            continue
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        title = slug.replace("-", " ").title()
        postings.append(Posting(
            source="staffal", source_id=match.group(1), url=url, title=title,
            company=None,
        ))
    return postings


def parse_detail(html: str, posting: Posting) -> Posting:
    soup = BeautifulSoup(html, "html.parser")
    job = None
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "JobPosting":
            job = data
            break
    if job:
        company = job.get("hiringOrganization", {}).get("name")
        posted_at = None
        expires_at = None
        if job.get("datePosted"):
            posted_at = datetime.fromisoformat(job["datePosted"].replace("Z", "+00:00"))
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=UTC)
            else:
                posted_at = posted_at.astimezone(UTC)
        if job.get("validThrough"):
            expires_at = datetime.fromisoformat(job["validThrough"].replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            else:
                expires_at = expires_at.astimezone(UTC)
        return posting.model_copy(update={
            "title": job.get("title") or posting.title,
            "company": company or posting.company,
            "description": job.get("description"),
            "posted_at": posted_at,
            "expires_at": expires_at,
        })
    return posting.model_copy(update={
        "title": soup.title.get_text(" ", strip=True) if soup.title else posting.title,
    })


def complete_source_ids() -> set[str]:
    with connect() as connection:
        return {row[0] for row in connection.execute(
            "SELECT source_id FROM postings "
            "WHERE source = 'staffal' AND posted_at IS NOT NULL "
            "AND expires_at IS NOT NULL"
        )}


def fetch() -> list[Posting]:
    response = httpx.get(LIST_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    postings = parse_response(response.text)
    if not postings:
        sitemap_response = httpx.get(SITEMAP_URL, timeout=30, follow_redirects=True)
        sitemap_response.raise_for_status()
        postings = parse_sitemap(sitemap_response.text)
    known_ids = complete_source_ids()
    fetched_detail = False
    for index, posting in enumerate(postings):
        if posting.source_id in known_ids or posting.description:
            continue
        if fetched_detail:
            time.sleep(1)
        detail_response = httpx.get(posting.url, timeout=30, follow_redirects=True)
        detail_response.raise_for_status()
        postings[index] = parse_detail(detail_response.text, posting)
        fetched_detail = True
    return postings
