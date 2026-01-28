"""Agent Memory Service - Core memory management for AI agents.

This module provides a unified, database-agnostic interface for managing
agent memory across conversations. Supports SQLite (local) and CosmosDB (enterprise).

Quick Start:
    from memory import AgentMemory, AgentMemoryConfig
    from memory.db.factory import DatabaseType
    
    # SQLite (default, no server required)
    async with AgentMemory(user_id="user123", openai_client=client) as memory:
        await memory.add_turn("Hello!", "Hi there!")
        context = memory.get_context()
    
    # CosmosDB (enterprise)
    memory = AgentMemory(
        user_id="user123",
        openai_client=client,
        db_type=DatabaseType.COSMOSDB
    )
"""

__version__ = "0.2.0"

# Main unified API
from memory.core.agent_memory import (
    AgentMemory,
    AgentMemoryConfig,
    create_agent_memory,
)

from memory.core.orchestrator import (
    MemoryOrchestrator,
    OrchestratorConfig,
    create_orchestrator,
)

# Database layer
from memory.db.factory import DatabaseType, create_database
from memory.db.base import MemoryDatabase, ContainerType, SearchResult

# Embedding providers
from memory.providers.embedding import EmbeddingProvider, OpenAIEmbeddingProvider

# Backward compatibility aliases
CosmosAgentMemory = AgentMemory  # Use AgentMemory with db_type=DatabaseType.COSMOSDB
SQLiteAgentMemory = AgentMemory  # Use AgentMemory with db_type=DatabaseType.SQLITE
MemoryServiceOrchestrator = MemoryOrchestrator  # Alias to unified MemoryOrchestrator


__all__ = [
    # Version
    "__version__",
    
    # Main API (recommended)
    "AgentMemory",
    "AgentMemoryConfig",
    "create_agent_memory",
    
    # Orchestrator (advanced usage)
    "MemoryOrchestrator",
    "OrchestratorConfig",
    "create_orchestrator",
    
    # Database layer
    "DatabaseType",
    "create_database",
    "MemoryDatabase",
    "ContainerType",
    "SearchResult",
    
    # Embedding providers
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    
    # Backward compatibility
    "CosmosAgentMemory",
    "SQLiteAgentMemory",
    "MemoryServiceOrchestrator",
]

