#!/usr/bin/env bash
# Data and runtime smoke for Story 6.2 (D13c): proves AWS ACCEPTED the
# configuration that the offline `terraform test` suites only prove was
# INTENDED. Operator-run, after the apply that set backend_image_digest and a
# passing run-migrate.sh, with the same AWS credentials used for the apply.
#
#   bash infra/scripts/smoke-data.sh               # defaults to envs/portfolio
#
# Needs: bash, python3, terraform, the AWS CLI v2 and gh (check 13) on PATH.
# Conventions are smoke-edge.sh's: inputs from `terraform output -json`, fatal
# on a missing output, `tr -d '\r'` on every python helper, and "could not
# determine" is a FAIL. Output never prints an ARN, account ID or email.
#
#   1  RDS: not public, encrypted, 18.4, single-AZ, 7-day backups, no deletion
#      protection, subnet group = the data subnets, only SG = data
#   2  it uses its parameter group (in-sync), where rds.force_ssl = 1
#   3  the endpoint resolves only inside the data subnets, and 5432 is not
#      reachable from this machine
#   4  data ingress is exactly 5432 from {api, worker, migrator}; migrator has
#      no ingress rule
#   5  evidence bucket: 4 BPA flags, versioning Enabled, AES256, BucketOwnerEnforced
#   6  evidence is create-only, live, for THIS operator (an admin): put with
#      If-None-Match -> 200, again -> 412, without the header -> 403,
#      delete -> 403, delete a version -> 403, get -> 200. The probe objects
#      stay, by design (D7).
#   7  ECR IMMUTABLE + scan on push; the migrate task's image is @sha256: and
#      that digest exists in the repository
#   8  the three log groups exist with retention 30
#   9  the four secrets exist with an AWSCURRENT version and no resource policy
#  10  simulate-principal-policy, two-sided: each execution role is allowed its
#      own secrets and denied the others; the task roles are denied what an
#      execution role is allowed; the deploy role may PutImage only on the
#      backend repository and is denied secrets, evidence deletes and
#      iam:CreateAccessKey
#  11  both task roles have zero attached and zero inline policies
#  12  the deploy role trusts the GitHub provider with StringEquals on aud and
#      the exact sub
#  13  no IAM user has an active access key, and no GitHub secret is an AWS key
#  14  the budget exists with D11's two notifications; both cost tags Active
#
# Exit status is 0 only if every check passed. Nothing here writes to evidence/.
set -uo pipefail
# Git Bash on Windows rewrites an argument that starts with `/` (the log group
# prefix) into a Windows path. No effect on Linux or macOS.
export MSYS_NO_PATHCONV=1

ENV_DIR="${ENV_DIR:-infra/terraform/envs/portfolio}"
PASS=0
FAIL=0
WORK="$(mktemp -d)"
# With MSYS_NO_PATHCONV set, hand Windows tools (aws.exe, python) a native path.
command -v cygpath >/dev/null 2>&1 && WORK="$(cygpath -m "$WORK")"
trap 'rm -rf "$WORK"' EXIT

for tool in python3 terraform aws; do
  command -v "$tool" >/dev/null 2>&1 || { echo "FATAL: '$tool' is required on PATH" >&2; exit 2; }
done

terraform -chdir="$ENV_DIR" output -json >"$WORK/tf.json" || { echo "FATAL: terraform output failed in $ENV_DIR" >&2; exit 2; }

