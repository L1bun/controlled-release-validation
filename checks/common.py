"""Shared plumbing for the Python gates: findings, console output, JSON reports."""

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

FAIL = "FAIL"
WARN = "WARN"
PASS = "PASS"


@dataclass
class Finding:
    rule: str
    status: str
    subject: str
    message: str


def summarize(findings: list) -> dict:
    counts = {FAIL: 0, WARN: 0, PASS: 0}
    for finding in findings:
        counts[finding.status] += 1
    return counts


def print_findings(gate: str, findings: list, verbose: bool = False) -> None:
    for finding in findings:
        if finding.status == PASS and not verbose:
            continue
        print(f"  {finding.status:<4} {finding.rule:<7} {finding.subject}: {finding.message}")
    counts = summarize(findings)
    print(f"{gate}: {counts[FAIL]} failed, {counts[WARN]} warnings, {counts[PASS]} passed")


def write_report(path, gate: str, target: str, findings: list) -> None:
    if not path:
        return
    report = {
        "gate": gate,
        "target": target,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summarize(findings),
        "findings": [asdict(finding) for finding in findings],
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")


def exit_code(findings: list) -> int:
    return 1 if any(finding.status == FAIL for finding in findings) else 0


def die(message: str) -> None:
    """Exit 2 for problems with the gate itself (bad input, unreachable target)."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)
