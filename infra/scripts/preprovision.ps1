# Preprovision hook for Azure Developer CLI (azd)
# This script runs before infrastructure provisioning to set up required environment variables

Write-Host "Running preprovision setup..." -ForegroundColor Cyan

# Check if auth is enabled
$enableAuth = azd env get-value ENABLE_AUTH
if ($enableAuth -eq "true") {
    Write-Host "\nEntra ID authentication is enabled" -ForegroundColor Yellow
    
    $authClientId = azd env get-value AUTH_CLIENT_ID
    $authTenantId = azd env get-value AUTH_TENANT_ID
    
    if ([string]::IsNullOrWhiteSpace($authClientId)) {
        Write-Host "⚠ Warning: ENABLE_AUTH is true but AUTH_CLIENT_ID is not set" -ForegroundColor Yellow
        Write-Host "  Set it with: azd env set AUTH_CLIENT_ID <your-client-id>" -ForegroundColor Yellow
    } else {
        Write-Host "  Client ID: $authClientId" -ForegroundColor Gray
        Write-Host "  Tenant ID: $(if ($authTenantId) { $authTenantId } else { '(deployment tenant)' })" -ForegroundColor Gray
        Write-Host "" -ForegroundColor Gray
        Write-Host "  ⚠ IMPORTANT: After deployment, add this redirect URI to your Entra ID app:" -ForegroundColor Yellow
        Write-Host "  https://<your-app-fqdn>/.auth/login/aad/callback" -ForegroundColor Cyan
        Write-Host "  (The exact URL will be shown in the deployment output)" -ForegroundColor Gray
    }
}

# Preprovision hook for Azure Developer CLI (azd)
# This script runs before infrastructure provisioning to set up required environment variables

Write-Host "Running preprovision setup..." -ForegroundColor Cyan

# Check if auth is enabled
$enableAuth = azd env get-value ENABLE_AUTH
if ($enableAuth -eq "true") {
    Write-Host "`nEntra ID authentication is enabled" -ForegroundColor Yellow
    
    $authClientId = azd env get-value AUTH_CLIENT_ID
    $authTenantId = azd env get-value AUTH_TENANT_ID
    
    if ([string]::IsNullOrWhiteSpace($authClientId)) {
        Write-Host "⚠ Warning: ENABLE_AUTH is true but AUTH_CLIENT_ID is not set" -ForegroundColor Yellow
        Write-Host "  Set it with: azd env set AUTH_CLIENT_ID <your-client-id>" -ForegroundColor Yellow
    } else {
        Write-Host "  Client ID: $authClientId" -ForegroundColor Gray
        Write-Host "  Tenant ID: $(if ($authTenantId) { $authTenantId } else { '(deployment tenant)' })" -ForegroundColor Gray
        Write-Host "" -ForegroundColor Gray
        Write-Host "  ⚠ IMPORTANT: After deployment, add this redirect URI to your Entra ID app:" -ForegroundColor Yellow
        Write-Host "  https://<your-app-fqdn>/.auth/login/aad/callback" -ForegroundColor Cyan
        Write-Host "  (The exact URL will be shown in the deployment output)" -ForegroundColor Gray
    }
}

# Get the signed-in user's object ID for Cosmos DB RBAC
Write-Host "Getting local developer object ID for Cosmos DB access..." -ForegroundColor Yellow

try {
    $signedInUser = az ad signed-in-user show --query id -o tsv
    
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get signed-in user object ID"
    }
    
    if ([string]::IsNullOrWhiteSpace($signedInUser)) {
        throw "Object ID is empty"
    }
    
    Write-Host "Found object ID: $signedInUser" -ForegroundColor Green
    
    # Set azd environment variable for use in Bicep
    azd env set LOCAL_DEVELOPER_OBJECT_ID $signedInUser
    
    Write-Host "✓ Local developer object ID configured" -ForegroundColor Green
    
} catch {
    Write-Host "⚠ Warning: Could not get local developer object ID" -ForegroundColor Yellow
    Write-Host "  You may need to manually assign Cosmos DB roles for local development" -ForegroundColor Yellow
    Write-Host "  Error: $_" -ForegroundColor Yellow
    
    # Set empty value so Bicep doesn't fail
    azd env set LOCAL_DEVELOPER_OBJECT_ID ""
}

Write-Host "`nPreprovision setup complete!" -ForegroundColor Cyan
