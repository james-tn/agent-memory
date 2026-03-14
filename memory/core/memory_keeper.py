"""
Database-agnostic Memory Keeper for Agent Memory Service.

This module provides the core memory management functionality that works
with any database backend implementing the MemoryDatabase interface.

The MemoryKeeper handles:
- Turn buffer management (K-turn buffer with pruning)
- Cumulative summary updates
- Session initialization context
- Interaction document creation and storage
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from pydantic import BaseModel, Field

from memory.db.base import ContainerType, MemoryDatabase
from memory.core.llm_json import call_llm_with_json
from memory.models import SessionInitContext
from memory.providers.embedding import EmbeddingProvider

if TYPE_CHECKING:
    from memory.core.reflection import Reflection


# ==================== Pydantic Models for Structured Output ====================

class MetadataOutput(BaseModel):
    """Structured output for metadata generation."""
    summary: str = Field(..., description="A brief summary of the conversation chunk")
    mentioned_topics: List[str] = Field(
        default_factory=list,
        description="List of topics mentioned in the conversation"
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Named entities (people, places, organizations) mentioned"
    )


class KeyTopicsOutput(BaseModel):
    """Structured output for key topics extraction."""
    key_topics: List[str] = Field(
        default_factory=list,
        description="List of key topics from the session"
    )


class CumulativeSummaryOutput(BaseModel):
    """Structured output for cumulative summary."""
    summary: str = Field(..., description="Updated cumulative summary")


# ==================== Data Classes ====================

@dataclass
class ConversationTurn:
    """Represents a single conversation turn."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MemoryConfig:
    """Configuration for memory management."""
    K_TURN_BUFFER: int = 6  # Number of turns before pruning
    N_ACTIVE_TURNS: int = 4  # Number of recent turns to keep in context
    NUM_RECENT_SESSIONS_FOR_INIT: int = 5  # Number of recent sessions to load
    PROCESSING_MODEL: str = "gpt-4o-mini"  # Model for metadata/summary generation


# ==================== Memory Keeper Class ====================

