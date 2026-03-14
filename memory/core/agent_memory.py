"""
Unified Agent Memory Interface.

Provides a clean, easy-to-use API for agent memory with:
- Database-agnostic design (SQLite, CosmosDB, PostgreSQL)
- Auto-session management
- Intuitive method names
- Context manager support

This is the recommended entry point for the Agent Memory Service.
"""

import os
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

# Agent Framework integration (optional dependency)
try:
    from agent_framework import BaseContextProvider, SessionContext
    HAS_AGENT_FRAMEWORK = True
except ImportError:
    HAS_AGENT_FRAMEWORK = False
    BaseContextProvider = object  # Fallback base class
    SessionContext = object

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
    include_longterm_insights: bool = True
    include_recent_sessions: bool = True
    include_cumulative_summary: bool = True
    
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


class AgentMemory(BaseContextProvider):
    """
    Unified agent memory with multi-tier storage.
    
    Provides a database-agnostic interface for:
    - Short-term: Active conversation buffer
    - Mid-term: Session summaries with vector search
    - Long-term: User insights and patterns
    
    Supports SQLite (default), CosmosDB, and PostgreSQL backends.
    
    Examples:
        # SQLite (default, simplest usage)
        memory = AgentMemory(
            user_id="user123",
            openai_client=openai_client,
            db_path="memory.db"
        )
        await memory.start_session()
        await memory.add_turn("Hello", "Hi there!")
        context = await memory.get_context()
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
            context = await memory.get_context()
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
        cosmos_endpoint: Optional[str] = None,
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
        if HAS_AGENT_FRAMEWORK:
            super().__init__(source_id="agent_memory")

        self.user_id = user_id
        self.config = config or AgentMemoryConfig()
        self.db_type = db_type
        self.db_path = db_path
        self.connection_string = connection_string
        self.cosmos_endpoint = cosmos_endpoint
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
            elif self.cosmos_endpoint:
                db_kwargs["endpoint"] = self.cosmos_endpoint
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
            self.session_id = session_id
            self._orchestrator.session_id = session_id
        elif not self._session_started and self.session_id is None:
            self.session_id = str(uuid.uuid4())
            self._orchestrator.session_id = self.session_id
        
        if restore and not (session_id or self.session_id):
            raise ValueError("restore=True requires an explicit session_id")

        result = await self._orchestrator.start_session(restore=restore)
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
        self.session_id = None
        
        return result

    async def get_context(self) -> str:
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

        return await self._orchestrator.get_formatted_context(
            include_longterm_insights=self.config.include_longterm_insights,
            include_recent_sessions=self.config.include_recent_sessions,
            include_cumulative_summary=self.config.include_cumulative_summary,
        )
    
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
            include_interactions=search_interactions,
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
        self._orchestrator = None
        self._initialized = False
    
    async def __aenter__(self) -> "AgentMemory":
        """Context manager entry - auto-starts session if configured."""
        await self._ensure_initialized()
        if self._auto_start or self.config.auto_manage_sessions:
            await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - auto-ends session if configured."""
        if self._session_started and self.config.auto_manage_sessions:
            await self.end_session(
                trigger_reflection=self.config.trigger_reflection_on_end
            )
        await self.close()
    
    # =========================================================================
    # Agent Framework Context Provider Interface
    # =========================================================================

    async def before_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """
        Called before each agent invocation.

        Injects memory context (insights, session summaries, active turns)
        into session context instructions. Optionally performs auto-enrichment
        based on keyword triggers in recent messages.
        """
        if not HAS_AGENT_FRAMEWORK:
            raise RuntimeError(
                "Agent Framework not installed. Install with: pip install agent-framework"
            )
        
        await self._before_agent_run(context)

    async def _before_agent_run(self, context: Any) -> None:
        """Shared implementation for pre-run context-provider hooks."""
        # Ensure initialized (but don't start a new session - let the demo manage that)
        await self._ensure_initialized()

        # If no session, auto-start one
        if not self._session_started:
            await self.start_session()

        context_parts = []
        
        # Get current memory context
        memory_context = await self.get_context()
        if memory_context.strip():
            context_parts.append(memory_context)
        
        # Auto-enrichment: search memory for relevant facts based on user message
        if self.config.auto_enrich_context:
            # Extract recent user message for query
            recent_text = self._extract_recent_user_text(context.input_messages)
            if recent_text and self._should_enrich(recent_text):
                try:
                    facts = await self.search(recent_text, top_k=3)
                    if facts and facts.strip():
                        context_parts.append(f"\n### Relevant Memory\n{facts}")
                except Exception:
                    pass  # Don't fail agent invocation if enrichment fails

        context_text = "\n".join(context_parts).strip() if context_parts else ""
        if context_text:
            context.extend_instructions(self.source_id, context_text)

    async def after_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """
        Called after each agent invocation.

        Automatically stores the conversation turn in memory.
        """
        await self._after_agent_run(context)

    async def _after_agent_run(self, context: Any) -> None:
        """Shared implementation for post-run context-provider hooks."""
        if not self._session_started:
            return  # No active session

        response = getattr(context, "response", None)
        response_messages = response.messages if response else None

        # Extract user message and assistant response
        user_text = self._extract_recent_user_text(getattr(context, "input_messages", None))
        assistant_text = self._extract_assistant_text(response_messages)

        if user_text and assistant_text:
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
    
    def _should_enrich(self, text: str) -> bool:
        """Check if text contains enrichment trigger keywords."""
        if not text:
            return False
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.config.enrichment_trigger_keywords)


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
