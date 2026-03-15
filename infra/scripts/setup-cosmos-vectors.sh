#!/usr/bin/env sh
set -eu

if command -v pwsh >/dev/null 2>&1; then
  pwsh ./infra/scripts/setup-cosmos-vectors.ps1
else
  echo "pwsh is not available; skipping Cosmos vector setup on POSIX."
fi
