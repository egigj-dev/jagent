# Duapune import tests; FIXTURE holds laptop data and collected_at fixes freshness checks.
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
from unittest.mock import Mock

import pytest

from jagent import runner
from jagent.sources import duapune

FIXTURE = Path(__file__).parent / "fixtures" / "duapune.json"


@pytest.fixture
def data():
    return json.loads(FIXTURE.read_text())


def test_fixture_fields_and_deadlines(data):
    postings = duapune.parse_response(data)
    assert len(postings) == 5
    assert postings[0].source_id == "120366"
    for job, posting in zip(data["jobs"], postings, strict=True):
        assert posting.source == "duapune"
        assert posting.source_id.isdecimal()
        assert (posting.title, posting.company, posting.url, posting.description) == (
            job["title"], job["company"], job["url"], job["category"],
        )
        assert posting.locations == [job["location"], "Albania"]
        assert posting.posted_at is None and posting.remote is None
        deadline = posting.expires_at.astimezone(duapune.TIRANE)
        assert deadline.strftime("%d-%m-%Y %H:%M") == job["date"] + " 23:59"
        assert posting.expires_at.tzinfo == UTC


def test_date_and_expires_agree_for_every_job(data):
    collected = datetime.fromisoformat(data["collected_at"]).astimezone(duapune.TIRANE).date()
    for job in data["jobs"]:
        days = re.fullmatch(r"edhe (\d+) ditë", job["expires"])
        assert days is not None, job
        assert datetime.strptime(job["date"], "%d-%m-%Y").date() == (
            collected + timedelta(days=int(days[1]))
        ), job


def test_fetch_reads_only_local_file(monkeypatch, data):
    collected_at = datetime.fromisoformat(data["collected_at"])
    clock = Mock()
    clock.now.return_value = collected_at + timedelta(hours=36)
    clock.fromisoformat = datetime.fromisoformat
    clock.strptime = datetime.strptime
    monkeypatch.setattr(duapune, "datetime", clock)
    monkeypatch.setattr(duapune, "IMPORT_PATH", FIXTURE)
    monkeypatch.setattr("httpx.get", Mock(side_effect=AssertionError("No network")))
    monkeypatch.setattr("httpx.Client.send", Mock(side_effect=AssertionError("No network")))
    assert len(duapune.fetch()) == 5
    assert runner.SOURCES["duapune"] is duapune.fetch


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_stale_import_records_error(monkeypatch, tmp_path, data, missing):
    path = tmp_path / "duapune.json"
    if not missing:
        data["collected_at"] = (datetime.now(UTC) - timedelta(hours=37)).isoformat()
        path.write_text(json.dumps(data))
    monkeypatch.setattr(duapune, "IMPORT_PATH", path)
    monkeypatch.setattr(runner, "connect", lambda: nullcontext(None))
    record = Mock()
    monkeypatch.setattr(runner, "record_run", record)
    result = runner.run("duapune")[0]
    assert result["status"] == "error"
    assert ("missing" if missing else "more than 36 hours old") in result["error"]
    record.assert_called_once_with(None, result)


@pytest.mark.parametrize("date,utc", [
    ("02-11-2026", "2026-11-02T22:59:00+00:00"),
    ("24-10-2026", "2026-10-24T21:59:00+00:00"),
])
def test_deadline_observes_tirane_daylight_saving(data, date, utc):
    data["jobs"] = [{**data["jobs"][0], "date": date}]
    assert duapune.parse_response(data)[0].expires_at.isoformat() == utc
