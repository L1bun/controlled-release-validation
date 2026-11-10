import copy
from pathlib import Path

import pytest
import yaml

from checks.common import FAIL, WARN
from checks.release_manifest import check_manifest

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    return yaml.safe_load((ROOT / path).read_text())


@pytest.fixture
def good():
    return load("release/manifest.yml")


def failed_rules(doc):
    return {finding.rule for finding in check_manifest(doc) if finding.status == FAIL}


def test_shipped_manifest_is_clean(good):
    findings = check_manifest(good)
    assert [f for f in findings if f.status in (FAIL, WARN)] == []


def test_broken_fixture_trips_every_rule_family():
    rules = failed_rules(load("tests/fixtures/manifest-bad.yml"))
    assert rules == {
        "CFG001",  # owner empty, change_ref missing
        "CFG012",  # mutable tag
        "CFG013",  # not a version
        "CFG014",  # no digest
        "CFG021",  # unknown environment
        "CFG022",  # RELEASE_VERSION != tag
        "CFG023",  # inline secret
        "CFG024",  # credentials in URL
        "CFG026",  # secret without a ref
        "CFG030",  # no resource limits
        "CFG031",  # readiness probe missing
        "CFG041",  # rollback to itself
    }


@pytest.mark.parametrize(
    "path, value, rule",
    [
        ("image.digest", "sha256:abc", "CFG014"),
        ("runtime.env.APP_ENV", "dev", "CFG021"),
        ("runtime.env.RELEASE_VERSION", "1.8.2", "CFG022"),
        ("runtime.env.API_TOKEN", "abc123", "CFG023"),
        ("runtime.env.CACHE_URL", "redis://default:pw@cache:6379/0", "CFG024"),
        ("runtime.resources.memory", None, "CFG030"),
        ("runtime.probes.readiness", "readyz", "CFG031"),
        ("rollback.previous_tag", None, "CFG040"),
        ("rollback.previous_tag", "1.8.3", "CFG041"),
    ],
)
def test_single_defects(good, path, value, rule):
    doc = copy.deepcopy(good)
    node = doc
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = value
    assert failed_rules(doc) == {rule}


@pytest.mark.parametrize(
    "tag, rules",
    [
        ("latest", {"CFG012", "CFG013"}),
        ("1.8", {"CFG013"}),
        ("v1.8.3", {"CFG013"}),
        ("1.8.3-rc.1", set()),
    ],
)
def test_image_tags(good, tag, rules):
    good["image"]["tag"] = tag
    good["runtime"]["env"]["RELEASE_VERSION"] = tag
    assert failed_rules(good) == rules


def test_secret_named_key_may_be_empty(good):
    # an empty placeholder is not a leaked value
    good["runtime"]["env"]["API_TOKEN"] = ""
    assert failed_rules(good) == set()


def test_production_needs_replicas(good):
    good["runtime"]["env"]["APP_ENV"] = "production"
    good["runtime"]["replicas"] = 1
    assert failed_rules(good) == {"CFG032"}


def test_unverified_rollback_is_a_warning_not_a_failure(good):
    good["rollback"]["verified"] = False
    findings = check_manifest(good)
    assert failed_rules(good) == set()
    assert [f.rule for f in findings if f.status == WARN] == ["CFG042"]
