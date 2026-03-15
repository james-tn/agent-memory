#!/usr/bin/env python3
"""Initialize PostgreSQL pgvector schema for Agent Memory."""

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

    connection_string = _env_or_azd("POSTGRES_CONNECTION_STRING") or _env_or_azd("DATABASE_URL")
    if not connection_string:
        print("PostgreSQL connection string not found; skipping schema setup.")
        return 0

    from memory.db.postgresql_backend import PostgreSQLDatabase

    database = PostgreSQLDatabase(connection_string=connection_string)

    print("Configuring PostgreSQL pgvector schema...")

    try:
        await database.initialize()
        async with database._pool.acquire() as conn:  # noqa: SLF001 - intentional setup-time verification
            value = await conn.fetchval("SELECT 1")
            if value != 1:
                raise RuntimeError("PostgreSQL connectivity check failed")
    finally:
        await database.close()

    print("PostgreSQL schema is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
