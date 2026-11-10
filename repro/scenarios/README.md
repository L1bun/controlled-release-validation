# Failure scenarios

Each `.yml` file here is a compose override layered on top of
`repro/docker-compose.yml`. A scenario should break **one** thing, and its
first comment line says what - `scripts/repro.sh scenarios` prints those
lines.

```bash
scripts/repro.sh scenario wrong-upstream-port
```

## Adding one

1. Copy the closest existing scenario.
2. Change only what reproduces the failure. Overrides may touch `environment`
   and `volumes`; they must not loosen the sandbox (no `privileged`, no extra
   ports, no writable root). `tests/test_compose_policy.py` enforces this.
3. Put the expected symptom in the header comment, so the next person knows
   whether what they are seeing is the reproduction or a new problem.
4. Proxy config variants go in `conf/` and are mounted over
   `/etc/nginx/crv/upstream.conf` or `/etc/nginx/crv/security-headers.conf`.

Paths inside override files are relative to `repro/`, not to this directory -
compose resolves them against the first `-f` file.

## Reproducing a real incident

Scenarios are the quick path for known failure modes. For a real incident,
start from the actual inputs instead: the image tag that failed, the
environment it was given, and the mounts it had. Put those in a new override
and run it the same way. The runbook is
[`runbooks/reproduce-deployment-issue.md`](../../runbooks/reproduce-deployment-issue.md).
