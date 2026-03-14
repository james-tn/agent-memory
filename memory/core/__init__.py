"""
Database-agnostic core components for Agent Memory Service.

This module provides the core memory management components that work
with any database backend implementing the MemoryDatabase interface.

Components:
- MemoryKeeper: Turn buffer management, cumulative summaries, context building
- FactRetrieval: Intelligent memory search using Agent Framework
- Reflection: Session insights extraction and long-term pattern synthesis
- MemoryOrchestrator: Unified orchestration layer for all components
"""

from memory.core.memory_keeper import (
    MemoryKeeper,
    MemoryConfig,
    ConversationTurn,
    SessionInitContext,
    MetadataOutput,
    KeyTopicsOutput,
    CumulativeSummaryOutput
)
from memory.core.fact_retrieval import (
    FactRetrieval,
    FactRetrievalConfig,
)
from memory.core.reflection import (
    Reflection,
    ReflectionConfig,
    SessionInsight,
    ComprehensiveSessionAnalysis,
    LongTermSynthesisOutput,
    LongTermProfileOutput,
)
from memory.core.orchestrator import (
    MemoryOrchestrator,
    OrchestratorConfig,
    create_orchestrator,
)
from memory.core.agent_memory import (
    AgentMemory,
    AgentMemoryConfig,
    create_agent_memory,
)

__all__ = [
    # Main classes (recommended entry points)
    "AgentMemory",
    "MemoryOrchestrator",
    "MemoryKeeper",
    "FactRetrieval",
    "Reflection",
    # Configurations
    "AgentMemoryConfig",
    "MemoryConfig",
    "FactRetrievalConfig",
    "ReflectionConfig",
    "OrchestratorConfig",
    # Factory functions
    "create_agent_memory",
    "create_orchestrator",
    # Data classes
    "ConversationTurn",
    "SessionInitContext",
    # Pydantic models
    "MetadataOutput",
    "KeyTopicsOutput",
    "CumulativeSummaryOutput",
    "SessionInsight",
    "ComprehensiveSessionAnalysis",
    "LongTermSynthesisOutput",
    "LongTermProfileOutput",
]
