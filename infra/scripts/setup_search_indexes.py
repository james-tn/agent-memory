#!/usr/bin/env python3
"""Create or update Azure AI Search indexes for Agent Memory."""

import asyncio
import os
import subprocess
import sys

from dotenv import load_dotenv


def _env_or_azd(name: str, default: str = "") -> str:
    try:
        result = subprocess.run(
            ["azd", "env", "get-value", name],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return default

    if result.returncode != 0:
        return os.getenv(name) or default

    value = result.stdout.strip()
    if value:
        return value

    return os.getenv(name) or default


async def main() -> int:
    load_dotenv()
    load_dotenv(".azure/agent-memory/.env", override=False)

    endpoint = _env_or_azd("AZURE_AI_SEARCH_ENDPOINT") or _env_or_azd("AZURE_SEARCH_ENDPOINT")
    api_key = _env_or_azd("AZURE_AI_SEARCH_API_KEY") or _env_or_azd("AZURE_SEARCH_API_KEY")
    index_prefix = _env_or_azd("AZURE_AI_SEARCH_INDEX_PREFIX", "agent-memory")

    if not endpoint or not api_key:
        print("Azure AI Search endpoint or API key not found; skipping index setup.")
        return 0

    from memory.db.azure_search_backend import AzureAISearchDatabase

    database = AzureAISearchDatabase(
        endpoint=endpoint,
        api_key=api_key,
        index_prefix=index_prefix,
    )

    print("Configuring Azure AI Search indexes...")
    print(f"  Endpoint: {endpoint}")
    print(f"  Index prefix: {index_prefix}")

    try:
        await database.initialize()
    finally:
        await database.close()

    print("Azure AI Search indexes are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
