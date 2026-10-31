# Label editor tests; temporary fixtures isolate writes and blocked connectors enforce offline operation.
from pathlib import Path
from unittest.mock import Mock

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from evals import label
from evals.data import load, save, validate_labels


@pytest.fixture
def editor(tmp_path, monkeypatch):
    monkeypatch.setattr(label, "ROOT", tmp_path)
    blocked = Mock(side_effect=AssertionError("External access forbidden"))
    monkeypatch.setattr("httpx.post", blocked)
    monkeypatch.setattr("psycopg.connect", blocked)
    (tmp_path / "profile.md").write_text(
        "<!-- Synthetic profile; Engineering provides comparison text. -->\n"
        "## Engineering\nPython and PostgreSQL experience. <script>alert(1)</script>"
    )
    for posting_id in (1, 2):
        save(tmp_path / "postings" / f"{posting_id}.fixture", {
            "id": posting_id, "title": "Python engineer", "company": "Company Synthetic",
            "locations": ["Remote"], "description": "Python and SQL required. Docker preferred.",
        }, "Synthetic posting; requirements provide highlight text.")
        save(tmp_path / "outputs" / f"{posting_id}.fixture", {"analysis": {
            "explanation": "Python fits. SQL fits. Docker is missing.", "evidence": {},
        }}, "Synthetic recording; explanation converts to three claims.")
        save(tmp_path / "labels" / f"{posting_id}.fixture", {
            "claims": {}, "missed_requirements": None,
        }, label.LABEL_COMMENT)
    with TestClient(label.app) as client:
        yield client, tmp_path
    blocked.assert_not_called()


def snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_save_writes_valid_labels_and_reload_prefills_values(editor):
    client, root = editor
    before = snapshot(root)
    response = client.post("/postings/1", data={
        "claim:0": "supported", "claim:1": "unsupported", "claim:2": "",
        "missed_requirements": " Kubernetes \n\n Terraform ", "action": "save",
    })
    assert response.status_code == 200 and "Labels saved." in response.text
    labels = load(root / "labels" / "1.fixture")
    validate_labels(labels, 3)
    assert labels == {"claims": {"0": "supported", "1": "unsupported"},
                      "missed_requirements": ["Kubernetes", "Terraform"]}
    assert (root / "labels" / "1.fixture").read_text().startswith(f"# {label.LABEL_COMMENT}\n")
    page = BeautifulSoup(client.get("/postings/1").text, "html.parser")
    assert page.select_one('input[name="claim:0"][value="supported"]').has_attr("checked")
    assert page.select_one('input[name="claim:1"][value="unsupported"]').has_attr("checked")
    assert page.select_one('input[name="claim:2"][value=""]').has_attr("checked")
    assert page.select_one("textarea").text == "Kubernetes\nTerraform"
    assert not page.select_one('input[name="reviewed"]').has_attr("checked")
    after = snapshot(root)
    assert before.keys() == after.keys()
    assert [path for path in before if before[path] != after[path]] == [Path("labels/1.fixture")]


@pytest.mark.parametrize("reviewed,expected", [(False, None), (True, [])])
def test_empty_requirements_distinguish_unreviewed_from_reviewed(editor, reviewed, expected):
    client, root = editor
    data = {"missed_requirements": " \n", "action": "save"}
    if reviewed:
        data["reviewed"] = "1"
    assert client.post("/postings/1", data=data).status_code == 200
    assert load(root / "labels" / "1.fixture")["missed_requirements"] == expected
    page = BeautifulSoup(client.get("/postings/1").text, "html.parser")
    assert page.select_one('input[name="reviewed"]').has_attr("checked") == reviewed


@pytest.mark.parametrize("invalid,message", [
    ({"claim:3": "supported"}, "unknown claim"),
    ({"claim:-1": "supported"}, "unknown claim"),
    ({"claim:01": "supported"}, "unknown claim"),
    ({"claim:0": "uncertain"}, "supported or unsupported"),
    ({"missed_requirements": "Python", "reviewed": "1"}, "Uncheck reviewed"),
    ({"reviewed": "yes"}, "invalid value"),
    ({"action": "erase"}, "Choose Save"),
])
def test_invalid_save_shows_error_without_writing(editor, invalid, message):
    client, root = editor
    before = snapshot(root)
    response = client.post("/postings/1", data=invalid)
    assert response.status_code == 422
    assert message in response.text and 'role="alert"' in response.text
    assert snapshot(root) == before
    if "missed_requirements" in invalid:
        assert BeautifulSoup(response.text, "html.parser").select_one("textarea").text == "Python"


def test_repeated_form_fields_are_rejected(editor):
    client, root = editor
    before = snapshot(root)
    response = client.post("/postings/1", content="claim%3A0=supported&claim%3A0=unsupported",
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 422
    assert snapshot(root) == before


def test_index_progress_and_save_next(editor):
    client, root = editor
    page = BeautifulSoup(client.get("/").text, "html.parser")
    assert [row.select_one(".status").contents[0] for row in page.select("tbody tr")] == ["unlabeled", "unlabeled"]
    client.post("/postings/1", data={"claim:0": "supported"})
    assert "partly labeled" in client.get("/").text
    response = client.post("/postings/1", data={
        "claim:0": "supported", "claim:1": "unsupported", "claim:2": "supported",
        "reviewed": "1", "action": "next",
    }, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/postings/2?saved=1"
    page = BeautifulSoup(client.get("/").text, "html.parser")
    assert page.select_one("tbody tr .status").contents[0] == "labeled"
    response = client.post("/postings/2", data={"action": "next"}, follow_redirects=False)
    assert response.headers["location"] == "/?saved=1"


def test_read_pages_highlight_skills_and_escape_text_without_writes(editor):
    client, root = editor
    before = snapshot(root)
    response = client.get("/postings/1")
    assert response.status_code == 200
    page = BeautifulSoup(response.text, "html.parser")
    assert page.select_one("#job-heading").text == "Job text"
    assert page.select_one("#profile-heading").text == "Synthetic profile"
    assert page.select_one("#claim-0 legend").text == "0 · strength · Python"
    assert page.select_one("#claim-0 .sentence").text == "Python fits."
    assert {mark.text for mark in page.select(".sources mark")} >= {"Python", "SQL", "Docker"}
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in response.text
    assert not page.select("script")
    assert snapshot(root) == before
    assert client.get("/postings/999").status_code == 404
    assert client.post("/postings/999", data={"claim:0": "supported"}).status_code == 404
    assert client.post("/profile", data={"text": "anything"}).status_code == 404
    assert snapshot(root) == before


def test_highlights_use_aliases_word_boundaries_and_escaped_markup():
    text = 'postgres Pythonic Python C++ C# go home. R programming <b>"sample"</b>'
    result = label.highlighted_text(text, ["PostgreSQL", "Python", "C++", "C#", "Go", "R"])
    page = BeautifulSoup(result, "html.parser")
    assert [mark.text for mark in page.select("mark")] == ["postgres", "Python", "C++", "C#", "R"]
    assert '&lt;b&gt;&quot;sample&quot;&lt;/b&gt;' in result


def test_serve_binds_only_loopback_on_label_port(monkeypatch):
    run = Mock()
    monkeypatch.setattr("uvicorn.run", run)
    label.main()
    run.assert_called_once_with("evals.label:app", host="127.0.0.1", port=8001)
