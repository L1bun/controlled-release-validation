// Isolated network for the validation host.
//
// Nothing in the validation subnet has a public IP and inbound traffic is
// limited to SSH from the Bastion subnet. Outbound goes through a NAT gateway
// and is limited to 80/443 so the host can pull packages and images. Setting
// `sealed` detaches the NAT gateway and drops the outbound allow rules, which
// leaves the host with no route to the internet at all.

param name string
param location string
param tags object
param addressSpace string
param validationSubnetPrefix string
param bastionSubnetPrefix string
param deployBastion bool
param sealed bool

var inboundRules = [
  {
    name: 'AllowSshFromBastion'
    properties: {
      priority: 100
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: bastionSubnetPrefix
      sourcePortRange: '*'
      destinationAddressPrefix: validationSubnetPrefix
      destinationPortRange: '22'
    }
  }
  {
    name: 'DenyAllInbound'
    properties: {
      priority: 4000
      direction: 'Inbound'
      access: 'Deny'
      protocol: '*'
      sourceAddressPrefix: '*'
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '*'
    }
  }
]

var egressRules = [
  {
    name: 'AllowWebOutbound'
    properties: {
      priority: 100
      direction: 'Outbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: validationSubnetPrefix
      sourcePortRange: '*'
      destinationAddressPrefix: 'Internet'
      destinationPortRanges: [
        '80'
        '443'
      ]
    }
  }
]

var denyInternetRule = [
  {
    name: 'DenyInternetOutbound'
    properties: {
      priority: 4000
      direction: 'Outbound'
      access: 'Deny'
      protocol: '*'
      sourceAddressPrefix: '*'
      sourcePortRange: '*'
      destinationAddressPrefix: 'Internet'
      destinationPortRange: '*'
    }
  }
]

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-${name}-validation'
  location: location
  tags: tags
  properties: {
    securityRules: concat(inboundRules, sealed ? [] : egressRules, denyInternetRule)
  }
}

resource natPublicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = if (!sealed) {
  name: 'pip-${name}-nat'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2024-05-01' = if (!sealed) {
  name: 'nat-${name}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 4
    publicIpAddresses: [
      {
        id: natPublicIp.id
      }
    ]
  }
}

var validationSubnet = {
  name: 'snet-validation'
  properties: {
    addressPrefix: validationSubnetPrefix
    defaultOutboundAccess: false
    networkSecurityGroup: {
      id: nsg.id
    }
    natGateway: sealed
      ? null
      : {
          id: natGateway.id
        }
  }
}

var bastionSubnet = {
  // the name is fixed by the Bastion service
  name: 'AzureBastionSubnet'
  properties: {
    addressPrefix: bastionSubnetPrefix
  }
}

// Subnets are declared inline so a redeploy never tries to drop one that is in use.
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${name}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        addressSpace
      ]
    }
    subnets: deployBastion
      ? [
          validationSubnet
          bastionSubnet
        ]
      : [
          validationSubnet
        ]
  }
}

resource bastionPublicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = if (deployBastion) {
  name: 'pip-${name}-bastion'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

// Standard SKU with tunneling so `az network bastion ssh` works from a laptop.
resource bastion 'Microsoft.Network/bastionHosts@2024-05-01' = if (deployBastion) {
  name: 'bas-${name}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    enableTunneling: true
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          subnet: {
            id: '${vnet.id}/subnets/AzureBastionSubnet'
          }
          publicIPAddress: {
            id: bastionPublicIp.id
          }
        }
      }
    ]
  }
}

output validationSubnetId string = '${vnet.id}/subnets/snet-validation'
output vnetName string = vnet.name
output bastionName string = deployBastion ? bastion.name : ''
