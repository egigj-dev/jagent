# HTML source tests; FIXTURES holds the saved listing pages and CARD_SELECTORS match cards.
from pathlib import Path
from unittest.mock import Mock

from bs4 import BeautifulSoup
import httpx
import pytest

from jagent.models import Posting
from jagent.sources import djinni, kosovajob, staffal

FIXTURES = Path(__file__).parent / "fixtures"
CASES = [
    (staffal, "staffal.html", ".job-card, [data-testid='job-card']"),
    (kosovajob, "kosovajob.html", ".jobListCnts"),
    (djinni, "djinni.html", ".job-item"),
]


@pytest.mark.parametrize("adapter,filename,selector", CASES)
def test_listing_cards_parse_with_required_fields(adapter, filename, selector):
    html = (FIXTURES / filename).read_text()
    card_count = len(BeautifulSoup(html, "html.parser").select(selector))
    postings = adapter.parse_response(html)
    assert len(postings) == card_count
    assert all(posting.title and posting.company and posting.url for posting in postings)


def test_expiry_dates_parse_as_utc():
    kosovo = kosovajob.parse_response((FIXTURES / "kosovajob.html").read_text())
    assert all(posting.expires_at and posting.expires_at.utcoffset().total_seconds() == 0
               for posting in kosovo)

    staff_posting = Posting(
        source="staffal", source_id="one", url="https://staff.al/one", title="One",
    )
    html = """<script type="application/ld+json">{
        "@type": "JobPosting", "title": "One",
        "datePosted": "2026-10-01T10:00:00Z",
        "validThrough": "2026-10-31T10:00:00Z"
    }</script>"""
    parsed = staffal.parse_detail(html, staff_posting)
    assert parsed.expires_at.isoformat() == "2026-10-31T10:00:00+00:00"


def test_djinni_empty_database_fetches_ten_pages(monkeypatch):
    monkeypatch.setattr(djinni, "known_source_ids", lambda: set())
    monkeypatch.setattr(djinni.time, "sleep", lambda seconds: None)
    get = Mock(side_effect=lambda url, **kwargs: httpx.Response(
        200, text=str(kwargs["params"]["page"]), request=httpx.Request("GET", url),
    ))
    monkeypatch.setattr(djinni.httpx, "get", get)
    monkeypatch.setattr(djinni, "parse_response", lambda page: [Posting(
        source="djinni", source_id=page, url=f"https://djinni.co/jobs/{page}-job",
        company="Company", title="Job",
    )])
    assert len(djinni.fetch()) == 10
    assert get.call_count == 10


def test_djinni_existing_database_stops_on_first_page(monkeypatch):
    monkeypatch.setattr(djinni, "known_source_ids", lambda: {"known", "older"})
    get = Mock(return_value=httpx.Response(
        200, text="known", request=httpx.Request("GET", djinni.LIST_URL),
    ))
    monkeypatch.setattr(djinni.httpx, "get", get)
    monkeypatch.setattr(djinni, "parse_response", lambda page: [Posting(
        source="djinni", source_id="known", url="https://djinni.co/jobs/1-job",
        company="Company", title="Job",
    )])
    assert len(djinni.fetch()) == 1
    assert get.call_count == 1
