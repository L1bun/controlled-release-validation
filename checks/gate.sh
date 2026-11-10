#!/usr/bin/env bash
# Run the release gates and print one verdict per gate.
#
#   checks/gate.sh static     gates that need nothing running
#   checks/gate.sh runtime    gates against a running stack (CRV_TARGET)
#   checks/gate.sh all        both
#   checks/gate.sh yaml owasp ...   any subset, by name
#
# Every gate runs even if an earlier one fails, so one pass shows everything
# that has to be fixed. Exit status is 1 if any gate failed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
export PATH="$ROOT/.venv/bin:$ROOT/.tools/bin:$PATH"

TARGET="${CRV_TARGET:-http://127.0.0.1:8080}"
MANIFEST="${CRV_MANIFEST:-release/manifest.yml}"
OUT="${CRV_OUT:-out}"
PYTHON="${PYTHON:-python3}"

STATIC_GATES=(yaml shell dockerfile secrets manifest compose deps)
RUNTIME_GATES=(smoke owasp)

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing tool: $1 (run 'make tools')" >&2
    return 127
  fi
}

gate_yaml() {
  need yamllint || return
  yamllint --strict .
}

gate_shell() {
  need shellcheck || return
  local files=()
  while IFS= read -r file; do files+=("$file"); done < <(
    find . -name '*.sh' -not -path './.venv/*' -not -path './.tools/*' -not -path './.git/*' | sort
  )
  shellcheck "${files[@]}"
}

gate_dockerfile() {
  need hadolint || return
  hadolint repro/app/Dockerfile
}

gate_secrets() {
  checks/secrets_scan.sh
}

gate_manifest() {
  "$PYTHON" -m checks.release_manifest "$MANIFEST" --report "$OUT/manifest.json"
}

gate_compose() {
  # policy runs on rendered config when docker is around, on the raw file otherwise
  if docker compose version >/dev/null 2>&1; then
    docker compose -f repro/docker-compose.yml config |
      "$PYTHON" -m checks.compose_policy - --report "$OUT/compose-policy.json"
  else
    "$PYTHON" -m checks.compose_policy repro/docker-compose.yml --report "$OUT/compose-policy.json"
  fi
}

gate_deps() {
  need pip-audit || return
  pip-audit --requirement repro/app/requirements.txt --progress-spinner off
}

gate_smoke() {
  "$PYTHON" -m checks.smoke --target "$TARGET" --manifest "$MANIFEST" --report "$OUT/smoke.json"
}

gate_owasp() {
  "$PYTHON" -m checks.owasp_probe --target "$TARGET" --report "$OUT/owasp.json"
}

run_gate() {
  case "$1" in
    yaml) gate_yaml ;;
    shell) gate_shell ;;
    dockerfile) gate_dockerfile ;;
    secrets) gate_secrets ;;
    manifest) gate_manifest ;;
    compose) gate_compose ;;
    deps) gate_deps ;;
    smoke) gate_smoke ;;
    owasp) gate_owasp ;;
  esac
}

ALL_GATES=("${STATIC_GATES[@]}" "${RUNTIME_GATES[@]}")

selected=()
for arg in "${@:-all}"; do
  case "$arg" in
    static) selected+=("${STATIC_GATES[@]}") ;;
    runtime) selected+=("${RUNTIME_GATES[@]}") ;;
    all) selected+=("${ALL_GATES[@]}") ;;
    *)
      if [[ " ${ALL_GATES[*]} " == *" $arg "* ]]; then
        selected+=("$arg")
      else
        echo "unknown gate: $arg" >&2
        echo "gates: ${ALL_GATES[*]}" >&2
        exit 2
      fi
      ;;
  esac
done

mkdir -p "$OUT"
results=()
failed=0

for gate in "${selected[@]}"; do
  echo
  echo "=== $gate"
  if run_gate "$gate"; then
    results+=("PASS  $gate")
  else
    results+=("FAIL  $gate")
    failed=1
  fi
done

{
  echo "release gates  $(date -u +%Y-%m-%dT%H:%M:%SZ)  commit $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  printf '%s\n' "${results[@]}"
} | tee "$OUT/gate-summary.txt" | sed '1s/^/\n/'

exit "$failed"
