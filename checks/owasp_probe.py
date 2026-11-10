"""OWASP gate: black-box checks against a running release candidate.

These are the checks that kept getting done by hand before a release went
out. Each one maps to an OWASP Top 10 (2021) category so a failure can be
filed against something people recognise. It is not a replacement for a full
scan - scripts/zap-baseline.sh covers that - but it is quick enough to run
on every candidate.

    python -m checks.owasp_probe --target http://127.0.0.1:8080
"""

import argparse
import re
import uuid

import requests

from checks.common import FAIL, PASS, Finding, die, exit_code, print_findings, write_report

TIMEOUT = 5

REQUIRED_HEADERS = {
    "X-Content-Type-Options": lambda v: v.strip().lower() == "nosniff",
    "X-Frame-Options": lambda v: v.strip().upper() in ("DENY", "SAMEORIGIN"),
    "Referrer-Policy": lambda v: (
        v.strip().lower() in ("no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin")
    ),
    "Content-Security-Policy": lambda v: "default-src" in v.lower() and "unsafe-eval" not in v.lower(),
    "Permissions-Policy": lambda v: bool(v.strip()),
}

# paths that should never be served by a deployed service
SENSITIVE_PATHS = (
    "/.env",
    "/.git/config",
    "/.git/HEAD",
    "/config.yml",
    "/server-status",
    "/debug",
    "/console",
    "/actuator/env",
    "/metrics",
)

LEAK_PATTERNS = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"File \"[^\"]+\.py\", line \d+"),
    re.compile(r"Werkzeug Debugger", re.I),
    re.compile(r"\bat [\w.$]+\([\w]+\.java:\d+\)"),
    re.compile(r"(^|[\s\"'])/(usr|srv|home|var|opt)/[\w./-]+\.(py|rb|js|php)"),
)

VERSION_IN_BANNER = re.compile(r"\d+\.\d+")


