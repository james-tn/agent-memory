"""
Unified providers for Agent Memory Service.

This module provides shared embedding and LLM providers used across
all database backends (SQLite, CosmosDB, Azure AI Search, PostgreSQL).
"""

from memory.providers.embedding import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
)

__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
]
