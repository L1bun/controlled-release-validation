"""Smoke gate: is the thing that is running the thing the manifest says we are releasing?

python -m checks.smoke --target http://127.0.0.1:8080 --manifest release/manifest.yml
"""

import argparse

import requests

from checks.common import FAIL, PASS, Finding, die, exit_code, print_findings, write_report
from checks.release_manifest import load_manifest

TIMEOUT = 5


def run_smoke(target: str, manifest: dict, session=None) -> list:
    http = session or requests.Session()
    target = target.rstrip("/")
    findings = []

    def record(rule, ok, subject, fail_msg):
        findings.append(Finding(rule, PASS if ok else FAIL, subject, "ok" if ok else fail_msg))

    probes = (manifest.get("runtime") or {}).get("probes") or {}
    for rule, kind in (("SMK001", "liveness"), ("SMK002", "readiness")):
        path = probes.get(kind)
        if not path:
            record(rule, False, kind, "no probe path in the manifest")
            continue
        response = http.get(target + path, timeout=TIMEOUT)
        detail = ""
        if response.status_code != 200:
            try:
                detail = "; ".join(response.json().get("problems", []))
            except ValueError:
                detail = ""
        record(rule, response.status_code == 200, f"GET {path}", f"returned {response.status_code} {detail}".strip())

    expected = str((manifest.get("image") or {}).get("tag", ""))
    response = http.get(target + "/api/version", timeout=TIMEOUT)
    try:
        running = response.json()
    except ValueError:
        running = {}
    record(
        "SMK003",
        response.status_code == 200 and running.get("version") == expected,
        "GET /api/version",
        f"running version {running.get('version')!r} is not the manifest version {expected!r}",
    )

    service = (manifest.get("release") or {}).get("service")
    record(
        "SMK004",
        running.get("service") == service,
        "GET /api/version",
        f"running service {running.get('service')!r} is not {service!r}",
    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a running release candidate.")
    parser.add_argument("--target", required=True)
    parser.add_argument("--manifest", default="release/manifest.yml")
    parser.add_argument("--report", help="write a JSON report to this path")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    try:
        findings = run_smoke(args.target, manifest)
    except requests.RequestException as exc:
        die(f"could not reach {args.target}: {exc}")

    print_findings("smoke", findings, args.verbose)
    write_report(args.report, "smoke", args.target, findings)
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
