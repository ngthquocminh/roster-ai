#!/usr/bin/env bash
# Edge smoke for Story 6.1 (D8c): proves AWS ACCEPTED the configuration that the
# offline `terraform test` suites only prove was INTENDED. Operator-run, after
# `terraform apply`, with the same AWS credentials used for the apply.
#
#   bash infra/scripts/smoke-edge.sh               # defaults to envs/portfolio
#   ENV_DIR=infra/terraform/envs/portfolio bash infra/scripts/smoke-edge.sh
#
# Needs: bash, curl, python3, terraform and the AWS CLI v2 on PATH. `dig` is used
# for DNS when present, otherwise python3's resolver.
#
# It reads everything from `terraform output -json`, uploads a throwaway
# index.html placeholder to the SPA bucket (Story 6.3 replaces it), then asserts
# each item below. It refuses to overwrite an index.html that is not its own
# placeholder unless SMOKE_OVERWRITE_INDEX=1, so it can never clobber a real
# deployed SPA.
#
#   1  https://<app>/ -> 200 with the placeholder; TLS 1.1 handshake is refused
#   2  http://<app>/  -> 301 to https
#   3  /scenario-data -> 200 placeholder (SPA rewrite); /assets/missing.js is NOT
#      rewritten (403/404, no placeholder)
#   4  GET  /api/v1/auth/session -> 503 from the ALB (empty target group).
#      A 502 means the origin certificate does not match origin.<app> (D2)
#   5  POST /api/v1/anything     -> 503 from the ALB, not a CloudFront 403 (D4)
#   6  origin.<app> resolves only to RFC 1918 addresses and a direct request fails
#   7  the direct S3 object URL for index.html -> 403
#   8  <oidc_issuer>/.well-known/openid-configuration: issuer == output (F3) and
#      authorization_endpoint is on the Cognito domain
#   9  the authorize URL for the exact BFF callback is NOT redirect_mismatch
#  10  describe-user-pool: AllowAdminCreateUserOnly is true
#  11  the live /api/* and default behaviors use the managed cache/origin-request
#      policies (the offline test cannot prove this: mock data-source ids are null)
#  12  the live worker security group has no ingress rule and the data route table
#      has no internet route (the offline test cannot see a separately declared
#      rule or route resource)
#
# Exit status is 0 only if every check passed. Nothing here writes to evidence/.
set -uo pipefail

ENV_DIR="${ENV_DIR:-infra/terraform/envs/portfolio}"
MARKER="shiftmind-smoke-placeholder"
PASS=0
FAIL=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for tool in curl python3 terraform aws; do
  command -v "$tool" >/dev/null 2>&1 || { echo "FATAL: '$tool' is required on PATH" >&2; exit 2; }
done

tf_json="$(terraform -chdir="$ENV_DIR" output -json)" || { echo "FATAL: terraform output failed in $ENV_DIR" >&2; exit 2; }

out() {
  # Print one terraform output by name. A missing or empty output is a fatal
  # setup error; `$(...)` cannot exit this shell, so every caller adds `|| exit 2`.
  python3 -c '
import json, sys
data = json.loads(sys.argv[1])
name = sys.argv[2]
if name not in data or data[name]["value"] in ("", None):
    sys.exit(f"FATAL: missing or empty terraform output: {name}")
print(data[name]["value"])
' "$tf_json" "$1" | tr -d '\r'
}

APP="$(out app_domain)" || exit 2
ORIGIN="$(out origin_domain)" || exit 2
REGION="$(out region)" || exit 2
BUCKET="$(out spa_bucket_name)" || exit 2
DIST_ID="$(out distribution_id)" || exit 2
ISSUER="$(out oidc_issuer)" || exit 2
CLIENT_ID="$(out oidc_client_id)" || exit 2
COGNITO_DOMAIN="$(out cognito_domain)" || exit 2
POOL_ID="$(out user_pool_id)" || exit 2
WORKER_SG="$(out worker_security_group_id)" || exit 2
DATA_RT="$(out data_route_table_id)" || exit 2
CALLBACK="https://${APP}/api/v1/auth/callback"

