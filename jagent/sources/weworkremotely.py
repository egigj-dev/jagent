# We Work Remotely RSS adapter; API_URL items use guid identity and RFC dates.
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import httpx

from jagent.models import Posting

API_URL = "https://weworkremotely.com/remote-jobs.rss"


def parse_response(data: str) -> list[Posting]:
    postings = []
    for item in ET.fromstring(data).findall("./channel/item"):
        full_title = item.findtext("title", "").strip()
        company, separator, title = full_title.partition(": ")
        location = item.findtext("region", "").strip()
        url = item.findtext("link", "").strip()
        postings.append(Posting(
            source="weworkremotely", source_id=item.findtext("guid") or url,
            url=url, company=company if separator else None,
            title=title if separator else full_title,
            locations=[location] if location else [], remote=True,
            posted_at=parsedate_to_datetime(item.findtext("pubDate")),
            description=item.findtext("description", ""),
        ))
    return postings


def fetch() -> list[Posting]:
    response = httpx.get(API_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_response(response.text)
