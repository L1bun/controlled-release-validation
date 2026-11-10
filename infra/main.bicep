// Controlled release validation environment.
//
// Deploys into an existing resource group:
//   - a VNet with an isolated validation subnet (and optionally Azure Bastion)
//   - one Linux host with Docker, reachable only through Bastion
//   - role assignments for the people who validate and operate releases
//
// See infra/README.md for how to deploy it.

targetScope = 'resourceGroup'

@description('Short name used in every resource name.')
@minLength(2)
@maxLength(10)
param name string = 'crv'

@description('Azure region. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Address space for the VNet.')
param addressSpace string = '10.42.0.0/24'

@description('Subnet for the validation host.')
param validationSubnetPrefix string = '10.42.0.0/26'

@description('Subnet for Azure Bastion. Must be /26 or larger.')
param bastionSubnetPrefix string = '10.42.0.64/26'

@description('Deploy Azure Bastion for SSH access. Without it the host is only reachable with az vm run-command.')
param deployBastion bool = true

@description('Cut the validation subnet off from the internet entirely (no NAT gateway, no outbound allow rules).')
param sealed bool = false

@description('VM size for the validation host.')
param vmSize string = 'Standard_B2s'

@description('Local admin account on the host. Break-glass only; day-to-day access goes through Entra ID.')
param adminUsername string = 'crvadmin'

@description('SSH public key for the local admin account.')
param sshPublicKey string

@description('Object ID of the Entra ID principal that validates releases. Leave empty to skip the assignment.')
param validatorsPrincipalId string = ''

@description('Object ID of the Entra ID principal that operates the environment. Leave empty to skip the assignment.')
param operatorsPrincipalId string = ''

@description('Type of the two principals above.')
@allowed([
  'Group'
  'User'
  'ServicePrincipal'
])
param principalType string = 'Group'

@description('Daily auto-shutdown time for the host, 24h HHmm.')
@minLength(4)
@maxLength(4)
param shutdownTime string = '1900'

@description('Time zone for the auto-shutdown schedule.')
param shutdownTimeZone string = 'UTC'

param tags object = {
  workload: 'controlled-release-validation'
  environment: 'validation'
  managedBy: 'bicep'
}

module network 'modules/network.bicep' = {
  name: 'network'
  params: {
    name: name
    location: location
    tags: tags
    addressSpace: addressSpace
    validationSubnetPrefix: validationSubnetPrefix
    bastionSubnetPrefix: bastionSubnetPrefix
    deployBastion: deployBastion
    sealed: sealed
  }
}

module host 'modules/host.bicep' = {
  name: 'host'
  params: {
    name: name
    location: location
    tags: tags
    subnetId: network.outputs.validationSubnetId
    vmSize: vmSize
    adminUsername: adminUsername
    sshPublicKey: sshPublicKey
    sealed: sealed
    shutdownTime: shutdownTime
    shutdownTimeZone: shutdownTimeZone
  }
}

module access 'modules/access.bicep' = {
  name: 'access'
  params: {
    vmName: host.outputs.vmName
    validatorsPrincipalId: validatorsPrincipalId
    operatorsPrincipalId: operatorsPrincipalId
    principalType: principalType
  }
}

output vmName string = host.outputs.vmName
output vmId string = host.outputs.vmId
output vmPrivateIp string = host.outputs.privateIp
output bastionName string = network.outputs.bastionName
