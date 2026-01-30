"""
Unified Agent Memory Interface.

Provides a clean, easy-to-use API for agent memory with:
- Database-agnostic design (SQLite, CosmosDB, PostgreSQL)
- Auto-session management
- Intuitive method names
- Context manager support

This is the recommended entry point for the Agent Memory Service.
"""

import uuid
import os
from typing import Dict, List, Optional, Any, Sequence, MutableSequence, TYPE_CHECKING
from dataclasses import dataclass, field

# Agent Framework integration (optional dependency)
try:
    from agent_framework import ContextProvider, Context, tool
    HAS_AGENT_FRAMEWORK = True
except ImportError:
    HAS_AGENT_FRAMEWORK = False
    ContextProvider = object  # Fallback base class
    tool = None  # Fallback

from memory.db.base import MemoryDatabase, ContainerType
from memory.db.factory import create_database, DatabaseType
from memory.providers.embedding import EmbeddingProvider, OpenAIEmbeddingProvider
from memory.core.orchestrator import MemoryOrchestrator, OrchestratorConfig


@dataclass
class AgentMemoryConfig:
    """Configuration for Agent Memory.
    
    This provides a simplified configuration interface that maps to
    the underlying OrchestratorConfig.
    """
    # Memory buffer settings
    buffer_size: int = 6  # Turns before summarization (K_TURN_BUFFER)
    active_turns: int = 4  # Recent turns in context (N_ACTIVE_TURNS)
    num_recent_sessions_for_init: int = 5  # Recent session summaries to load
    
    # Retrieval settings
    top_k_results: int = 5
    similarity_threshold: float = 0.75
    
    # Auto-enrichment (keyword-triggered memory search)
    auto_enrich_context: bool = False
    enrichment_trigger_keywords: List[str] = field(default_factory=lambda: [
        "remember", "recall", "previous", "last time", "before",
        "allergy", "allergies", "medication", "prescribe",
        "history", "past", "earlier", "mentioned"
    ])
    
    # Session management
    auto_manage_sessions: bool = True  # Auto-end sessions in __aexit__
    
    # Reflection
    trigger_reflection_on_end: bool = True
    longterm_synthesis_frequency: int = 5  # Auto-synthesize every N sessions
    
    # Model settings (configured via env vars if not specified)
    reasoning_model: Optional[str] = None  # AZURE_OPENAI_REASONING_MODEL
    processing_model: Optional[str] = None  # AZURE_OPENAI_PROCESSING_MODEL
    embedding_model: str = "text-embedding-ada-002"  # Most common Azure embedding model
    embedding_dimensions: int = 1536  # 1536 for ada-002, 3072 for text-embedding-3-large
    
    # Database settings (for CosmosDB)
    database_name: str = "agent_memory_db"
    interactions_container: str = "interactions"
    summaries_container: str = "session_summaries"
    insights_container: str = "insights"
    
    # =========================================================================
    # Context injection settings (granular control)
    # =========================================================================
    include_longterm_insights: bool = True    # Include user insights
    include_recent_sessions: bool = True      # Include recent session summaries
    include_cumulative_summary: bool = True   # Include current session summary
    include_active_turns: bool = False        # Usually redundant with thread history
    
    # Context formatting
    context_injection_mode: str = "instructions"  # "messages" or "instructions"
    context_prompt: str = "## Memory Context\nThe following information is relevant from past interactions:"
    longterm_insights_header: str = "### Long-term User Profile"
    recent_sessions_header: str = "### Recent Session Summaries"
    cumulative_summary_header: str = "### Current Session Summary"
    active_turns_header: str = "### Recent Conversation"
    
    # =========================================================================
    # Hidden tool injection for automatic fact retrieval
    # =========================================================================
    inject_recall_tool: bool = False  # Enable hidden recall_facts tool
    recall_tool_name: str = "recall_facts"
    recall_tool_description: str = (
        "Search long-term memory for relevant information from past conversations. "
        "Use this when you need context about the user's history, preferences, or past interactions "
        "that isn't in the current conversation. This searches across all previous sessions, "
        "session summaries, and extracted insights."
    )
    
    def to_orchestrator_config(self) -> OrchestratorConfig:
        """Convert to OrchestratorConfig."""
        return OrchestratorConfig(
            K_TURN_BUFFER=self.buffer_size,
            N_ACTIVE_TURNS=self.active_turns,
            NUM_RECENT_SESSIONS_FOR_INIT=self.num_recent_sessions_for_init,
            DEFAULT_TOP_K=self.top_k_results,
            LONGTERM_SYNTHESIS_FREQUENCY=self.longterm_synthesis_frequency,
            REASONING_MODEL=self.reasoning_model or os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o"),
            PROCESSING_MODEL=self.processing_model or os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4o-mini"),
            EMBEDDING_MODEL=self.embedding_model,
            EMBEDDING_DIMENSIONS=self.embedding_dimensions,
            auto_enrich_context=self.auto_enrich_context,
            enrichment_trigger_keywords=self.enrichment_trigger_keywords,
        )


