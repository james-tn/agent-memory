"""
Database Factory for Agent Memory Service.

This module provides a factory function to create database backends
based on configuration. Supports SQLite, CosmosDB, and PostgreSQL.
"""

import os
from enum import Enum
from typing import Any, Dict, Optional

from memory.db.base import EmbeddingProvider, MemoryDatabase


class DatabaseType(Enum):
    """Supported database backend types."""
    SQLITE = "sqlite"
    COSMOSDB = "cosmosdb"
    POSTGRESQL = "postgresql"


def create_database(
    db_type: DatabaseType = DatabaseType.SQLITE,
    embedding_provider: Optional[EmbeddingProvider] = None,
    **kwargs
) -> MemoryDatabase:
    """
    Create a database backend instance.
    
    Args:
        db_type: Type of database backend to create
        embedding_provider: Provider for generating embeddings
        **kwargs: Backend-specific configuration options
        
    Returns:
        MemoryDatabase instance
        
    Raises:
        ValueError: If db_type is not supported
        
    Examples:
        # SQLite (default, no server required)
        db = create_database(
            db_type=DatabaseType.SQLITE,
            embedding_provider=my_embedder,
            db_path="memory.db"
        )
        
        # CosmosDB
        db = create_database(
            db_type=DatabaseType.COSMOSDB,
            embedding_provider=my_embedder,
            cosmos_client=my_client,
            database_name="agent_memory_db"
        )
        
        # PostgreSQL (future)
        db = create_database(
            db_type=DatabaseType.POSTGRESQL,
            embedding_provider=my_embedder,
            connection_string="postgresql://..."
        )
    """
    if db_type == DatabaseType.SQLITE:
        from memory.db.sqlite_backend import SQLiteDatabase
        
        return SQLiteDatabase(
            db_path=kwargs.get("db_path", "agent_memory.db"),
            embedding_provider=embedding_provider,
            vector_dimensions=kwargs.get("vector_dimensions", 1536)
        )
    
    elif db_type == DatabaseType.COSMOSDB:
        from memory.db.cosmos_backend import CosmosDBDatabase
        
        return CosmosDBDatabase(
            cosmos_client=kwargs.get("cosmos_client"),
            database_name=kwargs.get("database_name", "agent_memory_db"),
            embedding_provider=embedding_provider,
            connection_string=kwargs.get("connection_string"),
            endpoint=kwargs.get("endpoint"),
            key=kwargs.get("key"),
            credential=kwargs.get("credential"),
            vector_dimensions=kwargs.get("vector_dimensions", 1536)
        )
    
    elif db_type == DatabaseType.POSTGRESQL:
        # PostgreSQL backend not yet implemented
        raise NotImplementedError(
            "PostgreSQL backend is planned but not yet implemented. "
            "Please use SQLite or CosmosDB for now."
        )
    
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def create_database_from_config(
    config: Optional[Dict[str, Any]] = None,
    embedding_provider: Optional[EmbeddingProvider] = None
) -> MemoryDatabase:
    """
    Create database backend from configuration dictionary or environment.
    
    Configuration priority:
    1. Explicit config dict
    2. Environment variables
    3. Defaults (SQLite)
    
    Environment variables:
        AGENT_MEMORY_DB_TYPE: "sqlite", "cosmosdb", or "postgresql"
        AGENT_MEMORY_DB_PATH: Path for SQLite database
        AZURE_COSMOS_ENDPOINT: CosmosDB endpoint
        AZURE_COSMOS_KEY: CosmosDB key
        AZURE_COSMOS_CONNECTION_STRING: CosmosDB connection string
        AZURE_COSMOS_DATABASE: CosmosDB database name
    
    Args:
        config: Configuration dictionary
        embedding_provider: Provider for generating embeddings
        
    Returns:
        MemoryDatabase instance
    """
    config = config or {}
    
    # Determine database type
    db_type_str = config.get(
        "db_type",
        os.getenv("AGENT_MEMORY_DB_TYPE", "sqlite")
    ).lower()
    
    try:
        db_type = DatabaseType(db_type_str)
    except ValueError:
        raise ValueError(
            f"Invalid database type: {db_type_str}. "
            f"Supported: {[t.value for t in DatabaseType]}"
        )
    
    # Build kwargs based on type
    kwargs = {
        "vector_dimensions": config.get(
            "vector_dimensions",
            int(os.getenv("AGENT_MEMORY_VECTOR_DIM", "1536"))
        )
    }
    
    if db_type == DatabaseType.SQLITE:
        kwargs["db_path"] = config.get(
            "db_path",
            os.getenv("AGENT_MEMORY_DB_PATH", "agent_memory.db")
        )
    
    elif db_type == DatabaseType.COSMOSDB:
        kwargs["database_name"] = config.get(
            "database_name",
            os.getenv("AZURE_COSMOS_DATABASE", "agent_memory_db")
        )
        kwargs["connection_string"] = config.get(
            "connection_string",
            os.getenv("AZURE_COSMOS_CONNECTION_STRING")
        )
        kwargs["endpoint"] = config.get(
            "endpoint",
            os.getenv("AZURE_COSMOS_ENDPOINT")
        )
        kwargs["key"] = config.get(
            "key",
            os.getenv("AZURE_COSMOS_KEY")
        )
        kwargs["cosmos_client"] = config.get("cosmos_client")
    
    return create_database(
        db_type=db_type,
        embedding_provider=embedding_provider,
        **kwargs
    )


# Re-export OpenAIEmbeddingProvider for backward compatibility
from memory.providers.embedding import OpenAIEmbeddingProvider
