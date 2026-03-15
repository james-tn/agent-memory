$ErrorActionPreference = 'Stop'

Write-Host "Running postprovision setup..." -ForegroundColor Cyan

pwsh ./infra/scripts/setup-cosmos-vectors.ps1
pwsh ./infra/scripts/setup-search-indexes.ps1
pwsh ./infra/scripts/setup-postgres-schema.ps1

Write-Host "Postprovision setup complete." -ForegroundColor Green
