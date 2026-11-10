#!/usr/bin/env bash
# Secrets gate. Scans the files as they are on disk and, inside a git repo,
# every commit in history - a secret that was committed and then deleted is
# still a leaked secret.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/.tools/bin:$PATH"
OUT="${CRV_OUT:-out}"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "missing tool: gitleaks (run 'make tools')" >&2
  exit 127
fi

mkdir -p "$OUT"
status=0

echo "working tree"
gitleaks dir . --config .gitleaks.toml --redact --no-banner --no-color \
  --report-format json --report-path "$OUT/secrets-tree.json" || status=1

if git rev-parse --git-dir >/dev/null 2>&1 && git rev-parse HEAD >/dev/null 2>&1; then
  echo "git history"
  gitleaks git . --config .gitleaks.toml --redact --no-banner --no-color \
    --report-format json --report-path "$OUT/secrets-history.json" || status=1
fi

exit "$status"
