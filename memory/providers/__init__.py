"""
Unified providers for Agent Memory Service.

This module provides shared embedding and LLM providers used across
all database backends (SQLite, CosmosDB, PostgreSQL).
"""

from memory.providers.embedding import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
)

__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
]
