#!/usr/bin/env bash
# Run the one-off migrate task on ECS and require its verdict (Story 6.2 D13c).
# Operator-run, after an apply that set backend_image_digest, with the same AWS
# credentials used for the apply.
#
#   bash infra/scripts/run-migrate.sh
#   EXPECT_PLANNER_CREATED=false bash infra/scripts/run-migrate.sh   # a replay
#
# It reads everything from `terraform output -json`, starts the task on Fargate
# in the private app subnets with the migrator security group and no public IP,
# waits for it to stop, requires container exit code 0, then reads the task's
# log stream and parses the ONE JSON line `python -m scripts.bootstrap_hosted
# --require-tls` prints. It requires `passed`, `privileges.passed`,
# `tls == "required"` and at least MIN_CHECKS checks.
#
# Prints task IDs and check names only, never an ARN (they carry the account
# ID), a URL or a host. Exit 0 only on a passing verdict. Writes no evidence/.
set -uo pipefail
# Git Bash on Windows rewrites an argument that starts with `/` into a Windows
# path, which turns the log group `/shiftmind/<env>/migrate` into an invalid
# name. No effect on Linux or macOS.
export MSYS_NO_PATHCONV=1

ENV_DIR="${ENV_DIR:-infra/terraform/envs/portfolio}"
# 8 catalog checks + the rotated-login probe + the TLS probe.
MIN_CHECKS="${MIN_CHECKS:-10}"
EXPECT_PLANNER_CREATED="${EXPECT_PLANNER_CREATED:-}"
WORK="$(mktemp -d)"
# With MSYS_NO_PATHCONV set, hand Windows tools (aws.exe, python) a native path.
command -v cygpath >/dev/null 2>&1 && WORK="$(cygpath -m "$WORK")"
trap 'rm -rf "$WORK"' EXIT

for tool in python3 terraform aws; do
  command -v "$tool" >/dev/null 2>&1 || { echo "FATAL: '$tool' is required on PATH" >&2; exit 2; }
done

terraform -chdir="$ENV_DIR" output -json >"$WORK/tf.json" || { echo "FATAL: terraform output failed in $ENV_DIR" >&2; exit 2; }

out() {
  # One terraform output by name; a list or map prints as JSON. A missing or
  # empty output is fatal, and `$(...)` cannot exit, so callers add `|| exit 2`.
  python3 - "$WORK/tf.json" "$1" <<'PY' | tr -d '\r'
import json, sys
data = json.load(open(sys.argv[1]))
name = sys.argv[2]
if name not in data or data[name]["value"] in ("", None, [], {}):
    sys.exit(f"FATAL: missing or empty terraform output: {name}")
value = data[name]["value"]
print(value if isinstance(value, str) else json.dumps(value))
PY
}

REGION="$(out region)" || exit 2
CLUSTER="$(out cluster_name)" || exit 2
TASK_DEF="$(out migrate_task_definition_arn)" || { echo "FATAL: set backend_image_digest and apply first" >&2; exit 2; }
SUBNETS="$(out app_subnet_ids)" || exit 2
MIGRATOR_SG="$(out migrator_security_group_id)" || exit 2
LOG_GROUP="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["migrate"])' "$(out log_group_names)" | tr -d '\r')" || exit 2
SUBNET_CSV="$(python3 -c 'import json,sys; print(",".join(json.loads(sys.argv[1])))' "$SUBNETS" | tr -d '\r')"
export AWS_REGION="$REGION"

echo "== run-migrate: cluster ${CLUSTER}, log group ${LOG_GROUP}"
aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --count 1 \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_CSV}],securityGroups=[${MIGRATOR_SG}],assignPublicIp=DISABLED}" \
  --output json >"$WORK/run.json" 2>"$WORK/err" \
  || { echo "FATAL: run-task failed: $(sed -E 's/[0-9]{12}/<account>/g' "$WORK/err")" >&2; exit 2; }

TASK_ARN="$(python3 - "$WORK/run.json" <<'PY' | tr -d '\r'
import json, sys
run = json.load(open(sys.argv[1]))
if run.get("failures"):
    sys.exit(f"FATAL: run-task failures: {[f.get('reason') for f in run['failures']]}")
print(run["tasks"][0]["taskArn"])
PY
)" || exit 2
TASK_ID="${TASK_ARN##*/}"
echo "-- task ${TASK_ID} started; waiting for it to stop"

# The waiter gives up after 10 minutes; a cold first migration can be longer.
for _ in 1 2 3; do
  aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK_ARN" 2>/dev/null && break
done
aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK_ARN" --output json >"$WORK/task.json" \
  || { echo "FATAL: describe-tasks failed" >&2; exit 2; }

python3 - "$WORK/task.json" <<'PY' | tr -d '\r'
import json, sys
task = json.load(open(sys.argv[1]))["tasks"][0]
container = task["containers"][0]
print(f"-- lastStatus={task.get('lastStatus')} stopCode={task.get('stopCode')} "
      f"exitCode={container.get('exitCode')} reason={container.get('reason') or task.get('stoppedReason')}")
sys.exit(0 if task.get("lastStatus") == "STOPPED" and container.get("exitCode") == 0 else 1)
PY
exit_ok=$?

STREAM="migrate/migrate/${TASK_ID}"
aws logs get-log-events --log-group-name "$LOG_GROUP" --log-stream-name "$STREAM" \
  --start-from-head --output json >"$WORK/logs.json" 2>"$WORK/err" \
  || { echo "FATAL: could not read log stream ${STREAM}" >&2; exit 2; }

python3 - "$WORK/logs.json" "$MIN_CHECKS" "$EXPECT_PLANNER_CREATED" <<'PY' | tr -d '\r'
import json, sys
events = json.load(open(sys.argv[1]))["events"]
floor = int(sys.argv[2])
expect_created = sys.argv[3]
lines = [e["message"].strip() for e in events if e["message"].strip().startswith("{")]
if not lines:
    print("FAIL  no JSON verdict line in the task log")
    sys.exit(1)
report = json.loads(lines[-1])
checks = report.get("privileges", {}).get("checks", [])
for check in checks:
    print(f"{'PASS' if check['passed'] else 'FAIL'}  {check['name']}" + ("" if check["passed"] else f"\n      {check['detail']}"))
print(f"-- fixtures={report.get('fixtures')} planner_created={report.get('planner_created')} tls={report.get('tls')}")
problems = []
if report.get("passed") is not True:
    problems.append(f"passed={report.get('passed')} failed_stage={report.get('failed_stage')} error={report.get('error')}")
if report.get("privileges", {}).get("passed") is not True:
    problems.append("privileges.passed is not true")
if report.get("tls") != "required":
    problems.append(f"tls={report.get('tls')}, expected required")
if len(checks) < floor:
    problems.append(f"{len(checks)} checks < floor {floor}")
if expect_created and str(report.get("planner_created")).lower() != expect_created.lower():
    problems.append(f"planner_created={report.get('planner_created')}, expected {expect_created}")
for problem in problems:
    print(f"FAIL  {problem}")
sys.exit(1 if problems else 0)
PY
verdict_ok=$?

if [ "$exit_ok" -eq 0 ] && [ "$verdict_ok" -eq 0 ]; then
  echo "== PASS: migrate task ${TASK_ID} exited 0 with a passing verdict"
  exit 0
fi
echo "== FAIL: migrate task ${TASK_ID} (exit ok: $([ "$exit_ok" -eq 0 ] && echo yes || echo no), verdict ok: $([ "$verdict_ok" -eq 0 ] && echo yes || echo no))"
exit 1
