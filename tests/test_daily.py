# Daily script tests; SCRIPT is sourced with a fake absolute uv function and calls records step order.
import os
from pathlib import Path
import re
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "daily.sh"


@pytest.mark.parametrize("failed", ["", "run", "match", "analyze", "health", "all"])
def test_daily_continues_and_reports_failure(tmp_path, failed):
    calls = tmp_path / "calls"
    # Bash allows an absolute path as a function name, intercepting the actual script's uv call.
    wrapper = '''
function /home/egigj/.local/bin/uv() {
    printf '%s\\n' "$*" >> "$CALLS"
    if [[ "$3" == "$FAILED_STEP" || "$FAILED_STEP" == all ]]; then
        return 7
    fi
    return 0
}
source "$1"
'''
    result = subprocess.run(
        ["bash", "-c", wrapper, "bash", str(SCRIPT)],
        env={**os.environ, "CALLS": str(calls), "FAILED_STEP": failed},
        capture_output=True, text=True,
    )
    assert result.returncode == (1 if failed else 0), result.stderr
    assert calls.read_text().splitlines() == [
        "run jagent run", "run jagent match", "run jagent analyze", "run jagent health",
    ]
    lines = result.stdout.splitlines()
    assert len(lines) == 4
    for line, step in zip(lines, ["run", "match", "analyze", "health"], strict=True):
        assert re.fullmatch(r"\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\] jagent " + step, line)
