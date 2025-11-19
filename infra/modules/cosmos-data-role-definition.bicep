// Custom Cosmos DB data plane role definition used by local developers and managed identities
param cosmosDbAccountName string

@description('Display name for the custom data plane role')
param roleName string = 'AgentMemory Native Data Owner'

@description('Salt used to derive a deterministic GUID for the role definition')
param roleIdSalt string = 'native-data-owner-role'

@description('Data plane actions granted to the custom role')
param dataPlaneActions array = [
  'Microsoft.DocumentDB/databaseAccounts/readMetadata'
  'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/*'
  'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/*'
  'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/*'
]

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosDbAccountName
}

resource customRoleDefinition 'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions@2024-05-15' = {
  name: guid(cosmosDbAccountName, roleIdSalt)
  parent: cosmosAccount
  properties: {
    roleName: roleName
    type: 'CustomRole'
    assignableScopes: [
      cosmosAccount.id
    ]
    permissions: [
      {
        dataActions: dataPlaneActions
        notDataActions: []
      }
    ]
  }
}

output roleDefinitionId string = customRoleDefinition.id