class Probe:
    def __init__(self, target: str, session=None):
        self.target = target.rstrip("/")
        self.https = self.target.lower().startswith("https://")
        self.http = session or requests.Session()
        self.findings = []

    def record(self, rule, ok, subject, fail_msg, ok_msg="ok"):
        self.findings.append(Finding(rule, PASS if ok else FAIL, subject, ok_msg if ok else fail_msg))

    def request(self, method, path, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT)
        kwargs.setdefault("allow_redirects", False)
        return self.http.request(method, self.target + path, **kwargs)

    # A05 Security Misconfiguration ---------------------------------------

    def check_security_headers(self):
        # headers must be present on error responses too, not only on 200s
        for label, path in (("GET /api/version", "/api/version"), ("GET <unknown path>", f"/{uuid.uuid4().hex}")):
            response = self.request("GET", path)
            for header, is_valid in REQUIRED_HEADERS.items():
                value = response.headers.get(header)
                if value is None:
                    self.record("A05-01", False, label, f"{header} header is missing")
                else:
                    self.record("A05-01", is_valid(value), label, f"{header} has a weak value: {value!r}")
            if self.https:
                hsts = response.headers.get("Strict-Transport-Security", "")
                match = re.search(r"max-age=(\d+)", hsts)
                self.record(
                    "A05-02",
                    bool(match) and int(match.group(1)) >= 15552000,
                    label,
                    "Strict-Transport-Security is missing or max-age is under 180 days",
                )

    def check_banner(self):
        response = self.request("GET", "/api/version")
        server = response.headers.get("Server", "")
        self.record(
            "A05-03",
            not VERSION_IN_BANNER.search(server),
            "Server header",
            f"discloses a version: {server!r}",
        )
        for header in ("X-Powered-By", "X-AspNet-Version", "X-Runtime"):
            self.record("A05-03", header not in response.headers, f"{header} header", "should not be sent")

    def check_methods(self):
        for method in ("TRACE", "PUT", "DELETE", "PATCH"):
            response = self.request(method, "/api/version")
            self.record(
                "A05-04",
                response.status_code in (403, 405, 501),
                f"{method} /api/version",
                f"returned {response.status_code}; unused methods should be rejected",
            )
        response = self.request("TRACE", "/", headers={"X-Probe": "crv-trace-echo"})
        self.record("A05-04", "crv-trace-echo" not in response.text, "TRACE /", "request headers are echoed back")

    def check_error_handling(self):
        cases = (
            ("GET <unknown path>", "GET", f"/{uuid.uuid4().hex}", {}),
            (
                "POST /api/notes (broken JSON)",
                "POST",
                "/api/notes",
                {"data": "{not json", "headers": {"Content-Type": "application/json"}},
            ),
            ("POST /api/notes (wrong type)", "POST", "/api/notes", {"json": {"text": {"$gt": ""}}}),
            ("GET /api/notes (odd query)", "GET", "/api/notes?id='%22%3E%3Cscript%3E", {}),
        )
        for label, method, path, kwargs in cases:
            response = self.request(method, path, **kwargs)
            self.record("A05-05", response.status_code < 500, label, f"returned {response.status_code}")
            leaked = [p.pattern for p in LEAK_PATTERNS if p.search(response.text)]
            self.record("A05-05", not leaked, label, "response leaks internals (stack trace or file paths)")

    def check_body_limit(self):
        response = self.request(
            "POST", "/api/notes", data=b"x" * (256 * 1024), headers={"Content-Type": "application/json"}
        )
        self.record(
            "A05-06",
            response.status_code in (400, 413),
            "POST /api/notes (256 KiB body)",
            f"returned {response.status_code}; oversized bodies should be refused",
        )

    # A01 Broken Access Control -------------------------------------------

    def check_sensitive_paths(self):
        for path in SENSITIVE_PATHS:
            response = self.request("GET", path)
            self.record(
                "A01-01",
                response.status_code in (401, 403, 404),
                f"GET {path}",
                f"returned {response.status_code}; this path should not be reachable",
            )

    def check_cors(self):
        origin = "https://crv-probe.invalid"
        response = self.request("GET", "/api/notes", headers={"Origin": origin})
        allow_origin = response.headers.get("Access-Control-Allow-Origin")
        allow_credentials = response.headers.get("Access-Control-Allow-Credentials", "").lower() == "true"
        self.record("A01-02", allow_origin != origin, "CORS", "reflects an arbitrary Origin")
        self.record(
            "A01-02",
            not (allow_origin == "*" and allow_credentials),
            "CORS",
            "wildcard origin combined with credentials",
        )

    # A07 Identification and Authentication Failures ----------------------

    def check_cookies(self):
        response = self.request("GET", "/api/version")
        # requests folds repeated headers together, so read Set-Cookie from urllib3
        cookies = response.raw.headers.getlist("Set-Cookie")
        if not cookies:
            self.record("A07-01", True, "cookies", "", ok_msg="no cookies set")
            return
        for cookie in cookies:
            name = cookie.split("=", 1)[0]
            attrs = [part.strip().lower() for part in cookie.split(";")[1:]]
            self.record("A07-01", "httponly" in attrs, f"cookie {name}", "HttpOnly is not set")
            self.record(
                "A07-01", any(a.startswith("samesite=") for a in attrs), f"cookie {name}", "SameSite is not set"
            )
            if self.https:
                self.record("A07-01", "secure" in attrs, f"cookie {name}", "Secure is not set")

    def run(self) -> list:
        self.check_security_headers()
        self.check_banner()
        self.check_methods()
        self.check_error_handling()
        self.check_body_limit()
        self.check_sensitive_paths()
        self.check_cors()
        self.check_cookies()
        return self.findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OWASP gate against a running service.")
    parser.add_argument("--target", required=True, help="base URL, e.g. http://127.0.0.1:8080")
    parser.add_argument("--report", help="write a JSON report to this path")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list passing checks")
    args = parser.parse_args()

    probe = Probe(args.target)
    try:
        findings = probe.run()
    except requests.RequestException as exc:
        die(f"could not complete the probe against {args.target}: {exc}")

    print_findings("owasp gate", findings, args.verbose)
    write_report(args.report, "owasp", args.target, findings)
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
