# Runbook: triage a failed gate

Find the gate that failed in `out/gate-summary.txt`, then the section below.
Re-run a single gate with `checks/gate.sh <name>`.

Exit codes are the same everywhere: `0` passed, `1` the gate found problems,
`2` the gate itself could not run (bad input, target unreachable), `127` a
tool is missing - run `make tools`.

## yaml

yamllint prints `file:line:col` and the rule. Most failures are indentation,
trailing spaces or a duplicated key.

A **duplicated key** is the one to take seriously: YAML keeps the last value
and silently drops the first, so the file parses but does not mean what it
says. Fix the file; do not disable the rule.

## shell

shellcheck gives an `SCxxxx` code; `https://www.shellcheck.net/wiki/SCxxxx`
explains each one. If a warning is genuinely wrong for a line, disable it on
that line with a comment saying why. No file-wide disables.

## dockerfile

hadolint `DLxxxx` codes. The usual ones: unpinned base image, `pip install`
without `--no-cache-dir`, no `USER`. Fix in `repro/app/Dockerfile`.

## secrets

Reports: `out/secrets-tree.json`, `out/secrets-history.json` (values are
redacted).

**If it is a real credential, treat it as leaked from the moment it was
committed.** In this order:

1. Revoke or rotate it. Now, before anything else.
2. Remove it from the code and load it from the secret store instead.
3. If it only ever existed in an unpushed commit, rewrite that commit.
   If it was pushed, rotation is the fix - history rewriting is cleanup, and
   needs the repo owner.

If it is a false positive (a test fixture, a placeholder digest), add the
narrowest possible allowlist entry in `.gitleaks.toml` - a path or a specific
regex, never a whole rule - and say why in the commit message.

## manifest

Report: `out/manifest.json`. Run with `-v` to see passing rules as well:
`python -m checks.release_manifest release/manifest.yml -v`

| Rule | Meaning | Fix |
| --- | --- | --- |
| CFG001 | Release id / service / owner / change reference missing | Fill it in; an unowned release can't be rolled back by anyone |
| CFG010-013 | Image repository or tag missing, mutable (`latest`…) or not `X.Y.Z` | Pin the exact version |
| CFG014 | No sha256 digest | Add the digest of the image that was actually validated |
| CFG020-022 | Env block malformed, unknown `APP_ENV`, or `RELEASE_VERSION` ≠ image tag | Usually a half-finished version bump - update both |
| CFG023 | Secret-looking key with an inline value | Move to `runtime.secrets` with a store reference. Then go read the *secrets* section above |
| CFG024 | `user:password@` inside a URL | Same as CFG023 |
| CFG025-026 | `runtime.secrets` malformed / entry without `name` + `ref` | Each secret needs a name and a `scheme://` reference |
| CFG030 | CPU or memory limit missing | Set both |
| CFG031 | Liveness or readiness probe path missing | Set both; they are what the smoke gate hits |
| CFG032 | Production with fewer than 2 replicas | |
| CFG040-041 | No rollback target, or it equals the release | Record the previous good tag |
| CFG042 (warn) | Rollback not exercised | Not blocking here; blocking in the readiness decision |

## compose

Report: `out/compose-policy.json`. The gate reads the *rendered* config, so a
value coming from an override or an environment variable counts.

| Rule | Meaning |
| --- | --- |
| CMP001 | Image without a version tag or on `latest` |
| CMP002-004 | Privileged, host network, host PID namespace |
| CMP005 | Root filesystem writable - set `read_only: true`, add a `tmpfs` for what must be written |
| CMP006-007 | `cap_drop: [ALL]` missing, or capabilities added back |
| CMP008 | `no-new-privileges` not set |
| CMP009 | Runs as root |
| CMP010 | Port published on all interfaces - bind to `127.0.0.1` |
| CMP011 | Docker socket or a sensitive host path mounted |
| CMP012-013 (warn) | No memory limit / no healthcheck |

If a service truly needs an exception, it needs a reviewer, not a quiet edit
to the policy.

## deps

pip-audit lists the package, the advisory and the fixed version. Bump the pin
in `repro/app/requirements.txt`, rebuild, re-run the runtime gates. If there
is no fixed version yet, record the advisory ID and the reason it doesn't
apply (or the mitigation) in the handoff note - don't just skip the gate.

A network error here is exit code `1` from pip-audit too; read the output
before concluding there is a vulnerability.

## smoke

| Rule | Meaning | Look at |
| --- | --- | --- |
| SMK001 | Liveness failed - nothing is answering | `docker compose -p crv ps -a`; is the proxy up, is the port right? A 502 means the proxy is fine and the app isn't reachable |
| SMK002 | Not ready | The message includes the app's own reasons (missing setting, data dir not writable) |
| SMK003 | Running version ≠ manifest | You are testing the wrong build, or the tag was bumped in one place only |
| SMK004 | Wrong service answering on that port | Something else is bound to 8080 |

`error: could not reach …` (exit 2) means the stack isn't running: `make up`.

## owasp

Report: `out/owasp.json`; `-v` lists passing checks.

| Rule | Meaning | Usual fix |
| --- | --- | --- |
| A05-01 | Security header missing or weak. Checked on a 200 **and** a 404 | `repro/proxy/security-headers.conf`; headers need `always` or they vanish on error responses |
| A05-02 | HSTS missing / too short (https targets only) | Add at the TLS terminator |
| A05-03 | Version in `Server`, or `X-Powered-By` present | `server_tokens off`, `proxy_hide_header` |
| A05-04 | TRACE/PUT/DELETE/PATCH accepted | `limit_except` in the proxy |
| A05-05 | 5xx on bad input, or stack trace / file path in a response | Application bug - validate input, return a generic error |
| A05-06 | Oversized body accepted | `client_max_body_size`, app-level limit |
| A01-01 | Sensitive path reachable (`/.env`, `/.git/config`, `/metrics`…) | Find out why it is being served before blocking it |
| A01-02 | CORS reflects any origin, or `*` with credentials | Explicit origin allowlist |
| A07-01 | Cookie without `HttpOnly` / `SameSite` / `Secure` | Set at the application |

Many A05-05 and A01-01 failures at once, all "returned 502", is not thirteen
problems - it is one: the app is down behind the proxy. Fix `smoke` first.

## git (`make release-check`)

| Message | Fix |
| --- | --- |
| working tree has uncommitted or untracked changes | Commit or remove them. What was validated must be what is tagged |
| HEAD is not part of main | You are on a branch that isn't merged |
| tag vX.Y.Z does not exist | `git tag -a vX.Y.Z -m "…"` |
| tag is lightweight | Delete and recreate with `-a`; annotated tags record who and when |
| tag does not point at HEAD | Commits were added after tagging. Re-validate, then move the tag |

## Still stuck

Run `make collect`, and hand over the `out/` directory with the gate name and
what you already tried.
