"""
Database Abstraction Layer for Agent Memory Service.

This module provides a unified interface for multiple database backends:
- SQLite with sqlite-vec extension (default, no server required)
- Azure CosmosDB for NoSQL
- Azure AI Search for native hybrid retrieval
- PostgreSQL with pgvector

Example usage:
    from memory.db import create_database, DatabaseType, ContainerType

    # Create SQLite database (default)
    db = create_database(
        db_type=DatabaseType.SQLITE,
        embedding_provider=my_embedder,
        db_path="memory.db"
    )

    # Use async context manager
    async with db:
        await db.upsert(ContainerType.INTERACTIONS, doc)
        results = await db.vector_search(...)
"""

# Import from submodules - these don't depend on main memory module
from memory.db.base import (
    ContainerType,
    DatabaseCapabilities,
    EmbeddingProvider,
    MemoryDatabase,
    SearchResult,
)
from memory.db.factory import (
    DatabaseType,
    OpenAIEmbeddingProvider,
    create_database,
    create_database_from_config,
)

__all__ = [
    # Base classes and types
    "ContainerType",
    "DatabaseCapabilities",
    "EmbeddingProvider",
    "MemoryDatabase",
    "SearchResult",
    # Factory functions
    "DatabaseType",
    "OpenAIEmbeddingProvider",
    "create_database",
    "create_database_from_config",
]