ok()   { PASS=$((PASS + 1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf 'FAIL  %s\n' "$1"; [ -n "${2:-}" ] && printf '      %s\n' "$2"; }
check() { # check "<name>" <condition-exit-status> "<detail on failure>"
  if [ "$2" -eq 0 ]; then ok "$1"; else bad "$1" "${3:-}"; fi
}

# Body, headers and stderr of the last request land in $WORK; the headers file is
# removed first so a failed request cannot leave the previous response's behind.
http_code() {
  rm -f "$WORK/headers"
  curl -sS --max-time 30 -o "$WORK/body" -D "$WORK/headers" -w '%{http_code}' "$@" 2>"$WORK/err" || echo "000"
}
# An ALB-generated response carries `Server: awselb/...`; CloudFront passes it through.
from_alb() { grep -qi '^server: awselb' "$WORK/headers" 2>/dev/null; }

echo "== smoke-edge: https://${APP}  (origin ${ORIGIN}, bucket ${BUCKET}, region ${REGION})"

# --- Wait for the distribution, then seed the placeholder ----------------------
echo "-- waiting for CloudFront distribution ${DIST_ID} to be deployed"
aws cloudfront wait distribution-deployed --id "$DIST_ID" || { echo "FATAL: distribution not deployed" >&2; exit 2; }

# Only a definite "Not Found" means there is nothing to protect. Any other read
# failure (throttling, an expired session, a role that can Put but not Get) is
# fatal, so it can never be mistaken for an empty bucket.
if aws s3api head-object --bucket "$BUCKET" --key index.html >/dev/null 2>"$WORK/err"; then
  existing="$(aws s3 cp "s3://${BUCKET}/index.html" - 2>"$WORK/err")" \
    || { echo "FATAL: could not read the existing index.html: $(cat "$WORK/err")" >&2; exit 2; }
  if ! grep -q "$MARKER" <<<"$existing" && [ "${SMOKE_OVERWRITE_INDEX:-0}" != "1" ]; then
    echo "FATAL: s3://${BUCKET}/index.html exists and is not the smoke placeholder." >&2
    echo "       Refusing to overwrite a real SPA. Set SMOKE_OVERWRITE_INDEX=1 to force." >&2
    exit 2
  fi
elif ! grep -qE '\((404|NoSuchKey)\)|Not Found' "$WORK/err"; then
  echo "FATAL: could not check s3://${BUCKET}/index.html: $(cat "$WORK/err")" >&2
  exit 2
fi
printf '<!doctype html><title>%s</title><p>%s</p>\n' "$MARKER" "$MARKER" \
  | aws s3 cp - "s3://${BUCKET}/index.html" --content-type "text/html" --only-show-errors \
  || { echo "FATAL: could not upload the placeholder" >&2; exit 2; }

# --- 1. HTTPS root, and TLS 1.1 refused ----------------------------------------
code="$(http_code "https://${APP}/")"
[ "$code" = "200" ] && grep -q "$MARKER" "$WORK/body"
check "1a https://${APP}/ -> 200 with the placeholder" $? "got HTTP ${code}; $(cat "$WORK/err")"

# PASS needs positive evidence that the SERVER refused: a TLS alert it sent back.
# A failure on our side proves nothing. OpenSSL 3 will not even offer TLS 1.1 at
# its default security level ("no protocols available"), and DNS, connect and
# timeout errors never reach a handshake, so each of those is a FAIL, not a pass.
if command -v openssl >/dev/null 2>&1; then
  # @SECLEVEL=0 lets this client offer TLS 1.1, so any refusal is CloudFront's.
  openssl s_client -connect "${APP}:443" -servername "${APP}" -tls1_1 -cipher 'DEFAULT:@SECLEVEL=0' \
    </dev/null >"$WORK/tls11" 2>&1
  probe="openssl"
else
  curl -sS --max-time 15 --tls-max 1.1 -o /dev/null "https://${APP}/" 2>"$WORK/tls11"
  probe="curl exit $?"
fi
if grep -q "BEGIN CERTIFICATE\|Cipher is [A-Z]" "$WORK/tls11"; then
  bad "1b TLS 1.1 handshake is refused" "the server accepted TLS 1.1 (${probe})"
else
  grep -qi "alert protocol version\|alert handshake failure\|TLS alert is received" "$WORK/tls11"
  check "1b TLS 1.1 handshake is refused" $? "no server alert, so the refusal was not proven (${probe}): $(tail -n 3 "$WORK/tls11" | tr '\n' ' ')"
fi

# --- 2. HTTP redirects to HTTPS ------------------------------------------------
code="$(curl -sS --max-time 30 -o /dev/null -w '%{http_code} %{redirect_url}' "http://${APP}/" 2>/dev/null || echo "000 ")"
[[ "$code" == 301\ https://* ]]
check "2 http://${APP}/ -> 301 to https" $? "got: ${code}"

# --- 3. SPA deep link rewritten, missing asset not rewritten -------------------
code="$(http_code "https://${APP}/scenario-data")"
[ "$code" = "200" ] && grep -q "$MARKER" "$WORK/body"
check "3a /scenario-data -> 200 placeholder (SPA rewrite)" $? "got HTTP ${code}"

code="$(http_code "https://${APP}/assets/missing.js")"
{ [ "$code" = "403" ] || [ "$code" = "404" ]; } && ! grep -q "$MARKER" "$WORK/body"
check "3b /assets/missing.js -> 403/404 and not the placeholder" $? "got HTTP ${code}"

# --- 4/5. API reaches the ALB (empty target group => 503) ----------------------
code="$(http_code "https://${APP}/api/v1/auth/session")"
if [ "$code" = "502" ]; then
  bad "4 GET /api/v1/auth/session -> 503 from the ALB" "HTTP 502: the origin certificate does not match ${ORIGIN} (D2)"
else
  [ "$code" = "503" ] && from_alb
  check "4 GET /api/v1/auth/session -> 503 from the ALB" $? "got HTTP ${code}; Server: $(grep -i '^server:' "$WORK/headers" 2>/dev/null | tr -d '\r')"
fi

code="$(http_code -X POST -H 'content-type: application/json' -d '{}' "https://${APP}/api/v1/anything")"
[ "$code" = "503" ] && from_alb
check "5 POST /api/v1/anything reaches the ALB (503), not a CloudFront 403" $? "got HTTP ${code}; Server: $(grep -i '^server:' "$WORK/headers" 2>/dev/null | tr -d '\r')"

# --- 6. Origin name is private -------------------------------------------------
if command -v dig >/dev/null 2>&1; then
  addrs="$(dig +short A "$ORIGIN" | grep -E '^[0-9.]+$' | sort -u)"
else
  addrs="$(python3 -c '
import socket, sys
print("\n".join(sorted({a[4][0] for a in socket.getaddrinfo(sys.argv[1], 443, socket.AF_INET)})))
' "$ORIGIN" 2>/dev/null | tr -d '\r')"
fi
if [ -z "$addrs" ]; then
  bad "6a ${ORIGIN} resolves only to RFC 1918 addresses" "no A record resolved"
else
  python3 -c '
import ipaddress, sys
nets = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
sys.exit(0 if all(any(ipaddress.ip_address(a) in n for n in nets) for a in sys.argv[1:]) else 1)
' $addrs
  check "6a ${ORIGIN} resolves only to RFC 1918 addresses" $? "resolved: $(tr '\n' ' ' <<<"$addrs")"
fi
curl -sS --connect-timeout 5 --max-time 8 -o /dev/null "https://${ORIGIN}/health" 2>/dev/null
[ $? -ne 0 ]
check "6b a direct request to ${ORIGIN} from this machine fails to connect" $? "the internal ALB answered from the public internet"

# --- 7. Bucket is not directly readable ----------------------------------------
code="$(http_code "https://${BUCKET}.s3.${REGION}.amazonaws.com/index.html")"
[ "$code" = "403" ]
check "7 the direct S3 object URL -> 403" $? "got HTTP ${code}"

# --- 8/9. OIDC discovery and the exact callback --------------------------------
curl -sS --max-time 30 -o "$WORK/oidc.json" "${ISSUER}/.well-known/openid-configuration" 2>"$WORK/err"
# `tr -d '\r'`: Python on Windows writes CRLF, and `read -r` would keep the CR on
# the last field (auth_endpoint), turning check 9's URL into a malformed request.
read -r disc_issuer auth_endpoint < <(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("issuer", ""), d.get("authorization_endpoint", ""))
except Exception:
    print("", "")
' "$WORK/oidc.json" | tr -d '\r')
[ -n "$disc_issuer" ] && [ "$disc_issuer" = "$ISSUER" ]
check "8a discovery issuer equals the oidc_issuer output exactly (F3)" $? "discovery issuer='${disc_issuer}' output='${ISSUER}'"
[[ "$auth_endpoint" == "https://${COGNITO_DOMAIN}/"* ]]
check "8b authorization_endpoint is on the Cognito domain" $? "authorization_endpoint='${auth_endpoint}' domain='${COGNITO_DOMAIN}'"

if [ -n "$auth_endpoint" ]; then
  url="${auth_endpoint}?response_type=code&client_id=${CLIENT_ID}&redirect_uri=${CALLBACK}&scope=openid+email"
  code="$(http_code "$url")"
  # Cognito answers other authorize errors (bad client_id, bad scope) with a 302
  # too, to its /error page or back to the callback, so "not redirect_mismatch"
  # alone proves nothing. A valid request is redirected to the hosted /login page.
  location="$(grep -i '^location:' "$WORK/headers" 2>/dev/null | tail -n 1 | tr -d '\r')"
  [ "$code" = "302" ] && grep -Eqi "^location: (https://${COGNITO_DOMAIN})?/login\?" <<<"$location" \
    && ! grep -qi "redirect_mismatch" <<<"$location"
  check "9 authorize URL for ${CALLBACK} redirects to the hosted login page" $? "got HTTP ${code}; ${location}"
else
  bad "9 authorize URL for ${CALLBACK} redirects to the hosted login page" "no authorization_endpoint to probe"
fi

# --- 10. Public sign-up is closed ----------------------------------------------
admin_only="$(aws cognito-idp describe-user-pool --region "$REGION" --user-pool-id "$POOL_ID" \
  --query 'UserPool.AdminCreateUserConfig.AllowAdminCreateUserOnly' --output text 2>"$WORK/err")"
[ "$admin_only" = "True" ]
check "10 describe-user-pool: AllowAdminCreateUserOnly is true" $? "got '${admin_only}' $(cat "$WORK/err")"

# --- 11. Live behaviors use the managed policies -------------------------------
aws cloudfront get-distribution-config --id "$DIST_ID" --output json >"$WORK/dist.json" 2>"$WORK/err"
aws cloudfront list-cache-policies --type managed --output json >"$WORK/cache.json" 2>>"$WORK/err"
aws cloudfront list-origin-request-policies --type managed --output json >"$WORK/orp.json" 2>>"$WORK/err"
python3 - "$WORK/dist.json" "$WORK/cache.json" "$WORK/orp.json" <<'PY'
import json, sys

dist = json.load(open(sys.argv[1]))["DistributionConfig"]
cache = {p["CachePolicy"]["CachePolicyConfig"]["Name"]: p["CachePolicy"]["Id"]
         for p in json.load(open(sys.argv[2]))["CachePolicyList"]["Items"]}
orp = {p["OriginRequestPolicy"]["OriginRequestPolicyConfig"]["Name"]: p["OriginRequestPolicy"]["Id"]
       for p in json.load(open(sys.argv[3]))["OriginRequestPolicyList"]["Items"]}

errors = []
default = dist["DefaultCacheBehavior"]
if default["CachePolicyId"] != cache["Managed-CachingOptimized"]:
    errors.append("default behavior is not Managed-CachingOptimized")
api = [b for b in dist["CacheBehaviors"]["Items"] if b["PathPattern"] == "/api/*"]
if len(api) != 1:
    errors.append("expected exactly one /api/* behavior")
else:
    api = api[0]
    if api["CachePolicyId"] != cache["Managed-CachingDisabled"]:
        errors.append("/api/* is not Managed-CachingDisabled")
    if api.get("OriginRequestPolicyId") != orp["Managed-AllViewerExceptHostHeader"]:
        errors.append("/api/* is not Managed-AllViewerExceptHostHeader")
if dist["CustomErrorResponses"]["Quantity"] != 0:
    errors.append("the distribution has custom error responses")
if errors:
    print("      " + "; ".join(errors))
sys.exit(1 if errors else 0)
PY
rc=$?
check "11 live behaviors use the managed cache and origin-request policies" "$rc" "see the message above; $(cat "$WORK/err")"

# --- 12. Live network boundary (AC2 second clause) -----------------------------
# The offline suite sees only the rule and route resources the module declares;
# this reads what is actually attached in AWS.
aws ec2 describe-security-group-rules --region "$REGION" \
  --filters "Name=group-id,Values=${WORKER_SG}" --output json >"$WORK/sg.json" 2>"$WORK/err"
aws ec2 describe-route-tables --region "$REGION" --route-table-ids "$DATA_RT" \
  --output json >"$WORK/rt.json" 2>>"$WORK/err"
python3 - "$WORK/sg.json" "$WORK/rt.json" <<'PY'
import json, sys

errors = []
rules = json.load(open(sys.argv[1]))["SecurityGroupRules"]
ingress = [r["SecurityGroupRuleId"] for r in rules if not r["IsEgress"]]
if ingress:
    errors.append(f"worker security group has ingress rules: {', '.join(ingress)}")
# Only the VPC-local route and the S3 gateway endpoint may sit in the data table.
for route in json.load(open(sys.argv[2]))["RouteTables"][0]["Routes"]:
    target = route.get("GatewayId", "") or route.get("NatGatewayId", "") or "other"
    if not (target == "local" or target.startswith("vpce-")):
        dest = route.get("DestinationCidrBlock") or route.get("DestinationIpv6CidrBlock") or route.get("DestinationPrefixListId")
        errors.append(f"data route table routes {dest} to {target}")
if errors:
    print("      " + "; ".join(errors))
sys.exit(1 if errors else 0)
PY
rc=$?
check "12 live worker SG has no ingress rule and the data tier has no internet route" "$rc" "see the message above; $(cat "$WORK/err")"

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
