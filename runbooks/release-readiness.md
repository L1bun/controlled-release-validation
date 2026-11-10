# Runbook: release readiness

**Purpose:** decide go / no-go for a release candidate and leave behind
evidence someone else can check.
**Who:** the engineer cutting the release. Needs operator access if running
on the Azure host.
**Time:** about 15 minutes when everything is green.

## Before you start

- [ ] The change is merged to `main` and you are on that commit.
- [ ] `release/manifest.yml` describes this release: `image.tag`,
      `image.digest`, `runtime.env.RELEASE_VERSION`, `rollback.previous_tag`.
- [ ] You know the change reference (`release.change_ref`).

## Steps

### 1. Start clean

```bash
git checkout main && git pull --ff-only
git status --short        # must print nothing
make tools
```

### 2. Static gates

```bash
make validate
```

All seven lines must say `PASS`. If one doesn't, stop and go to
[triage-gate-failures.md](triage-gate-failures.md). Do not re-run until it
passes without changing anything - a gate that flips on retry is a finding in
itself; write it down.

### 3. Runtime gates

```bash
make up
make runtime
```

`smoke` confirms the running version is the one in the manifest. If it
reports a different version you are validating the wrong build: `make down`,
fix the tag, start again from step 2.

### 4. ZAP baseline

```bash
make zap
```

Open `out/zap/zap-baseline.html`. Warnings are expected to be reviewed, not
ignored: each one is either fixed, or listed in the handoff note with a
reason.

### 5. Tag and check git state

```bash
git tag -a "v$(.venv/bin/python -c 'import yaml;print(yaml.safe_load(open("release/manifest.yml"))["image"]["tag"])')" \
  -m "release $(date -u +%Y-%m-%d)"
make release-check
```

### 6. Collect evidence and shut down

```bash
make collect
make down
```

Keep the `out/` directory. On the Azure host, copy it to
`/srv/crv-evidence/<release id>/` so validators can read it.

### 7. Hand off

Fill in [`templates/handoff-note.md`](templates/handoff-note.md) and attach it
to the change record together with `out/gate-summary.txt`.

## Go / no-go

**Go** only if all of these are true:

- every gate in `out/gate-summary.txt` is `PASS`, from a single run
- `make release-check` passed on the tagged commit
- ZAP warnings are each fixed or explained
- `rollback.verified` is `true` in the manifest (the gate only warns on this;
  the decision is yours, and "we didn't try it" is a no-go for production)

Anything else is a **no-go**. Record which gate failed and link the evidence.

## If you have to stop halfway

Run `make down` and note the last completed step in the change record. The
gates are stateless; whoever picks it up starts again from step 1.
