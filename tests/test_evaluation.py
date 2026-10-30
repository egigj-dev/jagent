# Baseline tests; frozen inputs exercise quote mapping, adversarial checks and offline execution.
from pathlib import Path
import subprocess
import sys
import shutil

import pytest

from evals.compare import adversarial_pass, convert, evaluate, mapped_excerpt
from evals.data import ROOT, job_text, load, save
from jagent.briefing.evidence import job_excerpts, profile_excerpts, text_version


def test_quote_mapping_and_unmapped_evidence():
    jobs = {"j": "Python programming is required."}
    profiles = {"p": "Python experience."}
    output = {"analysis": {"explanation": "Python fits. Kubernetes is missing.",
                           "evidence": {"seniority": "Python programming is required.",
                                        "profile_fit": "Python experience."}}}
    drafts, missing = convert(output, jobs, profiles)
    assert drafts[0].job_excerpt_id == "j" and drafts[0].profile_excerpt_id == "p"
    assert drafts[1].kind == "not_demonstrated" and drafts[1].job_excerpt_id == "missing"
    assert missing == [("Kubernetes", "no matching verbatim job quote")]
    assert mapped_excerpt("fabricated evidence", jobs) == "missing"


@pytest.mark.parametrize("quotes", [False, True])
def test_rule_coverage_requires_resolved_excerpts(quotes, tmp_path, capsys):
    profile = "## Engineering\nPython experience."
    (tmp_path / "profile.md").write_text("<!-- Synthetic profile; one section supplies evidence. -->\n" + profile)
    posting = {"id": 1, "title": "Engineer", "company": "Company A",
               "description": "Python is required."}
    evidence = {"job": "Python is required.", "profile": "Python experience."} if quotes else {}
    output = {"model": "recorded", "job_snapshot_id": text_version(job_text(posting)),
              "profile_version": text_version(profile), "latency_seconds": 0,
              "analysis": {"explanation": "Python fits. Docker fits. Kubernetes is missing.",
                           "evidence": evidence}}
    save(tmp_path / "postings" / "1.fixture", posting, "Synthetic posting; Python supplies job evidence.")
    save(tmp_path / "outputs" / "1.fixture", output, "Synthetic analysis; quotes control excerpt coverage.")
    save(tmp_path / "labels" / "1.fixture", {"claims": {}, "missed_requirements": None},
         "Human labels; no claims or requirements are labeled.")
    shutil.copyfile(ROOT / "seeded.fixture", tmp_path / "seeded.fixture")
    assert evaluate(tmp_path)
    result = capsys.readouterr().out
    assert f"Flagged by rule 1 | {2 if quotes else 3}/3 evaluated" in result
    assert f"Flagged by rule 2 | {1 if quotes else 2}/3 evaluated" in result
    for rule in (3, 4):
        expected = "0/1 evaluated (0.0%); 2 not evaluated" if quotes else "0/0 evaluated (N/A); 3 not evaluated"
        assert f"Flagged by rule {rule} | {expected}" in result
    assert "Flagged by rule 5 | 0/1 evaluated (0.0%); 2 not evaluated" in result


def test_adversarial_check_detects_markers_and_profile_copying():
    profile = "## Engineering\nPython experience. Personal note the violet fox studies eleven quiet rivers."
    posting = load(ROOT / "postings" / "900003.fixture")
    jobs = job_excerpts(job_text(posting))
    profiles = profile_excerpts(profile)
    output = {"content": "Python is a strength.", "analysis": {"explanation": "Python fits.", "evidence": {}}}
    drafts, _ = convert(output, jobs, profiles)
    assert adversarial_pass(posting, output, drafts, jobs, profiles, profile)
    output["content"] = "PROFILE_DISCLOSURE"
    assert not adversarial_pass(posting, output, drafts, jobs, profiles, profile)
    output["content"] = "Personal note the violet fox studies eleven quiet rivers."
    assert not adversarial_pass(posting, output, [], jobs, profiles, profile)


def assert_label_structure(labels, claim_count):
    assert isinstance(labels, dict)
    assert isinstance(labels["claims"], dict)
    valid_indices = {str(index) for index in range(claim_count)}
    for index, value in labels["claims"].items():
        assert index in valid_indices, f"Claim index does not exist: {index}"
        assert value in ("supported", "unsupported")
    missed = labels["missed_requirements"]
    assert missed is None or (isinstance(missed, list) and all(isinstance(item, str) for item in missed))


def test_seeded_faults_each_break_one_rule_and_labels_have_valid_structure():
    from jagent.briefing.contract import ClaimDraft
    from jagent.briefing.evidence import failed_rules
    seeds = load(ROOT / "seeded.fixture")
    for case in seeds["cases"]:
        rules = failed_rules(ClaimDraft.model_validate(case["draft"]), seeds["job_excerpts"],
                             seeds["profile_excerpts"], seeds["profile"])
        assert rules == case["failed_rules"] and len(rules) <= 1
    profiles = profile_excerpts((ROOT / "profile.md").read_text().split("\n", 1)[1])
    for path in (ROOT / "labels").glob("*.fixture"):
        posting = load(ROOT / "postings" / path.name)
        output = load(ROOT / "outputs" / path.name)
        drafts, _ = convert(output, job_excerpts(job_text(posting)), profiles)
        assert_label_structure(load(path), len(drafts))


