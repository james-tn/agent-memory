// Azure Container Registry for storing container images
param location string
param baseName string
param environmentName string
param tags object

var acrName = replace('${baseName}${environmentName}acr', '-', '')

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
  }
  tags: tags
}

output registryName string = containerRegistry.name
output loginServer string = containerRegistry.properties.loginServer
output registryId string = containerRegistry.id
