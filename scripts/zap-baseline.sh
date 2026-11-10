#!/usr/bin/env bash
# OWASP ZAP baseline scan (spider + passive rules) against the running stack.
# Slower than the probe gate, so it is run on demand and before a release is
# signed off rather than on every push.
#
# The scanner joins the stack's edge network and talks to the proxy by service
# name, so nothing extra has to be published on the host.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${CRV_OUT:-$ROOT/out}/zap"
ZAP_IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"
NETWORK="${CRV_NETWORK:-crv_edge}"
TARGET="${ZAP_TARGET:-http://proxy:8080}"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  echo "network $NETWORK not found - start the stack first (make up)" >&2
  exit 2
fi

mkdir -p "$OUT"
# the zap user inside the container has to be able to write the reports
chmod 777 "$OUT"

# zap-baseline.py exits 0 when clean, 2 when it only has warnings, 1 on failures.
rc=0
docker run --rm \
  --network "$NETWORK" \
  --volume "$OUT:/zap/wrk:rw" \
  "$ZAP_IMAGE" \
  zap-baseline.py -t "$TARGET" -r zap-baseline.html -J zap-baseline.json || rc=$?

echo "reports: ${OUT#"$ROOT"/}/zap-baseline.html"

case "$rc" in
  0) echo "zap baseline: clean" ;;
  2)
    echo "zap baseline: warnings - review the report before sign-off"
    [[ "${ZAP_STRICT:-0}" == "1" ]] && exit 1
    ;;
  *)
    echo "zap baseline: failed (exit $rc)" >&2
    exit 1
    ;;
esac
exit 0
