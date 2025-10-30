"""
Configuration for CosmosMemoryProvider.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class CosmosMemoryProviderConfig:
    """
    Configuration for CosmosMemoryProvider behavior.
    
    Controls what context is injected, how sessions are managed,
    and how memory is formatted for the AI.
    """
    
    # === CosmosDB Connection ===
    database_name: str = "agent_memory"
    interactions_container: str = "interactions"
    summaries_container: str = "session_summaries"
    insights_container: str = "insights"
    
    # === Memory Behavior ===
    buffer_size: int = 10  # Turns before summarization
    active_turns: int = 5   # Recent turns in active context
    
    # === Context Injection Strategy ===
    # What to include in invoking() context
    include_longterm_insights: bool = True
    include_recent_sessions: bool = True
    include_cumulative_summary: bool = True
    include_active_turns: bool = False  # Default OFF - redundant with thread history
    
    # How many recent session summaries to include
    num_recent_sessions: int = 2
    
    # === Session Management ===
    # Should provider manage sessions automatically?
    auto_manage_sessions: bool = True
    
    # Use thread_id as session_id or generate unique session per thread?
    use_thread_as_session: bool = True
    
    # === Reflection ===
    trigger_reflection_on_end: bool = True
    min_confidence: float = 0.7
    
    # === Context Formatting ===
    context_prompt: str = "## Memory Context\nThe following information is relevant from past interactions:"
    
    # Section headers for context
    longterm_insights_header: str = "### Long-term User Profile"
    recent_sessions_header: str = "### Recent Session Summaries"
    cumulative_summary_header: str = "### Current Session Summary"
    active_turns_header: str = "### Recent Conversation"
    
    # Context injection mode
    context_injection_mode: Literal["messages", "instructions"] = "messages"
    
    # === Retrieval ===
    top_k_results: int = 5
    similarity_threshold: float = 0.75
    
    # === Advanced: Insight Categories ===
    insight_categories: Optional[list[str]] = None  # None = use defaults from MemoryConfig
