"""Release manifest gate.

Checks that a release manifest describes something that can be deployed,
identified and rolled back. Usage:

    python -m checks.release_manifest release/manifest.yml [--report out/manifest.json]
"""

import argparse
import re

import yaml

from checks.common import FAIL, PASS, WARN, Finding, die, exit_code, print_findings, write_report

MUTABLE_TAGS = {"latest", "stable", "main", "master", "dev", "edge", "nightly"}
ALLOWED_ENVS = {"validation", "staging", "production"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_KEY_RE = re.compile(r"(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIAL)", re.I)
# user:password@host inside a URL
URL_CREDENTIALS_RE = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


def _get(doc, dotted, default=None):
    node = doc
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def check_manifest(doc: dict) -> list:
    findings = []

    def record(rule, ok, subject, fail_msg, ok_msg="ok", level=FAIL):
        findings.append(Finding(rule, PASS if ok else level, subject, ok_msg if ok else fail_msg))
        return ok

    # --- identity ---------------------------------------------------------
    for key in ("release.id", "release.service", "release.owner", "release.change_ref"):
        value = _get(doc, key)
        record("CFG001", isinstance(value, str) and bool(value.strip()), key, "required field is missing or empty")

    # --- image ------------------------------------------------------------
    tag = _get(doc, "image.tag")
    tag = str(tag) if tag is not None else ""
    repository = _get(doc, "image.repository")
    record("CFG010", isinstance(repository, str) and bool(repository.strip()), "image.repository", "required")
    if record("CFG011", bool(tag), "image.tag", "required"):
        record("CFG012", tag.lower() not in MUTABLE_TAGS, "image.tag", f"'{tag}' is a mutable tag; pin a version")
        record("CFG013", bool(VERSION_RE.match(tag)), "image.tag", f"'{tag}' is not MAJOR.MINOR.PATCH")
    digest = _get(doc, "image.digest", "")
    record(
        "CFG014",
        isinstance(digest, str) and bool(DIGEST_RE.match(digest)),
        "image.digest",
        "must be a sha256 digest so the tag cannot be repointed after validation",
    )

    # --- runtime configuration -------------------------------------------
    env = _get(doc, "runtime.env", {})
    if not record("CFG020", isinstance(env, dict), "runtime.env", "must be a mapping"):
        env = {}

    app_env = env.get("APP_ENV")
    record(
        "CFG021", app_env in ALLOWED_ENVS, "runtime.env.APP_ENV", f"'{app_env}' is not one of {sorted(ALLOWED_ENVS)}"
    )
    record(
        "CFG022",
        bool(tag) and str(env.get("RELEASE_VERSION", "")) == tag,
        "runtime.env.RELEASE_VERSION",
        f"'{env.get('RELEASE_VERSION')}' does not match image.tag '{tag}'",
    )

    for key, value in env.items():
        text = "" if value is None else str(value)
        record(
            "CFG023",
            not (SECRET_KEY_RE.search(str(key)) and text),
            f"runtime.env.{key}",
            "looks like a secret with an inline value; move it to runtime.secrets",
        )
        record(
            "CFG024",
            not URL_CREDENTIALS_RE.search(text),
            f"runtime.env.{key}",
            "URL carries embedded credentials",
        )

    secrets = _get(doc, "runtime.secrets", [])
    if record("CFG025", isinstance(secrets, list), "runtime.secrets", "must be a list"):
        for index, item in enumerate(secrets):
            ok = (
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("ref"), str)
                and "://" in item["ref"]
            )
            record("CFG026", ok, f"runtime.secrets[{index}]", "needs 'name' and a 'ref' pointing at a secret store")

    for key in ("runtime.resources.cpu", "runtime.resources.memory"):
        record("CFG030", bool(_get(doc, key)), key, "resource limit is not set")

    for key in ("runtime.probes.liveness", "runtime.probes.readiness"):
        value = _get(doc, key)
        record("CFG031", isinstance(value, str) and value.startswith("/"), key, "probe path is required")

    replicas = _get(doc, "runtime.replicas")
    if app_env == "production":
        record(
            "CFG032",
            isinstance(replicas, int) and replicas >= 2,
            "runtime.replicas",
            "production needs at least 2 replicas",
        )

    # --- rollback ---------------------------------------------------------
    previous = _get(doc, "rollback.previous_tag")
    previous = str(previous) if previous is not None else ""
    if record("CFG040", bool(previous), "rollback.previous_tag", "no rollback target recorded"):
        record("CFG041", previous != tag, "rollback.previous_tag", "rollback target is the release itself")
    record(
        "CFG042",
        _get(doc, "rollback.verified") is True,
        "rollback.verified",
        "rollback has not been exercised for this release",
        level=WARN,
    )

    return findings


def load_manifest(path: str) -> dict:
    try:
        with open(path) as fh:
            doc = yaml.safe_load(fh)
    except OSError as exc:
        die(f"cannot read {path}: {exc.strerror}")
    except yaml.YAMLError as exc:
        die(f"{path} is not valid YAML: {exc}")
    if not isinstance(doc, dict):
        die(f"{path}: top level must be a mapping")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a release manifest.")
    parser.add_argument("manifest")
    parser.add_argument("--report", help="write a JSON report to this path")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list passing checks")
    args = parser.parse_args()

    findings = check_manifest(load_manifest(args.manifest))
    print_findings("release manifest", findings, args.verbose)
    write_report(args.report, "release-manifest", args.manifest, findings)
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
