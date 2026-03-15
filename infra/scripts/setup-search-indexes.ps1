$ErrorActionPreference = 'Stop'

Write-Host "Setting up Azure AI Search indexes..." -ForegroundColor Cyan
uv run python infra/scripts/setup_search_indexes.py
Write-Host "Azure AI Search index setup complete." -ForegroundColor Green
