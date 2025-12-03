"""
Configuration for CosmosMemoryProvider.
"""

from dataclasses import dataclass
from memory.config import MemoryConfig


@dataclass
class CosmosMemoryProviderConfig:
    """
    Configuration for CosmosMemoryProvider to integrate with Agent Framework.
    
    This class handles Agent Framework-specific settings like context injection.
    Core memory behavior (buffer size, reflection, etc.) is configured via MemoryConfig.
    """
    
    # Core memory configuration (required)
    memory_config: MemoryConfig
    
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

