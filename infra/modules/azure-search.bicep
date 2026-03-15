param location string
param baseName string
param environmentName string
param tags object

@description('SKU for the Azure AI Search service.')
param skuName string = 'basic'

@description('Replica count for the Azure AI Search service.')
param replicaCount int = 1

@description('Partition count for the Azure AI Search service.')
param partitionCount int = 1

var serviceName = take(toLower(replace('${baseName}-${environmentName}-search', '_', '')), 60)
var indexPrefix = take(toLower(replace('${baseName}-${take(environmentName, 8)}', '_', '-')), 96)

resource searchService 'Microsoft.Search/searchServices@2025-05-01' = {
  name: serviceName
  location: location
  sku: {
    name: skuName
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    replicaCount: replicaCount
    partitionCount: partitionCount
    hostingMode: 'Default'
    publicNetworkAccess: 'enabled'
    disableLocalAuth: false
    semanticSearch: 'standard'
    encryptionWithCmk: {
      enforcement: 'Disabled'
    }
  }
  tags: tags
}

output serviceName string = searchService.name
output endpoint string = 'https://${searchService.name}.search.windows.net'
@secure()
output primaryKey string = searchService.listAdminKeys().primaryKey
output indexPrefix string = indexPrefix
