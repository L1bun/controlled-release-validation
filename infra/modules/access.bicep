// Who can do what in the validation environment.
//
//   validators  - can see the environment and log in to the host as a normal
//                 user (read logs and evidence, no sudo)
//   operators   - can log in with sudo (run the stack, change the host)
//
// Login roles are scoped to the VM itself rather than the resource group so
// they cannot be used against anything else that ends up in the group.

param vmName string
param validatorsPrincipalId string
param operatorsPrincipalId string

@allowed([
  'Group'
  'User'
  'ServicePrincipal'
])
param principalType string

var roleIds = {
  reader: 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
  vmUserLogin: 'fb879df8-f326-4884-b1cf-06f3ad86be52'
  vmAdminLogin: '1c0163c0-47e6-4577-8991-ea5c82e286e4'
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' existing = {
  name: vmName
}

resource validatorsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(validatorsPrincipalId)) {
  name: guid(resourceGroup().id, validatorsPrincipalId, roleIds.reader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.reader)
    principalId: validatorsPrincipalId
    principalType: principalType
  }
}

resource validatorsLogin 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(validatorsPrincipalId)) {
  name: guid(vm.id, validatorsPrincipalId, roleIds.vmUserLogin)
  scope: vm
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.vmUserLogin)
    principalId: validatorsPrincipalId
    principalType: principalType
  }
}

resource operatorsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(operatorsPrincipalId)) {
  name: guid(resourceGroup().id, operatorsPrincipalId, roleIds.reader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.reader)
    principalId: operatorsPrincipalId
    principalType: principalType
  }
}

resource operatorsLogin 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(operatorsPrincipalId)) {
  name: guid(vm.id, operatorsPrincipalId, roleIds.vmAdminLogin)
  scope: vm
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.vmAdminLogin)
    principalId: operatorsPrincipalId
    principalType: principalType
  }
}
