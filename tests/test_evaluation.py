# Baseline tests; frozen inputs exercise quote mapping, adversarial checks and offline execution.
from pathlib import Path
import subprocess
import sys
import shutil

import pytest

from evals.compare import adversarial_pass, convert, mapped_excerpt
from evals.data import ROOT, job_text, load
from jagent.briefing.evidence import job_excerpts, profile_excerpts


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


def test_seeded_faults_each_break_one_rule_and_labels_are_empty():
    from jagent.briefing.contract import ClaimDraft
    from jagent.briefing.evidence import failed_rules
    seeds = load(ROOT / "seeded.fixture")
    for case in seeds["cases"]:
        rules = failed_rules(ClaimDraft.model_validate(case["draft"]), seeds["job_excerpts"],
                             seeds["profile_excerpts"], seeds["profile"])
        assert rules == case["failed_rules"] and len(rules) <= 1
    for path in (ROOT / "labels").glob("*.fixture"):
        assert load(path) == {"claims": {}, "missed_requirements": None}


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
