#!/usr/bin/env bash
# Git gate, run when a release is actually being cut (not on every push).
# Makes sure what was validated is exactly what is tagged:
#   - no uncommitted or untracked changes
#   - HEAD is on the release branch history
#   - an annotated tag v<image.tag> exists and points at HEAD
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
export PATH="$ROOT/.venv/bin:$PATH"

MANIFEST="${CRV_MANIFEST:-release/manifest.yml}"
BRANCH="${CRV_RELEASE_BRANCH:-main}"
PYTHON="${PYTHON:-python3}"

failed=0
fail() {
  echo "  FAIL $1"
  failed=1
}
pass() { echo "  ok   $1"; }

version="$("$PYTHON" -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["image"]["tag"])' "$MANIFEST")" || {
  echo "could not read image.tag from $MANIFEST" >&2
  exit 2
}
tag="v$version"

if [[ -n "$(git status --porcelain)" ]]; then
  fail "working tree has uncommitted or untracked changes"
else
  pass "working tree is clean"
fi

if git rev-parse --verify --quiet "refs/heads/$BRANCH" >/dev/null &&
  git merge-base --is-ancestor HEAD "$BRANCH"; then
  pass "HEAD is part of $BRANCH"
else
  fail "HEAD is not part of $BRANCH"
fi

if ! git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
  fail "tag $tag does not exist"
else
  if [[ "$(git cat-file -t "refs/tags/$tag")" == "tag" ]]; then
    pass "tag $tag is annotated"
  else
    fail "tag $tag is lightweight; use 'git tag -a'"
  fi
  if [[ "$(git rev-parse "$tag^{commit}")" == "$(git rev-parse HEAD)" ]]; then
    pass "tag $tag points at HEAD"
  else
    fail "tag $tag does not point at HEAD"
  fi
fi

exit "$failed"
