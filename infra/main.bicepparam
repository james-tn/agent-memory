using './main.bicep'

// These parameters will be populated from azd environment variables
param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'dev')
param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus')
param demoImageName = readEnvironmentVariable('SERVICE_DEMO_IMAGE_NAME', '')

// Optional: Set to false to deploy without VNet and private endpoints (simpler, cheaper)
param secureCosmosConnectivity = bool(readEnvironmentVariable('SECURE_COSMOS', 'true'))

// VNet CIDR configuration
param vnetAddressPrefix = readEnvironmentVariable('VNET_ADDRESS_PREFIX', '10.80.0.0/16')
param containerAppsSubnetPrefix = readEnvironmentVariable('CONTAINER_APPS_SUBNET_PREFIX', '10.80.0.0/23')
param privateEndpointSubnetPrefix = readEnvironmentVariable('PRIVATE_ENDPOINT_SUBNET_PREFIX', '10.80.2.0/24')

// Local developer object ID for Cosmos DB RBAC (set by preprovision hook)
param localDeveloperObjectId = readEnvironmentVariable('LOCAL_DEVELOPER_OBJECT_ID', '')

// Entra ID authentication configuration
param enableAuth = bool(readEnvironmentVariable('ENABLE_AUTH', 'true'))
param authClientId = readEnvironmentVariable('AUTH_CLIENT_ID', '')
param authTenantId = readEnvironmentVariable('AUTH_TENANT_ID', '')
param authClientSecret = readEnvironmentVariable('AUTH_CLIENT_SECRET', '')

// PostgreSQL configuration for live testing
param postgresAdminLogin = readEnvironmentVariable('POSTGRES_ADMIN_LOGIN', 'agentmemoryadmin')
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD', '')
param postgresLocation = readEnvironmentVariable('POSTGRES_LOCATION', readEnvironmentVariable('AZURE_LOCATION', 'eastus'))
param postgresServerNameSuffix = readEnvironmentVariable('POSTGRES_SERVER_NAME_SUFFIX', '')
param localDeveloperPublicIp = readEnvironmentVariable('LOCAL_DEVELOPER_PUBLIC_IP', '')
