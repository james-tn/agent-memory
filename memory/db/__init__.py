"""
Database Abstraction Layer for Agent Memory Service.

This module provides a unified interface for multiple database backends:
- SQLite with sqlite-vec extension (default, no server required)
- Azure CosmosDB for NoSQL
- Azure PostgreSQL with pgvector (future)

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

For integration with existing components:
    from memory.db import DatabaseBundle, create_database
    
    db = create_database(DatabaseType.SQLITE, ...)
    bundle = DatabaseBundle(db)
    
    async with bundle:
        # Use bundle.cosmos_utils, bundle.interactions_container, etc.
        orchestrator = MemoryServiceOrchestrator(
            cosmos_utils=bundle.cosmos_utils,
            interactions_container=bundle.interactions_container,
            ...
        )
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
from memory.db.adapters import (
    ContainerAdapter,
    CosmosUtilsAdapter,
    DatabaseBundle,
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
    # Adapters for existing code
    "ContainerAdapter",
    "CosmosUtilsAdapter",
    "DatabaseBundle",
]
