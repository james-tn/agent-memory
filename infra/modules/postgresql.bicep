param location string
param baseName string
param environmentName string
param tags object

@description('PostgreSQL admin login name.')
param adminLogin string

@secure()
@description('PostgreSQL admin password.')
param adminPassword string

@description('Database name for the Agent Memory service.')
param databaseName string = 'agent_memory_db'

@description('Optional suffix appended to the PostgreSQL server name to avoid collisions after failed creates.')
param serverNameSuffix string = ''

@description('Public IPv4 address allowed to connect for local live testing.')
param localPublicIp string = ''

var computedServerName = empty(serverNameSuffix)
  ? '${baseName}-${environmentName}-pg'
  : '${baseName}-${environmentName}-pg-${serverNameSuffix}'
var serverName = take(toLower(replace(computedServerName, '_', '')), 63)
var localRuleName = 'local-dev'
var azureServicesRuleName = 'azure-services'

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    version: '16'
    availabilityZone: '1'
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    createMode: 'Create'
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
      tier: 'P4'
    }
  }
  tags: tags
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgresServer
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource vectorExtensionConfig 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'azure.extensions'
  properties: {
    value: 'VECTOR'
    source: 'user-override'
  }
}

resource localFirewallRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = if (!empty(localPublicIp)) {
  parent: postgresServer
  name: localRuleName
  properties: {
    startIpAddress: localPublicIp
    endIpAddress: localPublicIp
  }
}

resource azureServicesFirewallRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgresServer
  name: azureServicesRuleName
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

var connectionString = 'postgresql://${adminLogin}:${uriComponent(adminPassword)}@${postgresServer.name}.postgres.database.azure.com:5432/${databaseName}?sslmode=require'

output serverName string = postgresServer.name
output host string = '${postgresServer.name}.postgres.database.azure.com'
output databaseName string = databaseName
output adminLogin string = adminLogin
@secure()
output connectionString string = connectionString
