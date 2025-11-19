param(
    [Parameter(Mandatory = $true)]
    [string]$AccountName,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$PrincipalId,

    [string]$RoleName = 'AgentMemory Native Data Owner'
)

$ErrorActionPreference = 'Stop'

function Invoke-AzCliJson {
    param(
        [Parameter(Mandatory = $true)][string]$Command
    )

    $raw = Invoke-Expression $Command
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return $raw | ConvertFrom-Json
}

Write-Host "Locating subscription context..." -ForegroundColor Cyan
$subscriptionId = (az account show --query id -o tsv).Trim()
if (-not $subscriptionId) {
    throw 'Unable to determine the active Azure subscription. Run `az login` first.'
}

$accountResourceId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.DocumentDB/databaseAccounts/$AccountName"
$scope = $accountResourceId

Write-Host "Checking for existing custom role '$RoleName'..." -ForegroundColor Cyan
$roleDefinitions = Invoke-AzCliJson "az cosmosdb sql role definition list --resource-group $ResourceGroup --account-name $AccountName"
$existingRole = $roleDefinitions | Where-Object { $_.roleName -eq $RoleName }

if ($existingRole) {
    $roleId = $existingRole.id
    Write-Host "Role already exists with id $roleId" -ForegroundColor Yellow
}
else {
    $roleId = (New-Guid).Guid
    $body = @{
        Id         = $roleId
        Properties = @{
            RoleName        = $RoleName
            Type            = 'CustomRole'
            AssignableScopes = @($scope)
            Permissions     = @(
                @{
                    DataActions   = @(
                        'Microsoft.DocumentDB/databaseAccounts/readMetadata'
                        'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/*'
                        'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/*'
                        'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/*'
                    )
                    NotDataActions = @()
                }
            )
        }
    } | ConvertTo-Json -Depth 6

    $tmpFile = New-TemporaryFile
    $body | Set-Content -Path $tmpFile -Encoding utf8

    Write-Host "Creating custom role definition $RoleName..." -ForegroundColor Cyan
    az cosmosdb sql role definition create `
        --resource-group $ResourceGroup `
        --account-name $AccountName `
        --body @$tmpFile.FullName | Out-Null

    Remove-Item $tmpFile -ErrorAction SilentlyContinue
}

Write-Host "Ensuring role assignment for principal $PrincipalId..." -ForegroundColor Cyan
$assignments = Invoke-AzCliJson "az cosmosdb sql role assignment list --resource-group $ResourceGroup --account-name $AccountName"
$existingAssignment = $assignments | Where-Object {
    $_.principalId -eq $PrincipalId -and $_.roleDefinitionId -eq $roleId -and $_.scope -eq $scope
}

if ($existingAssignment) {
    Write-Host "Role already assigned (assignment id $($existingAssignment.id))." -ForegroundColor Yellow
}
else {
    az cosmosdb sql role assignment create `
        --account-name $AccountName `
        --resource-group $ResourceGroup `
        --principal-id $PrincipalId `
        --role-definition-id $roleId `
        --scope $scope | Out-Null
    Write-Host "Role assigned successfully." -ForegroundColor Green
}

Write-Host "Custom role setup complete." -ForegroundColor Green
