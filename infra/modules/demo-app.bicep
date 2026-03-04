// Container App for Interactive Demo
param location string
param baseName string
param environmentName string
param tags object

param containerAppsEnvironmentId string
param containerRegistryName string

@secure()
param cosmosDbEndpoint string
@secure()
param cosmosDbKey string
param cosmosDbName string

param azureOpenAIEndpoint string
@secure()
param azureOpenAIKey string
param azureOpenAIChatDeploymentName string
param azureOpenAIEmbDeployment string
param azureOpenAIProcessingModel string

param imageName string = ''

@description('Container image tag to use when azd has not provided an image name yet')
param imageTag string = 'latest'

@description('Whether to use managed identity for Cosmos DB (true) or connection string (false)')
param useCosmosManagedIdentity bool = false

@description('Resource ID of user-assigned managed identity')
param userAssignedIdentityResourceId string = ''

@description('Client ID of user-assigned managed identity')
param userAssignedIdentityClientId string = ''

@description('Enable Entra ID authentication')
param enableAuth bool = false

@description('Entra ID Client ID for authentication')
param authClientId string = ''

@description('Entra ID Tenant ID for authentication')
param authTenantId string = ''

@description('Client secret for the Entra ID app registration used by Easy Auth')
@secure()
param authClientSecret string = ''

var appName = '${baseName}-${take(environmentName, 8)}'

// Follow azd convention: if azd provided a fully-qualified image use it, otherwise fall back to the default repo in ACR
var containerImage = !empty(imageName)
  ? imageName
  : '${containerRegistry.properties.loginServer}/agent-memory-demo:${imageTag}'

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' existing = {
  name: containerRegistryName
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  identity: useCosmosManagedIdentity ? {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityResourceId}': {}
    }
  } : {
    type: 'None'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 8501
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
      secrets: concat([
        {
          name: 'registry-password'
          value: containerRegistry.listCredentials().passwords[0].value
        }
        {
          name: 'openai-key'
          value: azureOpenAIKey
        }
      ], useCosmosManagedIdentity ? [] : [
        {
          name: 'cosmos-key'
          value: cosmosDbKey
        }
      ], (!enableAuth || empty(authClientSecret)) ? [] : [
        {
          name: 'aad-client-secret'
          value: authClientSecret
        }
      ])
    }
    template: {
      containers: [
        {
          name: 'demo-app'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            {
              name: 'COSMOS_ENDPOINT'
              value: cosmosDbEndpoint
            }
            {
              name: 'COSMOS_DATABASE_NAME'
              value: cosmosDbName
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAIEndpoint
            }
            {
              name: 'AZURE_OPENAI_API_KEY'
              secretRef: 'openai-key'
            }
            {
              name: 'AZURE_OPENAI_REASONING_MODEL'
              value: azureOpenAIChatDeploymentName
            }
            {
              name: 'AZURE_OPENAI_EMB_DEPLOYMENT'
              value: azureOpenAIEmbDeployment
            }
            {
              name: 'AZURE_OPENAI_PROCESSING_MODEL'
              value: azureOpenAIProcessingModel
            }
            {
              name: 'USE_MANAGED_IDENTITY'
              value: string(useCosmosManagedIdentity)
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: userAssignedIdentityClientId
            }
          ], useCosmosManagedIdentity ? [] : [
            {
              name: 'COSMOS_KEY'
              secretRef: 'cosmos-key'
            }
          ])
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 30
              successThreshold: 1
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
              successThreshold: 1
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
              successThreshold: 1
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
  tags: tags
}

// Easy Auth configuration (separate resource)
resource authConfig 'Microsoft.App/containerApps/authConfigs@2023-05-01' = if (enableAuth && !empty(authClientId)) {
  name: 'current'
  parent: containerApp
  properties: {
    platform: {
      enabled: true
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: authClientId
          clientSecretSettingName: !empty(authClientSecret) ? 'aad-client-secret' : ''
          openIdIssuer: '${environment().authentication.loginEndpoint}${!empty(authTenantId) ? authTenantId : tenant().tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            'api://${authClientId}'
            authClientId
          ]
        }
      }
    }
    login: {
      allowedExternalRedirectUrls: []
    }
  }
}

output appName string = containerApp.name
output appId string = containerApp.id
output fqdn string = containerApp.properties.configuration.ingress.fqdn
output demoUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
