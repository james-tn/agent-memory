#!/usr/bin/env sh
set -eu

echo "Running postprovision setup..."

sh ./infra/scripts/setup-cosmos-vectors.sh
sh ./infra/scripts/setup-search-indexes.sh
sh ./infra/scripts/setup-postgres-schema.sh

echo "Postprovision setup complete."
