"""
Current Memory Keeper for Agent Memory Service.

This module manages the active conversation context with:
- k-turn buffer before pruning
- N active turns in context
- Cumulative summary updates
- Session initialization with long-term insights
"""

import uuid
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from azure.cosmos import ContainerProxy
from openai import AzureOpenAI
from pydantic import BaseModel, Field

from memory.cosmos_utils import CosmosUtils
from memory.config import MemoryConfig
from memory.models import ConversationTurn, SessionInitContext


# Pydantic models for structured LLM outputs
class MetadataOutput(BaseModel):
    """Structured output for conversation metadata generation."""
    summary: str = Field(description="Concise 1-2 sentence summary of the conversation chunk")
    mentioned_topics: List[str] = Field(description="Key topics discussed (max 5)", max_length=5)
    entities: List[str] = Field(description="Specific entities mentioned (products, accounts, amounts, etc.)")


class KeyTopicsOutput(BaseModel):
    """Structured output for key topics extraction."""
    topics: List[str] = Field(description="3-5 key topics", min_length=1, max_length=5)


class CumulativeSummaryOutput(BaseModel):
    """Structured output for cumulative summary updates."""
    summary: str = Field(description="Updated cumulative summary incorporating new information (max 100 words)")


class CurrentMemoryKeeper:
    """
    Manages the active conversation memory with buffer-based pruning.
    
    Maintains:
    - Turn buffer (k turns before pruning)
    - Active turns (N most recent turns in context)
    - Cumulative summary (updated at each prune)
    - Session initialization block (loaded once at session start)
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        interactions_container: ContainerProxy,
        summaries_container: ContainerProxy,
        insights_container: ContainerProxy,
        chat_client: AzureOpenAI,
        cosmos_utils: CosmosUtils,
        config: MemoryConfig = None
    ):
        """
        Initialize the memory keeper.
        
        Args:
            user_id: User identifier
            session_id: Current session identifier
            interactions_container: CosmosDB interactions container
            summaries_container: CosmosDB session summaries container
            insights_container: CosmosDB insights container
            chat_client: Azure OpenAI client for chat completions
            cosmos_utils: CosmosDB utilities instance
            config: Configuration parameters
        """
        self.user_id = user_id
        self.session_id = session_id
        self.interactions_container = interactions_container
        self.summaries_container = summaries_container
        self.insights_container = insights_container
        self.chat_client = chat_client
        self.cosmos_utils = cosmos_utils
        self.config = config or MemoryConfig()
        
        # Buffer for turns before pruning
        self.turn_buffer: List[ConversationTurn] = []
        
        # Cumulative summary of conversation
        self.cumulative_summary: str = ""
        
        # Session initialization context (loaded once at start)
        self.session_init_context: Optional[SessionInitContext] = None
        
        # Track if session has started
        self.session_started = False
    
    async def initialize_session_context(self) -> SessionInitContext:
        """
        Load session initialization context at session start.
        
        Retrieves:
        1. Long-term insight for the user
        2. Recent session summaries (last N sessions)
        
        Returns:
            SessionInitContext with insights and recent summaries
        """
        print(f"[MemoryKeeper] Initializing session context for user: {self.user_id}")
        
        # Query recent insights (get top 3 most recent/important insights)
        insights_text = ""
        query = f"""
        SELECT TOP 3 c.insight_text, c.category, c.confidence, c.extracted_at
        FROM c
        WHERE c.user_id = @user_id
        ORDER BY c.extracted_at DESC
        """
        parameters = [{"name": "@user_id", "value": self.user_id}]
        
        results = self.cosmos_utils.query_documents(
            container=self.insights_container,
            query=query,
            parameters=parameters
        )
        
        longterm_insight = None
        if results:
            insights_list = [f"- {r['insight_text']}" for r in results]
            insights_text = "\n".join(insights_list)
            longterm_insight = insights_text
            print(f"  ✓ Loaded {len(results)} recent insights")
            for idx, insight in enumerate(results, 1):
                print(f"     {idx}. [{insight.get('category', 'N/A')}] {insight['insight_text'][:80]}...")
        else:
            print(f"  ℹ No insights found for user")
        
        # Query recent session summaries
        query = f"""
        SELECT TOP {self.config.NUM_RECENT_SESSIONS_FOR_INIT} 
               c.id, c.summary, c.end_time, c.key_topics, c.status
        FROM c
        WHERE c.user_id = @user_id AND c.status = 'completed'
        ORDER BY c.end_time DESC
        """
        
        results = self.cosmos_utils.query_documents(
            container=self.summaries_container,
            query=query,
            parameters=parameters
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
            timestamp=datetime.utcnow().isoformat()
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
            Dict with pruning info immediately (doesn't wait for CosmosDB)
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
        import asyncio
        asyncio.create_task(self._update_session_summary_async())
        
        # Prune buffer immediately (don't wait for CosmosDB)
        self.turn_buffer = self.turn_buffer[self.config.K_TURN_BUFFER:]
        
        print(f"  ✓ Pruned buffer. Remaining turns: {len(self.turn_buffer)}")
        
        # Launch async task to process and store interaction (non-blocking)
        asyncio.create_task(self._process_interaction_async(turns_to_prune))
        
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
        - CosmosDB storage
        """
        try:
            # Flatten turns into conversation text
            conversation_text = "\n".join([
                f"{turn.role}: {turn.content}" for turn in turns
            ])
            
            # Generate metadata using GPT-4o-mini
            metadata = await self._generate_metadata(conversation_text)
            
            # Generate embeddings
            content_embedding = self.cosmos_utils.get_embedding(conversation_text)
            summary_embedding = self.cosmos_utils.get_embedding(metadata["summary"])
            
            # Create interaction document
            interaction_doc = {
                "id": str(uuid.uuid4()),
                "user_id": self.user_id,
                "session_id": self.session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "content": conversation_text,
                "content_vector": content_embedding,
                "summary": metadata["summary"],
                "summary_vector": summary_embedding,
                "metadata": {
                    "mentioned_topics": metadata["mentioned_topics"],
                    "entities": metadata["entities"]
                }
            }
            
            # Store in CosmosDB
            result = self.cosmos_utils.upsert_document(
                container=self.interactions_container,
                document=interaction_doc
            )
            
            print(f"  ✓ [Background] Interaction document stored: {result['id']}")
            print(f"    Topics: {metadata['mentioned_topics']}")
            
        except Exception as e:
            print(f"  ✗ [Background] Error processing interaction: {e}")
    
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
        content_embedding = self.cosmos_utils.get_embedding(conversation_text)
        summary_embedding = self.cosmos_utils.get_embedding(metadata["summary"])
        
        # Create interaction document
        interaction_doc = {
            "id": str(uuid.uuid4()),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "content": conversation_text,
            "content_vector": content_embedding,
            "summary": metadata["summary"],
            "summary_vector": summary_embedding,
            "metadata": {
                "mentioned_topics": metadata["mentioned_topics"],
                "entities": metadata["entities"]
            }
        }
        
        # Store in CosmosDB
        result = self.cosmos_utils.upsert_document(
            container=self.interactions_container,
            document=interaction_doc
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
    

    
    def get_current_context(self) -> str:
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
            init_block = self._format_session_init_block()
            context_parts.append(init_block)
        
        # Add cumulative summary
        if self.cumulative_summary:
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
    
    def _format_session_init_block(self) -> str:
        """Format the session initialization block."""
        if not self.session_init_context:
            return ""
        
        parts = ["<session_initialization>"]
        
        # Add long-term insight
        if self.session_init_context.longterm_insight:
            parts.append("### Key Insights")
            parts.append(self.session_init_context.longterm_insight)
            parts.append("")
        
        # Add recent session summaries
        if self.session_init_context.recent_summaries:
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
        Generate metadata for conversation chunk using GPT-4o-mini with structured output.
        
        Returns:
            Dict with summary, mentioned_topics, entities
        """
        from memory.prompts import METADATA_GENERATION_PROMPT
        
        prompt = METADATA_GENERATION_PROMPT.format(conversation_content=conversation_text)
        
        # Use structured output with Pydantic model
        response = self.chat_client.responses.parse(
            model=self.config.MINI_DEPLOYMENT,
            input=[
                {"role": "system", "content": "You are a metadata extraction assistant."},
                {"role": "user", "content": prompt}
            ],
            text_format=MetadataOutput
        )
        
        # Parse structured output
        metadata_obj = response.output_parsed
        if metadata_obj is None:
            # Fallback if parsing fails
            print(f"    ⚠ Warning: Failed to parse metadata, using defaults")
            return {
                "summary": "Conversation chunk",
                "mentioned_topics": [],
                "entities": []
            }
        
        return {
            "summary": metadata_obj.summary,
            "mentioned_topics": metadata_obj.mentioned_topics,
            "entities": metadata_obj.entities
        }
    
    async def _update_cumulative_summary(
        self,
        old_summary: str,
        new_turns: List[ConversationTurn]
    ) -> str:
        """
        Update cumulative summary with new turns using GPT-4o-mini.
        
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
        
        # Use structured output
        print("self.config.MINI_DEPLOYMENT ", self.config.MINI_DEPLOYMENT)
        response = self.chat_client.responses.parse(
            model=self.config.MINI_DEPLOYMENT,
            input=[
                {"role": "system", "content": "You are a conversation summarization assistant."},
                {"role": "user", "content": prompt}
            ],
            text_format=CumulativeSummaryOutput
        )
        
        summary_obj = response.output_parsed
        if summary_obj is None or not summary_obj.summary.strip():
            print(f"    ⚠ Warning: Empty response from LLM for cumulative summary")
            return old_summary  # Fallback to old summary if LLM returns nothing
        
        return summary_obj.summary.strip()
    
    async def _update_session_summary_async(self) -> None:
        """
        Update the session document with current cumulative summary.
        This runs asynchronously to avoid blocking the agent.
        """
        try:
            # Update session document in CosmosDB
            session_update = {
                "id": self.session_id,
                "user_id": self.user_id,
                "cumulative_summary": self.cumulative_summary,
                "turn_count": len(self.turn_buffer),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Patch update (merge with existing document)
            self.cosmos_utils.upsert_document(
                container=self.summaries_container,
                document=session_update
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
            # First, check if session is already completed - don't overwrite completed sessions!
            existing_doc = None
            try:
                existing_doc = self.summaries_container.read_item(
                    item=self.session_id,
                    partition_key=self.user_id
                )
                if existing_doc.get("status") == "completed":
                    print(f"  ℹ️ Skipping metadata update - session {self.session_id} already completed")
                    return
            except:
                pass  # Document doesn't exist yet, proceed with update
            
            session_update = {
                "id": self.session_id,
                "user_id": self.user_id,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            if cumulative_summary is not None:
                session_update["cumulative_summary"] = cumulative_summary
            
            if turn_count is not None:
                session_update["turn_count"] = turn_count
            
            self.cosmos_utils.upsert_document(
                container=self.summaries_container,
                document=session_update
            )
            
            print(
                f"  ✓ Updated session metadata: {self.session_id}, "
                f"turns={turn_count}, summary_len={len(cumulative_summary or '')}"
            )
        
        except Exception as e:
            print(f"  ⚠ Warning: Failed to update session metadata: {e}")
