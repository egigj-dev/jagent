#!/bin/bash
# Daily pipeline; step names each CLI command and status remembers any failure.
status=0
for step in run match analyze health; do
    printf '[%s] jagent %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$step"
    if ! /home/egigj/.local/bin/uv run jagent "$step"; then
        status=1
    fi
done
exit "$status"
