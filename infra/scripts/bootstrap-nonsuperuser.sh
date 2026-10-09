#!/usr/bin/env bash
# Non-superuser bootstrap proof (Story 6.2 D13b): the whole migration chain,
# the fixture import, the seed planner, the login rotation and D4's privilege
# checks all succeed under a migrator shaped like the RDS master:
#   LOGIN NOSUPERUSER CREATEROLE CREATEDB NOBYPASSRLS INHERIT
#
#   bash infra/scripts/bootstrap-nonsuperuser.sh <superuser-url>
#   e.g. postgresql://postgres:secret@localhost:5433/postgres
#
# The cluster MUST be fresh: roles are cluster-global, and a shiftmind_* role
# that a superuser created earlier would hide exactly the failures this exists
# to find. That is also why this is a script against a throwaway cluster and
# not a pytest marker (F17: the default suite's deselection count is pinned).
#
# It runs `python -m scripts.bootstrap_hosted` twice as the simulated master
# with a generated login password, and asserts both verdicts. It is a LOWER
# bound on RDS's master, which additionally holds rds_superuser.
#
# Needs: bash, uv, and the backend's locked environment. Exit 0 only on pass.
set -euo pipefail

MIN_CHECKS="${MIN_CHECKS:-9}"
SUPERUSER_URL="${1:?usage: bootstrap-nonsuperuser.sh <superuser-url>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

py() {
  uv run --project backend --frozen python "$@"
}

# One python helper: provision the simulated master on the fresh cluster and
# print the two application URLs. Passwords are generated here and live only
# in this shell's environment.
urls="$(py - "$SUPERUSER_URL" <<'PY'
import secrets
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

superuser_url = sys.argv[1]
params = conninfo_to_dict(superuser_url)
host = params.get("host", "localhost")
port = params.get("port", "5432")
master_password = secrets.token_hex(20)
login_password = secrets.token_hex(20)

with psycopg.connect(superuser_url, autocommit=True) as conn:
    existing = conn.execute(
        "SELECT rolname FROM pg_roles WHERE rolname LIKE 'shiftmind%' OR rolname = 'rds_master_sim'"
    ).fetchall()
    if existing:
        sys.exit(f"FATAL: not a fresh cluster; roles exist: {sorted(r[0] for r in existing)}")
    conn.execute(
        sql.SQL(
            "CREATE ROLE rds_master_sim LOGIN NOSUPERUSER CREATEROLE CREATEDB "
            "NOBYPASSRLS INHERIT PASSWORD {}"
        ).format(sql.Literal(master_password))
    )
    # RDS creates the initial database owned by the master.
    conn.execute("CREATE DATABASE rosterai OWNER rds_master_sim")

print(f"postgresql+psycopg://rds_master_sim:{master_password}@{host}:{port}/rosterai")
print(f"postgresql+psycopg://shiftmind_login:{login_password}@{host}:{port}/rosterai")
PY
)"
provisioning_url="$(printf '%s\n' "$urls" | sed -n 1p | tr -d '\r')"
login_url="$(printf '%s\n' "$urls" | sed -n 2p | tr -d '\r')"
[ -n "$provisioning_url" ] && [ -n "$login_url" ] || { echo "FATAL: could not provision the simulated master" >&2; exit 2; }

run_bootstrap() {
  ROSTERAI_PROVISIONING_DATABASE_URL="$provisioning_url" \
  ROSTERAI_DATABASE_URL="$login_url" \
  SHIFTMIND_SEED_PLANNER_SUBJECT="nonsuperuser-proof-subject" \
  SHIFTMIND_SEED_PLANNER_EMAIL="planner@nonsuperuser.invalid" \
  PYTHONPATH="$REPO_ROOT/backend" \
    uv run --project backend --frozen python -m scripts.bootstrap_hosted
}

verdict() {
  # $1 = JSON line, $2 = expected planner_created ("true"/"false").
  py - "$1" "$2" "$MIN_CHECKS" <<'PY'
import json
import sys

report = json.loads(sys.argv[1])
expected_created = sys.argv[2] == "true"
floor = int(sys.argv[3])
checks = report["privileges"]["checks"]
problems = []
if report["passed"] is not True:
    problems.append(f"passed={report['passed']} stage={report.get('failed_stage')} error={report.get('error')}")
if len(checks) < floor:
    problems.append(f"{len(checks)} checks < floor {floor}")
for check in checks:
    if not check["passed"]:
        problems.append(f"{check['name']}: {check['detail']}")
if report["planner_created"] is not expected_created:
    problems.append(f"planner_created={report['planner_created']}, expected {expected_created}")
if not report["fixtures"] or report["fixtures"]["count"] < 1:
    problems.append(f"fixtures={report['fixtures']}")
print(f"checks={len(checks)} passed={report['passed']} planner_created={report['planner_created']} fixtures={report['fixtures']}")
for problem in problems:
    print(f"  FAIL {problem}")
sys.exit(1 if problems else 0)
PY
}

status=0
for run in 1 2; do
  expected=$([ "$run" = 1 ] && echo true || echo false)
  set +e
  output="$(run_bootstrap 2>"${TMPDIR:-/tmp}/bootstrap-nonsuperuser-$run.err")"
  code=$?
  set -e
  line="$(printf '%s\n' "$output" | tr -d '\r' | grep '^{' | tail -1 || true)"
  echo "run $run: exit $code"
  if [ -z "$line" ]; then
    echo "  FAIL no JSON line; stderr follows (secrets redacted by bootstrap_hosted)"
    cat "${TMPDIR:-/tmp}/bootstrap-nonsuperuser-$run.err" >&2
    status=1
    continue
  fi
  if ! verdict "$line" "$expected"; then
    status=1
    tail -40 "${TMPDIR:-/tmp}/bootstrap-nonsuperuser-$run.err" >&2
  fi
  [ "$code" = 0 ] || status=1
done

if [ "$status" = 0 ]; then
  echo "PASS: the chain, seed, rotation and privilege checks run under a non-superuser master"
else
  echo "FAIL: see above"
fi
exit "$status"