out() {
  # One terraform output by name; a list or map prints as JSON. Missing or
  # empty is fatal; `$(...)` cannot exit this shell, so callers add `|| exit 2`.
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
key() { python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$1" "$2" | tr -d '\r'; }

REGION="$(out region)" || exit 2
DB_ID="$(out db_instance_identifier)" || exit 2
DB_ADDRESS="$(out db_address)" || exit 2
DB_PARAMS="$(out db_parameter_group_name)" || exit 2
DATA_SUBNETS="$(out data_subnet_ids)" || exit 2
DATA_SG="$(out data_security_group_id)" || exit 2
API_SG="$(out api_security_group_id)" || exit 2
WORKER_SG="$(out worker_security_group_id)" || exit 2
MIGRATOR_SG="$(out migrator_security_group_id)" || exit 2
BUCKET="$(out evidence_bucket_name)" || exit 2
REPO="$(out backend_repository_name)" || exit 2
REPO_ARN="$(out backend_repository_arn)" || exit 2
TASK_DEF="$(out migrate_task_definition_arn)" || exit 2
LOG_GROUPS="$(out log_group_names)" || exit 2
SECRETS="$(out secret_arns)" || exit 2
EXEC_ROLES="$(out execution_role_arns)" || exit 2
TASK_ROLES="$(out task_role_arns)" || exit 2
DEPLOY_ROLE="$(out github_deploy_role_arn)" || exit 2
OIDC_PROVIDER="$(out github_oidc_provider_arn)" || exit 2
DEPLOY_SUB="$(out github_deploy_subject)" || exit 2
BUDGET="$(out budget_name)" || exit 2
export AWS_REGION="$REGION"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text 2>/dev/null | tr -d '\r')"
[ -n "$ACCOUNT" ] || { echo "FATAL: no AWS session" >&2; exit 2; }

ok()   { PASS=$((PASS + 1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf 'FAIL  %s\n' "$1"; [ -n "${2:-}" ] && printf '      %s\n' "$2"; }
check() { # check "<name>" <condition-exit-status> "<detail on failure>"
  if [ "$2" -eq 0 ]; then ok "$1"; else bad "$1" "${3:-}"; fi
}
redact() { sed -E "s/${ACCOUNT}/<account>/g" "$@"; }
# Run an AWS CLI call into $WORK/<name>.json; failure leaves the file absent,
# so the python check that reads it reports "could not determine".
fetch() { local name="$1"; shift; rm -f "$WORK/$name.json"; "$@" --output json >"$WORK/$name.json" 2>"$WORK/err" || rm -f "$WORK/$name.json"; }
pycheck() { # pycheck "<name>" <<'PY' ... PY   (python reads $WORK; exit 0 = pass, prints the reason)
  local label="$1" msg rc
  msg="$(WORK="$WORK" python3 - 2>&1)"
  rc=$?
  msg="$(printf '%s' "$msg" | tr -d '\r' | redact)"
  if [ "$rc" -eq 0 ]; then ok "$label"; else bad "$label" "$msg"; fi
}

echo "== smoke-data: region ${REGION}, db ${DB_ID}, bucket <evidence>, repo ${REPO}"

# --- 1. RDS instance -----------------------------------------------------------
fetch rds aws rds describe-db-instances --db-instance-identifier "$DB_ID"
fetch dbsubnets aws rds describe-db-subnet-groups --db-subnet-group-name "$(out db_subnet_group_name)"
DATA_SUBNETS="$DATA_SUBNETS" DATA_SG="$DATA_SG" pycheck "1 RDS is private, encrypted, 18.4, single-AZ, 7-day backups, data subnets and SG only" <<'PY'
import json, os, sys
w = os.environ["WORK"]
try:
    db = json.load(open(f"{w}/rds.json"))["DBInstances"][0]
    group = json.load(open(f"{w}/dbsubnets.json"))["DBSubnetGroups"][0]
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
want_subnets = set(json.loads(os.environ["DATA_SUBNETS"]))
errors = []
for field, expected in [("PubliclyAccessible", False), ("StorageEncrypted", True), ("EngineVersion", "18.4"),
                        ("MultiAZ", False), ("BackupRetentionPeriod", 7), ("DeletionProtection", False),
                        ("AutoMinorVersionUpgrade", False)]:
    if db.get(field) != expected:
        errors.append(f"{field}={db.get(field)!r}")
if {s["SubnetIdentifier"] for s in group["Subnets"]} != want_subnets:
    errors.append("subnet group is not exactly the data subnets")
if [g["VpcSecurityGroupId"] for g in db["VpcSecurityGroups"]] != [os.environ["DATA_SG"]]:
    errors.append("security groups are not exactly [data]")
print("; ".join(errors))
sys.exit(1 if errors else 0)
PY

# --- 2. TLS required -----------------------------------------------------------
# Every source, not `--source user`: 1 is the postgres18 default, so AWS lists
# it as a `system` value even though the group declares it.
fetch params aws rds describe-db-parameters --db-parameter-group-name "$DB_PARAMS"
DB_PARAMS="$DB_PARAMS" pycheck "2 the instance uses its parameter group, in-sync, with rds.force_ssl = 1" <<'PY'
import json, os, sys
w = os.environ["WORK"]
try:
    params = json.load(open(f"{w}/params.json"))["Parameters"]
    groups = json.load(open(f"{w}/rds.json"))["DBInstances"][0]["DBParameterGroups"]
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
values = [p.get("ParameterValue") for p in params if p["ParameterName"] == "rds.force_ssl"]
attached = [(g["DBParameterGroupName"], g["ParameterApplyStatus"]) for g in groups]
print(f"rds.force_ssl={values} groups={attached}")
sys.exit(0 if values == ["1"] and attached == [(os.environ["DB_PARAMS"], "in-sync")] else 1)
PY

# --- 3. Endpoint is private and unreachable from here --------------------------
fetch subnets aws ec2 describe-subnets --subnet-ids $(python3 -c 'import json,sys; print(" ".join(json.loads(sys.argv[1])))' "$DATA_SUBNETS" | tr -d '\r')
DB_ADDRESS="$DB_ADDRESS" pycheck "3 the endpoint resolves only inside the data subnets and 5432 is unreachable from here" <<'PY'
import ipaddress, json, os, socket, sys
try:
    cidrs = [ipaddress.ip_network(s["CidrBlock"]) for s in json.load(open(f"{os.environ['WORK']}/subnets.json"))["Subnets"]]
    addresses = {info[4][0] for info in socket.getaddrinfo(os.environ["DB_ADDRESS"], 5432, proto=socket.IPPROTO_TCP)}
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
outside = [a for a in addresses if not any(ipaddress.ip_address(a) in c for c in cidrs)]
reachable = []
for address in addresses:
    try:
        socket.create_connection((address, 5432), timeout=5).close()
        reachable.append(address)
    except OSError:
        pass
print(f"{len(addresses)} address(es); outside the data subnets: {len(outside)}; reachable: {len(reachable)}")
sys.exit(0 if addresses and not outside and not reachable else 1)
PY

# --- 4. Data and migrator security group rules ---------------------------------
fetch sgrules aws ec2 describe-security-group-rules --filters "Name=group-id,Values=${DATA_SG},${MIGRATOR_SG}"
DATA_SG="$DATA_SG" MIGRATOR_SG="$MIGRATOR_SG" API_SG="$API_SG" WORKER_SG="$WORKER_SG" \
pycheck "4 data ingress is exactly 5432 from api, worker and migrator; migrator has no ingress" <<'PY'
import json, os, sys
try:
    rules = json.load(open(f"{os.environ['WORK']}/sgrules.json"))["SecurityGroupRules"]
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
e = os.environ
data_in = [r for r in rules if r["GroupId"] == e["DATA_SG"] and not r["IsEgress"]]
sources = sorted((r.get("ReferencedGroupInfo") or {}).get("GroupId", r.get("CidrIpv4", "?")) for r in data_in)
ports_ok = all(r["FromPort"] == 5432 and r["ToPort"] == 5432 and r["IpProtocol"] == "tcp" for r in data_in)
migrator_in = [r for r in rules if r["GroupId"] == e["MIGRATOR_SG"] and not r["IsEgress"]]
want = sorted([e["API_SG"], e["WORKER_SG"], e["MIGRATOR_SG"]])
print(f"data ingress sources match: {sources == want}; ports 5432 only: {ports_ok}; migrator ingress rules: {len(migrator_in)}")
sys.exit(0 if sources == want and ports_ok and not migrator_in else 1)
PY

# --- 5. Evidence bucket posture ------------------------------------------------
fetch bpa aws s3api get-public-access-block --bucket "$BUCKET"
fetch versioning aws s3api get-bucket-versioning --bucket "$BUCKET"
fetch encryption aws s3api get-bucket-encryption --bucket "$BUCKET"
fetch ownership aws s3api get-bucket-ownership-controls --bucket "$BUCKET"
pycheck "5 evidence bucket: 4 BPA flags, versioning Enabled, AES256, BucketOwnerEnforced" <<'PY'
import json, os, sys
w = os.environ["WORK"]
try:
    bpa = json.load(open(f"{w}/bpa.json"))["PublicAccessBlockConfiguration"]
    versioning = json.load(open(f"{w}/versioning.json")).get("Status")
    sse = json.load(open(f"{w}/encryption.json"))["ServerSideEncryptionConfiguration"]["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
    owner = json.load(open(f"{w}/ownership.json"))["OwnershipControls"]["Rules"][0]["ObjectOwnership"]
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
ok = all(bpa.values()) and len(bpa) == 4 and versioning == "Enabled" and sse == "AES256" and owner == "BucketOwnerEnforced"
print(f"bpa={bpa} versioning={versioning} sse={sse} ownership={owner}")
sys.exit(0 if ok else 1)
PY

# --- 6. Evidence is create-only, for an admin too ------------------------------
KEY="smoke/$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM.txt"
printf 'shiftmind smoke-data probe\n' >"$WORK/probe.txt"
s3_code() { # classify the last s3api call's stderr
  if grep -q "PreconditionFailed" "$WORK/err"; then echo 412
  elif grep -q "AccessDenied" "$WORK/err"; then echo 403
  else echo "other"; fi
}
aws s3api put-object --bucket "$BUCKET" --key "$KEY" --body "$WORK/probe.txt" --if-none-match '*' --output json >"$WORK/put1.json" 2>"$WORK/err"
put1=$?
check "6a put with If-None-Match -> 200" "$put1" "$(redact "$WORK/err")"
aws s3api put-object --bucket "$BUCKET" --key "$KEY" --body "$WORK/probe.txt" --if-none-match '*' >/dev/null 2>"$WORK/err"
[ $? -ne 0 ] && [ "$(s3_code)" = "412" ]
check "6b the same put again -> 412 (no overwrite)" $? "$(redact "$WORK/err")"
aws s3api put-object --bucket "$BUCKET" --key "$KEY" --body "$WORK/probe.txt" >/dev/null 2>"$WORK/err"
[ $? -ne 0 ] && [ "$(s3_code)" = "403" ]
check "6c a put without the header -> 403" $? "$(redact "$WORK/err")"
aws s3api delete-object --bucket "$BUCKET" --key "$KEY" >/dev/null 2>"$WORK/err"
[ $? -ne 0 ] && [ "$(s3_code)" = "403" ]
check "6d delete-object -> 403" $? "$(redact "$WORK/err")"
VERSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("VersionId",""))' "$WORK/put1.json" 2>/dev/null | tr -d '\r')"
if [ -n "$VERSION_ID" ]; then
  aws s3api delete-object --bucket "$BUCKET" --key "$KEY" --version-id "$VERSION_ID" >/dev/null 2>"$WORK/err"
  [ $? -ne 0 ] && [ "$(s3_code)" = "403" ]
  check "6e delete-object --version-id -> 403" $? "$(redact "$WORK/err")"
else
  bad "6e delete-object --version-id -> 403" "could not determine: the first put returned no VersionId"
fi
aws s3api get-object --bucket "$BUCKET" --key "$KEY" "$WORK/probe.out" >/dev/null 2>"$WORK/err" && cmp -s "$WORK/probe.txt" "$WORK/probe.out"
check "6f get-object -> 200 with the probe's bytes" $? "$(redact "$WORK/err")"

# --- 7. ECR and the migrate image digest ---------------------------------------
fetch repo aws ecr describe-repositories --repository-names "$REPO"
fetch taskdef aws ecs describe-task-definition --task-definition "$TASK_DEF"
pycheck "7a ECR is IMMUTABLE with scan on push; the migrate image is pinned by digest" <<'PY'
import json, os, sys
w = os.environ["WORK"]
try:
    repo = json.load(open(f"{w}/repo.json"))["repositories"][0]
    image = json.load(open(f"{w}/taskdef.json"))["taskDefinition"]["containerDefinitions"][0]["image"]
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
digest = image.split("@", 1)[1] if "@" in image else ""
open(f"{w}/digest", "w").write(digest)
ok = repo["imageTagMutability"] == "IMMUTABLE" and repo["imageScanningConfiguration"]["scanOnPush"] is True and digest.startswith("sha256:") and len(digest) == 71
print(f"mutability={repo['imageTagMutability']} scanOnPush={repo['imageScanningConfiguration']['scanOnPush']} digest={digest or 'none'}")
sys.exit(0 if ok else 1)
PY
DIGEST="$(cat "$WORK/digest" 2>/dev/null)"
[ -n "$DIGEST" ] && aws ecr describe-images --repository-name "$REPO" --image-ids imageDigest="$DIGEST" >/dev/null 2>"$WORK/err"
check "7b the migrate task's digest exists in the repository" $? "digest=${DIGEST:-none}"

# --- 8. Log groups -------------------------------------------------------------
fetch logs aws logs describe-log-groups --log-group-name-prefix "$(key "$LOG_GROUPS" api | sed 's#/api$##')/"
LOG_GROUPS="$LOG_GROUPS" pycheck "8 the three log groups exist with retention 30" <<'PY'
import json, os, sys
try:
    found = {g["logGroupName"]: g.get("retentionInDays") for g in json.load(open(f"{os.environ['WORK']}/logs.json"))["logGroups"]}
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
want = json.loads(os.environ["LOG_GROUPS"]).values()
wrong = {name: found.get(name) for name in want if found.get(name) != 30}
print(f"retention not 30: {wrong}")
sys.exit(0 if not wrong else 1)
PY

# --- 9. Secrets ----------------------------------------------------------------
for name in database-url provisioning-database-url oidc-client-secret csrf-secret; do
  arn="$(key "$SECRETS" "$name")"
  fetch "secret-$name" aws secretsmanager describe-secret --secret-id "$arn"
  fetch "policy-$name" aws secretsmanager get-resource-policy --secret-id "$arn"
done
pycheck "9 the four secrets have an AWSCURRENT version and no resource policy" <<'PY'
import json, os, sys
w = os.environ["WORK"]
errors = []
for name in ["database-url", "provisioning-database-url", "oidc-client-secret", "csrf-secret"]:
    try:
        secret = json.load(open(f"{w}/secret-{name}.json"))
        policy = json.load(open(f"{w}/policy-{name}.json"))
    except Exception as exc:
        errors.append(f"{name}: could not determine ({type(exc).__name__})")
        continue
    stages = [s for stages in secret.get("VersionIdsToStages", {}).values() for s in stages]
    if "AWSCURRENT" not in stages:
        errors.append(f"{name}: no AWSCURRENT version")
    if policy.get("ResourcePolicy"):
        errors.append(f"{name}: has a resource policy")
print("; ".join(errors))
sys.exit(1 if errors else 0)
PY

# --- 10. Two-sided IAM simulation ----------------------------------------------
simulate() { # simulate <out-name> <role-arn> <action> <resource-arn>...
  local name="$1" role="$2" action="$3"; shift 3
  fetch "sim-$name" aws iam simulate-principal-policy --policy-source-arn "$role" --action-names "$action" --resource-arns "$@"
}
ALL_SECRETS=(database-url provisioning-database-url oidc-client-secret csrf-secret)
declare -A READS=([api]="database-url oidc-client-secret csrf-secret" [worker]="database-url" [migrate]="database-url provisioning-database-url")
for role in api worker migrate; do
  role_arn="$(key "$EXEC_ROLES" "$role")"
  for secret in "${ALL_SECRETS[@]}"; do
    simulate "exec-$role-$secret" "$role_arn" secretsmanager:GetSecretValue "$(key "$SECRETS" "$secret")"
  done
done
LOG_API_ARN="arn:aws:logs:${REGION}:${ACCOUNT}:log-group:$(key "$LOG_GROUPS" api):*"
for role in api worker; do
  role_arn="$(key "$TASK_ROLES" "$role")"
  simulate "task-$role-secret" "$role_arn" secretsmanager:GetSecretValue "$(key "$SECRETS" database-url)"
  simulate "task-$role-ecr" "$role_arn" ecr:BatchGetImage "$REPO_ARN"
  simulate "task-$role-logs" "$role_arn" logs:PutLogEvents "$LOG_API_ARN"
done
simulate "exec-api-ecr" "$(key "$EXEC_ROLES" api)" ecr:BatchGetImage "$REPO_ARN"
simulate "exec-api-logs" "$(key "$EXEC_ROLES" api)" logs:PutLogEvents "$LOG_API_ARN"
OTHER_REPO_ARN="${REPO_ARN%/*}/not-the-backend-repository"
EVIDENCE_OBJECT_ARN="arn:aws:s3:::${BUCKET}/smoke/x"
simulate "deploy-put-own" "$DEPLOY_ROLE" ecr:PutImage "$REPO_ARN"
simulate "deploy-put-other" "$DEPLOY_ROLE" ecr:PutImage "$OTHER_REPO_ARN"
simulate "deploy-secret" "$DEPLOY_ROLE" secretsmanager:GetSecretValue "$(key "$SECRETS" database-url)"
simulate "deploy-s3-delete" "$DEPLOY_ROLE" s3:DeleteObject "$EVIDENCE_OBJECT_ARN"
simulate "deploy-access-key" "$DEPLOY_ROLE" iam:CreateAccessKey "*"
READS_API="${READS[api]}" READS_WORKER="${READS[worker]}" READS_MIGRATE="${READS[migrate]}" \
pycheck "10 simulate-principal-policy is two-sided for execution, task and deploy roles" <<'PY'
import json, os, sys
w = os.environ["WORK"]
def decision(name):
    try:
        return json.load(open(f"{w}/sim-{name}.json"))["EvaluationResults"][0]["EvalDecision"]
    except Exception:
        return "undetermined"
errors = []
secrets = ["database-url", "provisioning-database-url", "oidc-client-secret", "csrf-secret"]
for role in ["api", "worker", "migrate"]:
    allowed = set(os.environ[f"READS_{role.upper()}"].split())
    for secret in secrets:
        got = decision(f"exec-{role}-{secret}")
        want = "allowed" if secret in allowed else "denied"
        if (got == "allowed") != (want == "allowed") or got == "undetermined":
            errors.append(f"{role}-exec {secret}: {got}, want {want}")
# The harness can see an allow (execution role) and the task roles get none.
for probe in ["exec-api-ecr", "exec-api-logs"]:
    if decision(probe) != "allowed":
        errors.append(f"{probe}: {decision(probe)}, want allowed")
for role in ["api", "worker"]:
    for what in ["secret", "ecr", "logs"]:
        got = decision(f"task-{role}-{what}")
        if got != "implicitDeny" and got != "explicitDeny":
            errors.append(f"{role}-task {what}: {got}, want denied")
if decision("deploy-put-own") != "allowed":
    errors.append(f"deploy PutImage own repo: {decision('deploy-put-own')}")
for probe in ["deploy-put-other", "deploy-secret", "deploy-s3-delete", "deploy-access-key"]:
    if decision(probe) not in ("implicitDeny", "explicitDeny"):
        errors.append(f"{probe}: {decision(probe)}, want denied")
print("; ".join(errors))
sys.exit(1 if errors else 0)
PY

# --- 11. Task roles carry no policy --------------------------------------------
for role in api worker; do
  name="$(key "$TASK_ROLES" "$role" | sed 's#.*/##')"
  fetch "attached-$role" aws iam list-attached-role-policies --role-name "$name"
  fetch "inline-$role" aws iam list-role-policies --role-name "$name"
done
pycheck "11 both task roles have zero attached and zero inline policies" <<'PY'
import json, os, sys
w = os.environ["WORK"]
errors = []
for role in ["api", "worker"]:
    try:
        attached = json.load(open(f"{w}/attached-{role}.json"))["AttachedPolicies"]
        inline = json.load(open(f"{w}/inline-{role}.json"))["PolicyNames"]
    except Exception as exc:
        errors.append(f"{role}: could not determine ({type(exc).__name__})")
        continue
    if attached or inline:
        errors.append(f"{role}: {len(attached)} attached, {len(inline)} inline")
print("; ".join(errors))
sys.exit(1 if errors else 0)
PY

# --- 12. Deploy role trust -----------------------------------------------------
fetch deployrole aws iam get-role --role-name "${DEPLOY_ROLE##*/}"
OIDC_PROVIDER="$OIDC_PROVIDER" DEPLOY_SUB="$DEPLOY_SUB" \
pycheck "12 the deploy role trusts GitHub's provider with StringEquals on aud and the exact sub" <<'PY'
import json, os, sys, urllib.parse
try:
    doc = json.load(open(f"{os.environ['WORK']}/deployrole.json"))["Role"]["AssumeRolePolicyDocument"]
    if isinstance(doc, str):
        doc = json.loads(urllib.parse.unquote(doc))
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
statements = doc["Statement"]
issuer = "token.actions.githubusercontent.com"
want = {"StringEquals": {f"{issuer}:aud": "sts.amazonaws.com", f"{issuer}:sub": os.environ["DEPLOY_SUB"]}}
ok = (len(statements) == 1
      and statements[0]["Principal"] == {"Federated": os.environ["OIDC_PROVIDER"]}
      and statements[0]["Action"] == "sts:AssumeRoleWithWebIdentity"
      and statements[0]["Condition"] == want)
print(f"one statement: {len(statements) == 1}; exact provider, action and StringEquals aud+sub: {ok}")
sys.exit(0 if ok else 1)
PY

# --- 13. No long-lived keys ----------------------------------------------------
fetch users aws iam list-users
python3 -c 'import json,sys; [print(u["UserName"]) for u in json.load(open(sys.argv[1]))["Users"]]' "$WORK/users.json" 2>/dev/null | tr -d '\r' >"$WORK/user-names" \
  || rm -f "$WORK/user-names"
active=0
undetermined=0
if [ -f "$WORK/user-names" ]; then
  while read -r user; do
    [ -n "$user" ] || continue
    n="$(aws iam list-access-keys --user-name "$user" --query "length(AccessKeyMetadata[?Status=='Active'])" --output text 2>/dev/null | tr -d '\r')"
    case "$n" in ''|*[!0-9]*) undetermined=1 ;; *) active=$((active + n)) ;; esac
  done <"$WORK/user-names"
else
  undetermined=1
fi
[ "$undetermined" -eq 0 ] && [ "$active" -eq 0 ]
check "13a no IAM user has an active access key" $? "active keys: ${active}; undetermined: ${undetermined}"
if command -v gh >/dev/null 2>&1 \
  && gh secret list --json name >"$WORK/gh-repo.json" 2>/dev/null \
  && gh secret list --env portfolio --json name >"$WORK/gh-env.json" 2>/dev/null; then
  python3 - "$WORK/gh-repo.json" "$WORK/gh-env.json" <<'PY' | tr -d '\r'
import json, sys
names = {s["name"] for path in sys.argv[1:] for s in json.load(open(path))}
bad = names & {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
print(f"static AWS key secrets: {sorted(bad) or 'none'}; AWS_DEPLOY_ROLE_ARN present: {'AWS_DEPLOY_ROLE_ARN' in names}")
sys.exit(1 if bad or "AWS_DEPLOY_ROLE_ARN" not in names else 0)
PY
  check "13b GitHub holds no static AWS key, only the deploy role ARN" $?
else
  bad "13b GitHub holds no static AWS key, only the deploy role ARN" "could not determine: gh is missing or not signed in"
fi

# --- 14. Budget and cost tags --------------------------------------------------
fetch budget aws budgets describe-budget --account-id "$ACCOUNT" --budget-name "$BUDGET" --region us-east-1
fetch notifications aws budgets describe-notifications-for-budget --account-id "$ACCOUNT" --budget-name "$BUDGET" --region us-east-1
fetch costtags aws ce list-cost-allocation-tags --tag-keys Project Environment --region us-east-1
pycheck "14 account-wide budget with 80% ACTUAL and 100% FORECASTED; both cost tags Active" <<'PY'
import json, os, sys
w = os.environ["WORK"]
try:
    budget = json.load(open(f"{w}/budget.json"))["Budget"]
    notes = json.load(open(f"{w}/notifications.json"))["Notifications"]
    tags = json.load(open(f"{w}/costtags.json"))["CostAllocationTags"]
except Exception as exc:
    sys.exit(f"could not determine: {type(exc).__name__}")
# AWS omits ThresholdType when it is the default, PERCENTAGE.
shape = sorted((n["NotificationType"], float(n["Threshold"]), n.get("ThresholdType", "PERCENTAGE"), n["ComparisonOperator"]) for n in notes)
want = [("ACTUAL", 80.0, "PERCENTAGE", "GREATER_THAN"), ("FORECASTED", 100.0, "PERCENTAGE", "GREATER_THAN")]
filters = budget.get("CostFilters") or budget.get("FilterExpression") or {}
statuses = {t["TagKey"]: t["Status"] for t in tags}
ok = budget["BudgetType"] == "COST" and budget["TimeUnit"] == "MONTHLY" and not filters and shape == want and statuses == {"Project": "Active", "Environment": "Active"}
print(f"type={budget['BudgetType']} unit={budget['TimeUnit']} filtered={bool(filters)} notifications_match={shape == want} tags={statuses}")
sys.exit(0 if ok else 1)
PY

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
