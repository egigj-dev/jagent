# KosovoJob adapter; LIST_URL contains cards and details fill unseen descriptions.
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import httpx

from jagent.db import connect
from jagent.models import Posting

LIST_URL = "https://kosovajob.com/"


def parse_response(html: str) -> list[Posting]:
    soup = BeautifulSoup(html, "html.parser")
    postings = []
    for card in soup.select(".jobListCnts"):
        link = card.select_one("a[href]")
        title = card.select_one(".jobListTitle")
        if link is None or title is None:
            continue
        url = urljoin(LIST_URL, link["href"])
        company = urlparse(url).path.strip("/").split("/")[0].replace("-", " ").title()
        city = card.select_one(".jobListCity")
        expires_at = None
        if title.get("date"):
            expires_at = datetime.strptime(
                title["date"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=ZoneInfo("Europe/Belgrade")).astimezone(UTC)
        postings.append(Posting(
            source="kosovajob", source_id=url, url=url, company=company,
            title=title.get_text(" ", strip=True),
            locations=[city.get_text(" ", strip=True)] if city else [],
            expires_at=expires_at,
        ))
    return postings


def parse_detail(html: str, posting: Posting) -> Posting:
    soup = BeautifulSoup(html, "html.parser")
    company = soup.select_one(".containerLeftAreaTopAreaRightTitleComp")
    description = soup.select_one(".containerLeftAreDescription")
    title = soup.title.get_text(" ", strip=True) if soup.title else posting.title
    return posting.model_copy(update={
        "title": title or posting.title,
        "company": company.get_text(" ", strip=True) if company else posting.company,
        "description": description.get_text("\n", strip=True) if description else None,
    })


def known_source_ids() -> set[str]:
    with connect() as connection:
        return {row[0] for row in connection.execute(
            "SELECT source_id FROM postings WHERE source = 'kosovajob'"
        )}


def fetch() -> list[Posting]:
    response = httpx.get(LIST_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    postings = parse_response(response.text)
    known_ids = known_source_ids()
    fetched_detail = False
    for index, posting in enumerate(postings):
        if posting.source_id in known_ids:
            continue
        if fetched_detail:
            time.sleep(1)
        detail_response = httpx.get(posting.url, timeout=30, follow_redirects=True)
        detail_response.raise_for_status()
        postings[index] = parse_detail(detail_response.text, posting)
        fetched_detail = True
    return postings
