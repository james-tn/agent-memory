$ErrorActionPreference = 'Stop'

Write-Host "Setting up PostgreSQL pgvector schema..." -ForegroundColor Cyan
uv run python infra/scripts/setup_postgres_schema.py
Write-Host "PostgreSQL schema setup complete." -ForegroundColor Green
