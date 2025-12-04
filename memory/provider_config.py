"""
Configuration for CosmosMemoryProvider.
"""

from dataclasses import dataclass
from typing import Optional
from memory.config import MemoryConfig


@dataclass
class CosmosMemoryProviderConfig:
    """
    Configuration for CosmosMemoryProvider to integrate with Agent Framework.
    
    This class handles Agent Framework-specific settings like context injection.
    Core memory behavior (buffer size, reflection, etc.) is configured via MemoryConfig.
    
    Note: memory_config is optional for remote provider (memory service handles it server-side).
    """
    
    # Core memory configuration (required for embedded provider, optional for remote)
    memory_config: Optional[MemoryConfig] = None
    
    # Agent Framework integration settings
    inject_instructions: bool = True
    inject_messages: bool = True
    inject_tools: bool = False
    auto_manage_session: bool = False
    
    # Context injection settings - what to include
    include_longterm_insights: bool = True
    include_recent_sessions: bool = True
    include_cumulative_summary: bool = True
    include_active_turns: bool = False  # Usually redundant with thread history
    
    # Session management
    use_thread_as_session: bool = True  # Use thread_id as session_id
    num_recent_sessions: int = 2  # How many recent sessions to include
    
    # Context formatting
    context_injection_mode: str = "messages"  # "messages" or "instructions"
    context_prompt: str = "## Memory Context\nThe following information is relevant from past interactions:"
    longterm_insights_header: str = "### Long-term User Profile"
    recent_sessions_header: str = "### Recent Session Summaries"
    cumulative_summary_header: str = "### Current Session Summary"
    active_turns_header: str = "### Recent Conversation"
    
    # Hidden tool injection for automatic fact retrieval
    inject_recall_tool: bool = True  # Enable hidden recall_facts tool by default
    recall_tool_name: str = "recall_facts"
    recall_tool_description: str = (
        "Search long-term memory for relevant information from past conversations. "
        "Use this when you need context about the user's history, preferences, or past interactions "
        "that isn't in the current conversation. This searches across all previous sessions, "
        "session summaries, and extracted insights."
    )

