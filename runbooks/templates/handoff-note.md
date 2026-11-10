# Release handoff note

Copy this into the change record. Delete the hints in parentheses.

| | |
| --- | --- |
| Release id | (release.id from the manifest) |
| Service / version | (release.service) / (image.tag) |
| Image digest | (image.digest) |
| Commit / tag | (git rev-parse --short HEAD) / (vX.Y.Z) |
| Change reference | (release.change_ref) |
| Validated by | |
| Validated at (UTC) | |
| Environment | (local / vm-crv, sealed or not) |

## Gate results

(paste out/gate-summary.txt)

```
```

`make release-check`: pass / fail

## ZAP baseline

- Warnings: (count)
- Each one fixed or accepted, with reason:
  -

## Exceptions and known issues

(advisories without a fix, warnings accepted, anything a reviewer should know. "None" is a valid answer.)

## Rollback

- Target: (rollback.previous_tag)
- Exercised for this release: yes / no
- How: (command or pipeline that performs it)

## Decision

**GO / NO-GO** - (one sentence why)

Evidence: (path under /srv/crv-evidence or link to the uploaded artifact)
