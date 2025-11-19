# Agent Memory Infrastructure

This directory contains Infrastructure as Code (IaC) for deploying the Agent Memory Service to Azure using Azure Developer CLI (azd) and Bicep.

## Architecture

The infrastructure deploys:

1. **Azure OpenAI Service**
   - Chat model: `gpt-4o` (2024-08-06)
   - Embedding model: `text-embedding-ada-002` (version 2)

2. **Azure Cosmos DB** (NoSQL with Vector Search)
   - Database: `agent_memory_db`
   - Containers:
     - `interactions`: User interaction history with vector embeddings
     - `session_summaries`: Session summaries with vector search
     - `insights`: AI-generated insights with semantic search

3. **Azure Container Apps**
   - Interactive demo application (Streamlit)
   - VNet integration (optional)
   - Managed identity authentication

4. **Networking** (Optional - Secure Mode)
   - Virtual Network with two subnets
   - Private endpoints for Cosmos DB
   - Private DNS zones
   - Network isolation

5. **Security**
   - Managed Identity for Container Apps
   - RBAC for Cosmos DB (data plane + control plane)
   - No connection strings in Container Apps
   - Local developer gets same RBAC roles

## Prerequisites

- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) (azd)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
- Azure subscription
- PowerShell 7+ or Bash
- **For Entra ID Auth**: App registration in Entra ID (can be in different tenant)

## Quick Start

### 1. Configure Authentication (Optional)

If you want to protect the demo app with Entra ID login:

```powershell
# Use your existing app registration
azd env set ENABLE_AUTH true
azd env set AUTH_CLIENT_ID a72cc4b5-df6b-41c4-b5d2-aca151b6838d
azd env set AUTH_TENANT_ID 16b3c013-d300-468d-ac64-7eda0820b6d3
azd env set AUTH_CLIENT_SECRET <client-secret-value>
```

**Notes**:
- You must use an Entra ID **Web** app registration configured as a confidential client with a client secret. Without `AUTH_CLIENT_SECRET`, Easy Auth cannot redeem tokens and you will see HTTP 401 after login.
- Add the redirect URI to your app registration after deployment (shown in output).

To disable authentication:
```powershell
azd env set ENABLE_AUTH false
```

### 2. Initialize azd

```powershell
cd agent_memory
azd init
```

### 2. Login to Azure

```powershell
azd auth login
```

### 3. Deploy Everything

```powershell
azd up
```

This single command will:
1. Run preprovision hooks (get your user object ID, check auth config)
2. Provision all Azure resources
3. Build and deploy the demo container
4. Configure Cosmos DB vector indexes
5. Output the demo URL and redirect URI (if auth enabled)

### 4. Configure Redirect URI (If Auth Enabled)

After deployment, you'll see output like:
```
Add this Redirect URI to your Entra ID app registration:
https://your-app-name.region.azurecontainerapps.io/.auth/login/aad/callback
```

**Add this to your Entra ID app**:
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: **Entra ID** > **App registrations** > **contoso_agent_demo**
3. Click: **Authentication** > **Add a platform** > **Web**
4. Paste the redirect URI
5. Check **ID tokens** (if needed)
6. Save

### 5. Access the Demo

After deployment completes, azd will output:
```
DEMO_APP_URL: https://your-app.region.azurecontainerapps.io
```

Open this URL in your browser to interact with the demo.

## Deployment Modes

### Standard Mode (Secure with VNet)

Default deployment with private endpoints and VNet integration:

```powershell
azd up
```

### Simple Mode (Public Endpoints)

Deploy without VNet for lower cost and simpler setup:

```powershell
azd env set SECURE_COSMOS false
azd up
```

## Configuration

Environment variables (set with `azd env set <NAME> <VALUE>`):

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_ENV_NAME` | `dev` | Environment name (dev/staging/prod) |
| `AZURE_LOCATION` | `eastus` | Azure region for resources |
| `SECURE_COSMOS` | `true` | Enable VNet and private endpoints |
| `DEMO_IMAGE_NAME` | `agent-memory-demo` | Container image name |
| `VNET_ADDRESS_PREFIX` | `10.80.0.0/16` | VNet CIDR block |
| `CONTAINER_APPS_SUBNET_PREFIX` | `10.80.0.0/23` | Container Apps subnet |
| `PRIVATE_ENDPOINT_SUBNET_PREFIX` | `10.80.2.0/24` | Private endpoint subnet |
| `ENABLE_AUTH` | `true` | Enable Entra ID authentication |
| `AUTH_CLIENT_ID` | _(required if auth enabled)_ | Entra ID app client ID |
| `AUTH_TENANT_ID` | _(optional)_ | Entra ID tenant (if cross-tenant) |
| `AUTH_CLIENT_SECRET` | _(required if auth enabled)_ | Client secret for the Entra ID app registration |

## Project Structure

```
infra/
├── main.bicep                          # Main orchestration file
├── main.bicepparam                     # Parameter mappings from azd
├── modules/
│   ├── openai.bicep                    # Azure OpenAI deployment
│   ├── cosmosdb.bicep                  # Cosmos DB with containers
│   ├── container-registry.bicep        # Container image storage
│   ├── log-analytics.bicep             # Monitoring workspace
│   ├── network.bicep                   # VNet, subnets, DNS
│   ├── container-apps-environment.bicep # Container Apps env
│   ├── managed-identity.bicep          # User-assigned identity
│   ├── cosmos-roles.bicep              # RBAC assignments
│   └── demo-app.bicep                  # Demo Container App
└── scripts/
    ├── preprovision.ps1                # Get user object ID
    └── setup-cosmos-vectors.ps1        # Configure vector indexes
