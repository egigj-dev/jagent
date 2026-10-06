# Profile tests; sample text lives in tmp_path and recorded versions verify append-only storage.
from contextlib import nullcontext
import json
from unittest.mock import Mock

from jagent import cli, profile


def test_profile_set_stores_new_versions_and_reads_latest(monkeypatch, tmp_path):
    text_path = tmp_path / "sample.md"
    text_path.write_text("Python developer looking for work in Europe.")
    filters_path = tmp_path / "filters.json"
    filters_path.write_text(json.dumps({"countries": ["germany"]}))
    versions = []
    connection = Mock()

    def execute(sql, parameters=None):
        result = Mock()
        if sql.startswith("INSERT"):
            versions.append((len(versions) + 1, parameters[0], parameters[1].obj))
            result.fetchone.return_value = (versions[-1][0],)
        else:
            assert "ORDER BY id DESC LIMIT 1" in sql
            result.fetchone.return_value = versions[-1]
        return result

    connection.execute.side_effect = execute
    monkeypatch.setattr(profile, "connect", lambda: nullcontext(connection))
    assert profile.set_profile(text_path, filters_path) == 1
    text_path.write_text("Python developer seeking remote work.")
    assert profile.set_profile(text_path, filters_path) == 2
    assert profile.active_profile(connection) == (
        2, "Python developer seeking remote work.", {"countries": ["germany"]},
    )
    assert versions[0][1] == "Python developer looking for work in Europe."


def test_profile_set_splits_sections_and_keeps_full_text(monkeypatch, tmp_path):
    text_path = tmp_path / "sample.md"
    text_path.write_text("# Sample profile\n\n## Engineering\nPython and NLP.\n\n## Security\nDetection models.\n")
    filters_path = tmp_path / "filters.json"
    filters_path.write_text("{}")
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (7,)
    monkeypatch.setattr(profile, "connect", lambda: nullcontext(connection))
    assert profile.set_profile(text_path, filters_path) == 7
    calls = connection.execute.call_args_list
    assert calls[0].args[1][0] == text_path.read_text()
    assert calls[1].args[1] == (7, "Engineering", "Python and NLP.")
    assert calls[2].args[1] == (7, "Security", "Detection models.")


def test_profile_set_cli(monkeypatch, capsys):
    store = Mock(return_value=3)
    monkeypatch.setattr(cli, "set_profile", store)
    monkeypatch.setattr("sys.argv", ["jagent", "profile", "set", "sample.md", "filters.json"])
    assert cli.main() == 0
    store.assert_called_once_with("sample.md", "filters.json")
    assert capsys.readouterr().out == "Profile version 3 is active.\n"
