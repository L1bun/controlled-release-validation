#!/usr/bin/env bash
# Drive the validation stack.
#
#   scripts/repro.sh up                 build and start the stack, wait until healthy
#   scripts/repro.sh scenario <name>    restart it with a failure scenario applied
#   scripts/repro.sh scenarios          list available scenarios
#   scripts/repro.sh collect [label]    save logs/state/probes to out/repro/
#   scripts/repro.sh down               stop it and delete its volume
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/repro/docker-compose.yml"
SCENARIOS="$ROOT/repro/scenarios"
PROJECT=crv
TARGET="${CRV_TARGET:-http://127.0.0.1:8080}"
OUT="${CRV_OUT:-$ROOT/out}"
SETTLE_SECONDS="${CRV_SETTLE_SECONDS:-45}"

usage() {
  sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 2
}

list_scenarios() {
  for file in "$SCENARIOS"/*.yml; do
    printf '%-26s %s\n' "$(basename "$file" .yml)" "$(sed -n '1s/^# *//p' "$file")"
  done
}

# Wait until no container is still in its healthcheck start period.
settle() {
  local deadline=$((SECONDS + SETTLE_SECONDS)) ids states
  while ((SECONDS < deadline)); do
    ids="$(docker compose -p "$PROJECT" ps -aq)"
    if [[ -n "$ids" ]]; then
      # shellcheck disable=SC2086  # ids is a whitespace-separated list
      states="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $ids)"
      grep -q starting <<<"$states" || return 0
    fi
    sleep 2
  done
}

probe() {
  local path code body
  body="$(mktemp)"
  for path in /healthz /readyz /api/version; do
    code="$(curl --silent --max-time 5 --output "$body" --write-out '%{http_code}' "$TARGET$path" || true)"
    printf '%s %s  %s\n' "${code:-000}" "$path" "$(head -c 300 "$body" | tr -d '\n')"
    : >"$body"
  done
  rm -f "$body"
}

collect() {
  local label="${1:-manual}" dir ids
  dir="$OUT/repro/${label}-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$dir"

  docker compose -p "$PROJECT" ps -a >"$dir/ps.txt" 2>&1 || true
  docker compose -p "$PROJECT" logs --no-color --timestamps >"$dir/logs.txt" 2>&1 || true
  docker compose "${COMPOSE_FILES[@]}" config >"$dir/compose-rendered.yml" 2>&1 || true
  ids="$(docker compose -p "$PROJECT" ps -aq)"
  if [[ -n "$ids" ]]; then
    # shellcheck disable=SC2086
    docker inspect $ids >"$dir/inspect.json" 2>&1 || true
  fi
  probe >"$dir/probe.txt"
  {
    date -u +%Y-%m-%dT%H:%M:%SZ
    git -C "$ROOT" rev-parse HEAD 2>/dev/null || true
    docker version --format 'docker {{.Server.Version}}' 2>/dev/null || true
    uname -srm
  } >"$dir/context.txt"

  echo "evidence saved to ${dir#"$ROOT"/}"
}

COMPOSE_FILES=(-f "$BASE")

case "${1:-}" in
  up)
    docker compose "${COMPOSE_FILES[@]}" up -d --build --wait
    probe
    ;;
  scenario)
    name="${2:-}"
    if [[ -z "$name" || ! -f "$SCENARIOS/$name.yml" ]]; then
      echo "unknown scenario '${name}'. available:" >&2
      list_scenarios >&2
      exit 2
    fi
    COMPOSE_FILES+=(-f "$SCENARIOS/$name.yml")
    # start from nothing so the result only reflects this scenario
    docker compose -p "$PROJECT" down --volumes --remove-orphans >/dev/null 2>&1 || true
    docker compose "${COMPOSE_FILES[@]}" up -d --build
    settle
    echo
    docker compose -p "$PROJECT" ps -a
    echo
    probe
    echo
    collect "$name"
    echo "stack is still running for inspection; 'scripts/repro.sh down' when finished."
    ;;
  scenarios)
    list_scenarios
    ;;
  collect)
    collect "${2:-manual}"
    ;;
  down)
    docker compose -p "$PROJECT" down --volumes --remove-orphans
    ;;
  *)
    usage
    ;;
esac
