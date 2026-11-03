#!/bin/bash
# Daily pipeline; the CLI records stage outcomes and returns 0 success, 2 degraded, or 1 failed.
exec "${HOME}/.local/bin/uv" run jagent daily
