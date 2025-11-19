// Cosmos DB deployment with memory service containers (interactions, summaries, insights)
param location string
param baseName string
param environmentName string
param tags object

@description('Enable private endpoint + private DNS (disables public network access)')
param enablePrivateEndpoint bool = false

@description('Subnet resource ID used for the Cosmos DB private endpoint')
param privateEndpointSubnetId string = ''

@description('Private DNS zone resource ID for privatelink.documents.azure.com')
param privateDnsZoneId string = ''

var cosmosDbName = '${baseName}-${environmentName}-cosmos'
var databaseName = 'agent_memory_db'
var interactionsContainerName = 'interactions'
var summariesContainerName = 'session_summaries'
var insightsContainerName = 'insights'

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts@2025-10-15' = {
  name: cosmosDbName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: false
    locations: [
      {
        failoverPriority: 0
        isZoneRedundant: false
        locationName: location
      }
    ]
    capabilities: [
      {
        name: 'EnableNoSQLVectorSearch'
      }
    ]
    publicNetworkAccess: enablePrivateEndpoint ? 'Disabled' : 'Enabled'
  }
  tags: tags
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2025-10-15' = {
  parent: cosmosDb
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// Interactions container - stores conversation chunks with vector embeddings
resource interactionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15' = {
  parent: database
  name: interactionsContainerName
  properties: {
    resource: {
      id: interactionsContainerName
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
      indexingPolicy: any({
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/_etag/?'
          }
          {
            path: '/content_vector/*'
          }
          {
            path: '/summary_vector/*'
          }
        ]
        vectorIndexes: [
          {
            path: '/content_vector'
            type: 'diskANN'
          }
          {
            path: '/summary_vector'
            type: 'quantizedFlat'
          }
        ]
      })
      vectorEmbeddingPolicy: any({
        vectorEmbeddings: [
          {
            path: '/content_vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 1536
          }
          {
            path: '/summary_vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 1536
          }
        ]
      })
      fullTextPolicy: any({
        defaultLanguage: 'en-US'
        fullTextPaths: [
          {
            path: '/content'
            language: 'en-US'
          }
          {
            path: '/metadata/mentioned_topics'
            language: 'en-US'
          }
          {
            path: '/metadata/entities'
            language: 'en-US'
          }
        ]
      })
    }
    options: {
      autoscaleSettings: {
        maxThroughput: 1000
      }
    }
  }
}

// Session summaries container - stores session metadata and summaries with vector embeddings
resource summariesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15' = {
  parent: database
  name: summariesContainerName
  properties: {
    resource: {
      id: summariesContainerName
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
      indexingPolicy: any({
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/_etag/?'
          }
          {
            path: '/summary_vector/*'
          }
        ]
        vectorIndexes: [
          {
            path: '/summary_vector'
            type: 'diskANN'
          }
        ]
      })
      vectorEmbeddingPolicy: any({
        vectorEmbeddings: [
          {
            path: '/summary_vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 1536
          }
        ]
      })
    }
    options: {
      autoscaleSettings: {
        maxThroughput: 1000
      }
    }
  }
}

// Insights container - stores long-term user insights with vector embeddings
resource insightsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15' = {
  parent: database
  name: insightsContainerName
  properties: {
    resource: {
      id: insightsContainerName
      partitionKey: {
        paths: ['/user_id']
        kind: 'Hash'
      }
      indexingPolicy: any({
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/_etag/?'
          }
          {
            path: '/insight_vector/*'
          }
        ]
        vectorIndexes: [
          {
            path: '/insight_vector'
            type: 'diskANN'
          }
        ]
      })
      vectorEmbeddingPolicy: any({
        vectorEmbeddings: [
          {
            path: '/insight_vector'
            dataType: 'float32'
            distanceFunction: 'cosine'
            dimensions: 1536
          }
        ]
      })
    }
    options: {
      autoscaleSettings: {
        maxThroughput: 1000
      }
    }
  }
}

// Private endpoint & DNS configuration
var privateEndpointName = '${cosmosDbName}-pe'
var privateDnsZoneGroupName = 'cosmosdb-zone-group'

resource cosmosPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-05-01' = if (enablePrivateEndpoint) {
  name: privateEndpointName
  location: location
  properties: {
    privateLinkServiceConnections: [
      {
        name: 'cosmosdb'
        properties: {
          privateLinkServiceId: cosmosDb.id
          groupIds: [
            'Sql'
          ]
        }
      }
    ]
    subnet: {
      id: privateEndpointSubnetId
    }
  }
  tags: tags
}

resource cosmosPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = if (enablePrivateEndpoint) {
  parent: cosmosPrivateEndpoint
  name: privateDnsZoneGroupName
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'documents'
        properties: {
          privateDnsZoneId: privateDnsZoneId
        }
      }
    ]
  }
}

output endpoint string = cosmosDb.properties.documentEndpoint
@secure()
output primaryKey string = cosmosDb.listKeys().primaryMasterKey
output databaseName string = databaseName
output accountName string = cosmosDb.name
output interactionsContainer string = interactionsContainerName
output summariesContainer string = summariesContainerName
output insightsContainer string = insightsContainerName
