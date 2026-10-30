# Privacy tests; invented identifiers exercise redaction, whole-word audits and parser identity preservation.
import json

import pytest

from evals import privacy
from evals.anonymize import company_token, employer_identifiers, identifier_hashes, redact_record, safe_url
from evals.data import save
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


def test_company_audit_uses_word_boundaries():
    hashes = identifier_hashes(["Invented Example"])
    assert list(remaining_identifiers("Join Invented Example today", hashes)) == ["Invented Example"]
    assert list(remaining_identifiers("invented example or Invented Examples", hashes)) == ["invented example"]


def test_company_tokens_preserve_deduplication_equivalence():
    first, second, different = "Example, Inc.", "example inc", "Another Company"
    assert make_dedupe_key(first, "Engineer") == make_dedupe_key(second, "Engineer")
    assert company_token(first) == company_token(second)
    assert company_token(first) != company_token(different)


def test_public_fixture_privacy_check_is_silent(capsys):
    assert audit()
    assert capsys.readouterr().out == ""


def test_dr_ansay_body_variant_is_redacted():
    record = {"id": 34491, "company": "Dr. Ansay", "description": "Join DrAnsay. Python and SQL required."}
    result, identifiers = redact_record(record, record["company"])
    assert result["description"] == f"Join {company_token(record['company'])}. Python and SQL required."
    assert not list(remaining_identifiers(json.dumps(result), identifiers))


def test_dr_ansay_body_variant_is_reported_by_audit(tmp_path, monkeypatch, capsys):
    root = tmp_path / "evals" / "fixtures"
    monkeypatch.setattr(privacy, "REPO", tmp_path)
    monkeypatch.setattr(privacy, "ROOT", root)
    record = {"id": 34491, "company": "Dr. Ansay", "description": "Join DrAnsay. Python and SQL required."}
    filename = "evals/fixtures/postings/34491.fixture"
    save(tmp_path / filename, {**record, "company": company_token(record["company"])},
         "Anonymized posting; body retains an employer variant for audit verification.")
    save(root / "redactions.fixture", [{"file": filename, "scope": [], "identifiers":
         identifier_hashes(employer_identifiers(record, record["company"]))}],
         "Employer audit; identifiers include company spelling variants.")
    (tmp_path / "evals" / "allowed_terms.txt").write_text("# No identifier exceptions.\n")
    assert not audit()
    result = capsys.readouterr().out
    assert f"{filename}:" in result
    assert "employer identifier remains: DrAnsay" in result


@pytest.mark.parametrize("suffix", ["GmbH", "AG", "Inc.", "Ltd", "LLC", "SE", "PLC", "B.V.", "GmbH & Co. KG"])
def test_employer_legal_and_compact_variants(suffix):
    company = f"Invented Example {suffix}"
    record = {"company": company, "description": "Invented Example and InventedExample use Python."}
    names = employer_identifiers(record, company)
    assert {company, "Invented Example", "InventedExample"} <= set(names)
    changed, identifiers = redact_record(record, company)
    assert changed["description"] == f"{company_token(company)} and {company_token(company)} use Python."
    assert not list(remaining_identifiers(json.dumps(changed), identifiers))


@pytest.mark.parametrize("path", [
    "boards-api.greenhouse.io/v1/boards/invented-employer/jobs",
    "api.lever.co/v0/postings/invented-employer",
    "api.ashbyhq.com/posting-api/job-board/invented-employer",
    "api.smartrecruiters.com/v1/companies/invented-employer/postings",
    "himalayas.app/companies/invented-employer/jobs/engineer",
])
def test_employer_slug_variants(path):
    record = {"company": "Invented Example AG", "url": "https://" + path}
    assert {"invented-employer", "inventedemployer"} <= set(employer_identifiers(record, record["company"]))


def test_compact_audit_uses_original_word_boundaries():
    identifiers = identifier_hashes(["Dr. Ansay"])
    assert "DrAnsay" in list(remaining_identifiers("Join DrAnsay today", identifiers))
    assert "Dr-Ansay" in list(remaining_identifiers("Join Dr-Ansay today", identifiers))
    assert not list(remaining_identifiers("OtherDrAnsay and DrAnsays", identifiers))


def test_redaction_matches_punctuation_and_spacing_variants():
    record = {"company": "Invented.Example", "description": "Invented Example, Invented-Example, InventedExample use Python."}
    result, identifiers = redact_record(record, record["company"])
    placeholder = company_token(record["company"])
    assert result["description"] == f"{placeholder}, {placeholder}, {placeholder} use Python."
    assert not list(remaining_identifiers(json.dumps(result), identifiers))


@pytest.mark.parametrize('spelling', ['INVENTED EXAMPLE', 'invented example', 'Invented-Example'])
def test_employer_audit_folds_distinctive_names(spelling):
    identifiers = identifier_hashes(['Invented Example'])
    assert spelling in list(remaining_identifiers(f'Join {spelling} today', identifiers))
    assert not list(remaining_identifiers('Invented Examples and OtherInventedExample', identifiers))


@pytest.mark.parametrize('name', ['Go', 'IT', 'We', 'Remote', 'Shepherd'])
def test_common_employer_words_preserve_ordinary_prose(name):
    record = {'company': name, 'description': f'{name} hires; {name.lower()} stays in prose. Python required.'}
    result, identifiers = redact_record(record, name)
    assert result['description'] == f'{company_token(name)} hires; {name.lower()} stays in prose. Python required.'
    assert not list(remaining_identifiers(result['description'], identifiers))


@pytest.mark.parametrize('apostrophe', ['\u00e2\u0080\u0099', '\u00e2\u20ac\u2122'])
def test_employer_possessive_with_misdecoded_apostrophe(apostrophe):
    record = {'company': 'Invented Example', 'description': f'Invented Example{apostrophe}s team uses Python.'}
    identifiers = identifier_hashes([record['company']])
    assert 'Invented Example' in list(remaining_identifiers(record['description'], identifiers))
    result, _ = redact_record(record, record['company'])
    assert result['description'] == f'{company_token(record["company"])}’s team uses Python.'


def test_scoped_extra_identifier_is_reported_before_redaction(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'evals' / 'fixtures'
    monkeypatch.setattr(privacy, 'REPO', tmp_path)
    monkeypatch.setattr(privacy, 'ROOT', root)
    filename = 'evals/fixtures/postings/1.fixture'
    record = {'company': 'Invented Recruiting', 'description': 'Alternate Brand hires Python developers.'}
    extras = ['Alternate Brand']
    identifiers = identifier_hashes(employer_identifiers(record, record['company']) + extras)
    save(tmp_path / filename, record, 'Employer example; description contains a client brand.')
    save(root / 'redactions.fixture', [{'file': filename, 'scope': [], 'identifiers': identifiers,
                                      'extra_identifiers': identifier_hashes(extras)}],
         'Scoped employer digests; extra_identifiers covers a reviewed brand.')
    (tmp_path / 'evals' / 'allowed_terms.txt').write_text('# No exceptions.\n')
    assert not audit()
    assert 'Alternate Brand' in capsys.readouterr().out
    cleaned, _ = redact_record(record, record['company'], extras)
    save(tmp_path / filename, cleaned, 'Employer example; description uses a placeholder.')
    assert audit()
    assert capsys.readouterr().out == ''
