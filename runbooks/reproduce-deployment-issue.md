# Runbook: reproduce a deployment issue

**Purpose:** make a deployment failure happen again, on purpose, somewhere
isolated - then capture enough to hand the fix to whoever owns it.
**Who:** on-call or release engineer with operator access.

The rule for this runbook: **change one thing at a time and write down what
you changed.** A reproduction nobody can repeat is just a second incident.

## 1. Write down the failure first

Before touching anything, record:

- what was deployed (image tag and digest)
- where, and when (UTC)
- the symptom as observed: status codes, the exact error line, which probe
  failed
- what changed since the last good deployment (config, mounts, proxy, image)

If you can't fill in the last line, get the diff between the two release
manifests - that is usually the answer.

## 2. Get into the environment

```bash
infra/deploy.sh status      # is the host running? auto-shutdown may have stopped it
az vm start -g "$CRV_RG" -n vm-crv   # if not
infra/deploy.sh ssh
cd /srv/crv && git pull --ff-only
```

If the build is untrusted, or the suspicion is an unexpected outbound
dependency, seal the network before running it - see
[environment-lifecycle.md](environment-lifecycle.md#seal-the-network).

## 3. Confirm the baseline is healthy

```bash
make down; make up && make runtime
```

If the baseline is red, you are debugging the environment, not the incident.
Fix that first.

## 4. Apply the failing condition

Known failure mode - use the scenario:

```bash
scripts/repro.sh scenarios
make scenario NAME=<name>
```

Something new - describe it as an override:

```bash
cp repro/scenarios/missing-release-version.yml repro/scenarios/incident-<ref>.yml
# edit: put in the environment / mounts / image tag from step 1
make scenario NAME=incident-<ref>
```

The script prints container state and what `/healthz`, `/readyz` and
`/api/version` return through the proxy.

## 5. Did it reproduce?

Compare with the symptom from step 1.

| You see | Meaning | Next |
| --- | --- | --- |
| Same symptom | Reproduced | Step 6 |
| Stack is healthy | The condition you applied isn't the cause | Go back to the diff in step 1, apply the next difference |
| A different failure | You changed more than one thing, or found a second problem | Reduce the override until only one change remains |

Useful while it is running:

```bash
docker compose -p crv ps -a
docker compose -p crv logs --tail 50 app
docker compose -p crv logs --tail 50 proxy
docker compose -p crv exec app env | sort
docker compose -p crv exec app sh -c 'touch /data/.probe && echo writable'
```

## 6. Capture and hand over

`make scenario` already saved a bundle under `out/repro/<name>-<timestamp>/`:

| File | Contents |
| --- | --- |
| `ps.txt` | container state and health |
| `logs.txt` | timestamped logs from every container |
| `compose-rendered.yml` | the exact configuration that ran |
| `inspect.json` | full container details (mounts, env, health log) |
| `probe.txt` | probe results through the proxy |
| `context.txt` | time, commit, Docker and kernel versions |

Re-run `make collect` if you changed anything by hand afterwards.

Copy the bundle to `/srv/crv-evidence/<ref>/`, commit the scenario file if it
is worth keeping, and attach to the incident:

- the override file (it *is* the reproduction steps)
- the bundle path
- one sentence: what condition causes what symptom

## 7. Verify the fix the same way

When a fix is ready, run the same scenario against the fixed build. The
reproduction is done when the scenario that used to fail now passes
`make runtime` - or fails loudly at a gate before deployment, which is often
the better fix.

## 8. Clean up

```bash
make down
```

If you sealed the network, unseal it. If nobody else needs the environment
this week, delete it.
