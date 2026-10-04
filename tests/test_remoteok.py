# Test the real API fixture; FIXTURE holds metadata followed by Remote OK jobs.
import json
from datetime import UTC
from pathlib import Path

import httpx

from jagent.sources import remoteok

FIXTURE = Path(__file__).parent / "fixtures" / "remoteok.json"


def test_fetch_parses_real_response(monkeypatch):
    data = json.loads(FIXTURE.read_text())

    def get(url, **kwargs):
        assert url == remoteok.API_URL
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(remoteok.httpx, "get", get)
    postings = remoteok.fetch()
    assert len(postings) == len(data) - 1 == 99
    first = postings[0]
    assert first.source == "remoteok"
    assert first.source_id == "1137460"
    assert first.company == "Empire Assets"
    assert first.title == "Junior Crypto Analyst & Trader"
    assert first.url == data[1]["url"]
    assert first.description == data[1]["description"]
    assert first.locations == []
    assert first.remote is True
    assert first.posted_at.tzinfo == UTC
    assert all(posting.source_id for posting in postings)


def test_fetch_raises_on_http_error(monkeypatch):
    import pytest

    monkeypatch.setattr(remoteok.httpx, "get", lambda url, **kwargs:
                        httpx.Response(503, request=httpx.Request("GET", url)))
    with pytest.raises(httpx.HTTPStatusError):
        remoteok.fetch()
