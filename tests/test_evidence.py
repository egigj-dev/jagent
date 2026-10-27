# Evidence tests; seeded cases isolate each rule and technical contexts disambiguate short skill names.
import pytest
from pydantic import ValidationError

from evals.data import ROOT, load
from jagent.briefing.contract import ClaimDraft, InputPacket
from jagent.briefing.evidence import check, failed_rules, job_excerpts, mentions, profile_excerpts, text_version


@pytest.mark.parametrize("case", load(ROOT / "seeded.fixture")["cases"], ids=lambda case: case["name"])
def test_seeded_rules(case):
    data = load(ROOT / "seeded.fixture")
    draft = ClaimDraft.model_validate(case["draft"])
    assert failed_rules(draft, data["job_excerpts"], data["profile_excerpts"], data["profile"]) == case["failed_rules"]
    claim = check(draft, data["job_excerpts"], data["profile_excerpts"], data["profile"])
    assert (claim.status == "flagged") == bool(case["failed_rules"])


@pytest.mark.parametrize("text,skill,expected", [
    ("Deploy K8s clusters", "Kubernetes", True), ("Postgres queries", "PostgreSQL", True),
    ("postgresql", "postgres", True), ("Pythonic", "Python", False),
    ("We go to the office", "Go", False), ("Go programming", "Go", True),
    ("languages: go", "Go", True), ("Python, Go, R", "Go", True),
    ("R programming", "R", True), ("R&D teams", "R", False),
    ("Our goals are clear", "R", False), ("C++ experience", "C++", True),
    ("C# experience", "C++", False), ("C++ experience", "C#", False),
    ("C# experience", "C#", True), ("C plus plus", "C++", False),
    ("ReactJS", "React", True), ("transaction", "React", False),
    ("Golang backend", "Go", True),
])
def test_skill_boundaries(text, skill, expected):
    assert mentions(text, skill) is expected


def test_excerpt_ids_and_whitespace_normalization():
    text = "First  paragraph\nwrapped.\n\n- Python\n* SQL\n2. Docker"
    jobs = job_excerpts(text)
    assert list(jobs.values()) == ["First paragraph wrapped.", "Python", "SQL", "Docker"]
    assert jobs == job_excerpts(text)
    assert list(jobs) == [f"job:{text_version(text)}:{i}" for i in range(4)]
    assert text_version("Python  and\nSQL") == text_version("Python and SQL")
    assert profile_excerpts("## Engineering\n- Python\n- SQL") == {
        "profile:Engineering:0": "Python", "profile:Engineering:1": "SQL",
    }


def test_rule_five_searches_whole_profile_and_synonyms():
    draft = ClaimDraft(kind="not_demonstrated", skill="Kubernetes", job_excerpt_id="j", profile_excerpt_id=None)
    assert failed_rules(draft, {"j": "Kubernetes"}, {}, "## Other\nUsed K8s") == [5]
    assert failed_rules(draft, {"j": "Kubernetes"}, {}, "## Other\nUsed Docker") == []


def test_negated_mention_passes_lexical_checks_known_limitation():
    draft = ClaimDraft(kind="strength", skill="Kubernetes", job_excerpt_id="j", profile_excerpt_id="p")
    claim = check(draft, {"j": "Kubernetes experience"}, {"p": "no Kubernetes experience"}, "no Kubernetes experience")
    assert claim.status == "passed_checks"


def test_drafts_reject_status_and_confidence():
    draft = load(ROOT / "seeded.fixture")["cases"][0]["draft"]
    for field in ("status", "confidence"):
        with pytest.raises(ValidationError):
            ClaimDraft.model_validate({**draft, field: "passed_checks"})
    assert set(InputPacket.model_fields) == {"posting_id", "job_snapshot_id", "profile_version", "model"}