class AgentMemory(ContextProvider if HAS_AGENT_FRAMEWORK else object):
    """
    Unified agent memory with multi-tier storage.
    
    Provides a database-agnostic interface for:
    - Short-term: Active conversation buffer
    - Mid-term: Session summaries with vector search
    - Long-term: User insights and patterns
    
    Supports SQLite (default), CosmosDB, and PostgreSQL backends.
    
    Implements Agent Framework's ContextProvider interface for seamless
    integration with ChatAgent. Features:
    - Automatic context injection via invoking()
    - Automatic turn storage via invoked()
    - Hidden recall_facts tool injection (optional)
    - Granular control over what context is injected
    
    Examples:
        # SQLite (default, simplest usage)
        memory = AgentMemory(
            user_id="user123",
            openai_client=openai_client,
            db_path="memory.db"
        )
        await memory.start_session()
        await memory.add_turn("Hello", "Hi there!")
        context = memory.get_context()
        await memory.end_session()
        
        # CosmosDB (enterprise)
        memory = AgentMemory(
            user_id="user123",
            openai_client=openai_client,
            db_type=DatabaseType.COSMOSDB,
            connection_string=os.getenv("COSMOS_CONNECTION_STRING")
        )
        
        # Context manager (auto session management)
        async with AgentMemory(
            user_id="user123",
            openai_client=openai_client
        ) as memory:
            await memory.add_turn("What's a Roth IRA?", "A Roth IRA is...")
            context = memory.get_context()
        
        # With Agent Framework (recommended)
        memory = AgentMemory(user_id="user123", openai_client=client)
        agent = ChatAgent(
            chat_client=...,
            context_providers=[memory],  # Memory as context provider
        )
        result = await agent.run("Hello")
        await memory.end_session()  # Must call explicitly
    """
    
    def __init__(
        self,
        user_id: str,
        *,
        # Client options
        openai_client=None,
        chat_client=None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        
        # Database options
        db_type: DatabaseType = DatabaseType.SQLITE,
        database: Optional[MemoryDatabase] = None,
        
        # SQLite options
        db_path: str = "agent_memory.db",
        
        # CosmosDB options
        connection_string: Optional[str] = None,
        cosmos_client=None,
        
        # Configuration
        config: Optional[AgentMemoryConfig] = None,
        
        # Session management
        session_id: Optional[str] = None,
        auto_start_session: bool = False,
    ):
        """
        Initialize Agent Memory.
        
        Args:
            user_id: User identifier (required)
            openai_client: Azure OpenAI client for embeddings/chat
            chat_client: Separate chat client (optional, defaults to openai_client)
            embedding_provider: Custom embedding provider (optional)
            db_type: Database type (SQLITE, COSMOSDB, POSTGRESQL)
            database: Pre-created database instance (advanced)
            db_path: Path to SQLite database file (SQLite only)
            connection_string: Cosmos connection string (CosmosDB only)
            cosmos_client: Pre-created CosmosClient (CosmosDB only)
            config: Memory configuration
            session_id: Optional session ID (auto-generated if None)
            auto_start_session: Automatically start session on context manager entry
        
        Raises:
            ValueError: If insufficient connection/client information provided
        """
        self.user_id = user_id
        self.config = config or AgentMemoryConfig()
        self.db_type = db_type
        self.db_path = db_path
        self.connection_string = connection_string
        self.session_id = session_id
        self._session_started = False
        self._initialized = False
        self._auto_start = auto_start_session
        
        # Store client references
        self._openai_client = openai_client
        self._chat_client = chat_client or openai_client
        self._cosmos_client = cosmos_client
        
        # Validate we have what we need
        if not openai_client and not embedding_provider:
            raise ValueError(
                "Either openai_client or embedding_provider must be provided. "
                "An embedding provider is required for semantic search."
            )
        
        # Setup embedding provider
        if embedding_provider:
            self._embedding_provider = embedding_provider
        else:
            self._embedding_provider = OpenAIEmbeddingProvider(
                openai_client,
                model=self.config.embedding_model,
                dimensions=self.config.embedding_dimensions
            )
        
        # Store pre-created database if provided
        self._database = database
        self._orchestrator: Optional[MemoryOrchestrator] = None
        
        # Thread tracking (for Agent Framework integration)
        self._current_thread_id: Optional[str] = None
        self._last_user_message: Optional[str] = None
    
    async def _ensure_initialized(self) -> None:
        """Ensure orchestrator is initialized."""
        if self._initialized:
            return
        
        # Prepare database kwargs
        db_kwargs = {}
        
        if self.db_type == DatabaseType.SQLITE:
            db_kwargs["db_path"] = self.db_path
            db_kwargs["vector_dimensions"] = self.config.embedding_dimensions
        elif self.db_type == DatabaseType.COSMOSDB:
            if self.connection_string:
                db_kwargs["connection_string"] = self.connection_string
            elif self._cosmos_client:
                db_kwargs["cosmos_client"] = self._cosmos_client
            else:
                # Try environment variables
                env_connection = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("AZURE_COSMOS_CONNECTION_STRING")
                env_endpoint = os.getenv("COSMOS_ENDPOINT") or os.getenv("AZURE_COSMOS_ENDPOINT")
                
                if env_connection:
                    db_kwargs["connection_string"] = env_connection
                elif env_endpoint:
                    # Will use AAD auth via DefaultAzureCredential in backend
                    db_kwargs["endpoint"] = env_endpoint
                else:
                    raise ValueError(
                        "CosmosDB requires connection_string, cosmos_client, or "
                        "COSMOS_ENDPOINT/COSMOS_CONNECTION_STRING environment variable."
                    )
            db_kwargs["database_name"] = self.config.database_name
            db_kwargs["vector_dimensions"] = self.config.embedding_dimensions
        
        # Create orchestrator
        self._orchestrator = MemoryOrchestrator(
            user_id=self.user_id,
            session_id=self.session_id,
            config=self.config.to_orchestrator_config(),
            database=self._database,
            db_type=self.db_type,
            openai_client=self._openai_client,
            chat_client=self._chat_client,
            embedding_provider=self._embedding_provider,
            **db_kwargs
        )
        
        # Sync session_id back (orchestrator auto-generates if not provided)
        self.session_id = self._orchestrator.session_id
        
        # Initialize database connection
        await self._orchestrator.initialize()
        
        self._initialized = True
    
    async def start_session(
        self,
        session_id: Optional[str] = None,
        restore: bool = False
    ) -> Dict[str, Any]:
        """
        Start a new session or restore an existing one.
        
        Args:
            session_id: Optional session ID (auto-generated if None for new sessions)
            restore: If True, attempt to restore session state from database
        
        Returns:
            Initial context with insights, recent summaries, and session info
        """
        await self._ensure_initialized()
        
        if session_id:
            # Use provided session_id
            self.session_id = session_id
            self._orchestrator.session_id = session_id
        elif not restore:
            # Generate a new session_id for new sessions
            import uuid
            new_session_id = str(uuid.uuid4())
            self.session_id = new_session_id
            self._orchestrator.session_id = new_session_id
        
        result = await self._orchestrator.start_session()
        self._session_started = True
        
        return result
    
    async def add_turn(
        self,
        user_message: str,
        assistant_message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a conversation turn to memory.
        Automatically handles summarization when buffer is full.
        
        Args:
            user_message: User's message
            assistant_message: Assistant's response
            metadata: Optional metadata (reserved for future use)
        
        Returns:
            Turn processing result with summarization status
        
        Raises:
            RuntimeError: If session not started
        """
        if not self._session_started:
            raise RuntimeError(
                "Session not started. Call start_session() first or use context manager."
            )
        
        # Note: metadata support can be added in future orchestrator versions
        return await self._orchestrator.process_turn(
            user_message=user_message,
            assistant_message=assistant_message
        )
    
    async def end_session(self, trigger_reflection: bool = None) -> Dict[str, Any]:
        """
        End current session. Extracts summary, topics, and insights.
        
        Args:
            trigger_reflection: Whether to extract insights (uses config default if None)
        
        Returns:
            Session summary, topics, and extracted insights
        """
        if not self._session_started:
            return {
                "session_id": self.session_id,
                "message": "Session was not started"
            }
        
        if trigger_reflection is None:
            trigger_reflection = self.config.trigger_reflection_on_end
        
        result = await self._orchestrator.end_session(
            trigger_reflection=trigger_reflection
        )
        self._session_started = False
        
        return result
    
    def get_context(self) -> str:
        """
        Get formatted memory context for AI prompt.
        Includes: long-term insights + recent summaries + active turns.
        
        Returns:
            Formatted context string ready for AI prompt
        
        Raises:
            RuntimeError: If session not started
        """
        if not self._session_started or not self._orchestrator:
            raise RuntimeError(
                "Session not started. Call start_session() first or use context manager."
            )
        
        # get_current_context returns a dict with 'context_text'
        return self._orchestrator._memory_keeper.get_current_context()
    
    async def search(
        self,
        query: str,
        top_k: int = None,
        search_interactions: bool = True,
        search_insights: bool = True,
        search_summaries: bool = False
    ) -> str:
        """
        Search memory for relevant information.
        
        Args:
            query: Natural language search query
            top_k: Number of results (uses config default if None)
            search_interactions: Search past conversations
            search_insights: Search extracted insights
            search_summaries: Search session summaries
        
        Returns:
            Synthesized response with relevant memory
        """
        await self._ensure_initialized()
        
        if top_k is None:
            top_k = self.config.top_k_results
        
        return await self._orchestrator.retrieve_facts(
            query,
            top_k=top_k,
            include_summaries=search_summaries,
            include_insights=search_insights
        )
    
    async def get_insights(
        self,
        category: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get stored insights about the user.
        
        Args:
            category: Optional category filter
            limit: Maximum number of insights to return
        
        Returns:
            List of insight documents
        """
        await self._ensure_initialized()
        return await self._orchestrator.get_user_insights(category, limit)
    
    async def get_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent session summaries.
        
        Args:
            limit: Maximum number of sessions to return
        
        Returns:
            List of session summary documents
        """
        await self._ensure_initialized()
        return await self._orchestrator.get_recent_sessions(limit)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current memory status.
        
        Returns:
            Status information including session state and buffer status
        """
        status = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "db_type": self.db_type.value if hasattr(self.db_type, 'value') else str(self.db_type),
            "session_started": self._session_started,
            "initialized": self._initialized,
        }
        
        if self._orchestrator:
            status["orchestrator_status"] = self._orchestrator.get_status()
        
        return status
    
    @property
    def database(self) -> Optional[MemoryDatabase]:
        """Get the underlying database instance."""
        if self._orchestrator:
            return self._orchestrator._database
        return self._database
    
    @property
    def orchestrator(self) -> Optional[MemoryOrchestrator]:
        """Get the underlying orchestrator instance."""
        return self._orchestrator
    
    async def close(self) -> None:
        """Close database connection and cleanup resources."""
        if self._orchestrator:
            await self._orchestrator.close()
        self._initialized = False
    
    async def __aenter__(self) -> "AgentMemory":
        """Context manager entry - auto-starts session if configured."""
        await self._ensure_initialized()
        if self._auto_start or self.config.auto_manage_sessions:
            await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - auto-ends session if configured.
        
        Note: When used as a ContextProvider with Agent Framework, the framework
        enters/exits the context manager for each run(). We should NOT close the
        database on each exit - only end the session if configured.
        The database should only be closed when explicitly called via close().
        """
        if self._session_started and self.config.auto_manage_sessions:
            await self.end_session(
                trigger_reflection=self.config.trigger_reflection_on_end
            )
        # Don't close the database here - it should stay open for subsequent
        # invoked() calls and future run() invocations.
        # The user should call close() explicitly when done.
    
    # =========================================================================
    # Agent Framework ContextProvider Interface
    # =========================================================================
    
    async def thread_created(self, thread_id: str | None = None) -> None:
        """
        Called when a new thread is created.
        
        Args:
            thread_id: The thread ID from Agent Framework
        """
        self._current_thread_id = thread_id
    
    async def invoking(
        self,
        messages: Any,  # ChatMessage | MutableSequence[ChatMessage]
        **kwargs: Any
    ) -> Any:  # Returns Context
        """
        Called BEFORE each agent invocation.
        
        Injects memory context (insights, session summaries, active turns)
        into the agent's context. Optionally performs auto-enrichment
        based on keyword triggers in recent messages.
        
        This method implements the Agent Framework ContextProvider protocol.
        
        Args:
            messages: The messages being sent to the agent
            **kwargs: Additional context (e.g., thread_id)
        
        Returns:
            Context object with instructions and messages to inject
        """
        if not HAS_AGENT_FRAMEWORK:
            raise RuntimeError(
                "Agent Framework not installed. Install with: pip install agent-framework"
            )
        
        # Ensure initialized (but don't start a new session - let the demo manage that)
        await self._ensure_initialized()
        
        # If no session, auto-start one
        if not self._session_started:
            await self.start_session()
        
        # Cache user message for invoked()
        self._last_user_message = self._extract_recent_user_text(messages)
        
        # Build context parts based on configuration
        context_parts = []
        
        # Get formatted context based on granular settings
        formatted_context = self._build_formatted_context()
        if formatted_context:
            context_parts.append(formatted_context)
        
        # Auto-enrichment: search memory for relevant facts based on user message
        if self.config.auto_enrich_context:
            recent_text = self._last_user_message
            if recent_text and self._should_enrich(recent_text):
                try:
                    facts = await self.search(recent_text, top_k=3)
                    if facts and facts.strip():
                        context_parts.append(f"\n### Relevant Memory\n{facts}")
                except Exception:
                    pass  # Don't fail agent invocation if enrichment fails
        
        # Build context with memory injection
        context_text = "\n".join(context_parts) if context_parts else None
        
        # Inject hidden recall_facts tool if enabled
        context_tools = None
        if self.config.inject_recall_tool and tool is not None:
            context_tools = [self._create_recall_tool()]
        
        # Return context based on injection mode
        if self.config.context_injection_mode == "messages":
            # Import Role for message creation
            try:
                from agent_framework import ChatMessage, Role
                context_messages = [ChatMessage(role=Role.USER, text=context_text)] if context_text else None
                return Context(
                    instructions=None,
                    messages=context_messages,
                    tools=context_tools
                )
            except ImportError:
                pass
        
        # Default: instructions mode
        return Context(
            instructions=context_text,
            messages=None,
            tools=context_tools
        )
    
    async def invoked(
        self,
        request_messages: Any,  # ChatMessage | Sequence[ChatMessage]
        response_messages: Any = None,  # ChatMessage | Sequence[ChatMessage] | None
        invoke_exception: Optional[Exception] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called AFTER each agent invocation.
        
        Automatically stores the conversation turn in memory.
        
        This method implements the Agent Framework ContextProvider protocol.
        
        Args:
            request_messages: The messages sent to the agent
            response_messages: The agent's response messages
            invoke_exception: Any exception that occurred
            **kwargs: Additional context
        """
        if invoke_exception:
            return  # Don't store failed invocations
        
        if not self._session_started:
            return  # No active session
        
        # Use cached user message from invoking() or extract from request
        user_text = self._last_user_message or self._extract_recent_user_text(request_messages)
        assistant_text = self._extract_assistant_text(response_messages)
        
        if user_text and assistant_text:
            # Filter out context injection messages (skip our own injected content)
            if not user_text.startswith(self.config.context_prompt.split('\n')[0]):
                await self.add_turn(user_text, assistant_text)
    
    def _extract_recent_user_text(self, messages: Any) -> Optional[str]:
        """Extract the most recent user message text."""
        if messages is None:
            return None
        
        # Handle single message
        if hasattr(messages, 'text') and hasattr(messages, 'role'):
            if str(messages.role).lower() in ('user', 'role.user'):
                return messages.text
            return None
        
        # Handle sequence of messages
        if isinstance(messages, (list, tuple)):
            for msg in reversed(messages):
                if hasattr(msg, 'role') and hasattr(msg, 'text'):
                    if str(msg.role).lower() in ('user', 'role.user'):
                        return msg.text
        
        return None
    
    def _extract_assistant_text(self, messages: Any) -> Optional[str]:
        """Extract assistant response text."""
        if messages is None:
            return None
        
        # Handle single message
        if hasattr(messages, 'text'):
            return messages.text
        
        # Handle sequence - get first assistant message
        if isinstance(messages, (list, tuple)) and len(messages) > 0:
            msg = messages[0]
            if hasattr(msg, 'text'):
                return msg.text
        
        return None
    
    def _build_formatted_context(self) -> str:
        """
        Build formatted context string based on granular configuration settings.
        
        Returns:
            Formatted context string with selected memory components
        """
        if not self._orchestrator or not self._orchestrator._memory_keeper:
            return ""
        
        memory_keeper = self._orchestrator._memory_keeper
        context_parts = []
        
        # Start with context prompt
        has_content = False
        
        # 1. Long-term insights
        if self.config.include_longterm_insights:
            init_context = memory_keeper.session_init_context
            if init_context and hasattr(init_context, 'longterm_insight') and init_context.longterm_insight:
                context_parts.append(
                    f"{self.config.longterm_insights_header}\n{init_context.longterm_insight}"
                )
                has_content = True
        
        # 2. Recent session summaries
        if self.config.include_recent_sessions:
            init_context = memory_keeper.session_init_context
            if init_context and hasattr(init_context, 'recent_summaries') and init_context.recent_summaries:
                summaries_text = "\n".join([
                    f"- Session {i+1} ({s.get('end_time', 'Unknown')[:10] if s.get('end_time') else 'Unknown'}): {s.get('summary', '')}"
                    for i, s in enumerate(init_context.recent_summaries[:self.config.num_recent_sessions_for_init])
                ])
                if summaries_text:
                    context_parts.append(
                        f"{self.config.recent_sessions_header}\n{summaries_text}"
                    )
                    has_content = True
        
        # 3. Cumulative summary (current session)
        if self.config.include_cumulative_summary:
            cumulative = memory_keeper.cumulative_summary
            if cumulative:
                context_parts.append(
                    f"{self.config.cumulative_summary_header}\n{cumulative}"
                )
                has_content = True
        
        # 4. Active conversation turns
        if self.config.include_active_turns:
            active_context = memory_keeper.get_current_context()
            if active_context:
                context_parts.append(
                    f"{self.config.active_turns_header}\n{active_context}"
                )
                has_content = True
        
        if not has_content:
            return ""
        
        # Combine with context prompt
        combined = "\n\n".join(context_parts)
        return f"{self.config.context_prompt}\n\n{combined}"
    
    def _create_recall_tool(self):
        """
        Create the hidden recall_facts tool that gets injected into agent context.
        
        This tool allows the agent to autonomously search memory when needed,
        without the user explicitly defining it.
        
        Returns:
            AIFunction tool for memory recall
        """
        if tool is None:
            raise RuntimeError("tool decorator not available - agent-framework not installed")
        
        # Capture self in closure for the async function
        memory = self
        session_active = lambda: self._session_started
        config = self.config
        
        @tool(name=config.recall_tool_name, description=config.recall_tool_description)
        async def recall_facts(query: str) -> str:
            """
            Search long-term memory for relevant information from past conversations.
            
            Args:
                query: Natural language search query describing what information to recall
            
            Returns:
                Relevant facts and context from past interactions
            """
            if not session_active():
                return "Memory not available - session not started"
            
            try:
                # Search with summaries and insights for comprehensive results
                return await memory.search(
                    query,
                    search_summaries=True,
                    search_insights=True
                )
            except Exception as e:
                return f"Search failed: {str(e)}"
        
        return recall_facts
    
    def _should_enrich(self, text: str) -> bool:
        """Check if text contains enrichment trigger keywords."""
        if not text:
            return False
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.config.enrichment_trigger_keywords)


# Backward compatibility aliases
CosmosAgentMemory = AgentMemory
SQLiteAgentMemory = AgentMemory


def create_agent_memory(
    user_id: str,
    db_type: DatabaseType = DatabaseType.SQLITE,
    *,
    openai_client=None,
    config: Optional[AgentMemoryConfig] = None,
    **kwargs
) -> AgentMemory:
    """
    Factory function to create an AgentMemory instance.
    
    Args:
        user_id: User identifier
        db_type: Database type (SQLITE, COSMOSDB, POSTGRESQL)
        openai_client: OpenAI client for embeddings and chat
        config: Memory configuration
        **kwargs: Additional arguments passed to AgentMemory constructor
    
    Returns:
        Configured AgentMemory instance
    
    Examples:
        # SQLite
        memory = create_agent_memory("user123", openai_client=client)
        
        # CosmosDB
        memory = create_agent_memory(
            "user123",
            db_type=DatabaseType.COSMOSDB,
            openai_client=client,
            connection_string="..."
        )
    """
    return AgentMemory(
        user_id=user_id,
        db_type=db_type,
        openai_client=openai_client,
        config=config,
        **kwargs
    )
