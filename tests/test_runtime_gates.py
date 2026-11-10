"""The runtime gates, run against a real HTTP server on a random local port."""

from pathlib import Path

import yaml

from checks.common import FAIL
from checks.owasp_probe import Probe
from checks.smoke import run_smoke

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = yaml.safe_load((ROOT / "release/manifest.yml").read_text())


def failures(findings):
    return [(f.rule, f.subject, f.message) for f in findings if f.status == FAIL]


def test_owasp_gate_passes_behind_hardening(hardened_service):
    assert failures(Probe(hardened_service).run()) == []


def test_owasp_gate_catches_an_unprotected_service(bare_service):
    failed = failures(Probe(bare_service).run())
    rules = {rule for rule, _, _ in failed}
    # no proxy in front: headers are missing and the dev server advertises itself
    assert rules == {"A05-01", "A05-03"}
    missing = {message.split(" header")[0] for rule, _, message in failed if rule == "A05-01"}
    assert missing == {
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
        "Permissions-Policy",
    }


def test_smoke_passes_when_running_version_matches(hardened_service):
    assert failures(run_smoke(hardened_service, MANIFEST)) == []


def test_smoke_catches_wrong_version(hardened_service, monkeypatch):
    monkeypatch.setenv("RELEASE_VERSION", "1.8.2")
    assert [rule for rule, _, _ in failures(run_smoke(hardened_service, MANIFEST))] == ["SMK003"]


def test_smoke_reports_why_the_service_is_not_ready(hardened_service, monkeypatch):
    monkeypatch.setenv("APP_ENV", "")
    failed = failures(run_smoke(hardened_service, MANIFEST))
    assert ("SMK002", "GET /readyz", "returned 503 APP_ENV is not set") in failed
