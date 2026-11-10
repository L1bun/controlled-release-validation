#!/usr/bin/env bash
# Deploy, inspect and remove the Azure validation environment.
#
#   infra/deploy.sh what-if     show what a deployment would change
#   infra/deploy.sh up          create or update the environment
#   infra/deploy.sh ssh         open a shell on the host through Bastion (Entra ID login)
#   infra/deploy.sh ssh-key     same, with the local admin account and your SSH key
#   infra/deploy.sh status      power state and private IP of the host
#   infra/deploy.sh down        delete the resource group and everything in it
#
# Settings come from the environment (see infra/README.md):
#   CRV_RG, CRV_LOCATION, CRV_NAME, CRV_SSH_PUBLIC_KEY_FILE,
#   CRV_VALIDATORS_ID, CRV_OPERATORS_ID, CRV_PRINCIPAL_TYPE, CRV_SEALED, CRV_BASTION
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RG="${CRV_RG:-rg-crv-validation}"
LOCATION="${CRV_LOCATION:-eastus2}"
NAME="${CRV_NAME:-crv}"
KEY_FILE="${CRV_SSH_PUBLIC_KEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
ADMIN_USER="${CRV_ADMIN_USER:-crvadmin}"

usage() {
  sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 2
}

params() {
  if [[ ! -r "$KEY_FILE" ]]; then
    echo "SSH public key not found: $KEY_FILE (set CRV_SSH_PUBLIC_KEY_FILE)" >&2
    exit 2
  fi
  PARAMS=(
    name="$NAME"
    adminUsername="$ADMIN_USER"
    sshPublicKey="$(cat "$KEY_FILE")"
    validatorsPrincipalId="${CRV_VALIDATORS_ID:-}"
    operatorsPrincipalId="${CRV_OPERATORS_ID:-}"
    principalType="${CRV_PRINCIPAL_TYPE:-Group}"
    sealed="${CRV_SEALED:-false}"
    deployBastion="${CRV_BASTION:-true}"
  )
}

vm_id() {
  az vm show --resource-group "$RG" --name "vm-$NAME" --query id --output tsv
}

case "${1:-}" in
  what-if)
    params
    az group create --name "$RG" --location "$LOCATION" --output none
    az deployment group what-if --resource-group "$RG" \
      --template-file "$HERE/main.bicep" --parameters "${PARAMS[@]}"
    ;;
  up)
    params
    az group create --name "$RG" --location "$LOCATION" --output none
    az deployment group create --resource-group "$RG" --name "crv-$(date -u +%Y%m%d%H%M%S)" \
      --template-file "$HERE/main.bicep" --parameters "${PARAMS[@]}" \
      --query properties.outputs --output json
    ;;
  ssh)
    az network bastion ssh --resource-group "$RG" --name "bas-$NAME" \
      --target-resource-id "$(vm_id)" --auth-type AAD
    ;;
  ssh-key)
    az network bastion ssh --resource-group "$RG" --name "bas-$NAME" \
      --target-resource-id "$(vm_id)" --auth-type ssh-key \
      --username "$ADMIN_USER" --ssh-key "${KEY_FILE%.pub}"
    ;;
  status)
    az vm show --resource-group "$RG" --name "vm-$NAME" --show-details \
      --query '{name:name, power:powerState, privateIp:privateIps}' --output table
    ;;
  down)
    echo "This deletes resource group '$RG' and everything in it."
    read -r -p "Type the resource group name to confirm: " answer
    if [[ "$answer" != "$RG" ]]; then
      echo "aborted"
      exit 1
    fi
    az group delete --name "$RG" --yes --no-wait
    echo "deletion started"
    ;;
  *)
    usage
    ;;
esac
