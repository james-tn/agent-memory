"""
SAM Storage Engines

Provides database abstraction layer with implementations for:
- SQLite (default, local-first)
- PostgreSQL (production)
- CosmosDB (Azure scale)
"""

from sam.stores.base import MemoryStore
from sam.stores.factory import create_store

__all__ = ["MemoryStore", "create_store"]