class MemoryKeeper:
    """
    Database-agnostic memory keeper for managing conversation context.
    
    Handles:
    - Turn buffer management with K-turn pruning
    - Cumulative summary updates
    - Session initialization with historical context
    - Interaction document creation and storage
    
    Uses the MemoryDatabase interface to work with any backend
    (SQLite, CosmosDB, PostgreSQL).
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        database: MemoryDatabase,
        embedding_provider: EmbeddingProvider,
        chat_client: Any,
        config: Optional[MemoryConfig] = None
    ):
        """
        Initialize the MemoryKeeper.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            database: Database backend implementing MemoryDatabase interface
            embedding_provider: Provider for generating embeddings
            chat_client: OpenAI-compatible chat client for LLM calls
            config: Configuration settings (uses defaults if not provided)
        """
        self.user_id = user_id
        self.session_id = session_id
        self.database = database
        self.embedding_provider = embedding_provider
        self.chat_client = chat_client
        self.config = config or MemoryConfig()
        
        # State
        self.turn_buffer: List[ConversationTurn] = []
        self.cumulative_summary: str = ""
        self.session_init_context: Optional[SessionInitContext] = None
        self.session_started: bool = False
        self._closing = False

        # Track background tasks for cleanup
        self._pending_tasks: List[asyncio.Task] = []
    
    def _call_llm_with_json(
        self,
        system_prompt: str,
        user_prompt: str,
        output_model: Type[BaseModel]
    ) -> BaseModel:
        """
        Call LLM with chat completions API and parse JSON response.
        
        Uses JSON mode for structured output, compatible with Azure OpenAI.
        
        Args:
            system_prompt: System message content
            user_prompt: User message content  
            output_model: Pydantic model class for output parsing
            
        Returns:
            Parsed Pydantic model instance
        """
        return call_llm_with_json(
            self.chat_client,
            self.config.PROCESSING_MODEL,
            system_prompt,
            user_prompt,
            output_model,
        )
    
    async def start_session(
        self,
        reflection: Optional["Reflection"] = None
    ) -> SessionInitContext:
        """
        Initialize session context with historical data.
        
        Retrieves:
        1. Long-term insight for the user (if reflection provided)
        2. Recent session summaries (last N sessions)
        
        Args:
            reflection: Optional Reflection instance for fetching long-term insights
        
        Returns:
            SessionInitContext with insights and recent summaries
        """
        print(f"[MemoryKeeper] Initializing session context for user: {self.user_id}")
        self._closing = False
        
        # Fetch long-term insight if reflection is available
        longterm_insight = None
        if reflection:
            longterm_insight = await reflection.get_longterm_insight(self.user_id)
            if longterm_insight:
                print(f"  ✓ Loaded long-term insight profile ({len(longterm_insight)} chars)")
                print(f"     Preview: {longterm_insight[:150]}...")
            else:
                print(f"  ℹ No long-term insight found for user (will be created after sufficient sessions)")
        else:
            print(f"  ℹ Reflection not provided, skipping long-term insight fetch")
        
        # Query recent session summaries using database abstraction
        results = await self.database.query(
            container=ContainerType.SESSION_SUMMARIES,
            filters={"user_id": self.user_id, "status": "completed"},
            order_by="-end_time",
            limit=self.config.NUM_RECENT_SESSIONS_FOR_INIT
        )
        
        recent_summaries = []
        for result in results:
            session_id = result.get("id", "")
            summary = result.get("summary", "")
            recent_summaries.append({
                "session_id": session_id,
                "summary": summary,
                "end_time": result.get("end_time", ""),
                "key_topics": result.get("key_topics", [])
            })
            if summary:
                print(f"     📋 Session {session_id[:8]}...: {summary[:100]}...")
        
        print(f"  ✓ Loaded {len(recent_summaries)} recent session summaries")
        
        # Create session init context
        self.session_init_context = SessionInitContext(
            longterm_insight=longterm_insight,
            recent_summaries=recent_summaries
        )
        
        self.session_started = True
        return self.session_init_context
    
    def add_turn(self, role: str, content: str) -> None:
        """
        Add a conversation turn to the buffer.
        
        Args:
            role: "user" or "assistant"
            content: Turn content
        """
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        self.turn_buffer.append(turn)
        print(f"[MemoryKeeper] Added {role} turn. Buffer: {len(self.turn_buffer)}/{self.config.K_TURN_BUFFER}")
    
    async def maybe_prune(self) -> Optional[Dict]:
        """
        Check if buffer has reached k turns and prune if needed.
        
        When buffer reaches k turns:
        1. Update cumulative summary (synchronous - agent needs this)
        2. Prune buffer immediately
        3. Launch async task to create & store interaction document
        
        Returns:
            Dict with pruning info immediately (doesn't wait for database)
        """
        if len(self.turn_buffer) < self.config.K_TURN_BUFFER:
            return None
        
        print(f"\n[MemoryKeeper] Buffer full ({self.config.K_TURN_BUFFER} turns). Starting pruning...")
        
        # Get the k turns to prune
        turns_to_prune = self.turn_buffer[:self.config.K_TURN_BUFFER]
        
        # Update cumulative summary (keep synchronous - agent needs this for context)
        old_summary = self.cumulative_summary
        new_summary = await self._update_cumulative_summary(
            old_summary=old_summary,
            new_turns=turns_to_prune
        )
        self.cumulative_summary = new_summary if new_summary else old_summary
        
        print(f"  ✓ Updated cumulative summary ({len(self.cumulative_summary)} chars)")
        if not new_summary:
            print(f"  ⚠ Warning: LLM returned empty summary")
        
        # Update session document with new cumulative summary (for restoration)
        self._track_pending_task(asyncio.create_task(self._update_session_summary_async()))
        
        # Prune buffer immediately (don't wait for database)
        self.turn_buffer = self.turn_buffer[self.config.K_TURN_BUFFER:]
        
        print(f"  ✓ Pruned buffer. Remaining turns: {len(self.turn_buffer)}")
        
        # Launch async task to process and store interaction (non-blocking)
        if not self._closing:
            self._track_pending_task(asyncio.create_task(self._process_interaction_async(turns_to_prune)))
        
        print(f"  🔄 Interaction processing started in background\n")
        
        return {
            "turns_pruned": self.config.K_TURN_BUFFER,
            "cumulative_summary": self.cumulative_summary,
            "interaction_processing": "background"
        }
    
    async def _process_interaction_async(self, turns: List[ConversationTurn]) -> None:
        """
        Process and store interaction document in background (non-blocking).
        
        This runs asynchronously to avoid blocking the agent during:
        - Metadata generation (LLM call)
        - Embedding generation
        - Database storage
        """
        # Flatten turns into conversation text
        conversation_text = "\n".join([
            f"{turn.role}: {turn.content}" for turn in turns
        ])
        
        # Generate metadata using processing model
        metadata = await self._generate_metadata(conversation_text)
        
        # Generate embeddings using the embedding provider
        content_embedding = self.embedding_provider.get_embedding(conversation_text)
        summary_embedding = self.embedding_provider.get_embedding(metadata["summary"])
        
        # Create interaction document
        interaction_doc = {
            "id": str(uuid.uuid4()),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": conversation_text,
            "content_vector": content_embedding,
            "summary": metadata["summary"],
            "summary_vector": summary_embedding,
            "metadata": {
                "mentioned_topics": metadata["mentioned_topics"],
                "entities": metadata["entities"]
            }
        }
        
        # Store in database using abstraction layer
        result = await self.database.upsert(
            container=ContainerType.INTERACTIONS,
            document=interaction_doc,
            partition_key=self.user_id
        )
        
        print(f"  ✓ [Background] Interaction document stored: {result['id']}")
        print(f"    Topics: {metadata['mentioned_topics']}")
    
    async def final_prune(self) -> Optional[Dict]:
        """
        Prune any remaining turns in buffer at session end.
        
        Called when session ends to ensure all turns are stored.
        
        Returns:
            Dict with pruning info if turns were pruned, None otherwise
        """
        if len(self.turn_buffer) == 0:
            return None
        
        print(f"\n[MemoryKeeper] Final prune. Remaining turns: {len(self.turn_buffer)}")
        
        # Generate metadata for remaining turns
        conversation_text = "\n".join([
            f"{turn.role}: {turn.content}" for turn in self.turn_buffer
        ])
        
        metadata = await self._generate_metadata(conversation_text)
        
        # Generate embeddings
        content_embedding = self.embedding_provider.get_embedding(conversation_text)
        summary_embedding = self.embedding_provider.get_embedding(metadata["summary"])
        
        # Create interaction document
        interaction_doc = {
            "id": str(uuid.uuid4()),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": conversation_text,
            "content_vector": content_embedding,
            "summary": metadata["summary"],
            "summary_vector": summary_embedding,
            "metadata": {
                "mentioned_topics": metadata["mentioned_topics"],
                "entities": metadata["entities"]
            }
        }
        
        # Store in database
        result = await self.database.upsert(
            container=ContainerType.INTERACTIONS,
            document=interaction_doc,
            partition_key=self.user_id
        )
        
        print(f"  ✓ Final interaction document: {result['id']}")
        
        # Clear buffer
        turns_count = len(self.turn_buffer)
        self.turn_buffer = []
        
        return {
            "interaction_id": result["id"],
            "turns_pruned": turns_count,
            "summary": metadata["summary"]
        }
    
    async def wait_for_pending_tasks(self) -> None:
        """
        Wait for all pending background tasks to complete.
        
        Should be called before closing the database connection
        to ensure all writes are complete.
        """
        self._closing = True
        if self._pending_tasks:
            print(f"  ⏳ Waiting for {len(self._pending_tasks)} pending tasks...")
            # Filter out completed tasks
            pending = [t for t in self._pending_tasks if not t.done()]
            if pending:
                results = await asyncio.gather(*pending, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        print(f"  ⚠ Warning: Background task failed: {result}")
            self._pending_tasks.clear()
            print(f"  ✓ All pending tasks completed")

    def _track_pending_task(self, task: asyncio.Task) -> None:
        """Track background tasks and surface failures."""
        def _on_done(done_task: asyncio.Task) -> None:
            try:
                exc = done_task.exception()
            except asyncio.CancelledError:
                return
            if exc is not None:
                print(f"  ⚠ Warning: Background task raised an exception: {exc}")

        task.add_done_callback(_on_done)
        self._pending_tasks.append(task)
    
    def get_current_context(
        self,
        *,
        include_longterm_insights: bool = True,
        include_recent_sessions: bool = True,
        include_cumulative_summary: bool = True,
    ) -> str:
        """
        Build formatted context for the agent.
        
        Context structure:
        1. Session initialization block (if available)
        2. Cumulative summary (if available)
        3. Active turns (last N turns from buffer)
        
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Add session initialization block
        if self.session_init_context:
            init_block = self._format_session_init_block(
                include_longterm_insights=include_longterm_insights,
                include_recent_sessions=include_recent_sessions,
            )
            context_parts.append(init_block)
        
        # Add cumulative summary
        if include_cumulative_summary and self.cumulative_summary:
            context_parts.append("### Conversation Summary")
            context_parts.append(self.cumulative_summary)
            context_parts.append("")
        
        # Add active turns (last N turns)
        if self.turn_buffer:
            active_turns = self.turn_buffer[-self.config.N_ACTIVE_TURNS:]
            context_parts.append("### Active Conversation")
            for turn in active_turns:
                context_parts.append(f"{turn.role}: {turn.content}")
        
        return "\n".join(context_parts)
    
    def _format_session_init_block(
        self,
        *,
        include_longterm_insights: bool = True,
        include_recent_sessions: bool = True,
    ) -> str:
        """Format the session initialization block."""
        if not self.session_init_context:
            return ""
        
        parts = ["<session_initialization>"]
        
        # Add long-term insight
        if include_longterm_insights and self.session_init_context.longterm_insight:
            parts.append("### Key Insights")
            parts.append(self.session_init_context.longterm_insight)
            parts.append("")
        
        # Add recent session summaries
        if include_recent_sessions and self.session_init_context.recent_summaries:
            parts.append("### Recent Session Summaries")
            for session in self.session_init_context.recent_summaries:
                end_time = session.get("end_time", "")
                summary = session.get("summary", "")
                parts.append(f"- {end_time}: {summary}")
            parts.append("")
        
        parts.append("</session_initialization>")
        parts.append("")
        
        return "\n".join(parts)
    
    async def _generate_metadata(self, conversation_text: str) -> Dict:
        """
        Generate metadata for conversation chunk using LLM with structured output.
        
        Returns:
            Dict with summary, mentioned_topics, entities
        """
        from memory.prompts import METADATA_GENERATION_PROMPT
        
        prompt = METADATA_GENERATION_PROMPT.format(conversation_content=conversation_text)
        
        try:
            # Use chat completions with JSON mode
            metadata_obj = self._call_llm_with_json(
                system_prompt="You are a metadata extraction assistant.",
                user_prompt=prompt,
                output_model=MetadataOutput
            )
            
            return {
                "summary": metadata_obj.summary,
                "mentioned_topics": metadata_obj.mentioned_topics,
                "entities": metadata_obj.entities
            }
        except Exception as e:
            # Fallback if parsing fails
            print(f"    ⚠ Warning: Failed to generate metadata: {e}")
            return {
                "summary": "Conversation chunk",
                "mentioned_topics": [],
                "entities": []
            }
    
    async def _update_cumulative_summary(
        self,
        old_summary: str,
        new_turns: List[ConversationTurn]
    ) -> str:
        """
        Update cumulative summary with new turns using LLM.
        
        Args:
            old_summary: Previous cumulative summary
            new_turns: New turns to incorporate
            
        Returns:
            Updated cumulative summary
        """
        from memory.prompts import CUMULATIVE_SUMMARY_PROMPT
        
        # Format new turns
        new_turns_text = "\n".join([
            f"{turn.role}: {turn.content}" for turn in new_turns
        ])
        
        prompt = CUMULATIVE_SUMMARY_PROMPT.format(
            old_summary=old_summary or "No previous summary.",
            new_turns=new_turns_text
        )
        
        try:
            # Use chat completions with JSON mode
            summary_obj = self._call_llm_with_json(
                system_prompt="You are a conversation summarization assistant.",
                user_prompt=prompt,
                output_model=CumulativeSummaryOutput
            )
            
            if not summary_obj.summary.strip():
                print(f"    ⚠ Warning: Empty summary from LLM")
                return old_summary  # Fallback to old summary
            
            return summary_obj.summary.strip()
        except Exception as e:
            print(f"    ⚠ Warning: Failed to generate cumulative summary: {e}")
            return old_summary  # Fallback to old summary if LLM call fails
    
    async def _update_session_summary_async(self) -> None:
        """
        Update the session document with current cumulative summary.
        This runs asynchronously to avoid blocking the agent.
        """
        try:
            # Get existing session to preserve start_time
            existing = await self.database.get_by_id(
                container=ContainerType.SESSION_SUMMARIES,
                document_id=self.session_id,
                partition_key=self.user_id
            )
            start_time = existing.get("start_time") if existing else datetime.now(timezone.utc).isoformat()
            
            # Update session document in database
            session_update = {
                "id": self.session_id,
                "user_id": self.user_id,
                "start_time": start_time,  # Required NOT NULL field
                "cumulative_summary": self.cumulative_summary,
                "turn_count": len(self.turn_buffer),
                "updated_at": datetime.now(timezone.utc).isoformat()  # Use updated_at, not last_updated
            }
            
            await self.database.upsert(
                container=ContainerType.SESSION_SUMMARIES,
                document=session_update,
                partition_key=self.user_id
            )
        except Exception as e:
            print(f"  ⚠ Warning: Failed to update session summary: {e}")
    
    async def update_session_metadata(
        self,
        cumulative_summary: Optional[str] = None,
        turn_count: Optional[int] = None
    ) -> None:
        """
        Update session metadata in the database.
        Used by SessionPool during persistence.
        
        Args:
            cumulative_summary: Updated cumulative summary
            turn_count: Current number of turns
        """
        try:
            # First, check if session is already completed - don't overwrite!
            existing_doc = await self.database.get_by_id(
                container=ContainerType.SESSION_SUMMARIES,
                document_id=self.session_id,
                partition_key=self.user_id
            )
            
            if existing_doc and existing_doc.get("status") == "completed":
                print(f"  ℹ️ Skipping metadata update - session {self.session_id} already completed")
                return
            
            session_update = {
                "id": self.session_id,
                "user_id": self.user_id,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            
            if cumulative_summary is not None:
                session_update["cumulative_summary"] = cumulative_summary
            
            if turn_count is not None:
                session_update["turn_count"] = turn_count
            
            await self.database.upsert(
                container=ContainerType.SESSION_SUMMARIES,
                document=session_update,
                partition_key=self.user_id
            )
            
            print(
                f"  ✓ Updated session metadata: {self.session_id}, "
                f"turns={turn_count}, summary_len={len(cumulative_summary or '')}"
            )
        
        except Exception as e:
            print(f"  ⚠ Warning: Failed to update session metadata: {e}")
