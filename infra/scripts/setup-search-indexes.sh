#!/usr/bin/env sh
set -eu

echo "Setting up Azure AI Search indexes..."
uv run python infra/scripts/setup_search_indexes.py
echo "Azure AI Search index setup complete."
