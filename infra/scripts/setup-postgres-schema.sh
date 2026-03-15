#!/usr/bin/env sh
set -eu

echo "Setting up PostgreSQL pgvector schema..."
uv run python infra/scripts/setup_postgres_schema.py
echo "PostgreSQL schema setup complete."
