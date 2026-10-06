# ATS adapters; PLATFORM_URLS maps public board APIs and slug identifies each company board.
from datetime import UTC, datetime
import re

import httpx

from jagent.models import Posting

PLATFORM_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
}


def utc_datetime(value):
    if not value:
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000, UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def locations(value):
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        return [str(item) for item in value.values() if item]
    return []


def parse_greenhouse(data, slug):
    return [
        Posting(
            source=f"ats:greenhouse:{slug}", source_id=str(job["id"]),
            url=job.get("absolute_url"), company=slug, title=job["title"],
            locations=locations(job.get("location")), description=job.get("content"),
            posted_at=utc_datetime(job.get("updated_at") or job.get("first_published")),
        )
        for job in data.get("jobs", [])
    ]


def parse_lever(data, slug):
    return [
        Posting(
            source=f"ats:lever:{slug}", source_id=job["id"],
            url=job.get("hostedUrl") or job.get("applyUrl"), company=slug,
            title=job["text"], locations=locations(job.get("categories", {}).get("location")),
            description=job.get("descriptionPlain") or job.get("description"),
            posted_at=utc_datetime(job.get("createdAt")),
        )
        for job in data
    ]


def parse_ashby(data, slug):
    return [
        Posting(
            source=f"ats:ashby:{slug}", source_id=job["id"],
            url=job.get("jobUrl") or job.get("applyUrl"), company=slug,
            title=job["title"], locations=locations(job.get("location")),
            description=job.get("descriptionHtml") or job.get("descriptionPlain"),
            posted_at=utc_datetime(job.get("publishedAt")),
        )
        for job in data.get("jobs", [])
    ]


def parse_smartrecruiters(data, slug):
    return [
        Posting(
            source=f"ats:smartrecruiters:{slug}", source_id=job["id"],
            url=job.get("ref") or f"https://jobs.smartrecruiters.com/{slug}/{job['id']}",
            company=slug, title=job["name"], locations=locations(job.get("location")),
            description=job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text"),
            posted_at=utc_datetime(job.get("releasedDate")),
        )
        for job in data.get("content", [])
    ]


PARSERS = {
    "greenhouse": parse_greenhouse,
    "lever": parse_lever,
    "ashby": parse_ashby,
    "smartrecruiters": parse_smartrecruiters,
}


def fetch(platform, slug):
    if platform not in PLATFORM_URLS:
        raise ValueError(f"Unknown ATS platform: {platform}")
    params = {"content": "true"} if platform == "greenhouse" else {}
    if platform == "smartrecruiters":
        params = {"limit": 100}
    response = httpx.get(
        PLATFORM_URLS[platform].format(slug=slug), params=params,
        timeout=30, follow_redirects=True,
    )
    response.raise_for_status()
    return PARSERS[platform](response.json(), slug)


BOARD_PATTERNS = {
    "greenhouse": re.compile(
        r"(?:boards|job-boards)\.greenhouse\.io/([a-z0-9_-]+)", re.IGNORECASE,
    ),
    "lever": re.compile(r"jobs\.lever\.co/([a-z0-9_-]+)", re.IGNORECASE),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_-]+)", re.IGNORECASE),
    "smartrecruiters": re.compile(
        r"jobs\.smartrecruiters\.com/([a-z0-9_-]+)", re.IGNORECASE,
    ),
}


def extract_company_slugs(text):
    found = set()
    for platform, pattern in BOARD_PATTERNS.items():
        for match in pattern.finditer(text or ""):
            found.add((platform, match.group(1).lower()))
    return found
