<!-- Deployment plan only; jagent_revision pins source, jagent_release isolates code, and jagent_backup preserves units and database recovery material. -->
# Atlas × Terminal + Milestone A deployment and rollback

**Plan only. No production steps below were executed during integration.**
The candidate is the clean local branch `integration/atlas-milestone-a` in
`/tmp/jagent-integration`. The original checkout and Milestone A checkout remain
unchanged. Copy the verified Git bundle/archive and review evidence out of `/tmp`
before its contents can be cleaned up.

Deploy a fixed release directory with its own virtual environment. Do not apply
patches, switch branches, stage files, or reset the checkout used by the live
services. The existing `.env` and import directory are shared inputs; code and
installed dependencies belong to the release. The external laptop collector can
continue writing its existing import path.

## Preflight and release preparation

Run as `egigj` on the VPS after approval, keeping these variables in the same shell.
This block prepares files/dependencies and reads service/database configuration;
it does not run collection, matching or paid analysis.

```bash
set -euo pipefail
umask 077
jagent_repo=/tmp/jagent-integration
jagent_old=/home/egigj/jagent
jagent_revision=$(git -C "$jagent_repo" rev-parse integration/atlas-milestone-a)
jagent_release=/home/egigj/jagent-releases/$jagent_revision
jagent_stamp=$(date -u +%Y%m%dT%H%M%SZ)
jagent_backup=/home/egigj/jagent-deploy-backups/$jagent_revision-$jagent_stamp

test -z "$(git -C "$jagent_repo" status --porcelain)"
# Abort and re-review if the preserved live UI tree changed since the integration snapshot.
"$jagent_repo/.venv/bin/python" /tmp/jagent-integration-review/check-inputs.py ui
systemctl show jagent.service jagent-web.service jagent.timer \
  --property=Id,ActiveState,WorkingDirectory,FragmentPath,DropInPaths
# Confirm this exact output; never use the other project's port 5433.
test "$(docker port jagent-db-1 5432/tcp)" = '127.0.0.1:5434'

test ! -e "$jagent_release"
mkdir -p "$jagent_release" "$jagent_backup/units" "$jagent_backup/prepared-units"
git -C "$jagent_repo" archive "$jagent_revision" | tar -x -C "$jagent_release"
# Preserve the exact pre-Milestone UI source as a separate rollback reference.
git -C "$jagent_repo" archive --format=tar.gz 7ec5c33 > "$jagent_backup/ui-source.tar.gz"
printf '%s\n' "$jagent_revision" > "$jagent_backup/revision.txt"
test -r "$jagent_old/.env"
test -d "$jagent_old/imports"
ln -s "$jagent_old/.env" "$jagent_release/.env"
ln -s "$jagent_old/imports" "$jagent_release/imports"
for jagent_input in profile.md filters.json; do
  if test -f "$jagent_old/$jagent_input"; then
    ln -s "$jagent_old/$jagent_input" "$jagent_release/$jagent_input"
  fi
done
cd "$jagent_release"
/home/egigj/.local/bin/uv sync --locked
"$jagent_release/.venv/bin/python" - <<'PYCONFIG'
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict
values = {}
for line in Path('.env').read_text().splitlines():
    key, separator, value = line.partition('=')
    if separator:
        values[key.strip()] = value.strip().strip("\"'")
config = conninfo_to_dict(values['DATABASE_URL'])
assert config.get('host') in ('127.0.0.1', 'localhost')
assert config.get('port') == '5434' and config.get('dbname') == 'jagent'
print('Database configuration targets loopback jagent on port 5434')
PYCONFIG
"$jagent_release/.venv/bin/jagent" --help
"$jagent_release/.venv/bin/python" -c 'import jagent.dashboard; print(jagent.dashboard.__file__)'
# The module path above must resolve inside this release, not the old checkout.
for jagent_unit in jagent.service jagent-web.service jagent.timer; do
  sudo cp -a "/etc/systemd/system/$jagent_unit" "$jagent_backup/units/$jagent_unit"
  sed -e 's|@USER@|egigj|g' -e 's|@HOME@|/home/egigj|g' \
      -e "s|@PROJECT_DIR@|$jagent_release|g" "deploy/$jagent_unit" \
      > "$jagent_backup/prepared-units/$jagent_unit"
done
systemd-analyze verify "$jagent_backup/prepared-units/"*.service \
  "$jagent_backup/prepared-units/jagent.timer"
systemctl show jagent.service jagent-web.service jagent.timer \
  --property=Id,ActiveState,SubState,Result,ExecMainStatus \
  > "$jagent_backup/service-state.txt"
df -h "$jagent_backup"
```

At inspection the unit files were under `/etc/systemd/system` with no drop-ins.
Abort if that changes; preserve/review any new overrides before continuing.
The release is pinned by commit and installed from the unchanged `uv.lock`.
No private input is committed or included in the source archive.

## Approved maintenance window: backup, additive DDL, cutover

The following **does change production** and is intentionally left for a later
approved rollout. Do not run `jagent daily`, `run`, `match`, `analyze` or `init-db`
as a deployment check. In particular, `init-db` also runs a deduplication backfill.

