$ErrorActionPreference = 'Stop'

Write-Host "Running preprovision setup..." -ForegroundColor Cyan

function Get-AzdValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = azd env get-value $Name 2>$null
    if ($LASTEXITCODE -ne 0) {
        return ''
    }
    return ($value | Out-String).Trim()
}

function Set-AzdValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    azd env set $Name $Value | Out-Null
}

function Ensure-AuthReminder {
    $enableAuth = Get-AzdValue 'ENABLE_AUTH'
    if ($enableAuth -ne 'true') {
        return
    }

    Write-Host "`nEntra ID authentication is enabled" -ForegroundColor Yellow
    $authClientId = Get-AzdValue 'AUTH_CLIENT_ID'
    $authTenantId = Get-AzdValue 'AUTH_TENANT_ID'

    if ([string]::IsNullOrWhiteSpace($authClientId)) {
        Write-Host "⚠ Warning: ENABLE_AUTH is true but AUTH_CLIENT_ID is not set" -ForegroundColor Yellow
        Write-Host "  Set it with: azd env set AUTH_CLIENT_ID <your-client-id>" -ForegroundColor Yellow
        return
    }

    Write-Host "  Client ID: $authClientId" -ForegroundColor Gray
    Write-Host "  Tenant ID: $(if ($authTenantId) { $authTenantId } else { '(deployment tenant)' })" -ForegroundColor Gray
    Write-Host "  Redirect URI will be shown again after deployment." -ForegroundColor Gray
}

function Ensure-LocalDeveloperObjectId {
    Write-Host "`nGetting local developer object ID for Cosmos DB access..." -ForegroundColor Yellow

    try {
        $signedInUser = (az ad signed-in-user show --query id -o tsv).Trim()
        if ([string]::IsNullOrWhiteSpace($signedInUser)) {
            throw "Object ID is empty"
        }

        Set-AzdValue -Name 'LOCAL_DEVELOPER_OBJECT_ID' -Value $signedInUser
        Write-Host "  ✓ LOCAL_DEVELOPER_OBJECT_ID set" -ForegroundColor Green
    }
    catch {
        Write-Host "  ⚠ Could not determine local developer object ID: $_" -ForegroundColor Yellow
        Set-AzdValue -Name 'LOCAL_DEVELOPER_OBJECT_ID' -Value ''
    }
}

function Ensure-PostgresCredentials {
    $adminLogin = Get-AzdValue 'POSTGRES_ADMIN_LOGIN'
    if ([string]::IsNullOrWhiteSpace($adminLogin)) {
        $adminLogin = 'agentmemoryadmin'
        Set-AzdValue -Name 'POSTGRES_ADMIN_LOGIN' -Value $adminLogin
        Write-Host "`nSet default POSTGRES_ADMIN_LOGIN to $adminLogin" -ForegroundColor Green
    }

    $postgresLocation = Get-AzdValue 'POSTGRES_LOCATION'
    if ([string]::IsNullOrWhiteSpace($postgresLocation)) {
        Write-Host "PostgreSQL will use AZURE_LOCATION unless POSTGRES_LOCATION is explicitly set." -ForegroundColor Gray
    }
    else {
        Write-Host "Using explicit POSTGRES_LOCATION override: $postgresLocation" -ForegroundColor Gray
    }

    $adminPassword = Get-AzdValue 'POSTGRES_ADMIN_PASSWORD'
    if ([string]::IsNullOrWhiteSpace($adminPassword)) {
        $bytes = New-Object byte[] 24
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
        $generatedPassword = [Convert]::ToBase64String($bytes).Replace('+', 'A').Replace('/', 'b') + '9!'
        Set-AzdValue -Name 'POSTGRES_ADMIN_PASSWORD' -Value $generatedPassword
        Write-Host "Generated and stored POSTGRES_ADMIN_PASSWORD in the local azd environment." -ForegroundColor Green
    }
    else {
        Write-Host "`nUsing existing POSTGRES_ADMIN_PASSWORD from azd env." -ForegroundColor Gray
    }
}

function Ensure-LocalPublicIp {
    Write-Host "`nDetecting public IPv4 address for PostgreSQL firewall..." -ForegroundColor Yellow
    try {
        $ip = (Invoke-RestMethod -Uri 'https://api.ipify.org').Trim()
        if ([string]::IsNullOrWhiteSpace($ip)) {
            throw "IP address lookup returned empty value"
        }
        Set-AzdValue -Name 'LOCAL_DEVELOPER_PUBLIC_IP' -Value $ip
        Write-Host "  ✓ LOCAL_DEVELOPER_PUBLIC_IP set to $ip" -ForegroundColor Green
    }
    catch {
        Write-Host "  ⚠ Could not determine public IP: $_" -ForegroundColor Yellow
        Write-Host "    PostgreSQL local firewall rule may need manual follow-up." -ForegroundColor Yellow
        Set-AzdValue -Name 'LOCAL_DEVELOPER_PUBLIC_IP' -Value ''
    }
}

Ensure-AuthReminder
Ensure-LocalDeveloperObjectId
Ensure-PostgresCredentials
Ensure-LocalPublicIp

Write-Host "`nPreprovision setup complete!" -ForegroundColor Cyan
