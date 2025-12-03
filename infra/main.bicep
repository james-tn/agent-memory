// Main infrastructure deployment for Agent Memory Service
// Deploys: Azure OpenAI, Cosmos DB with Vector Search, Container App for Interactive Demo

targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Demo container image')
param demoImageName string = ''

@description('Tag used for the demo container image when azd has not built one yet')
param demoImageTag string = 'latest'

@description('Enable fully private networking between Container Apps and Cosmos DB (VNet + private endpoint).')
param secureCosmosConnectivity bool = true

@description('CIDR for the secure VNet when secureCosmosConnectivity is enabled.')
param vnetAddressPrefix string = '10.80.0.0/16'

@description('CIDR for the Container Apps infrastructure subnet when secureCosmosConnectivity is enabled (must be /23 or larger).')
param containerAppsSubnetPrefix string = '10.80.0.0/23'

@description('CIDR for the private endpoint subnet when secureCosmosConnectivity is enabled.')
param privateEndpointSubnetPrefix string = '10.80.2.0/24'

@description('Optional Entra ID object ID for a developer that should get Cosmos DB data-plane roles in secure mode.')
param localDeveloperObjectId string = ''

@description('Enable Entra ID authentication for demo app')
param enableAuth bool = true

@description('Entra ID Client ID for authentication')
param authClientId string = ''

@description('Entra ID Tenant ID for authentication (if different from deployment tenant)')
param authTenantId string = ''

@description('Client secret for the Entra ID application used when authentication is enabled')
@secure()
param authClientSecret string = ''

var secureCosmos = secureCosmosConnectivity

// Tags to apply to all resources
var tags = {
  'azd-env-name': environmentName
  Application: 'Agent-Memory-Service'
  ManagedBy: 'azd'
}

// Service-specific tags for the demo Container App so azd can locate it on deploy
var demoServiceTags = union(tags, {
  'azd-service-name': 'demo'
})

// Generate a unique token to be used in naming resources
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var baseName = 'agentmem-${resourceToken}'
var demoAppName = '${baseName}-${take(environmentName, 8)}'

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// Azure OpenAI Service
module openai './modules/openai.bicep' = {
  scope: rg
  name: 'openai-deployment'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    tags: tags
  }
}

// Container Registry
module acr './modules/container-registry.bicep' = {
  scope: rg
  name: 'acr-deployment'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    tags: tags
  }
}

// Log Analytics Workspace (for Container Apps)
module logAnalytics './modules/log-analytics.bicep' = {
  scope: rg
  name: 'logs-deployment'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    tags: tags
  }
}

// Network resources for secure deployments
module network './modules/network.bicep' = if (secureCosmos) {
  scope: rg
  name: 'network-deployment'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    tags: tags
    addressPrefix: vnetAddressPrefix
    containerAppsSubnetPrefix: containerAppsSubnetPrefix
    privateEndpointSubnetPrefix: privateEndpointSubnetPrefix
  }
}

// Cosmos DB with memory service containers
module cosmosdb './modules/cosmosdb.bicep' = {
  scope: rg
  name: 'cosmosdb-deployment'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    tags: tags
    enablePrivateEndpoint: secureCosmos
    privateEndpointSubnetId: secureCosmos ? network!.outputs.privateEndpointSubnetId : ''
    privateDnsZoneId: secureCosmos ? network!.outputs.privateDnsZoneId : ''
  }
}

// Shared Cosmos DB data-plane role definition used by managed identity and developers
module cosmosDataRole './modules/cosmos-data-role-definition.bicep' = {
  scope: rg
  name: 'cosmos-data-role-definition'
  params: {
    cosmosDbAccountName: cosmosdb.outputs.accountName
  }
}

// Container Apps Environment
module containerAppsEnv './modules/container-apps-environment.bicep' = {
  scope: rg
  name: 'container-apps-env-deployment'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    tags: tags
    infrastructureSubnetId: secureCosmos ? network!.outputs.containerAppsSubnetId : ''
  }
}

// Managed identity for secure Container Apps deployment
module appIdentity './modules/managed-identity.bicep' = if (secureCosmos) {
  scope: rg
  name: 'app-identity'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    tags: tags
  }
}

