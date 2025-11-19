// Virtual Network with subnets for secure connectivity
@description('Azure region for networking resources')
param location string

@description('Base name applied to networking resources')
param baseName string

@description('Environment suffix for resource names')
param environmentName string

@description('Tags propagated to networking resources')
param tags object

@description('Address space for the virtual network')
param addressPrefix string = '10.80.0.0/16'

@description('Subnet CIDR for the Container Apps managed environment infrastructure subnet')
param containerAppsSubnetPrefix string = '10.80.0.0/23'

@description('Subnet CIDR for private endpoints (Cosmos DB, etc.)')
param privateEndpointSubnetPrefix string = '10.80.2.0/24'

var vnetName = '${baseName}-${environmentName}-vnet'
var containerAppsSubnetName = 'containerapps-infra'
var privateEndpointSubnetName = 'private-endpoints'
var dnsZoneName = 'privatelink.documents.azure.com'
var dnsLinkName = '${vnetName}-cosmos-link'

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        addressPrefix
      ]
    }
    subnets: [
      {
        name: containerAppsSubnetName
        properties: {
          addressPrefix: containerAppsSubnetPrefix
          privateEndpointNetworkPolicies: 'Enabled'
          privateLinkServiceNetworkPolicies: 'Enabled'
        }
      }
      {
        name: privateEndpointSubnetName
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
          privateLinkServiceNetworkPolicies: 'Enabled'
        }
      }
    ]
  }
}

resource privateDnsZone 'Microsoft.Network/privateDnsZones@2018-09-01' = {
  name: dnsZoneName
  location: 'global'
  tags: tags
}

resource privateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2018-09-01' = {
  parent: privateDnsZone
  name: dnsLinkName
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

output vnetId string = vnet.id
output containerAppsSubnetId string = vnet.properties.subnets[0].id
output privateEndpointSubnetId string = vnet.properties.subnets[1].id
output privateDnsZoneId string = privateDnsZone.id
