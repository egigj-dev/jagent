# Pagination tests; NOW fixes the UTC window and fixture jobs supply realistic fields.
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from jagent.sources import himalayas, remotive

NOW = datetime(2026, 10, 4, 20, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def empty_database(monkeypatch):
    monkeypatch.setattr(himalayas, "known_source_ids", lambda: set())


def freeze_time(monkeypatch, adapter):
    clock = Mock()
    clock.now.return_value = NOW
    clock.fromtimestamp = datetime.fromtimestamp
    clock.fromisoformat = datetime.fromisoformat
    monkeypatch.setattr(adapter, "datetime", clock)


def job(source_id, age):
    item = json.loads((FIXTURES / "himalayas.json").read_text())["jobs"][0]
    return {**item, "guid": source_id, "pubDate": int((NOW - age).timestamp())}


def test_himalayas_paginates_deduplicates_and_finishes_boundary_page(monkeypatch):
    freeze_time(monkeypatch, himalayas)
    events = []
    pages = [
        {"jobs": [job("one", timedelta(days=1))], "nextCursor": "second"},
        {"jobs": [job("one", timedelta(days=1)), job("two", timedelta(days=2))],
         "nextCursor": "third"},
        {"jobs": [job("boundary", timedelta(days=7)),
                  job("old", timedelta(days=7, seconds=1))], "nextCursor": "unused"},
    ]

    def get(url, **kwargs):
        events.append(dict(kwargs["params"]))
        return httpx.Response(200, json=pages.pop(0), request=httpx.Request("GET", url))

    monkeypatch.setattr(himalayas.httpx, "get", get)
    monkeypatch.setattr(himalayas.time, "sleep", lambda seconds: events.append(seconds))
    postings = himalayas.fetch()
    assert [posting.source_id for posting in postings] == ["one", "two", "boundary"]
    assert events == [{"limit": 20}, 1, {"limit": 20, "cursor": "second"},
                      1, {"limit": 20, "cursor": "third"}]
    assert not pages


@pytest.mark.parametrize("page", [
    {"jobs": []},
    {"jobs": [job("one", timedelta(days=1))]},
    {"jobs": [job("one", timedelta(days=1))], "nextCursor": None},
])
def test_himalayas_stops_at_end_of_feed(monkeypatch, page):
    freeze_time(monkeypatch, himalayas)
    get = Mock(return_value=httpx.Response(
        200, json=page, request=httpx.Request("GET", himalayas.API_URL)))
    monkeypatch.setattr(himalayas.httpx, "get", get)
    assert len(himalayas.fetch()) == len(page["jobs"])
    assert get.call_count == 1


def test_himalayas_repeated_cursor_fails_instead_of_looping(monkeypatch):
    freeze_time(monkeypatch, himalayas)
    page = {"jobs": [job("one", timedelta(days=1))], "nextCursor": "same"}
    monkeypatch.setattr(himalayas.httpx, "get", lambda url, **kwargs:
                        httpx.Response(200, json=page, request=httpx.Request("GET", url)))
    monkeypatch.setattr(himalayas.time, "sleep", lambda seconds: None)
    with pytest.raises(ValueError, match="repeated pagination cursor"):
        himalayas.fetch()


def test_remotive_keeps_all_jobs_with_one_request(monkeypatch):
    freeze_time(monkeypatch, remotive)
    item = json.loads((FIXTURES / "remotive.json").read_text())["jobs"][0]
    data = {"jobs": [
        {**item, "id": name, "publication_date": date.isoformat()}
        for name, date in [
            ("recent", NOW - timedelta(days=1)),
            ("boundary", NOW - timedelta(days=7)),
            ("old", NOW - timedelta(days=7, seconds=1)),
            ("future", NOW + timedelta(seconds=1)),
        ]
    ]}
    get = Mock(return_value=httpx.Response(
        200, json=data, request=httpx.Request("GET", remotive.API_URL)))
    monkeypatch.setattr(remotive.httpx, "get", get)
    assert [posting.source_id for posting in remotive.fetch()] == ["recent", "boundary", "old", "future"]
    assert get.call_count == 1
    assert get.call_args.args == (remotive.API_URL,)


def test_himalayas_existing_database_ignores_cutoff_and_stops_on_known_page(monkeypatch):
    freeze_time(monkeypatch, himalayas)
    monkeypatch.setattr(himalayas, "known_source_ids", lambda: {"known"})
    monkeypatch.setattr(himalayas.time, "sleep", lambda seconds: None)
    pages = [
        {"jobs": [job("new", timedelta(days=8))], "nextCursor": "second"},
        {"jobs": [job("known", timedelta(days=9)), job("also-new", timedelta(days=10))],
         "nextCursor": "unused"},
    ]
    calls = []

    def get(url, **kwargs):
        calls.append(dict(kwargs["params"]))
        return httpx.Response(200, json=pages.pop(0), request=httpx.Request("GET", url))

    monkeypatch.setattr(himalayas.httpx, "get", get)
    assert [p.source_id for p in himalayas.fetch()] == ["new", "known", "also-new"]
    assert len(calls) == 2


def test_himalayas_live_order_fixture_is_newest_first():
    data = json.loads((FIXTURES / "himalayas_order.json").read_text())
    dates = [item["pubDate"] for item in data["jobs"]]
    assert len(dates) == 5
    assert dates == sorted(dates, reverse=True)
