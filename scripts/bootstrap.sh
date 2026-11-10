#!/usr/bin/env bash
# Install everything the gates need into the repo: a Python venv in .venv and
# pinned hadolint/gitleaks binaries in .tools/bin. Safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/.tools/bin"

HADOLINT_VERSION=2.15.1
GITLEAKS_VERSION=8.21.2

os="$(uname -s)"
arch="$(uname -m)"

if [[ "$os" != "Linux" ]]; then
  echo "bootstrap.sh downloads Linux binaries only." >&2
  echo "On macOS: brew install hadolint gitleaks, then re-run with SKIP_BINARIES=1." >&2
  [[ "${SKIP_BINARIES:-0}" == "1" ]] || exit 1
fi

case "$arch" in
  x86_64)
    hadolint_asset="hadolint-linux-x86_64"
    hadolint_sha="c7187db94eeeeca956519a6af171adc31453941a1e777961f6e680f697c8c507"
    gitleaks_asset="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
    gitleaks_sha="5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba"
    ;;
  aarch64 | arm64)
    hadolint_asset="hadolint-linux-arm64"
    hadolint_sha="f6198ef8090f404dbb771abfee086eb8c48ac177f30da7fd3510aca35b344b5d"
    gitleaks_asset="gitleaks_${GITLEAKS_VERSION}_linux_arm64.tar.gz"
    gitleaks_sha="654c935542c89f565aabe7bf7c6c500830f116c114f0aeb509d2460c1ac2e6da"
    ;;
  *)
    echo "unsupported architecture: $arch" >&2
    exit 1
    ;;
esac

fetch() {
  local url="$1" dest="$2" sha="$3"
  curl --fail --silent --show-error --location --retry 3 --output "$dest" "$url"
  echo "$sha  $dest" | sha256sum --check --quiet
}

echo "==> python environment (.venv)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$ROOT/.venv/bin/pip" install --quiet -r "$ROOT/requirements-dev.txt"

if [[ "${SKIP_BINARIES:-0}" != "1" ]]; then
  mkdir -p "$TOOLS"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  if [[ "$("$TOOLS/hadolint" --version 2>/dev/null || true)" != *"$HADOLINT_VERSION"* ]]; then
    echo "==> hadolint $HADOLINT_VERSION"
    fetch "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/${hadolint_asset}" \
      "$tmp/hadolint" "$hadolint_sha"
    install -m 0755 "$tmp/hadolint" "$TOOLS/hadolint"
  fi

  if [[ "$("$TOOLS/gitleaks" version 2>/dev/null || true)" != *"$GITLEAKS_VERSION"* ]]; then
    echo "==> gitleaks $GITLEAKS_VERSION"
    fetch "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${gitleaks_asset}" \
      "$tmp/gitleaks.tar.gz" "$gitleaks_sha"
    tar -xzf "$tmp/gitleaks.tar.gz" -C "$tmp" gitleaks
    install -m 0755 "$tmp/gitleaks" "$TOOLS/gitleaks"
  fi
fi

echo "done. tools are in .venv/bin and .tools/bin; the Makefile puts both on PATH."
