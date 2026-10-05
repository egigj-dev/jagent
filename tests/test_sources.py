# Adapter fixture tests; CASES defines expected first-job fields for each source.
import json
from datetime import UTC
from pathlib import Path

import httpx
import pytest

from jagent.sources import arbeitnow, himalayas, hn_hiring, jobicy, remotive, weworkremotely

FIXTURES = Path(__file__).parent / "fixtures"
CASES = [
    (remotive, "remotive.json", 18, "1749306", "Coalition Technologies",
     "Freelance Copywriter", ["Worldwide"], True),
    (arbeitnow, "arbeitnow.json", 325,
     "anwendungsarchitekt-full-stack-java-spring-react-k8s-munich-321699",
     "Auxilius.ai", "Anwendungsarchitekt - Full-Stack Java/Spring, React, K8s (m/w/d)",
     ["Munich"], False),
    (himalayas, "himalayas.json", 20,
     "https://himalayas.app/companies/empower-ai-inc/jobs/tier-i-service-desk-agent-junior-extended-hours",
     "Empower AI Inc.", "TIER I SERVICE DESK AGENT (JUNIOR, EXTENDED HOURS)",
     ["United States"], True),
    (jobicy, "jobicy.json", 200, "154514", "Canonical",
     "Solutions Architect for Automotive", ["Anywhere"], True),
    (weworkremotely, "weworkremotely.xml", 89,
     "https://weworkremotely.com/remote-jobs/assemblyai-senior-research-engineer",
     "AssemblyAI", "Senior Research Engineer", ["Anywhere in the World"], True),
]


@pytest.mark.parametrize("adapter,filename,count,source_id,company,title,locations,remote", CASES)
def test_parses_fixture(monkeypatch, adapter, filename, count, source_id,
                             company, title, locations, remote):
    def get(url, **kwargs):
        assert url == adapter.API_URL
        return httpx.Response(200, content=(FIXTURES / filename).read_bytes(),
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(adapter.httpx, "get", get)
    if adapter in (remotive, himalayas):
        postings = adapter.parse_response(json.loads((FIXTURES / filename).read_text()))
    else:
        postings = adapter.fetch()
    assert len(postings) == count
    first = postings[0]
    assert first.source == filename.split(".")[0]
    assert first.source_id == source_id
    assert first.company == company
    assert first.title == title
    assert first.locations == locations
    assert first.remote is remote
    assert first.url.startswith("https://")
    assert first.description
    assert all(posting.posted_at.tzinfo == UTC for posting in postings)
    assert len({posting.source_id for posting in postings}) == count


def test_hn_fetch_latest_story_and_top_level_comments(monkeypatch):
    search = json.loads((FIXTURES / "hn_hiring_search.json").read_text())
    story = json.loads((FIXTURES / "hn_hiring.json").read_text())
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url == hn_hiring.SEARCH_URL:
            assert kwargs["params"]["tags"] == "story,author_whoishiring"
            data = search
        else:
            assert url == hn_hiring.ITEM_URL + "49922569"
            data = story
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(hn_hiring.httpx, "get", get)
    postings = hn_hiring.fetch()
    assert len(calls) == 2
    assert len(postings) == len([item for item in story["children"] if item.get("text")])
    first = postings[0]
    assert first.source == "hn_hiring"
    assert first.source_id == "49922584"
    assert first.title == ("PrairieLearn (Remote US) — Full-Stack Software Engineer — "
                           "TypeScript / Postgres / React / AI")
    assert first.url == "https://news.ycombinator.com/item?id=49922584"
    assert first.description == story["children"][0]["text"]
    assert first.posted_at.tzinfo == UTC
    assert first.remote is None
    assert first.company is None
    assert first.locations is None
    top_level_ids = {str(item["id"]) for item in story["children"]}
    assert all(posting.source_id in top_level_ids for posting in postings)
    assert "49928484" not in {posting.source_id for posting in postings}


def test_hn_search_checks_all_pages_and_excludes_other_threads(monkeypatch):
    pages = [
        {"hits": [{"title": "Ask HN: Who is hiring? (Older)",
                   "objectID": "1", "created_at_i": 1}], "nbPages": 2},
        {"hits": [{"title": "Ask HN: Who is hiring? (Latest)",
                   "objectID": "2", "created_at_i": 2},
                  {"title": "Ask HN: Who wants to be hired?",
                   "objectID": "3", "created_at_i": 3}], "nbPages": 2},
    ]

    def get(url, **kwargs):
        if url == hn_hiring.SEARCH_URL:
            data = pages[kwargs["params"]["page"]]
        else:
            assert url == hn_hiring.ITEM_URL + "2"
            data = {"children": []}
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(hn_hiring.httpx, "get", get)
    assert hn_hiring.fetch() == []


def test_hn_skips_deleted_comments_and_preserves_inline_title_text():
    story = {"children": [
        {"text": None}, {"text": "Removed", "deleted": True},
        {"id": 7, "text": "<p>Acme <b>Inc</b> | Engineer<br>Details</p>",
         "created_at": "2026-10-01T15:00:00Z", "children": [{"text": "Reply"}]},
    ]}
    postings = hn_hiring.parse_response(story)
    assert len(postings) == 1
    assert postings[0].title == "Acme Inc | Engineer"


@pytest.mark.parametrize("adapter", [case[0] for case in CASES] + [hn_hiring])
def test_http_errors_are_reported(monkeypatch, adapter):
    monkeypatch.setattr(himalayas, "known_source_ids", lambda: set())
    def get(url, **kwargs):
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr(adapter.httpx, "get", get)
    with pytest.raises(httpx.HTTPStatusError):
        adapter.fetch()
