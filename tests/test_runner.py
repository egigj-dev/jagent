# Runner isolation test; recorded holds audit rows from failed and successful sources.
from contextlib import nullcontext

from jagent import runner


def test_failing_source_does_not_stop_others(monkeypatch):
    recorded = []

    def fail():
        raise RuntimeError("Source unavailable")

    monkeypatch.setattr(runner, "SOURCES", {"broken": fail, "working": lambda: []})
    monkeypatch.setattr(runner, "connect", lambda: nullcontext(None))
    monkeypatch.setattr(runner, "record_run", lambda connection, result:
                        recorded.append(result.copy()))
    results = runner.run()
    assert [result["status"] for result in results] == ["error", "ok"]
    assert recorded == results
    assert recorded[0]["error"] == "Source unavailable"
    assert recorded[0]["new"] == 0
    assert recorded[1]["error"] is None