```

## Manual Steps

### Vector Index Configuration

Due to Bicep API limitations, vector indexes are configured via post-deployment script. The `setup-cosmos-vectors.ps1` script runs automatically after `azd up`.

If needed, run manually:

```powershell
.\infra\scripts\setup-cosmos-vectors.ps1
```

### Local Development Setup

After deployment, you can run the agent memory service locally with the same permissions:

1. The preprovision script assigns Cosmos DB roles to your user account
2. Use `azd env get-values` to get connection strings
3. Set environment variables in your local `.env` file

```powershell
azd env get-values > .env
```

## Troubleshooting

### Role Assignment Errors

If Cosmos DB role assignments fail during deployment:

```powershell
# Get your object ID
$objectId = az ad signed-in-user show --query id -o tsv

# Manually assign roles
az cosmosdb sql role assignment create `
  --account-name <cosmos-account-name> `
  --resource-group <resource-group> `
  --scope "/" `
  --principal-id $objectId `
  --role-definition-id 00000000-0000-0000-0000-000000000002
```

### Container Build Issues

If the demo container fails to build:

```powershell
# Build and push manually
azd deploy demo
```

### Vector Search Not Working

Vector indexes may need manual configuration:

1. Go to Azure Portal → Cosmos DB → Data Explorer
2. Select container → Settings → Indexing Policy
3. Add vector index policy under "Vector Indexes" section

## Cleanup

Remove all deployed resources:

```powershell
azd down
```

Add `--purge` to also delete soft-deleted resources:

```powershell
azd down --purge
```

## Cost Estimation

### Standard Mode (with VNet)
- Azure OpenAI: ~$0.03/1K tokens
- Cosmos DB: ~$24/month (1000 RU/s autoscale)
- Container Apps: ~$15/month (0-3 replicas)
- Networking: ~$10/month (private endpoints)
- **Total**: ~$50-100/month (usage-dependent)

### Simple Mode (public endpoints)
- Azure OpenAI: ~$0.03/1K tokens
- Cosmos DB: ~$24/month
- Container Apps: ~$15/month
- **Total**: ~$40-80/month

## Security Considerations

### Standard Mode
✅ Private endpoints for Cosmos DB
✅ Network isolation via VNet
✅ Managed identity (no connection strings)
✅ RBAC at data plane and control plane
✅ Entra ID authentication for users (optional)

### Simple Mode
⚠️ Public endpoints for Cosmos DB (firewall recommended)
✅ Managed identity option available
✅ RBAC at data plane and control plane
✅ Entra ID authentication for users (optional)

## Authentication Details

When `ENABLE_AUTH=true`:
- **Easy Auth** (Container Apps built-in authentication)
- Users must sign in with Entra ID before accessing demo
- Supports cross-tenant authentication
- No code changes required
- Automatic token validation
- Session management included

Authentication Flow:
1. User accesses demo URL
2. Redirected to Microsoft login
3. After successful auth, redirected back to app
4. User identity available in request headers (X-MS-CLIENT-PRINCIPAL)

## Next Steps

1. **Configure vector indexes**: Run post-deployment script if not automatic
2. **Test the demo**: Open the demo URL and create test interactions
3. **Monitor costs**: Check Azure Portal cost management
4. **Scale as needed**: Adjust Container Apps replicas and Cosmos DB throughput
5. **Add CI/CD**: Configure GitHub Actions with azd for automated deployments

## Support

- [Azure Developer CLI Documentation](https://learn.microsoft.com/azure/developer/azure-developer-cli/)
- [Bicep Documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Cosmos DB Vector Search](https://learn.microsoft.com/azure/cosmos-db/nosql/vector-search)
- [Container Apps Documentation](https://learn.microsoft.com/azure/container-apps/)
