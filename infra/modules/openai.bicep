// Azure OpenAI deployment with chat and embedding models
param location string
param baseName string
param environmentName string
param tags object

@description('Chat model deployment name')
param chatDeploymentName string = 'gpt-5-chat'

@description('Chat model name')
param chatModelName string = 'gpt-5-chat'

@description('Chat model version')
param chatModelVersion string = '2025-10-03'

@description('Embedding model deployment name')
param embeddingDeploymentName string = 'text-embedding-ada-002'

@description('Embedding model name')
param embeddingModelName string = 'text-embedding-ada-002'

@description('Embedding model version')
param embeddingModelVersion string = '2'

@description('Processing model deployment name (for fast operations like metadata/summaries)')
param processingDeploymentName string = 'gpt-5-mini'

@description('Processing model name')
param processingModelName string = 'gpt-5-mini'

@description('Processing model version')
param processingModelVersion string = '2025-08-07'

var openAIName = '${baseName}-${environmentName}-openai'

resource openAI 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: openAIName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAIName
    publicNetworkAccess: 'Enabled'
  }
  tags: tags
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openAI
  name: chatDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: chatModelVersion
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openAI
  name: embeddingDeploymentName
  sku: {
    name: 'Standard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
  }
  dependsOn: [
    chatDeployment
  ]
}

resource processingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openAI
  name: processingDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: processingModelName
      version: processingModelVersion
    }
  }
  dependsOn: [
    chatDeployment
  ]
}

output endpoint string = openAI.properties.endpoint
@secure()
output key string = openAI.listKeys().key1
output openAIName string = openAI.name
output chatDeploymentName string = chatDeployment.name
output embeddingDeploymentName string = embeddingDeployment.name
output processingDeploymentName string = processingDeployment.name