```bash
sudo systemctl stop jagent.timer
if systemctl is-active --quiet jagent.service; then
  printf '%s\n' 'Daily processing is active. Abort this maintenance window; do not kill it.'
  # Resume the timer when abandoning this window, then arrange an idle window.
  sudo systemctl start jagent.timer
  exit 1
fi
sudo systemctl stop jagent-web.service
test "$(docker exec jagent-db-1 psql -U jagent -d jagent -At -v ON_ERROR_STOP=1 -c 'SELECT current_schema()')" = public
# Snapshot with review writes paused; this is a recovery backup, not a rollback prescription.
docker exec jagent-db-1 pg_dump -U jagent -d jagent -Fc > "$jagent_backup/database.dump"
docker exec -i jagent-db-1 pg_restore --list < "$jagent_backup/database.dump" \
  > "$jagent_backup/database-contents.txt"
docker exec jagent-db-1 psql -U jagent -d jagent -At -v ON_ERROR_STOP=1 -c \
  "SELECT 'postings',count(*) FROM postings UNION ALL SELECT 'profile',count(*) FROM profile UNION ALL SELECT 'reviews',count(*) FROM reviews UNION ALL SELECT 'matches',count(*) FROM matches ORDER BY 1" \
  > "$jagent_backup/counts-before.txt"
# This file creates only pipeline_runs, atomically, with a five-second lock timeout.
docker exec -i jagent-db-1 psql -U jagent -d jagent -v ON_ERROR_STOP=1 \
  < "$jagent_release/deploy/milestone-a.sql"
docker exec jagent-db-1 psql -U jagent -d jagent -At -v ON_ERROR_STOP=1 -c \
  "SELECT 'postings',count(*) FROM postings UNION ALL SELECT 'profile',count(*) FROM profile UNION ALL SELECT 'reviews',count(*) FROM reviews UNION ALL SELECT 'matches',count(*) FROM matches ORDER BY 1" \
  > "$jagent_backup/counts-after.txt"
cmp "$jagent_backup/counts-before.txt" "$jagent_backup/counts-after.txt"
docker exec jagent-db-1 psql -U jagent -d jagent -v ON_ERROR_STOP=1 -c '\d public.pipeline_runs'
for jagent_unit in jagent.service jagent-web.service jagent.timer; do
  sudo install -m 644 "$jagent_backup/prepared-units/$jagent_unit" "/etc/systemd/system/$jagent_unit"
done
sudo systemctl daemon-reload
sudo systemctl start jagent-web.service
systemctl is-active jagent-web.service
systemctl show jagent.service jagent-web.service \
  --property=Id,WorkingDirectory,ExecStart,SuccessExitStatus
for jagent_route in / /applied /profile /filters /health; do
  curl --fail --silent --show-error -o /dev/null \
    -w "$jagent_route %{http_code}\n" "http://127.0.0.1:8000$jagent_route"
done
journalctl -u jagent-web.service -n 30 --no-pager
```

Required smoke results: web is active, both unit working directories point at the
new release, daily `SuccessExitStatus` includes 2, all five GETs return 200, and
review/profile/match counts are unchanged by the migration. Inspect Opportunities,
a selected brief, Saved and Applied without submitting decisions. Health may
correctly show an existing source outage, stale Duapune input, and no recorded
new daily outcome yet; these are not grounds to trigger paid work during smoke tests.

Resume normal scheduling only after those checks pass:

```bash
systemctl show jagent.timer --property=LastTriggerUSec,NextElapseUSecRealtime
sudo systemctl start jagent.timer
systemctl list-timers jagent.timer --all
```

`Persistent=true` may trigger a missed daily run immediately when the timer is
re-enabled. Re-enable only when ready for normal collection and configured paid
AI processing. The first scheduled run must later be checked for its recorded
outcome, stage details and `ExecMainStatus`. Offline unit validation cannot replace
that production observation. Do not clear the old failed-run state to imply a
new pipeline has already completed.

## Rollback

For migration failure, the DDL transaction rolls back. If no units were installed,
restart the original web service and restore the previously active timer. Never
restore a database dump merely because an app startup failed.

For a failed release after unit installation, use the same saved `jagent_backup`
value and the following commands. Ensure no daily run is active before rollback;
if one is active, wait for completion rather than interrupting database work.

```bash
sudo systemctl stop jagent.timer
if systemctl is-active --quiet jagent.service; then
  printf '%s\n' 'Wait for the active daily run before rolling back.'
  exit 1
fi
sudo systemctl stop jagent-web.service
# Guard against later edits to the preserved original checkout before returning to it.
"$jagent_repo/.venv/bin/python" /tmp/jagent-integration-review/check-inputs.py ui
for jagent_unit in jagent.service jagent-web.service jagent.timer; do
  sudo install -m 644 "$jagent_backup/units/$jagent_unit" "/etc/systemd/system/$jagent_unit"
done
sudo systemctl daemon-reload
sudo systemctl start jagent-web.service
for jagent_route in / /applied /profile /filters /health; do
  curl --fail --silent --show-error -o /dev/null \
    -w "$jagent_route %{http_code}\n" "http://127.0.0.1:8000$jagent_route"
done
sudo systemctl start jagent.timer
systemctl show jagent.service jagent-web.service jagent.timer \
  --property=Id,ActiveState,WorkingDirectory,ExecStart
```

This restores the captured original unit configuration and preserved original UI
checkout; it does not reset or overwrite that tree. If the source guard fails,
stop and reconstruct a rollback release from `ui-source.tar.gz` (commit 7ec5c33),
install its own environment and point the restored units there after review.
Do not overwrite newer source edits to make the guard pass.

**Leave `pipeline_runs` and its audit rows in place.** The old application ignores
the additive table; original tables and review decisions remain compatible. No
DROP TABLE, profile rollback or match/review deletion is required. Restoring the
predeployment dump would discard subsequent decisions and is reserved for a
separately reviewed data-corruption recovery, not ordinary application rollback.
