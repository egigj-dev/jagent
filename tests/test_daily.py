# Daily entry-point tests; fake uv records invocation and preserves the classifier exit code for systemd.
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "daily.sh"


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_daily_preserves_pipeline_exit(tmp_path, exit_code):
    uv = tmp_path / ".local/bin/uv"
    uv.parent.mkdir(parents=True)
    uv.write_text('#!/bin/sh\n# Test executable; CALLS records arguments and UV_EXIT selects its result.\nprintf "%s\\n" "$*" > "$CALLS"\nexit "$UV_EXIT"\n')
    uv.chmod(0o755)
    calls = tmp_path / "calls"
    result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                            env={**os.environ, "HOME": str(tmp_path), "CALLS": str(calls),
                                 "UV_EXIT": str(exit_code)})
    assert result.returncode == exit_code, result.stderr
    assert calls.read_text() == "run jagent daily\n"
