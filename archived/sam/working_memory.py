"""
SAM Working Memory

In-memory buffer for active conversation turns.
Manages the flush cycle to Episodes and maintains active context.

This is the component that stays in-memory and unstructured,
as requested from the current implementation.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
import tiktoken

from sam.config import SAMConfig
from sam.models.graph import Episode, EpisodeCreate
from sam.stores.base import MemoryStore


class ConversationTurn(BaseModel):
    """A single conversation turn in the working memory buffer."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkingMemoryState(BaseModel):
    """Serializable state of working memory for persistence/restoration."""
    tenant_id: str
    turn_buffer: List[ConversationTurn] = Field(default_factory=list)
    cumulative_summary: str = ""
    current_episode_id: Optional[str] = None
    total_tokens_flushed: int = 0


class WorkingMemory:
    """
    In-memory buffer for active conversation turns.
    
    Lifecycle:
    1. Turns are added to the buffer via add_turn()
    2. When buffer reaches buffer_size, flush() is called
    3. Flushed content is appended to the current open Episode
    4. If Episode exceeds max_episode_tokens, a new Episode is started
    5. Active turns (last N) are kept for immediate context
    
    This replaces CurrentMemoryKeeper from the old implementation,
    keeping the good patterns:
    - In-memory buffer (unstructured)
    - Cumulative summary
    - Active turns window
    """
    
    def __init__(
        self,
        store: MemoryStore,
        tenant_id: str,
        config: Optional[SAMConfig] = None
    ):
        """
        Initialize working memory.
        
        Args:
            store: MemoryStore backend
            tenant_id: Tenant/user isolation
            config: SAM configuration
        """
        self.store = store
        self.tenant_id = tenant_id
        self.config = config or SAMConfig()
        
        # Buffer state
        self.turn_buffer: List[ConversationTurn] = []
        self.cumulative_summary: str = ""
        self.current_episode_id: Optional[str] = None
        
        # Token counting
        try:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._tokenizer = None
        
        # Track flushed tokens for Episode size checking
        self.total_tokens_flushed: int = 0
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        # Fallback: rough estimate
        return len(text) // 4
    
    async def initialize(self) -> None:
        """
        Initialize working memory, loading or creating current Episode.
        """
        # Check for existing open Episode
        episode = await self.store.get_open_episode(self.tenant_id)
        
        if episode:
            self.current_episode_id = episode.id
            self.total_tokens_flushed = episode.token_count
            print(f"[WorkingMemory] Restored open Episode: {episode.id} ({episode.token_count} tokens)")
        else:
            # Create new Episode
            episode = await self.store.create_episode(EpisodeCreate(
                tenant_id=self.tenant_id,
                source="chat"
            ))
            self.current_episode_id = episode.id
            self.total_tokens_flushed = 0
            print(f"[WorkingMemory] Created new Episode: {episode.id}")
    
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
            timestamp=datetime.utcnow()
        )
        self.turn_buffer.append(turn)
        print(f"[WorkingMemory] Added {role} turn. Buffer: {len(self.turn_buffer)}/{self.config.buffer_size}")
    
    async def maybe_flush(self) -> Optional[Dict[str, Any]]:
        """
        Check if buffer should be flushed and flush if needed.
        
        Returns:
            Flush result dict if flushed, None otherwise
        """
        if len(self.turn_buffer) < self.config.buffer_size:
            return None
        
        return await self.flush()
    
    async def flush(self) -> Dict[str, Any]:
        """
        Flush buffer to the current Episode.
        
        Process:
        1. Format turns into content string
        2. Append to current Episode
        3. Check if Episode exceeds size limit
        4. If so, close Episode and create new one
        5. Clear flushed turns from buffer (keep active_turns)
        
        Returns:
            Dict with flush details
        """
        if not self.turn_buffer:
            return {"turns_flushed": 0, "message": "Buffer empty"}
        
        # Ensure we have an Episode
        if not self.current_episode_id:
            await self.initialize()
        
        # Get turns to flush
        turns_to_flush = self.turn_buffer[:self.config.buffer_size]
        
        # Format turns into content
        content = self._format_turns(turns_to_flush)
        token_count = self._count_tokens(content)
        
        print(f"[WorkingMemory] Flushing {len(turns_to_flush)} turns ({token_count} tokens)")
        
        # Append to Episode
        try:
            episode = await self.store.append_to_episode(
                episode_id=self.current_episode_id,
                tenant_id=self.tenant_id,
                content=content,
                token_count=token_count,
                turn_count=len(turns_to_flush)
            )
            self.total_tokens_flushed = episode.token_count
        except ValueError as e:
            # Episode might be closed, create new one
            print(f"[WorkingMemory] Episode error: {e}, creating new Episode")
            new_episode = await self.store.create_episode(EpisodeCreate(
                tenant_id=self.tenant_id,
                source="chat"
            ))
            self.current_episode_id = new_episode.id
            self.total_tokens_flushed = 0
            
            episode = await self.store.append_to_episode(
                episode_id=self.current_episode_id,
                tenant_id=self.tenant_id,
                content=content,
                token_count=token_count,
                turn_count=len(turns_to_flush)
            )
            self.total_tokens_flushed = episode.token_count
        
        # Check if Episode exceeds size limit
        episode_closed = False
        if self.total_tokens_flushed >= self.config.max_episode_tokens:
            print(f"[WorkingMemory] Episode exceeded {self.config.max_episode_tokens} tokens, closing")
            await self._close_current_episode()
            episode_closed = True
        
        # Clear flushed turns, keep remaining
        self.turn_buffer = self.turn_buffer[len(turns_to_flush):]
        
        result = {
            "turns_flushed": len(turns_to_flush),
            "tokens_flushed": token_count,
            "episode_id": self.current_episode_id,
            "episode_token_count": self.total_tokens_flushed,
            "episode_closed": episode_closed,
            "buffer_remaining": len(self.turn_buffer)
        }
        
        print(f"[WorkingMemory] Flush complete: {result}")
        return result
    
    async def flush_all(self) -> Dict[str, Any]:
        """
        Flush all remaining turns (called at end of session).
        
        Returns:
            Dict with flush details
        """
        if not self.turn_buffer:
            return {"turns_flushed": 0, "message": "Buffer empty"}
        
        # Temporarily set buffer_size to current buffer length
        original_buffer_size = self.config.buffer_size
        self.config.buffer_size = len(self.turn_buffer)
        
        result = await self.flush()
        
        # Restore original buffer size
        self.config.buffer_size = original_buffer_size
        
        return result
    
    async def _close_current_episode(self) -> None:
        """Close current Episode and create a new one."""
        if self.current_episode_id:
            # Close without summary for now (summary generation happens separately)
            await self.store.close_episode(
                episode_id=self.current_episode_id,
                tenant_id=self.tenant_id
            )
            print(f"[WorkingMemory] Closed Episode: {self.current_episode_id}")
        
        # Create new Episode
        new_episode = await self.store.create_episode(EpisodeCreate(
            tenant_id=self.tenant_id,
            source="chat"
        ))
        self.current_episode_id = new_episode.id
        self.total_tokens_flushed = 0
        print(f"[WorkingMemory] Created new Episode: {new_episode.id}")
    
    def _format_turns(self, turns: List[ConversationTurn]) -> str:
        """Format turns into a content string."""
        lines = []
        for turn in turns:
            lines.append(f"{turn.role}: {turn.content}")
        return "\n".join(lines)
    
    def get_active_turns(self) -> List[ConversationTurn]:
        """Get the most recent N turns for active context."""
        return self.turn_buffer[-self.config.active_turns:]
    
    def get_active_context(self) -> str:
        """Get formatted active context (recent turns only)."""
        active = self.get_active_turns()
        if not active:
            return ""
        
        lines = ["### Active Conversation"]
        for turn in active:
            lines.append(f"{turn.role}: {turn.content}")
        
        return "\n".join(lines)
    
    def get_full_context(self) -> str:
        """
        Get full formatted context including:
        - Cumulative summary (if any)
        - Active turns
        """
        parts = []
        
        if self.cumulative_summary:
            parts.append("### Conversation Summary")
            parts.append(self.cumulative_summary)
            parts.append("")
        
        active_context = self.get_active_context()
        if active_context:
            parts.append(active_context)
        
        return "\n".join(parts)
    
    def update_cumulative_summary(self, summary: str) -> None:
        """Update the cumulative summary."""
        self.cumulative_summary = summary
    
    def get_state(self) -> WorkingMemoryState:
        """Get serializable state for persistence."""
        return WorkingMemoryState(
            tenant_id=self.tenant_id,
            turn_buffer=self.turn_buffer.copy(),
            cumulative_summary=self.cumulative_summary,
            current_episode_id=self.current_episode_id,
            total_tokens_flushed=self.total_tokens_flushed
        )
    
    def restore_state(self, state: WorkingMemoryState) -> None:
        """Restore from serialized state."""
        self.tenant_id = state.tenant_id
        self.turn_buffer = state.turn_buffer.copy()
        self.cumulative_summary = state.cumulative_summary
        self.current_episode_id = state.current_episode_id
        self.total_tokens_flushed = state.total_tokens_flushed
    
    async def close(self) -> Dict[str, Any]:
        """
        Close working memory (end of session).
        
        Flushes any remaining turns and closes the current Episode.
        """
        result = {"turns_flushed": 0, "episode_closed": False}
        
        # Flush remaining turns
        if self.turn_buffer:
            flush_result = await self.flush_all()
            result["turns_flushed"] = flush_result.get("turns_flushed", 0)
        
        # Close current Episode
        if self.current_episode_id:
            await self.store.close_episode(
                episode_id=self.current_episode_id,
                tenant_id=self.tenant_id
            )
            result["episode_closed"] = True
            result["episode_id"] = self.current_episode_id
        
        return result
