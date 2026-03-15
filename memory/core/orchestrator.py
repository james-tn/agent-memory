"""
Unified Memory Orchestrator for Agent Memory Service.

This module provides a database-agnostic orchestrator that coordinates:
- MemoryKeeper: Short-term working memory (k-turn buffer)
- FactRetrieval: Contextual fact retrieval
- Reflection: Insight extraction and synthesis

Works with any database backend implementing the MemoryDatabase interface
(SQLite, CosmosDB, Azure AI Search, PostgreSQL).
"""

import uuid
import asyncio
import math
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from memory.db.base import MemoryDatabase, ContainerType, DatabaseCapabilities, SearchResult
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
    insight_categories: List[str] = field(default_factory=lambda: [
        "preferences",
        "knowledge_level",
        "goals",
        "behavior_patterns",
        "learning_progress",
    ])
    custom_extraction_prompt: Optional[str] = None
    custom_conflict_resolution_prompt: Optional[str] = None
    max_conflict_candidates: int = 5
    
    # Model settings
    REASONING_MODEL: str = "gpt-4o"
    PROCESSING_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-ada-002"
    EMBEDDING_DIMENSIONS: int = 1536
    
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
    - Azure AI Search (managed hybrid search)
    - PostgreSQL (pgvector-backed)
    
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
        agent_id: str = "default",
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
        self.agent_id = agent_id
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

    def _utcnow_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _resolve_azure_openai_settings(self) -> Dict[str, Optional[str]]:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION")

        client = self._chat_client or getattr(self, "_openai_client", None)
        if client is not None:
            if not endpoint:
                azure_endpoint = getattr(client, "_azure_endpoint", None)
                if azure_endpoint:
                    endpoint = str(azure_endpoint).rstrip("/")
                else:
                    base_url = getattr(client, "base_url", None)
                    if base_url:
                        endpoint = str(base_url).split("/openai", 1)[0].rstrip("/")
            if not api_key:
                client_api_key = getattr(client, "api_key", None)
                if client_api_key:
                    api_key = str(client_api_key)
            if not api_version:
                client_api_version = getattr(client, "_api_version", None) or getattr(client, "api_version", None)
                if client_api_version:
                    api_version = str(client_api_version)

        return {
            "endpoint": endpoint,
            "api_key": api_key,
            "api_version": api_version,
        }
    
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
            agent_id=self.agent_id,
            session_id=self.session_id,
            database=self._database,
            embedding_provider=self._embedding_provider,
            chat_client=self._chat_client,
            config=mk_config
        )
        
        azure_openai_settings = self._resolve_azure_openai_settings()

        self._fact_retrieval = FactRetrieval(
            user_id=self.user_id,
            agent_id=self.agent_id,
            database=self._database,
            embedding_provider=self._embedding_provider,
            config=FactRetrievalConfig(REASONING_MODEL=self.config.REASONING_MODEL),
            azure_openai_endpoint=azure_openai_settings["endpoint"],
            azure_openai_api_key=azure_openai_settings["api_key"],
            azure_openai_api_version=azure_openai_settings["api_version"],
        )

        self._reflection = Reflection(
            agent_id=self.agent_id,
            database=self._database,
            embedding_provider=self._embedding_provider,
            chat_client=self._chat_client,
            config=ReflectionConfig(
                PROCESSING_MODEL=self.config.PROCESSING_MODEL,
                insight_categories=self.config.insight_categories,
                custom_extraction_prompt=self.config.custom_extraction_prompt,
                custom_conflict_resolution_prompt=self.config.custom_conflict_resolution_prompt,
                max_conflict_candidates=self.config.max_conflict_candidates,
            )
        )
        
        self._initialized = True
    
    async def start_session(self, restore: bool = False) -> Dict[str, Any]:
        """
        Start a new session and load historical context.
        
        Returns:
            Dictionary with session initialization context
        """
        await self.initialize()
        
        if self._session_started:
            return {"already_started": True}
        
        print(f"[Orchestrator] Starting session {self.session_id}")
        
        if restore:
            existing_session = await self._database.get_by_id(
                container=ContainerType.SESSION_SUMMARIES,
                document_id=self.session_id,
                partition_key=self.user_id,
            )
            if existing_session and existing_session.get("agent_id", "default") != self.agent_id:
                existing_session = None
            if not existing_session:
                raise ValueError(f"Cannot restore missing session: {self.session_id}")
            if existing_session.get("status") == "completed":
                raise ValueError(f"Cannot restore completed session: {self.session_id}")
            self._session_start_time = existing_session.get("start_time") or self._utcnow_iso()
            self._memory_keeper.cumulative_summary = existing_session.get("cumulative_summary", "")
        else:
            # Track session start time
            self._session_start_time = self._utcnow_iso()
            session_timestamp = self._utcnow_iso()
            
            # Create session document in database
            session_doc = {
                "id": self.session_id,
                "user_id": self.user_id,
                "agent_id": self.agent_id,
                "start_time": self._session_start_time,
                "status": "active",
                "cumulative_summary": "",
                "turn_count": 0,
                "created_at": session_timestamp,
                "updated_at": session_timestamp,
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
            "agent_id": self.agent_id,
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
            "pruning_triggered": prune_result is not None,
            "active_turns_count": len(self._memory_keeper.turn_buffer),
            "turn_count": self.turn_count,
            "prune_result": prune_result
        }
    
    async def retrieve_facts(
        self,
        query: str,
        top_k: int = 5,
        include_interactions: bool = True,
        include_summaries: bool = True,
        include_insights: bool = True,
        search_mode: str = "auto",
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
        resolved_search_mode = self._resolve_search_mode(search_mode)

        if self._memory_keeper:
            await self._memory_keeper.wait_for_pending_tasks()

        results = []
        query_vector = self._embedding_provider.get_embedding(query)

        # 1. Search the current in-memory session first if we don't yet have
        # persisted interaction chunks for this turn buffer.
        active_session_results = self._search_active_session_facts(query_vector, top_k)
        results.extend(active_session_results)

        # 2. Search persisted interactions.
        if include_interactions:
            interaction_results = await self._search_persisted_interactions(
                query_text=query,
                query_vector=query_vector,
                top_k=top_k,
                search_mode=resolved_search_mode,
            )
            for r in interaction_results:
                summary = r.get("summary", "")
                content = r.get("content", "")[:300]
                if summary:
                    results.append(f"[Conversation] {summary}")
                elif content:
                    results.append(f"[Conversation] {content}...")

        # 3. Search session summaries
        if include_summaries:
            summary_results = await self._search_container(
                container=ContainerType.SESSION_SUMMARIES,
                query_text=query,
                query_vector=query_vector,
                vector_field="summary_vector",
                top_k=top_k,
                filters={"user_id": self.user_id, "agent_id": self.agent_id},
                search_mode=resolved_search_mode,
            )
            for r in summary_results:
                summary = r.get("summary", "")
                if summary:
                    results.append(f"[Session Summary] {summary}")

        # 4. Search insights
        if include_insights:
            insight_results = await self._search_container(
                container=ContainerType.INSIGHTS,
                query_text=query,
                query_vector=query_vector,
                vector_field="insight_vector",
                top_k=top_k,
                filters={"user_id": self.user_id, "agent_id": self.agent_id},
                search_mode=resolved_search_mode,
            )
            for r in insight_results:
                if r.get("is_deleted", False):
                    continue
                insight_text = r.get("insight_text", "")
                category = r.get("category", "general")
                if insight_text:
                    results.append(f"[Insight: {category}] {insight_text}")

        results = self._dedupe_retrieved_facts(results)

        if not results:
            return "No relevant information found."

        return "\n".join(results[:top_k * 3])

    async def _search_persisted_interactions(
        self,
        *,
        query_text: str,
        query_vector: List[float],
        top_k: int,
        search_mode: str,
    ) -> List[SearchResult]:
        """Search persisted interaction chunks, preferring summary embeddings."""
        seen_ids = set()
        merged_results: List[SearchResult] = []

        for vector_field in ("summary_vector", "content_vector"):
            vector_results = await self._search_container(
                container=ContainerType.INTERACTIONS,
                query_text=query_text,
                query_vector=query_vector,
                vector_field=vector_field,
                top_k=top_k,
                filters={"user_id": self.user_id, "agent_id": self.agent_id},
                search_mode=search_mode,
            )
            for result in vector_results:
                if result.id in seen_ids:
                    continue
                seen_ids.add(result.id)
                merged_results.append(result)

        return merged_results

    def _resolve_search_mode(self, search_mode: str) -> str:
        """Resolve the requested search mode against backend capabilities."""
        requested = (search_mode or "auto").lower()
        get_capabilities = getattr(self._database, "get_capabilities", None)
        if not callable(get_capabilities):
            return "vector" if requested in {"auto", "hybrid", "keyword"} else requested
        capabilities = get_capabilities()

        if requested == "auto":
            if capabilities.supports_hybrid_search:
                return "hybrid"
            return "vector"
        if requested == "hybrid" and not capabilities.supports_hybrid_search:
            return "vector"
        if requested == "keyword" and not capabilities.supports_full_text_search:
            return "vector"
        return requested

    async def _search_container(
        self,
        *,
        container: ContainerType,
        query_text: str,
        query_vector: List[float],
        vector_field: str,
        top_k: int,
        filters: Dict[str, Any],
        search_mode: str,
    ) -> List[SearchResult]:
        """Search a container using the resolved retrieval mode."""
        if search_mode == "hybrid":
            return await self._database.hybrid_search(
                container=container,
                query_text=query_text,
                query_embedding=query_vector,
                vector_field=vector_field,
                top_k=top_k,
                filters=filters,
            )
        if search_mode == "keyword":
            return await self._database.hybrid_search(
                container=container,
                query_text=query_text,
                query_embedding=query_vector,
                vector_field=vector_field,
                top_k=top_k,
                filters=filters,
            )
        return await self._database.vector_search(
            container=container,
            query_embedding=query_vector,
            vector_field=vector_field,
            top_k=top_k,
            filters=filters,
        )

    def _search_active_session_facts(
        self,
        query_vector: List[float],
        top_k: int,
    ) -> List[str]:
        """Search the current in-memory session state as a fallback for live turns."""
        if not self._memory_keeper:
            return []

        candidates: List[tuple[float, str]] = []

        if self._memory_keeper.cumulative_summary:
            similarity = self._cosine_similarity(
                query_vector,
                self._embedding_provider.get_embedding(self._memory_keeper.cumulative_summary),
            )
            candidates.append(
                (
                    similarity,
                    f"[Current Session Summary] {self._memory_keeper.cumulative_summary}",
                )
            )

        if self._memory_keeper.turn_buffer:
            active_text = "\n".join(
                f"{turn.role}: {turn.content}" for turn in self._memory_keeper.turn_buffer
            )
            similarity = self._cosine_similarity(
                query_vector,
                self._embedding_provider.get_embedding(active_text),
            )
            candidates.append(
                (
                    similarity,
                    f"[Active Conversation] {active_text}",
                )
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [text for score, text in candidates[:top_k] if score > 0]

    def _dedupe_retrieved_facts(self, results: List[str]) -> List[str]:
        """Preserve order while removing duplicate retrieval lines."""
        deduped = []
        seen = set()
        for result in results:
            if result in seen:
                continue
            seen.add(result)
            deduped.append(result)
        return deduped

    def _cosine_similarity(self, left: List[float], right: List[float]) -> float:
        """Compute cosine similarity for two embedding vectors."""
        if not left or not right or len(left) != len(right):
            return 0.0

        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)
    
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

    async def get_formatted_context(
        self,
        *,
        include_longterm_insights: bool = True,
        include_recent_sessions: bool = True,
        include_cumulative_summary: bool = True,
    ) -> str:
        """Return formatted context text for prompt injection."""
        await self.initialize()

        if not self._session_started:
            await self.start_session()

        return self._memory_keeper.get_current_context(
            include_longterm_insights=include_longterm_insights,
            include_recent_sessions=include_recent_sessions,
            include_cumulative_summary=include_cumulative_summary,
        )
    
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
        start_time = self._session_start_time or self._utcnow_iso()
        
        # Update session document
        session_doc = {
            "id": self.session_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "start_time": start_time,  # Preserve start_time
            "end_time": self._utcnow_iso(),
            "summary": summary_text,
            "summary_vector": summary_vector,
            "key_topics": analysis.get("key_topics", []),
            "status": "completed",
            "reflection_status": "processed" if analysis.get("has_meaningful_insights") else "no-insight"
        }
        
        await self._database.upsert(
            container=ContainerType.SESSION_SUMMARIES,
            document=session_doc,
            partition_key=self.user_id
        )
        
        # Reconcile and store insights through the reflection pipeline.
        insights_stored = []
        insight_mutations = []
        if trigger_reflection and analysis.get("insights"):
            insights_stored, insight_mutations = await self._reflection.reconcile_session_insights(
                user_id=self.user_id,
                session_id=self.session_id,
                extracted_insights=analysis["insights"],
            )
        
        # Check long-term synthesis trigger
        synthesis_triggered = await self._check_longterm_synthesis_trigger()
        
        total_duration = time.time() - _timer_start
        print(f"  ✓ Session ended (total: {total_duration:.2f}s)")
        self._session_started = False
        self._recent_turns = []
        
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "session_summary": summary_text,
            "key_topics": analysis.get("key_topics", []),
            "insights_extracted": insights_stored,
            "has_meaningful_insights": analysis.get("has_meaningful_insights", False),
            "total_turns": len(self._recent_turns),
            "synthesis_triggered": synthesis_triggered,
            "insight_mutations": insight_mutations,
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
    
    async def _check_longterm_synthesis_trigger(self) -> bool:
        """Check if it's time to trigger long-term synthesis."""
        try:
            # Count completed sessions
            completed_sessions = await self._database.query(
                container=ContainerType.SESSION_SUMMARIES,
                filters={"user_id": self.user_id, "agent_id": self.agent_id, "status": "completed"}
            )
            
            session_count = len(completed_sessions)
            frequency = self.config.LONGTERM_SYNTHESIS_FREQUENCY
            
            if session_count > 0 and session_count % frequency == 0:
                print(f"[LongTerm] 🔄 Triggering synthesis (session #{session_count})")
                await self._reflection.update_longterm_insight(self.user_id)
                return True
            return False
        except Exception as e:
            print(f"[LongTerm] ⚠ Error checking trigger: {e}")
            return False

    @property
    def turn_count(self) -> int:
        """Return the number of recorded user/assistant turn pairs."""
        return len(self._recent_turns) // 2
    
    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "initialized": self._initialized,
            "session_started": self._session_started,
            "turn_count": self.turn_count,
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
        
        filters = {"user_id": self.user_id, "agent_id": self.agent_id}
        if category:
            filters["category"] = category
        
        try:
            insights = await self._database.query(
                container=ContainerType.INSIGHTS,
                filters=filters,
                limit=limit
            )
            return [insight for insight in insights if not insight.get("is_deleted", False)]
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
                filters={"user_id": self.user_id, "agent_id": self.agent_id, "status": "completed"},
                order_by="-end_time",
                limit=limit
            )
            return sessions
        except Exception as e:
            print(f"[Orchestrator] Error getting sessions: {e}")
            return []
    
    async def close(self, *, close_database: Optional[bool] = None) -> None:
        """Close the orchestrator and optionally its owned database."""
        should_close_database = self._owns_database if close_database is None else (close_database and self._owns_database)
        if should_close_database and self._database:
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
    agent_id: str = "default",
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
        agent_id=agent_id,
        session_id=session_id,
        db_type=db_type,
        openai_client=openai_client,
        config=config,
        **db_kwargs
    )
