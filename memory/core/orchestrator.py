"""
Unified Memory Orchestrator for Agent Memory Service.

This module provides a database-agnostic orchestrator that coordinates:
- MemoryKeeper: Short-term working memory (k-turn buffer)
- FactRetrieval: Contextual fact retrieval
- Reflection: Insight extraction and synthesis

Works with any database backend implementing the MemoryDatabase interface
(SQLite, CosmosDB, PostgreSQL).
"""

import uuid
import asyncio
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from memory.db.base import MemoryDatabase, ContainerType, DatabaseCapabilities
from memory.db.factory import create_database, DatabaseType
from memory.providers.embedding import EmbeddingProvider, OpenAIEmbeddingProvider
from memory.core.memory_keeper import MemoryKeeper, MemoryConfig as MemoryKeeperConfig
from memory.core.fact_retrieval import FactRetrieval, FactRetrievalConfig
from memory.core.reflection import Reflection, ReflectionConfig


@dataclass
class OrchestratorConfig:
    """Configuration for the memory orchestrator."""
    # Memory keeper settings
    K_TURN_BUFFER: int = 6  # Turns before pruning
    N_ACTIVE_TURNS: int = 4  # Recent turns in context
    NUM_RECENT_SESSIONS_FOR_INIT: int = 5  # Recent sessions to load
    
    # Fact retrieval settings
    DEFAULT_TOP_K: int = 5
    
    # Reflection settings
    LONGTERM_SYNTHESIS_FREQUENCY: int = 5  # Sessions between synthesis
    
    # Model settings
    REASONING_MODEL: str = "gpt-4o"
    PROCESSING_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072
    
    # Auto-enrichment (LLM-based semantic detection)
    auto_enrich_context: bool = False
    enrichment_mode: str = "llm"  # "llm" (semantic) or "keyword" (simple)
    enrichment_trigger_keywords: List[str] = field(default_factory=lambda: [
        "remember", "recall", "previous", "last time", "before",
        "allergy", "allergies", "medication", "prescribe",
        "history", "past", "earlier", "mentioned"
    ])


