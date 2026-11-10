# Runbook: environment lifecycle

Creating, accessing, sealing and removing the Azure validation environment.
Reference for parameters and the access model: [`infra/README.md`](../infra/README.md).

## Create

Requires Owner or User Access Administrator on the target resource group.

```bash
az login
az account show --query name -o tsv      # check you are in the right subscription

export CRV_RG=rg-crv-validation CRV_LOCATION=eastus2
export CRV_SSH_PUBLIC_KEY_FILE=~/.ssh/id_ed25519.pub
export CRV_VALIDATORS_ID=<object id> CRV_OPERATORS_ID=<object id>

infra/deploy.sh what-if
infra/deploy.sh up
```

Read the what-if output. On a first deployment everything is `+ Create`. On
any later one, an unexpected `- Delete` or a change to the subnet means stop
and ask.

First boot takes a few minutes while cloud-init installs Docker. Check:

```bash
infra/deploy.sh ssh
cloud-init status --wait
docker compose version
```

## Access

| I need to… | Role | Command |
| --- | --- | --- |
| Read logs and evidence | Validator | `infra/deploy.sh ssh` |
| Run the stack / gates | Operator | `infra/deploy.sh ssh`, then `sudo -i` or `sudo docker …` |
| Get in when Entra login is unavailable | Holder of the admin key | `infra/deploy.sh ssh-key` |

Access is granted by adding someone to the validators or operators group, and
removed the same way. Do not add SSH keys to the host by hand.

`Permission denied` right after being added to a group usually means the
token is stale: `az logout && az login`.

## Start a stopped host

The host shuts down at 19:00 UTC every day.

```bash
infra/deploy.sh status
az vm start -g "$CRV_RG" -n vm-crv
```

## Seal the network

Use when running an untrusted build, or to prove a release has no undeclared
outbound dependency.

```bash
CRV_SEALED=true infra/deploy.sh what-if   # expect: NSG rule removed, subnet loses its NAT gateway
CRV_SEALED=true infra/deploy.sh up
```

Verify from the host (connect with `infra/deploy.sh ssh-key` - Entra login
does not work without egress):

```bash
curl -sS -m 5 -o /dev/null https://example.com && echo "STILL OPEN" || echo "sealed"
```

Images must already be on the host before sealing; pull or build first.

Unseal with `CRV_SEALED=false infra/deploy.sh up`.

## Remove

```bash
infra/deploy.sh down
```

It asks for the resource group name. Deletion takes a few minutes and removes
everything, including evidence on the host - copy `/srv/crv-evidence` off
first if the change record needs it.

Confirm it is gone:

```bash
az group exists -n "$CRV_RG"
```

## Checklist before leaving an environment up overnight

- [ ] Someone's name is on it (tag the resource group or note it in the channel)
- [ ] The stack is down (`make down`) - nothing should be left half-reproduced
- [ ] The network is unsealed, unless the next person expects it sealed