// Cosmos DB data-plane roles for managed identity
module appCosmosRoles './modules/cosmos-roles.bicep' = if (secureCosmos) {
  scope: rg
  name: 'app-cosmos-roles'
  params: {
    cosmosDbAccountName: cosmosdb.outputs.accountName
    principalId: appIdentity!.outputs.principalId
    dataOwnerRoleDefinitionId: cosmosDataRole.outputs.roleDefinitionId
    roleAssignmentSalt: 'demo'
  }
}

// Optional Cosmos DB role assignment for a developer (needed for local setup scripts that rely on RBAC)
module devCosmosRoles './modules/cosmos-roles.bicep' = if (!empty(localDeveloperObjectId)) {
  scope: rg
  name: 'developer-cosmos-roles'
  params: {
    cosmosDbAccountName: cosmosdb.outputs.accountName
    principalId: localDeveloperObjectId
    dataOwnerRoleDefinitionId: cosmosDataRole.outputs.roleDefinitionId
    roleAssignmentSalt: 'localdev'
  }
}

// Interactive Demo Container App
module demoApp './modules/demo-app.bicep' = {
  scope: rg
  name: 'demo-app-deployment'
  params: {
    location: location
    baseName: baseName
    environmentName: environmentName
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryName: acr.outputs.registryName
    cosmosDbEndpoint: cosmosdb.outputs.endpoint
    cosmosDbKey: secureCosmos ? '' : cosmosdb.outputs.primaryKey
    cosmosDbName: cosmosdb.outputs.databaseName
    useCosmosManagedIdentity: secureCosmos
    userAssignedIdentityResourceId: secureCosmos ? appIdentity!.outputs.identityId : ''
    userAssignedIdentityClientId: secureCosmos ? appIdentity!.outputs.clientId : ''
    azureOpenAIEndpoint: openai.outputs.endpoint
    azureOpenAIKey: openai.outputs.key
    azureOpenAIChatDeploymentName: openai.outputs.chatDeploymentName
    azureOpenAIEmbDeployment: openai.outputs.embeddingDeploymentName
    azureOpenAIProcessingModel: openai.outputs.processingDeploymentName
    imageName: !empty(demoImageName) ? demoImageName : ''
    imageTag: demoImageTag
    enableAuth: enableAuth
    authClientId: authClientId
    authTenantId: authTenantId
    authClientSecret: authClientSecret
    tags: demoServiceTags
  }
}

// Outputs for azd
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name

output AZURE_OPENAI_ENDPOINT string = openai.outputs.endpoint
output AZURE_OPENAI_CHAT_DEPLOYMENT string = openai.outputs.chatDeploymentName
output AZURE_OPENAI_EMB_DEPLOYMENT string = openai.outputs.embeddingDeploymentName
output AZURE_OPENAI_PROCESSING_MODEL string = openai.outputs.processingDeploymentName

output AZURE_COSMOS_ENDPOINT string = cosmosdb.outputs.endpoint
output AZURE_COSMOS_ACCOUNT_NAME string = cosmosdb.outputs.accountName
output AZURE_COSMOS_DATABASE_NAME string = cosmosdb.outputs.databaseName
output AZURE_COSMOS_INTERACTIONS_CONTAINER string = cosmosdb.outputs.interactionsContainer
output AZURE_COSMOS_SUMMARIES_CONTAINER string = cosmosdb.outputs.summariesContainer
output AZURE_COSMOS_INSIGHTS_CONTAINER string = cosmosdb.outputs.insightsContainer

output AZURE_CONTAINER_REGISTRY_NAME string = acr.outputs.registryName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.outputs.loginServer

output AZURE_CONTAINER_APPS_ENVIRONMENT_ID string = containerAppsEnv.outputs.environmentId

// Service-specific outputs for azd deploy
output SERVICE_DEMO_NAME string = demoAppName
output SERVICE_DEMO_IMAGE_NAME string = !empty(demoImageName) ? demoImageName : '${acr.outputs.loginServer}/agent-memory-demo:${demoImageTag}'
output SERVICE_DEMO_RESOURCE_EXISTS bool = true

// User-friendly outputs
output DEMO_APP_URL string = demoApp.?outputs.?demoUrl ?? ''
output DEMO_APP_NAME string = demoAppName
