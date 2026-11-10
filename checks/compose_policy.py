"""Container runtime policy gate for docker compose files.

Works on rendered output, so overrides and variable substitution are already
applied by the time the rules run:

    docker compose -f repro/docker-compose.yml config | python -m checks.compose_policy -

A plain file path works too.
"""

import argparse
import sys

import yaml

from checks.common import FAIL, PASS, WARN, Finding, die, exit_code, print_findings, write_report

LOOPBACK = ("127.0.0.1", "::1", "localhost")
SENSITIVE_MOUNTS = ("/var/run/docker.sock", "/run/docker.sock", "/proc", "/sys", "/etc")


def _image_tag(image: str) -> str:
    """Return the tag of an image reference, '' if it has none."""
    name = image.split("@", 1)[0]
    last = name.rsplit("/", 1)[-1]
    return last.split(":", 1)[1] if ":" in last else ""


def _port_host_ip(port) -> str:
    """Host IP a port is published on; '' means all interfaces."""
    if isinstance(port, dict):
        return str(port.get("host_ip", ""))
    parts = str(port).rsplit(":", 2)
    return parts[0].strip("[]") if len(parts) == 3 else ""


def _is_published(port) -> bool:
    if isinstance(port, dict):
        return "published" in port
    return ":" in str(port)


def _mount_source(volume) -> str:
    if isinstance(volume, dict):
        return str(volume.get("source", ""))
    return str(volume).split(":", 1)[0]


def check_compose(doc: dict) -> list:
    findings = []
    services = doc.get("services")
    if not isinstance(services, dict) or not services:
        return [Finding("CMP000", FAIL, "services", "no services defined")]

    for name, svc in services.items():
        svc = svc or {}

        def record(rule, ok, fail_msg, level=FAIL, _name=name):
            findings.append(Finding(rule, PASS if ok else level, _name, "ok" if ok else fail_msg))

        image = str(svc.get("image", ""))
        if "@sha256:" in image:
            record("CMP001", True, "")
        else:
            tag = _image_tag(image)
            record("CMP001", bool(tag) and tag != "latest", f"image '{image}' is not pinned to a version")

        record("CMP002", svc.get("privileged") is not True, "runs privileged")
        record("CMP003", svc.get("network_mode") != "host", "uses the host network")
        record("CMP004", svc.get("pid") != "host", "shares the host PID namespace")
        record("CMP005", svc.get("read_only") is True, "root filesystem is writable; set read_only: true")

        cap_drop = [str(cap).upper() for cap in svc.get("cap_drop") or []]
        record("CMP006", "ALL" in cap_drop, "does not drop all capabilities")
        record("CMP007", not svc.get("cap_add"), f"adds capabilities: {svc.get('cap_add')}")

        security_opt = [str(opt).replace("=", ":") for opt in svc.get("security_opt") or []]
        record(
            "CMP008",
            any(opt in ("no-new-privileges:true", "no-new-privileges") for opt in security_opt),
            "no-new-privileges is not set",
        )

        user = str(svc.get("user", "")).split(":", 1)[0]
        record("CMP009", user not in ("", "0", "root"), "runs as root; set a non-root user")

        open_ports = [p for p in svc.get("ports") or [] if _is_published(p) and _port_host_ip(p) not in LOOPBACK]
        record("CMP010", not open_ports, "publishes ports on all interfaces; bind to 127.0.0.1")

        bad_mounts = [
            src
            for src in map(_mount_source, svc.get("volumes") or [])
            if any(src == path or src.startswith(path + "/") for path in SENSITIVE_MOUNTS)
        ]
        record("CMP011", not bad_mounts, f"mounts sensitive host paths: {bad_mounts}")

        has_limit = bool(svc.get("mem_limit") or (svc.get("deploy") or {}).get("resources", {}).get("limits"))
        record("CMP012", has_limit, "no memory limit", level=WARN)
        record("CMP013", bool(svc.get("healthcheck")), "no healthcheck", level=WARN)

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a compose file against the runtime policy.")
    parser.add_argument("compose", help="compose file, or - to read rendered config from stdin")
    parser.add_argument("--report", help="write a JSON report to this path")
    parser.add_argument("-v", "--verbose", action="store_true", help="also list passing checks")
    args = parser.parse_args()

    try:
        if args.compose == "-":
            doc = yaml.safe_load(sys.stdin)
        else:
            with open(args.compose) as fh:
                doc = yaml.safe_load(fh)
    except OSError as exc:
        die(f"cannot read {args.compose}: {exc.strerror}")
    except yaml.YAMLError as exc:
        die(f"not valid YAML: {exc}")
    if not isinstance(doc, dict):
        die("compose input is empty or not a mapping")

    findings = check_compose(doc)
    print_findings("compose policy", findings, args.verbose)
    write_report(args.report, "compose-policy", args.compose, findings)
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
