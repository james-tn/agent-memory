// Cosmos DB Role Assignments (Data Plane + Control Plane)
param cosmosDbAccountName string
param principalId string

@description('Resource ID of the custom Cosmos DB data plane role that grants sqlDatabase management actions')
param dataOwnerRoleDefinitionId string

@description('Use a unique salt to force new deployment on updates - pass from main deployment')
param roleAssignmentSalt string

// Built-in Cosmos DB data plane role IDs
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosDbAccountName
}

// Role assignment for Cosmos DB Data Owner (needed for schema + vector index ops)
resource dataOwnerAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: guid(principalId, cosmosDbAccountName, 'custom-data-owner', roleAssignmentSalt)
  parent: cosmosAccount
  properties: {
    roleDefinitionId: dataOwnerRoleDefinitionId
    principalId: principalId
    scope: cosmosAccount.id
  }
}

// Role assignment for Cosmos DB Data Contributor (write/query access to containers)
resource dataContributorAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: guid(principalId, cosmosDbAccountName, dataContributorRoleId, roleAssignmentSalt)
  parent: cosmosAccount
  properties: {
    roleDefinitionId: resourceId('Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions', cosmosDbAccountName, dataContributorRoleId)
    principalId: principalId
    scope: cosmosAccount.id
  }
}

// Control plane roles so the principal can create databases/containers via ARM
var cosmosContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5bd9cd88-fe45-4216-938b-f97437e15450')
var cosmosOperatorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '230815da-be43-4aae-9cb4-875f7bd000aa')

resource controlPlaneContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(principalId, cosmosDbAccountName, 'contributor', roleAssignmentSalt)
  scope: cosmosAccount
  properties: {
    roleDefinitionId: cosmosContributorRoleId
    principalId: principalId
  }
}

resource controlPlaneOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(principalId, cosmosDbAccountName, 'operator', roleAssignmentSalt)
  scope: cosmosAccount
  properties: {
    roleDefinitionId: cosmosOperatorRoleId
    principalId: principalId
  }
}

output dataOwnerRoleAssignmentId string = dataOwnerAssignment.id
output dataContributorRoleAssignmentId string = dataContributorAssignment.id
output controlPlaneContributorRoleId string = controlPlaneContributor.id
output controlPlaneOperatorRoleId string = controlPlaneOperator.id
