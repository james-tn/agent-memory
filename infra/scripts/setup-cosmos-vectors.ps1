# Post-provision hook to configure Cosmos DB vector indexes
# This runs after infrastructure deployment to set up vector search capabilities

Write-Host "Configuring Cosmos DB vector indexes..." -ForegroundColor Cyan

# Get deployment outputs from azd
$cosmosAccountName = azd env get-value AZURE_COSMOS_ACCOUNT_NAME
$cosmosDatabase = azd env get-value AZURE_COSMOS_DATABASE_NAME
$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP

if ([string]::IsNullOrWhiteSpace($cosmosAccountName) -or 
    [string]::IsNullOrWhiteSpace($cosmosDatabase) -or 
    [string]::IsNullOrWhiteSpace($resourceGroup)) {
    Write-Host "⚠ Warning: Missing required environment variables" -ForegroundColor Yellow
    Write-Host "  AZURE_COSMOS_ACCOUNT_NAME: $cosmosAccountName" -ForegroundColor Yellow
    Write-Host "  AZURE_COSMOS_DATABASE_NAME: $cosmosDatabase" -ForegroundColor Yellow
    Write-Host "  AZURE_RESOURCE_GROUP: $resourceGroup" -ForegroundColor Yellow
    Write-Host "  Vector indexes must be configured manually" -ForegroundColor Yellow
    exit 0
}

Write-Host "Account: $cosmosAccountName" -ForegroundColor Gray
Write-Host "Database: $cosmosDatabase" -ForegroundColor Gray
Write-Host "Resource Group: $resourceGroup" -ForegroundColor Gray

# Container configurations with vector policies
$containers = @(
    @{
        name = "interactions"
        vectorField = "summary_vector"
        dimensions = 1536
        distanceFunction = "cosine"
        indexType = "quantizedFlat"
    },
    @{
        name = "session_summaries"
        vectorField = "summary_vector"
        dimensions = 1536
        distanceFunction = "cosine"
        indexType = "quantizedFlat"
    },
    @{
        name = "insights"
        vectorField = "insight_vector"
        dimensions = 1536
        distanceFunction = "cosine"
        indexType = "quantizedFlat"
    }
)

foreach ($container in $containers) {
    Write-Host "`nConfiguring vector index for container: $($container.name)" -ForegroundColor Yellow
    
    # Build the vector embedding policy JSON
    $vectorEmbeddingPolicy = @{
        vectorEmbeddings = @(
            @{
                path = "/$($container.vectorField)"
                dataType = "float32"
                dimensions = $container.dimensions
                distanceFunction = $container.distanceFunction
            }
        )
    } | ConvertTo-Json -Depth 10 -Compress
    
    # Build the indexing policy with vector indexes
    $indexingPolicy = @{
        indexingMode = "consistent"
        automatic = $true
        includedPaths = @(
            @{ path = "/*" }
        )
        excludedPaths = @(
            @{ path = '/"_etag"/?' }
        )
        vectorIndexes = @(
            @{
                path = "/$($container.vectorField)"
                type = $container.indexType
            }
        )
    } | ConvertTo-Json -Depth 10 -Compress

    # Write JSON payloads to temp files to avoid PowerShell quote mangling
    $indexingPolicyFileInfo = New-TemporaryFile
    $indexingPolicyFile = $indexingPolicyFileInfo.FullName
    try {
        Set-Content -Path $indexingPolicyFile -Value $indexingPolicy -Encoding utf8
    } catch {
        Write-Host "⚠ Warning: Could not write indexing policy file" -ForegroundColor Yellow
        Write-Host "  Error: $_" -ForegroundColor Yellow
        continue
    }
    
    try {
        # Update container with vector policies using Azure CLI
        Write-Host "Updating indexing policy..." -ForegroundColor Gray
        $idxArgument = "@" + $indexingPolicyFile

        az cosmosdb sql container update `
            --account-name $cosmosAccountName `
            --database-name $cosmosDatabase `
            --name $($container.name) `
            --resource-group $resourceGroup `
            --idx $idxArgument `
            --output none
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Indexing policy updated" -ForegroundColor Green
        } else {
            throw "Failed to update indexing policy"
        }
        
        # Note: Vector embedding policy may require REST API or SDK
        # Azure CLI doesn't fully support it yet as of 2024
        Write-Host "⚠ Vector embedding policy may need manual configuration via Portal or REST API" -ForegroundColor Yellow
        Write-Host "  Path: /$($container.vectorField)" -ForegroundColor Gray
        Write-Host "  Dimensions: $($container.dimensions)" -ForegroundColor Gray
        Write-Host "  Distance: $($container.distanceFunction)" -ForegroundColor Gray
        
    } catch {
        Write-Host "⚠ Warning: Could not update container $($container.name)" -ForegroundColor Yellow
        Write-Host "  Error: $_" -ForegroundColor Yellow
        Write-Host "  You may need to configure vector indexes manually" -ForegroundColor Yellow
    } finally {
        if (Test-Path $indexingPolicyFile) {
            Remove-Item $indexingPolicyFile -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "`n✓ Vector index configuration complete!" -ForegroundColor Cyan
Write-Host "  Note: Some vector settings may require manual configuration in Azure Portal" -ForegroundColor Yellow

# Show Entra ID redirect URI if auth is enabled
$enableAuth = azd env get-value ENABLE_AUTH
if ($enableAuth -eq "true") {
    $demoUrl = azd env get-value DEMO_APP_URL
    if (![string]::IsNullOrWhiteSpace($demoUrl)) {
        $redirectUri = "$demoUrl/.auth/login/aad/callback"
        
        Write-Host "`n========================================" -ForegroundColor Cyan
        Write-Host "  ENTRA ID CONFIGURATION REQUIRED" -ForegroundColor Yellow
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Add this Redirect URI to your Entra ID app registration:" -ForegroundColor White
        Write-Host ""
        Write-Host "  $redirectUri" -ForegroundColor Green
        Write-Host ""
        Write-Host "Steps:" -ForegroundColor White
        Write-Host "1. Go to: https://portal.azure.com" -ForegroundColor Gray
        Write-Host "2. Navigate to: Entra ID > App registrations > contoso_agent_demo" -ForegroundColor Gray
        Write-Host "3. Click: Authentication > Add a platform > Web" -ForegroundColor Gray
        Write-Host "4. Add the redirect URI above" -ForegroundColor Gray
        Write-Host "5. Save changes" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Demo URL: $demoUrl" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
    }
}
