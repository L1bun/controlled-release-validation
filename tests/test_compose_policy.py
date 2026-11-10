from pathlib import Path

import pytest
import yaml

from checks.common import FAIL
from checks.compose_policy import check_compose

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def stack():
    return yaml.safe_load((ROOT / "repro/docker-compose.yml").read_text())


def failed(doc):
    return {(finding.subject, finding.rule) for finding in check_compose(doc) if finding.status == FAIL}


def test_shipped_stack_passes(stack):
    assert failed(stack) == set()


def test_scenarios_only_touch_config_and_mounts():
    # scenarios break the deployment; they must not loosen the sandbox itself
    for override in sorted((ROOT / "repro/scenarios").glob("*.yml")):
        for name, changes in yaml.safe_load(override.read_text())["services"].items():
            assert set(changes) <= {"environment", "volumes"}, f"{override.name}: {name}"


@pytest.mark.parametrize(
    "change, rule",
    [
        ({"image": "nginx"}, "CMP001"),
        ({"image": "nginx:latest"}, "CMP001"),
        ({"image": "registry.local:5000/nginx"}, "CMP001"),
        ({"privileged": True}, "CMP002"),
        ({"network_mode": "host"}, "CMP003"),
        ({"pid": "host"}, "CMP004"),
        ({"read_only": False}, "CMP005"),
        ({"cap_drop": ["NET_RAW"]}, "CMP006"),
        ({"cap_add": ["SYS_ADMIN"]}, "CMP007"),
        ({"security_opt": []}, "CMP008"),
        ({"user": "root"}, "CMP009"),
        ({"user": "0:0"}, "CMP009"),
        ({"ports": ["8080:8080"]}, "CMP010"),
        ({"ports": ["0.0.0.0:8080:8080"]}, "CMP010"),
        ({"ports": [{"target": 8080, "published": "8080", "host_ip": "0.0.0.0"}]}, "CMP010"),
        ({"volumes": ["/var/run/docker.sock:/var/run/docker.sock"]}, "CMP011"),
        ({"volumes": [{"type": "bind", "source": "/etc/shadow", "target": "/x"}]}, "CMP011"),
    ],
)
def test_single_violations(stack, change, rule):
    stack["services"]["proxy"].update(change)
    assert failed(stack) == {("proxy", rule)}


@pytest.mark.parametrize(
    "change",
    [
        {"image": "nginx@sha256:" + "0" * 64},
        {"image": "registry.local:5000/nginx:1.28"},
        {"ports": ["127.0.0.1:8080:8080"]},
        {"ports": ["[::1]:8080:8080"]},
        {"ports": ["8080"]},
        {"security_opt": ["no-new-privileges=true"]},
        {"user": "101:101"},
    ],
)
def test_acceptable_variants(stack, change):
    stack["services"]["proxy"].update(change)
    assert failed(stack) == set()


def test_empty_file_fails():
    assert failed({}) == {("services", "CMP000")}
