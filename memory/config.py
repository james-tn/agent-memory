# Agent Memory Service Configuration
import os
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class MemoryConfig:
    """Configuration parameters for Agent Memory Service."""
    
    # Memory behavior
    buffer_size: int = 10  # Turns before summarization (K_TURN_BUFFER)
    active_turns: int = 5  # Recent turns in context (N_ACTIVE_TURNS)
    num_recent_sessions_for_init: int = 2  # Recent session summaries to load at start
    
    # CosmosDB settings (with sensible defaults)
    database_name: str = "agent_memory"
    interactions_container: str = "interactions"
    summaries_container: str = "session_summaries"
    insights_container: str = "insights"
    
    # Retrieval
    retrieval_mode: str = "on-demand"  # Agent calls CFR via tool
    top_k_results: int = 5
    similarity_threshold: float = 0.75
    
    # Session Management
    auto_manage_sessions: bool = True  # Auto-end sessions in __aexit__
    
    # Reflection
    trigger_reflection_on_end: bool = True  # Run session reflection at end
    longterm_reflection_trigger: str = "manual"  # Manually triggered
    min_confidence: float = 0.7  # Insight confidence threshold
    min_sessions_for_aggregation: int = 3  # Min sessions before aggregation
    
    # Azure OpenAI (optional - can be set from connection)
    chat_deployment: Optional[str] = None
    mini_deployment: Optional[str] = None
    embedding_model: str = "text-embedding-ada-002"
    embedding_dimensions: int = 1536
    
    # Reflection Categories (customizable per domain)
    insight_categories: List[str] = field(default_factory=lambda: [
        "demographics",
        "financial_goals",
        "risk_profile",
        "current_situation",
        "concern",
        "preference"
    ])
    
    # Legacy property mappings for backward compatibility
    @property
    def K_TURN_BUFFER(self) -> int:
        return self.buffer_size
    
    @property
    def N_ACTIVE_TURNS(self) -> int:
        return self.active_turns
    
    @property
    def NUM_RECENT_SESSIONS_FOR_INIT(self) -> int:
        return self.num_recent_sessions_for_init
    
    @property
    def TOP_K_FACTS(self) -> int:
        return self.top_k_results
    
    @property
    def SIMILARITY_THRESHOLD(self) -> float:
        return self.similarity_threshold
    
    @property
    def INSIGHT_CONFIDENCE_THRESHOLD(self) -> float:
        return self.min_confidence
    
    @property
    def MIN_SESSIONS_FOR_AGGREGATION(self) -> int:
        return self.min_sessions_for_aggregation
    
    @property
    def COSMOS_DB_NAME(self) -> str:
        return self.database_name
    
    @property
    def INTERACTIONS_CONTAINER(self) -> str:
        return self.interactions_container
    
    @property
    def INSIGHTS_CONTAINER(self) -> str:
        return self.insights_container
    
    @property
    def SUMMARIES_CONTAINER(self) -> str:
        return self.summaries_container
    
    @property
    def CHAT_DEPLOYMENT(self) -> Optional[str]:
        return self.chat_deployment or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-5-chat")
    
    @property
    def MINI_DEPLOYMENT(self) -> Optional[str]:
        return self.mini_deployment or os.getenv("AZURE_OPENAI_MINI_DEPLOYMENT_NAME", "gpt-5-mini")
    
    @property
    def EMBEDDING_MODEL(self) -> str:
        return self.embedding_model
    
    @property
    def EMBEDDING_DIMENSIONS(self) -> int:
        return self.embedding_dimensions
    
    @property
    def INSIGHT_CATEGORIES(self) -> List[str]:
        return self.insight_categories
