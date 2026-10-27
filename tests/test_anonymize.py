# Privacy tests; invented identifiers exercise redaction, whole-word audits and parser identity preservation.
import json

import pytest

from evals.anonymize import company_token, identifier_hashes, redact_record, safe_url
from evals.privacy import audit, remaining_identifiers
from jagent.runner import make_dedupe_key


def test_posting_redaction_preserves_skills_and_removes_contacts():
    record = {"company": "Invented Example Ltd", "description": (
        "Join Invented Example Ltd. Python, Docker and C++ required. "
        "Contact Jane Person at " + "person-1@" + "invented.example.net or "
        + "+1" + " 212" + "-555" + "-0199. "
        + "Visit 123" + " Example Street. " + "https://" + "invented.example.net/careers"
    )}
    result, identifiers = redact_record(record, record["company"])
    text = json.dumps(result)
    assert "Python, Docker and C++ required" in text
    assert "Jane Person" not in text and "jane@invented" not in text
    assert "+1 212" not in text and "123" + " Example Street" not in text
    assert result["company"] == company_token(record["company"])
    assert not list(remaining_identifiers(text, identifiers))


@pytest.mark.parametrize("url", [
    "https://" + "jobs.lever.co/invented/abc",
    "https://" + "djinni.co/jobs/123-invented-role/",
    "https://" + "invented.example.net/careers",
    "https://news.ycombinator.com/item?id=123",
])
def test_url_tokens_are_deterministic_and_idempotent(url):
    result = safe_url(url)
    assert safe_url(url) == result
    assert safe_url(result) == result
    if "lever.co" in url or "djinni.co" in url:
        assert result.split('/')[2] == url.split('/')[2]


def test_company_audit_is_case_sensitive_and_uses_word_boundaries():
    hashes = identifier_hashes(["Invented Example"])
    assert list(remaining_identifiers("Join Invented Example today", hashes)) == ["Invented Example"]
    assert not list(remaining_identifiers("invented example or Invented Examples", hashes))


def test_company_tokens_preserve_deduplication_equivalence():
    first, second, different = "Example, Inc.", "example inc", "Another Company"
    assert make_dedupe_key(first, "Engineer") == make_dedupe_key(second, "Engineer")
    assert company_token(first) == company_token(second)
    assert company_token(first) != company_token(different)


def test_public_fixture_privacy_check_is_silent(capsys):
    assert audit()
    assert capsys.readouterr().out == ""
