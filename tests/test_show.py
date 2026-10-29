# Fixture viewer tests; ROOT supplies frozen inputs and tmp_path holds sentence-origin examples.
import re
from unittest.mock import Mock

import pytest

from evals import show
from evals.compare import convert
from evals.data import ROOT, job_text, load, save
from jagent.briefing.evidence import job_excerpts, profile_excerpts
from jagent.profile import split_sections


@pytest.mark.parametrize("path", sorted((ROOT / "postings").glob("*.fixture")), ids=lambda path: path.stem)
def test_frozen_claim_indices_and_inputs(path, capsys, monkeypatch):
    blocked = Mock(side_effect=AssertionError("External access forbidden"))
    monkeypatch.setattr("socket.socket.connect", blocked)
    monkeypatch.setattr("httpx.post", blocked)
    monkeypatch.setattr("psycopg.connect", blocked)
    posting = load(path)
    output = load(ROOT / "outputs" / path.name)
    profile = (ROOT / "profile.md").read_text().split("\n", 1)[1]
    drafts, _ = convert(output, job_excerpts(job_text(posting)), profile_excerpts(profile))
    before = {path: path.read_bytes() for path in ROOT.rglob("*") if path.is_file()}
    show.show(posting["id"])
    result = capsys.readouterr().out
    assert job_text(posting) in result
    for heading, body in split_sections(profile):
        assert f"## {heading}\n{body}" in result
    rows = re.findall(r"^(\d+) \| (strength|not_demonstrated) \| (.+)\nExplanation: (.+)$", result, re.M)
    assert [(int(index), kind, skill) for index, kind, skill, _ in rows] == [
        (index, draft.kind, draft.skill) for index, draft in enumerate(drafts)
    ]
    assert all(sentence in output["analysis"]["explanation"] for _, _, _, sentence in rows)
    assert before == {path: path.read_bytes() for path in ROOT.rglob("*") if path.is_file()}
    blocked.assert_not_called()


def test_first_sentence_preserves_claim_kind_and_deduplication(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(show, "ROOT", tmp_path)
    (tmp_path / "profile.md").write_text("<!-- Synthetic profile; Engineering supplies sample text. -->\n## Engineering\nPython experience.")
    save(tmp_path / "postings" / "1.fixture",
         {"id": 1, "title": "Engineer", "company": "Company A", "description": "Python required."},
         "Synthetic posting; Python supplies the requirement.")
    save(tmp_path / "outputs" / "1.fixture", {"analysis": {
        "explanation": "Python fits, but Kubernetes is missing. Python fits again; Docker fits! Python is missing?",
        "evidence": {},
    }}, "Synthetic analysis; repeated skills and mixed clauses exercise sentence origins.")
    show.show(1)
    result = capsys.readouterr().out
    assert "0 | strength | Python\nExplanation: Python fits, but Kubernetes is missing." in result
    assert "1 | not_demonstrated | Kubernetes\nExplanation: Python fits, but Kubernetes is missing." in result
    assert "2 | strength | Docker\nExplanation: Python fits again; Docker fits!" in result
    assert "3 | not_demonstrated | Python\nExplanation: Python is missing?" in result