class MemoryOrchestrator:
    """
    Unified memory orchestrator for any database backend.
    
    Coordinates MemoryKeeper, FactRetrieval, and Reflection components
    using the MemoryDatabase abstraction layer.
    
    Supports:
    - SQLite (default, no server required)
    - CosmosDB (enterprise, hybrid search)
    - PostgreSQL (future)
    
    Usage:
        # With SQLite (default)
        orchestrator = MemoryOrchestrator(
            user_id="user123",
            openai_client=openai_client,
            db_type=DatabaseType.SQLITE,
            db_path="memory.db"
        )
        
        # With CosmosDB
        orchestrator = MemoryOrchestrator(
            user_id="user123",
            openai_client=openai_client,
            db_type=DatabaseType.COSMOSDB,
            connection_string="AccountEndpoint=..."
        )
        
        # With existing database instance
        orchestrator = MemoryOrchestrator(
            user_id="user123",
            openai_client=openai_client,
            database=my_database_instance
        )
        
        async with orchestrator:
            await orchestrator.process_turn("Hello", "Hi there!")
            context = await orchestrator.get_current_context()
            await orchestrator.end_session()
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        config: Optional[OrchestratorConfig] = None,
        # Database options (use one of these)
        database: Optional[MemoryDatabase] = None,
        db_type: DatabaseType = DatabaseType.SQLITE,
        # Client options
        openai_client=None,
        chat_client=None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        # Database-specific kwargs
        **db_kwargs
    ):
        """
        Initialize the unified memory orchestrator.
        
        Args:
            user_id: User identifier
            session_id: Session identifier (auto-generated if not provided)
            config: Orchestrator configuration
            database: Existing MemoryDatabase instance (optional)
            db_type: Type of database to create if not provided
            openai_client: OpenAI client for embeddings and chat
            chat_client: Separate chat client (optional, defaults to openai_client)
            embedding_provider: Custom embedding provider (optional)
            **db_kwargs: Additional arguments for database creation
                - SQLite: db_path="memory.db"
                - CosmosDB: connection_string="...", database_name="..."
        
        Raises:
            ValueError: If neither openai_client nor embedding_provider provided
        """
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.config = config or OrchestratorConfig()
        
        # Setup embedding provider
        if embedding_provider:
            self._embedding_provider = embedding_provider
        elif openai_client:
            self._embedding_provider = OpenAIEmbeddingProvider(
                openai_client,
                model=self.config.EMBEDDING_MODEL,
                dimensions=self.config.EMBEDDING_DIMENSIONS
            )
        else:
            raise ValueError(
                "Either openai_client or embedding_provider must be provided. "
                "An embedding provider is required for semantic search."
            )
        
        self._chat_client = chat_client or openai_client
        self._db_type = db_type
        self._db_kwargs = db_kwargs
        
        # Database: use provided or create new
        if database:
            self._database = database
            self._owns_database = False
        else:
            self._database = create_database(
                db_type=db_type,
                embedding_provider=self._embedding_provider,
                **db_kwargs
            )
            self._owns_database = True
        
        # Components (initialized lazily)
        self._memory_keeper: Optional[MemoryKeeper] = None
        self._fact_retrieval: Optional[FactRetrieval] = None
        self._reflection: Optional[Reflection] = None
        
        # State
        self._initialized = False
        self._session_started = False
        self._session_start_time: Optional[str] = None
        self._recent_turns: List[tuple] = []  # (role, content) tuples
        
        # Auto-enrichment cache
        self._enrichment_cache: Optional[Dict[str, Any]] = None
        self._last_enrichment_turn_count: int = 0
    
    async def initialize(self) -> None:
        """Initialize the orchestrator, database, and components."""
        if self._initialized:
            return
        
        # Initialize database
        await self._database.initialize()
        
        # Create memory keeper config
        mk_config = MemoryKeeperConfig(
            K_TURN_BUFFER=self.config.K_TURN_BUFFER,
            N_ACTIVE_TURNS=self.config.N_ACTIVE_TURNS,
            NUM_RECENT_SESSIONS_FOR_INIT=self.config.NUM_RECENT_SESSIONS_FOR_INIT,
            PROCESSING_MODEL=self.config.PROCESSING_MODEL
        )
        
        # Initialize components
        self._memory_keeper = MemoryKeeper(
            user_id=self.user_id,
            session_id=self.session_id,
            database=self._database,
            embedding_provider=self._embedding_provider,
            chat_client=self._chat_client,
            config=mk_config
        )
        
        self._fact_retrieval = FactRetrieval(
            user_id=self.user_id,
            database=self._database,
            embedding_provider=self._embedding_provider,
            config=FactRetrievalConfig(REASONING_MODEL=self.config.REASONING_MODEL)
        )
        
        self._reflection = Reflection(
            database=self._database,
            embedding_provider=self._embedding_provider,
            chat_client=self._chat_client,
            config=ReflectionConfig(PROCESSING_MODEL=self.config.PROCESSING_MODEL)
        )
        
        self._initialized = True
    
    async def start_session(self) -> Dict[str, Any]:
        """
        Start a new session and load historical context.
        
        Returns:
            Dictionary with session initialization context
        """
        await self.initialize()
        
        if self._session_started:
            return {"already_started": True}
        
        print(f"[Orchestrator] Starting session {self.session_id}")
        
        # Track session start time
        self._session_start_time = datetime.utcnow().isoformat()
        
        # Create session document in database
        session_doc = {
            "id": self.session_id,
            "user_id": self.user_id,
            "start_time": self._session_start_time,
            "status": "active",
            "cumulative_summary": "",
            "turn_count": 0
        }
        
        await self._database.upsert(
            container=ContainerType.SESSION_SUMMARIES,
            document=session_doc,
            partition_key=self.user_id
        )
        
        # Initialize memory keeper with historical context
        session_init_context = await self._memory_keeper.start_session(self._reflection)
        
        self._session_started = True
        
        return {
            "session_id": self.session_id,
            "longterm_insight": session_init_context.longterm_insight,
            "recent_summaries": session_init_context.recent_summaries,
            "context": self._memory_keeper.get_current_context()
        }
    
    async def process_turn(
        self,
        user_message: str,
        assistant_message: str
    ) -> Dict[str, Any]:
        """
        Process a conversation turn.
        
        Args:
            user_message: User's message
            assistant_message: Assistant's response
            
        Returns:
            Status dictionary with turn processing info
        """
        await self.initialize()
        
        if not self._session_started:
            await self.start_session()
        
        # Add turns to memory keeper
        self._memory_keeper.add_turn("user", user_message)
        self._memory_keeper.add_turn("assistant", assistant_message)
        
        # Track for reflection
        self._recent_turns.append(("user", user_message))
        self._recent_turns.append(("assistant", assistant_message))
        
        # Check if pruning is needed
        prune_result = await self._memory_keeper.maybe_prune()
        
        return {
            "turn_added": True,
            "summarization_triggered": prune_result is not None,
            "active_turns_count": len(self._memory_keeper.turn_buffer),
            "prune_result": prune_result
        }
    
    async def retrieve_facts(
        self,
        query: str,
        top_k: int = 5,
        include_summaries: bool = True,
        include_insights: bool = True
    ) -> str:
        """
        Retrieve relevant facts from memory.
        
        Args:
            query: Search query
            top_k: Number of results per container
            include_summaries: Search session summaries
            include_insights: Search insights
            
        Returns:
            Formatted string with retrieved facts
        """
        await self.initialize()
        
        results = []
        query_vector = self._embedding_provider.get_embedding(query)
        
        # 1. Search interactions (always)
        interaction_results = await self._database.vector_search(
            ContainerType.INTERACTIONS,
            query_vector,
            "content_vector",
            top_k,
            {"user_id": self.user_id}
        )
        for r in interaction_results:
            content = r.get("content", "")[:300]
            if content:
                results.append(f"[Conversation] {content}...")
        
        # 2. Search session summaries
        if include_summaries:
            summary_results = await self._database.vector_search(
                ContainerType.SESSION_SUMMARIES,
                query_vector,
                "summary_vector",
                top_k,
                {"user_id": self.user_id}
            )
            for r in summary_results:
                summary = r.get("summary", "")
                if summary:
                    results.append(f"[Session Summary] {summary}")
        
        # 3. Search insights
        if include_insights:
            insight_results = await self._database.vector_search(
                ContainerType.INSIGHTS,
                query_vector,
                "insight_vector",
                top_k,
                {"user_id": self.user_id}
            )
            for r in insight_results:
                insight_text = r.get("insight_text", "")
                category = r.get("category", "general")
                if insight_text:
                    results.append(f"[Insight: {category}] {insight_text}")
        
        if not results:
            return "No relevant information found."
        
        return "\n".join(results[:top_k * 3])
    
    async def get_current_context(
        self,
        auto_enrich: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Get the current working memory context.
        
        Args:
            auto_enrich: Whether to auto-enrich with recalled facts
            
        Returns:
            Dictionary with context information
        """
        await self.initialize()
        
        if not self._session_started:
            await self.start_session()
        
        context = {
            "context_text": self._memory_keeper.get_current_context(),
            "active_turns": [
                {"role": role, "content": content}
                for role, content in self._recent_turns[-20:]
            ],
            "cumulative_summary": self._memory_keeper.cumulative_summary,
            "buffer_status": {
                "current_size": len(self._memory_keeper.turn_buffer),
                "max_size": self.config.K_TURN_BUFFER,
            },
            "enrichment_triggered": False,
            "recalled_facts": ""
        }
        
        # Auto-enrichment
        should_enrich = auto_enrich if auto_enrich is not None else self.config.auto_enrich_context
        if should_enrich:
            recalled_facts = await self._enrich_with_recalled_facts()
            if recalled_facts:
                context["enrichment_triggered"] = True
                context["recalled_facts"] = recalled_facts
        
        return context
    
    async def end_session(self, trigger_reflection: bool = True) -> Dict[str, Any]:
        """
        End the current session with reflection.
        
        Args:
            trigger_reflection: Whether to trigger insight extraction
            
        Returns:
            Session summary with insights
        """
        import time
        _timer_start = time.time()
        
        await self.initialize()
        
        print(f"[Orchestrator] Ending session {self.session_id}")
        
        # Wait for any pending background tasks before doing final operations
        await self._memory_keeper.wait_for_pending_tasks()
        
        # Final prune any remaining turns
        await self._memory_keeper.final_prune()
        
        # Run reflection if enabled and we have content
        analysis = {"session_summary": "", "key_topics": [], "insights": [], "has_meaningful_insights": False}
        
        if trigger_reflection and self._chat_client and len(self._recent_turns) >= 2:
            analysis = await self._reflection.reflect_on_session(
                user_id=self.user_id,
                session_id=self.session_id,
                cumulative_summary=self._memory_keeper.cumulative_summary,
                recent_turns=self._recent_turns
            )
        
        # Generate embedding for session summary
        summary_text = analysis.get("session_summary", "Session completed.")
        summary_vector = self._embedding_provider.get_embedding(summary_text)
        
        # Use tracked start_time (or fallback to now if not tracked)
        start_time = self._session_start_time or datetime.utcnow().isoformat()
        
        # Update session document
        session_doc = {
            "id": self.session_id,
            "user_id": self.user_id,
            "start_time": start_time,  # Preserve start_time
            "end_time": datetime.utcnow().isoformat(),
            "summary": summary_text,
            "summary_vector": summary_vector,
            "key_topics": analysis.get("key_topics", []),
            "status": "completed",
            "reflection_status": "processed" if analysis.get("has_meaningful_insights") else "no_insights"
        }
        
        await self._database.upsert(
            container=ContainerType.SESSION_SUMMARIES,
            document=session_doc,
            partition_key=self.user_id
        )
        
        # Store insights
        insights_stored = []
        if trigger_reflection and analysis.get("insights"):
            for insight_data in analysis["insights"]:
                insight_text = insight_data.get("insight_text", "")
                if not insight_text:
                    continue
                
                insight_vector = self._embedding_provider.get_embedding(insight_text)
                insight_doc = {
                    "id": insight_data.get("id", str(uuid.uuid4())),
                    "user_id": self.user_id,
                    "session_ids": [self.session_id],  # JSON array format
                    "insight_type": "session",
                    "insight_text": insight_text,
                    "insight_vector": insight_vector,
                    "category": insight_data.get("category", "general"),
                    "confidence": insight_data.get("confidence", 0.5),
                    "importance": insight_data.get("importance", "medium"),
                    "processed": False,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                await self._database.upsert(
                    container=ContainerType.INSIGHTS,
                    document=insight_doc,
                    partition_key=self.user_id
                )
                insights_stored.append(insight_doc)
        
        # Check long-term synthesis trigger
        await self._check_longterm_synthesis_trigger()
        
        total_duration = time.time() - _timer_start
        print(f"  ✓ Session ended (total: {total_duration:.2f}s)")
        
        return {
            "session_id": self.session_id,
            "session_summary": summary_text,
            "key_topics": analysis.get("key_topics", []),
            "insights_extracted": insights_stored,
            "has_meaningful_insights": analysis.get("has_meaningful_insights", False),
            "total_turns": len(self._recent_turns)
        }
    
    async def get_longterm_insight(self) -> Optional[str]:
        """
        Retrieve the long-term insight profile for the current user.
        
        Returns:
            Profile text or None
        """
        await self.initialize()
        return await self._reflection.get_longterm_insight(self.user_id)
    
    async def update_longterm_insight(self) -> Optional[Dict[str, Any]]:
        """
        Manually trigger long-term insight synthesis.
        
        Returns:
            Synthesized insight document or None
        """
        await self.initialize()
        return await self._reflection.update_longterm_insight(self.user_id)
    
    def _should_enrich_context(self) -> bool:
        """Check if recent conversation needs memory retrieval (keyword mode)."""
        if not self.config.auto_enrich_context:
            return False
        
        if not self._recent_turns:
            return False
        
        recent_messages = [content.lower() for _, content in self._recent_turns[-6:]]
        
        for message in recent_messages:
            for keyword in self.config.enrichment_trigger_keywords:
                if keyword.lower() in message:
                    print(f"  [Auto-Enrich] Trigger detected: '{keyword}'")
                    return True
        
        return False
    
    async def _should_enrich_context_llm(self) -> tuple[bool, Optional[str]]:
        """
        Use LLM to semantically detect if conversation needs memory retrieval.
        
        This is more natural than keyword matching - it understands context,
        implicit references, and nuanced requests for past information.
        
        Returns:
            (should_enrich, suggested_query): Whether to retrieve and what to search for
        """
        if not self.config.auto_enrich_context:
            return False, None
        
        if not self._recent_turns or len(self._recent_turns) < 1:
            return False, None
        
        # Check cache to avoid repeated LLM calls for same conversation state
        current_turn_count = len(self._recent_turns)
        if (hasattr(self, '_llm_enrich_cache') and 
            self._llm_enrich_cache.get('turn_count') == current_turn_count):
            cached = self._llm_enrich_cache
            return cached.get('should_enrich', False), cached.get('query')
        
        # Build conversation context for analysis
        recent_conversation = "\n".join([
            f"{role}: {content}" 
            for role, content in self._recent_turns[-4:]
        ])
        
        # Use fast model for detection
        detection_prompt = f"""Analyze this conversation and determine if the user is:
1. Referencing past conversations or information ("you told me", "we discussed", "last time")
2. Asking about something that requires historical context (allergies, preferences, past decisions)
3. Expecting the assistant to remember prior interactions
4. Making a request where past information is critical (e.g., prescribing medication, financial advice)

Conversation:
{recent_conversation}

Respond in this exact format:
NEEDS_MEMORY: yes/no
QUERY: <search query to find relevant past information, or 'none'>
REASON: <brief explanation>"""
        
        try:
            from openai import AzureOpenAI
            import os
            
            # Use processing model (fast) for detection
            client = AzureOpenAI(
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_version="2024-12-01-preview"
            )
            
            response = client.chat.completions.create(
                model=self.config.PROCESSING_MODEL,
                messages=[{"role": "user", "content": detection_prompt}],
                max_completion_tokens=150,
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse response
            should_enrich = "NEEDS_MEMORY: yes" in result_text.lower() or "needs_memory: yes" in result_text
            
            # Extract query
            query = None
            if should_enrich:
                for line in result_text.split("\n"):
                    if line.upper().startswith("QUERY:"):
                        query = line.split(":", 1)[1].strip()
                        if query.lower() == "none":
                            query = None
                        break
            
            # Cache result
            self._llm_enrich_cache = {
                'turn_count': current_turn_count,
                'should_enrich': should_enrich,
                'query': query
            }
            
            if should_enrich:
                print(f"  [Auto-Enrich] 🧠 LLM detected memory need")
                print(f"  [Auto-Enrich] Suggested query: {query}")
            
            return should_enrich, query
            
        except Exception as e:
            print(f"  [Auto-Enrich] ⚠ LLM detection failed: {e}")
            # Fallback to keyword detection
            return self._should_enrich_context(), None
    
    async def _enrich_with_recalled_facts(self, force: bool = False) -> Optional[str]:
        """
        Automatically enrich context with recalled facts.
        
        Uses LLM-based semantic detection (default) or keyword matching to determine
        when memory retrieval is needed. The LLM approach is more natural and
        understands implicit references to past conversations.
        """
        # Check cache first
        current_turn_count = len(self._recent_turns)
        if (self._enrichment_cache is not None and 
            self._last_enrichment_turn_count == current_turn_count):
            return self._enrichment_cache.get('facts')
        
        if not self._recent_turns:
            return None
        
        # Determine if enrichment is needed and get optimal query
        query_text = None
        should_enrich = force
        
        if not force:
            if self.config.enrichment_mode == "llm":
                # Use LLM for semantic detection (more natural, human-like)
                should_enrich, query_text = await self._should_enrich_context_llm()
            else:
                # Use keyword matching (simpler, faster, cheaper)
                should_enrich = self._should_enrich_context()
        
        if not should_enrich:
            return None
        
        # If LLM didn't provide a query, build one from recent turns
        if not query_text:
            query_turns = self._recent_turns[-6:]
            query_text = " ".join([content for _, content in query_turns])[:500]
        
        print(f"  [Auto-Enrich] Searching for relevant facts...")
        print(f"  [Auto-Enrich] Query: {query_text[:100]}...")
        
        try:
            # Use CFR agent for intelligent retrieval
            facts = await self.retrieve_facts(
                query_text,
                include_summaries=True,  # CFR agent can search summaries
                include_insights=True    # CFR agent can search insights
            )
            self._enrichment_cache = {'facts': facts}
            self._last_enrichment_turn_count = current_turn_count
            print(f"  [Auto-Enrich] ✓ Retrieved {len(facts)} chars")
            return facts
        except Exception as e:
            print(f"  [Auto-Enrich] ⚠ Error: {e}")
            return None
    
    async def _check_longterm_synthesis_trigger(self) -> None:
        """Check if it's time to trigger long-term synthesis."""
        try:
            # Count completed sessions
            completed_sessions = await self._database.query(
                container=ContainerType.SESSION_SUMMARIES,
                filters={"user_id": self.user_id, "status": "completed"}
            )
            
            session_count = len(completed_sessions)
            frequency = self.config.LONGTERM_SYNTHESIS_FREQUENCY
            
            if session_count > 0 and session_count % frequency == 0:
                print(f"[LongTerm] 🔄 Triggering synthesis (session #{session_count})")
                await self._reflection.update_longterm_insight(self.user_id)
        except Exception as e:
            print(f"[LongTerm] ⚠ Error checking trigger: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "initialized": self._initialized,
            "session_started": self._session_started,
            "active_turns": len(self._memory_keeper.turn_buffer) if self._memory_keeper else 0,
            "buffer_capacity": self.config.K_TURN_BUFFER,
            "database_type": self._db_type.value if hasattr(self._db_type, 'value') else str(self._db_type),
            "capabilities": self._database.get_capabilities() if self._initialized else None
        }
    
    async def get_user_insights(
        self,
        category: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get insights stored for the current user.
        
        Args:
            category: Optional category filter
            limit: Maximum number of insights to return
            
        Returns:
            List of insight documents
        """
        await self.initialize()
        
        filters = {"user_id": self.user_id}
        if category:
            filters["category"] = category
        
        try:
            insights = await self._database.query(
                container=ContainerType.INSIGHTS,
                filters=filters,
                limit=limit
            )
            return insights
        except Exception as e:
            print(f"[Orchestrator] Error getting insights: {e}")
            return []
    
    async def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent session summaries for the current user.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of session summary documents (most recent first)
        """
        await self.initialize()
        
        try:
            sessions = await self._database.query(
                container=ContainerType.SESSION_SUMMARIES,
                filters={"user_id": self.user_id, "status": "completed"},
                order_by="-end_time",
                limit=limit
            )
            return sessions
        except Exception as e:
            print(f"[Orchestrator] Error getting sessions: {e}")
            return []
    
    async def close(self) -> None:
        """Close the orchestrator and database."""
        if self._owns_database and self._database:
            await self._database.close()
        self._initialized = False
        self._session_started = False
    
    async def __aenter__(self) -> "MemoryOrchestrator":
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Factory function for convenience
def create_orchestrator(
    user_id: str,
    session_id: Optional[str] = None,
    db_type: DatabaseType = DatabaseType.SQLITE,
    openai_client=None,
    config: Optional[OrchestratorConfig] = None,
    **db_kwargs
) -> MemoryOrchestrator:
    """
    Create a memory orchestrator with specified backend.
    
    Args:
        user_id: User identifier
        session_id: Session identifier (auto-generated if not provided)
        db_type: Database type (SQLITE, COSMOSDB)
        openai_client: OpenAI client for embeddings and LLM
        config: Orchestrator configuration
        **db_kwargs: Database-specific arguments
        
    Returns:
        Configured MemoryOrchestrator
    """
    return MemoryOrchestrator(
        user_id=user_id,
        session_id=session_id,
        db_type=db_type,
        openai_client=openai_client,
        config=config,
        **db_kwargs
    )


# Backward compatibility aliases
MemoryServiceOrchestrator = MemoryOrchestrator
SQLiteMemoryOrchestrator = MemoryOrchestrator
