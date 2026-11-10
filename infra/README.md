# Azure validation environment

Bicep for an environment where a release candidate can be run, broken and
inspected without touching anything shared.

## What gets deployed

| Resource | Name | Notes |
| --- | --- | --- |
| Virtual network | `vnet-crv` | `10.42.0.0/24` |
| Validation subnet | `snet-validation` | `defaultOutboundAccess: false`, NSG attached, no public IPs |
| Network security group | `nsg-crv-validation` | Inbound: SSH from the Bastion subnet only. Outbound to the internet: 80/443 only |
| NAT gateway + public IP | `nat-crv`, `pip-crv-nat` | The only way out. Not deployed when `sealed=true` |
| Bastion + public IP | `bas-crv`, `pip-crv-bastion` | Standard SKU with tunneling. Optional (`deployBastion`) |
| Linux VM | `vm-crv` | Ubuntu 24.04, Docker from cloud-init, key-only SSH, system-assigned identity |
| Entra ID login extension | `AADSSHLoginForLinux` | Makes the login roles below work |
| Auto-shutdown schedule | `shutdown-computevm-vm-crv` | 19:00 UTC by default |
| Role assignments | | See below |

## Access model

| Principal | Role | Scope | Result |
| --- | --- | --- | --- |
| Validators | Reader | Resource group | Can see the environment in the portal / CLI |
| Validators | Virtual Machine User Login | The VM | SSH as a normal user: read logs and `/srv/crv-evidence`, no sudo, no Docker |
| Operators | Reader | Resource group | |
| Operators | Virtual Machine Administrator Login | The VM | SSH with sudo: run the stack, change the host |

Login roles are scoped to the VM, not the resource group. The local
`crvadmin` account exists because Azure requires one; treat its key as
break-glass.

Pass `CRV_PRINCIPAL_TYPE=User` and your own object ID
(`az ad signed-in-user show --query id -o tsv`) if you are trying this out
alone and don't have groups.

## Deploy

You need the Azure CLI, a subscription, and **Owner or User Access
Administrator** on the resource group - Contributor is not enough because the
template creates role assignments.

```bash
az login
export CRV_RG=rg-crv-validation
export CRV_LOCATION=eastus2
export CRV_SSH_PUBLIC_KEY_FILE=~/.ssh/id_ed25519.pub
export CRV_VALIDATORS_ID=<object id>
export CRV_OPERATORS_ID=<object id>

infra/deploy.sh what-if     # always look first
infra/deploy.sh up
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `CRV_RG` | `rg-crv-validation` | Resource group (created if missing) |
| `CRV_LOCATION` | `eastus2` | Region |
| `CRV_NAME` | `crv` | Short name used in resource names |
| `CRV_SSH_PUBLIC_KEY_FILE` | `~/.ssh/id_ed25519.pub` | Public key for the local admin account |
| `CRV_VALIDATORS_ID` / `CRV_OPERATORS_ID` | empty | Entra object IDs; empty skips the assignment |
| `CRV_PRINCIPAL_TYPE` | `Group` | `Group`, `User` or `ServicePrincipal` |
| `CRV_BASTION` | `true` | Deploy Bastion |
| `CRV_SEALED` | `false` | Remove all internet egress |

## Connect

```bash
infra/deploy.sh ssh        # Entra ID login through Bastion
infra/deploy.sh ssh-key    # local admin account, uses the private key next to the public one
```

Both need the `ssh` and `bastion` CLI extensions; `az` offers to install them
on first use.

Then, on the host:

```bash
cd /srv/crv
git clone <this repo> .
make tools && make gate
```

## Sealed mode

`CRV_SEALED=true infra/deploy.sh up` detaches the NAT gateway and removes the
outbound allow rule. The host keeps running but has no route to the internet,
which is what you want when reproducing an issue with an untrusted build or
checking that a release doesn't quietly depend on something external.

Two things to know:

- Seal **after** the first deployment. A host that is sealed from its very
  first boot cannot install Docker.
- Entra ID login needs to reach Microsoft's sign-in endpoints, so in sealed
  mode use `infra/deploy.sh ssh-key`.

Re-running with `CRV_SEALED=false` restores egress. Sealing does not delete
the NAT gateway (incremental deployments never delete), so it keeps billing
until you remove it or the resource group.

## Cost

The parts that cost money while they exist are Bastion Standard and the NAT
gateway; the VM is small and shuts itself down every evening. This is meant to
be created for a validation window and deleted afterwards:

```bash
infra/deploy.sh down
```

If the environment has to live longer, deploy with `CRV_BASTION=false` and use
`az vm run-command invoke` for the occasional command.
