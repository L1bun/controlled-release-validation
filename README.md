# Controlled Release Validation Framework

A small, opinionated setup for answering one question before a release goes
out: *is this candidate safe to deploy, and if it isn't, can we reproduce why
somewhere that doesn't matter?*

It has three parts:

- **An isolated Azure environment** (`infra/`) - a VNet with no public IPs on
  the validation subnet, a Linux host with Docker, access through Bastion, and
  RBAC that separates people who *validate* from people who *operate*.
- **A validation stack and failure scenarios** (`repro/`) - the release
  candidate behind an edge proxy, locked down the way it would be in
  production, plus one-line scenarios that recreate common deployment
  failures on demand.
- **Release gates** (`checks/`) - secrets scanning, OWASP checks,
  configuration and container policy checks, and a git check for the release
  tag. One command, one verdict per gate.

The procedures that go with it are in [`runbooks/`](runbooks/).

```
                    Azure resource group
 ┌──────────────────────────────────────────────────────────────┐
 │  vnet-crv 10.42.0.0/24                                       │
 │                                                              │
 │  AzureBastionSubnet          snet-validation (no public IPs) │
 │  ┌──────────┐   ssh/22      ┌─────────────────────────────┐  │
 │  │ bas-crv  ├──────────────►│ vm-crv  (Ubuntu + Docker)   │  │
 │  └────▲─────┘               │                             │  │
 │       │                     │  proxy :8080 ──► app :8000  │  │
 │       │                     │  (edge net)    (internal)   │  │
 │       │                     └──────────────┬──────────────┘  │
 │       │                                    │ 80/443 only     │
 │       │                              ┌─────▼─────┐           │
 │       │                              │  nat-crv  │ (removed  │
 │       │                              └───────────┘  when     │
 │       │                                             sealed)  │
 └───────┼──────────────────────────────────────────────────────┘
   Entra ID login
   validators: read-only   operators: sudo
```

## Quick start (local)

Needs Docker with the compose plugin, Python 3.11+, `make` and `curl`.

```bash
make tools      # venv + pinned hadolint/gitleaks into the repo, nothing global
make validate   # static gates
make test       # unit tests
make up         # build and start the stack on 127.0.0.1:8080
make runtime    # smoke + OWASP gates against it
make down
```

`make gate` runs the whole sequence. Output looks like this:

```
release gates  2026-11-09T21:14:02Z  commit 3f2a91c
PASS  yaml
PASS  shell
PASS  dockerfile
PASS  secrets
PASS  manifest
PASS  compose
PASS  deps
PASS  smoke
PASS  owasp
```

Every gate runs even when an earlier one fails, so a single pass shows
everything that needs fixing. JSON reports land in `out/`.

## The gates

| Gate | What it catches | Implemented in |
| --- | --- | --- |
| `yaml` | Malformed or sloppy YAML (compose, workflows, manifest, cloud-init) | yamllint, `.yamllint.yml` |
| `shell` | Shell script bugs | shellcheck |
| `dockerfile` | Dockerfile problems | hadolint |
| `secrets` | Credentials in the working tree **and** in git history | gitleaks, `checks/secrets_scan.sh` |
| `manifest` | Release manifest defects: mutable tags, missing digest, inline secrets, no rollback target, version mismatch | `checks/release_manifest.py` |
| `compose` | Containers that are privileged, root, writable, or exposed beyond loopback | `checks/compose_policy.py` |
| `deps` | Known-vulnerable dependencies (OWASP A06) | pip-audit |
| `smoke` | The running service is healthy, ready, and is the version the manifest says | `checks/smoke.py` |
| `owasp` | Missing security headers, version banners, unsafe methods, leaky errors, exposed sensitive paths, CORS and cookie mistakes (OWASP A01/A05/A07) | `checks/owasp_probe.py` |
| `git` | Dirty tree, or release tag missing / lightweight / not at HEAD | `checks/git_state.sh` (`make release-check`) |

A deeper scan with OWASP ZAP is available as `make zap`. It takes a few
minutes, so it runs on demand and before sign-off rather than on every push.

Run any subset by name: `checks/gate.sh secrets manifest`.

## Reproducing a deployment failure

```bash
scripts/repro.sh scenarios
make scenario NAME=readonly-data
```

Each scenario is a compose override that breaks exactly one thing. The script
restarts the stack with it applied, waits for health checks to settle, prints
what the probes see, and saves logs, container state and the rendered config
under `out/repro/`. The stack stays up afterwards so you can poke at it.

| Scenario | What is broken | What you see |
| --- | --- | --- |
| `missing-release-version` | Required setting not passed to the app | `/readyz` 503 naming the setting; smoke gate fails |
| `wrong-upstream-port` | Proxy points at a port the app isn't on | App healthy, every request a 502 |
| `readonly-data` | Data volume mounted read-only | `/readyz` 503 "not writable" |
| `stripped-headers` | Proxy lost its security header block | Healthy, smoke passes, OWASP gate fails |

To reproduce something that isn't covered, copy a scenario file and change
it; see [`repro/scenarios/README.md`](repro/scenarios/README.md).

## Azure environment

```bash
export CRV_RG=rg-crv-validation CRV_LOCATION=eastus2
export CRV_SSH_PUBLIC_KEY_FILE=~/.ssh/id_ed25519.pub
export CRV_VALIDATORS_ID=<entra group object id>
export CRV_OPERATORS_ID=<entra group object id>

infra/deploy.sh what-if
infra/deploy.sh up
infra/deploy.sh ssh
```

Details, cost notes and the sealed (no-egress) mode are in
[`infra/README.md`](infra/README.md).

## Runbooks

| Runbook | Use it when |
| --- | --- |
| [Release readiness](runbooks/release-readiness.md) | A candidate is ready and needs a go / no-go |
| [Reproduce a deployment issue](runbooks/reproduce-deployment-issue.md) | Something failed in a real deployment and you need to see it happen again |
| [Triage a failed gate](runbooks/triage-gate-failures.md) | A gate is red and you need to know what it means |
| [Environment lifecycle](runbooks/environment-lifecycle.md) | Creating, sealing, accessing or deleting the Azure environment |

The [handoff note template](runbooks/templates/handoff-note.md) is what gets
attached to the change record.

## Layout

```
infra/       Bicep templates, cloud-init, deploy script
repro/       sample service, proxy config, compose stack, failure scenarios
checks/      the gates
release/     release manifest for the candidate
runbooks/    procedures and the handoff template
scripts/     bootstrap, stack driver, ZAP wrapper
tests/       unit tests for the gates and the service
```

## Notes

- `notes-api` in `repro/app` is a stand-in. To validate a real service, point
  the compose file at its image, update `release/manifest.yml`, and adjust the
  paths the smoke and OWASP gates hit.
- The stack publishes on `127.0.0.1` only. On the Azure host that means it is
  reachable from the host itself and nowhere else.
- Nothing here needs or stores real credentials. The secrets gate will fail
  the build if that changes.
