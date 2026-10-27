# Filter tests; NOW fixes UTC activity dates and FILTERS defines search terms for the cases below.
from datetime import UTC, datetime, timedelta

import pytest

from jagent.filters import is_active, matches, passing_postings

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
FILTERS = {
    "countries": ["Germany", "Berlin", "Albania", "Shqiperi", "Tirane", "Istanbul"],
    "remote_regions": ["Worldwide", "Europe", "EMEA", "EU"],
    "remote_excluded": ["US only", "US based"],
    "exclude_title_keywords": ["sales", "account executive"],
}


def posting(**updates):
    return {
        "title": "Software Engineer", "locations": ["Berlin"], "remote": False,
        "expires_at": None, "posted_at": None, "first_seen": NOW,
        **updates,
    }


@pytest.mark.parametrize("text,term,expected", [
    ("İstanbul", "istanbul", True),
    ("Tiranë", "tirane", True),
    ("Shqipëri", "shqiperi", True),
    ("istanbul", "İstanbul", True),
    ("romania", "oman", False),
    ("seoul", "eu", False),
    ("EU-based", "eu", True),
    ("UK (London)", "uk", True),
    ("salesforce developer", "sales", False),
])
def test_normalization_and_word_boundaries(text, term, expected):
    assert matches(text, term) is expected


@pytest.mark.parametrize("updates,expected", [
    ({"expires_at": NOW + timedelta(seconds=1), "posted_at": NOW - timedelta(days=60)}, True),
    ({"expires_at": NOW}, False),
    ({"expires_at": NOW - timedelta(seconds=1)}, False),
    ({"posted_at": NOW - timedelta(days=30)}, True),
    ({"posted_at": NOW - timedelta(days=30, seconds=1)}, False),
    ({"posted_at": None, "first_seen": NOW - timedelta(days=29)}, True),
    ({"posted_at": None, "first_seen": NOW - timedelta(days=31)}, False),
    ({"posted_at": NOW + timedelta(days=1)}, False),
])
def test_activity(updates, expected):
    assert is_active(posting(**updates), NOW) is expected


@pytest.mark.parametrize("updates,expected", [
    ({"remote": True, "locations": []}, True),
    ({"remote": True, "locations": None}, True),
    ({"remote": True, "locations": ["Worldwide"]}, True),
    ({"remote": True, "locations": ["Europe"]}, True),
    ({"remote": True, "locations": ["EMEA"]}, True),
    ({"remote": True, "locations": ["Germany"]}, True),
    ({"remote": True, "locations": ["Japan"]}, False),
    ({"remote": True, "locations": ["Remote"]}, False),
    ({"remote": False, "locations": ["Remote EU"]}, True),
    ({"remote": False, "locations": ["Remote Japan"]}, False),
    ({"remote": False, "locations": ["İstanbul"]}, True),
    ({"remote": False, "locations": ["Tiranë, Shqipëri"]}, True),
    ({"remote": False, "locations": ["Tokyo"]}, False),
    ({"remote": False, "locations": []}, False),
    ({"remote": False, "locations": ["EU"]}, False),
    ({"remote": True, "locations": ["Europe", "US only"]}, False),
    ({"title": "Engineer (US based)"}, False),
    ({"title": "Sales Engineer"}, False),
    ({"title": "Account Executive"}, False),
    ({"title": "Salesforce Engineer"}, True),
    ({"expires_at": NOW - timedelta(days=1)}, False),
])
def test_all_filters(updates, expected):
    candidate = posting(**updates)
    assert passing_postings([candidate], FILTERS, NOW) == ([candidate] if expected else [])