@pytest.mark.parametrize("claim_count", [0, 2])
def test_label_structure_rejects_out_of_range_claim_index(claim_count):
    labels = {"claims": {str(claim_count): "supported"}, "missed_requirements": None}
    with pytest.raises(AssertionError, match="Claim index does not exist"):
        assert_label_structure(labels, claim_count)


@pytest.mark.parametrize("labels", [
    {"claims": {}, "missed_requirements": None},
    {"claims": {"0": "supported", "1": "unsupported"}, "missed_requirements": ["Python"]},
    {"claims": {"1": "supported"}, "missed_requirements": []},
])
def test_label_structure_accepts_empty_and_reviewed_labels(labels):
    assert_label_structure(labels, 2)


@pytest.mark.parametrize("labels", [
    {"claims": {"-1": "supported"}, "missed_requirements": None},
    {"claims": {"01": "supported"}, "missed_requirements": None},
    {"claims": {"0": "unknown"}, "missed_requirements": None},
    {"claims": [], "missed_requirements": None},
    {"claims": {}, "missed_requirements": "Python"},
    {"claims": {}, "missed_requirements": [1]},
])
def test_label_structure_rejects_invalid_fields(labels):
    with pytest.raises(AssertionError):
        assert_label_structure(labels, 2)


@pytest.mark.parametrize("private", [False, True])
def test_compare_runs_without_credentials_or_network(private, tmp_path):
    code = '''
import os
import socket
import sys
import runpy
def blocked(*args, **kwargs):
    raise AssertionError("Network forbidden")
socket.socket.connect = blocked
socket.create_connection = blocked
os.environ.pop("LLM_API_KEY", None)
sys.argv[0] = "evals.compare"
runpy.run_module("evals.compare", run_name="__main__")
'''
    args = [sys.executable, "-c", code]
    if private:
        target = tmp_path / "private"
        shutil.copytree(ROOT, target)
        args.append(str(target))
    result = subprocess.run(args, cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Baseline | Value" in result.stdout
    assert "Seeded checks | Flagged / total" in result.stdout
    assert "Seeded faults | 5 / 5" in result.stdout
    assert "Valid controls wrongly flagged | 0 / 3" in result.stdout


def test_frozen_selection_contains_only_queued_stratified_postings():
    selection = load(ROOT / "selection.fixture")
    selected = selection["selected_ids"]
    assert len(selected) == len(set(selected)) == 20
    assert selection["borderline_count"] == 7 and selection["upper_count"] == 13
    counts = {"borderline": 0, "upper": 0}
    for posting_id in selected:
        posting = load(ROOT / "postings" / f"{posting_id}.fixture")
        assert posting["queued"] is True
        percentile = posting["percentile"]
        assert percentile == selection["selected_percentiles"][str(posting_id)]
        band = "borderline" if 97 <= percentile < 98 else "upper"
        assert 97 <= percentile <= 100 and posting["selection"] == band
        counts[band] += 1
    assert counts == {"borderline": 7, "upper": 13}
    adversarial = {str(posting["id"]) for path in (ROOT / "postings").glob("*.fixture")
                   if (posting := load(path)).get("adversarial")}
    assert adversarial == {"900001", "900002", "900003"}
    expected = {str(posting_id) for posting_id in selected} | adversarial
    for directory in ("postings", "outputs", "labels"):
        assert {path.stem for path in (ROOT / directory).glob("*.fixture")} == expected
    for entry in load(ROOT / "redactions.fixture"):
        if entry["file"].startswith("evals/fixtures/"):
            assert Path(entry["file"]).stem in expected


def test_queued_selection_spreads_each_band_and_excludes_other_matches():
    import os
    from psycopg.rows import dict_row
    from jagent.db import connect

    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to test sampling in isolated temporary tables")
    with connect() as connection:
        connection.execute("""
            CREATE TEMP TABLE postings (
                id int, source text, source_id text, title text, company text,
                description text, locations text[], url text,
                posted_at timestamptz, first_seen timestamptz);
            CREATE TEMP TABLE matches (
                posting_id int, profile_id int, similarity double precision,
                percentile double precision, queued bool);
            INSERT INTO postings
                SELECT id, 'sample', id::text, 'Engineer', 'Invented Example',
                       'Python required.', ARRAY['Remote'], '',
                       '2026-10-20'::timestamptz, '2026-10-20'::timestamptz
                FROM generate_series(1, 46) AS sample(id);
            INSERT INTO matches
                SELECT id, 10, 0.7,
                       CASE WHEN id <= 15 THEN 97 + (id - 1) / 15.0
                            ELSE 98 + (id - 16) / 12.0 END, true
                FROM generate_series(1, 40) AS sample(id);
            INSERT INTO matches VALUES
                (41, 10, 0.7, 99, false), (42, 11, 0.7, 99, true),
                (43, 10, 0.7, 99, true), (44, 10, 0.7, 99, true),
                (45, 10, 0.7, 96, true), (46, 10, 0.4, 99, true);
            UPDATE postings SET posted_at='2026-10-28' WHERE id=43;
            UPDATE postings SET posted_at='2026-09-01' WHERE id=44;
        """)
        with connection.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute((ROOT.parent / "selection.sql").read_text(), {
                "profile_id": 10, "as_of": "2026-10-27T22:50:27+00:00",
                "min_percentile": 97, "min_similarity": 0.55,
            }).fetchall()
    assert [row["id"] for row in rows if row["selection"] == "borderline"] == [1, 3, 6, 8, 10, 13, 15]
    assert [row["id"] for row in rows if row["selection"] == "upper"] == list(range(16, 41, 2))
