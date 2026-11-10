// The validation host: one Ubuntu VM with Docker, no public IP, key-only SSH.

param name string
param location string
param tags object
param subnetId string
param vmSize string
param adminUsername string
param sshPublicKey string
param sealed bool
param shutdownTime string
param shutdownTimeZone string

var cloudInit = replace(loadTextContent('../cloud-init.yml'), '__ADMIN_USER__', adminUsername)

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-${name}'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: subnetId
          }
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'vm-${name}'
  location: location
  tags: tags
  identity: {
    // required by the Entra ID login extension
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        name: 'osdisk-${name}'
        createOption: 'FromImage'
        diskSizeGB: 64
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS'
        }
      }
    }
    osProfile: {
      computerName: 'vm-${name}'
      adminUsername: adminUsername
      customData: base64(cloudInit)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
    diagnosticsProfile: {
      bootDiagnostics: {
        enabled: true
      }
    }
  }
}

// Entra ID SSH login, so access is granted and revoked through role
// assignments instead of by handing out keys. The extension needs outbound
// access to install, so it is skipped when the network is deployed sealed.
resource entraLogin 'Microsoft.Compute/virtualMachines/extensions@2024-07-01' = if (!sealed) {
  parent: vm
  name: 'AADSSHLoginForLinux'
  location: location
  tags: tags
  properties: {
    publisher: 'Microsoft.Azure.ActiveDirectory'
    type: 'AADSSHLoginForLinux'
    typeHandlerVersion: '1.0'
    autoUpgradeMinorVersion: true
  }
}

// The host is only needed while someone is validating; stop paying for it overnight.
resource autoShutdown 'Microsoft.DevTestLab/schedules@2018-09-15' = {
  name: 'shutdown-computevm-${vm.name}'
  location: location
  tags: tags
  properties: {
    status: 'Enabled'
    taskType: 'ComputeVmShutdownTask'
    dailyRecurrence: {
      time: shutdownTime
    }
    timeZoneId: shutdownTimeZone
    targetResourceId: vm.id
    notificationSettings: {
      status: 'Disabled'
    }
  }
}

output vmName string = vm.name
output vmId string = vm.id
output privateIp string = nic.properties.ipConfigurations[0].properties.privateIPAddress
