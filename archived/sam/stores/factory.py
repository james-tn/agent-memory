"""
SAM Storage Factory

Factory function to create the appropriate MemoryStore based on configuration.
"""

from typing import Optional

from sam.config import SAMConfig
from sam.stores.base import MemoryStore


def create_store(config: Optional[SAMConfig] = None) -> MemoryStore:
    """
    Create a MemoryStore based on configuration.
    
    Args:
        config: SAM configuration (uses default if not provided)
    
    Returns:
        Appropriate MemoryStore implementation
    
    Raises:
        ValueError: If storage engine is not supported
    """
    if config is None:
        config = SAMConfig()
    
    engine = config.storage_engine.lower()
    
    if engine == "sqlite":
        from sam.stores.sqlite_store import SQLiteMemoryStore
        return SQLiteMemoryStore(database_url=config.database_url)
    
    elif engine == "postgres":
        # TODO: Implement PostgresMemoryStore
        raise NotImplementedError(
            "PostgreSQL storage engine is not yet implemented. "
            "Use 'sqlite' for now."
        )
    
    elif engine == "cosmos":
        # TODO: Implement CosmosMemoryStore
        raise NotImplementedError(
            "CosmosDB storage engine is not yet implemented. "
            "Use 'sqlite' for now."
        )
    
    else:
        raise ValueError(
            f"Unknown storage engine: {engine}. "
            f"Supported engines: sqlite, postgres, cosmos"
        )


async def create_and_initialize_store(config: Optional[SAMConfig] = None) -> MemoryStore:
    """
    Create and initialize a MemoryStore.
    
    This is a convenience function that creates the store and calls initialize().
    
    Args:
        config: SAM configuration
    
    Returns:
        Initialized MemoryStore
    """
    store = create_store(config)
    await store.initialize()
    return store
