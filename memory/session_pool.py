"""
Session Pool - In-Memory Session State Management.

Provides high-performance session caching with:
- LRU eviction based on TTL and capacity
- Shared resource pooling (CosmosDB, OpenAI clients)
- Automatic session persistence on eviction
- Zero-latency session restoration for hot sessions
"""

import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from collections import OrderedDict
import logging

from memory.orchestrator import MemoryServiceOrchestrator
from memory.config import MemoryConfig
from memory.cosmos_utils import CosmosUtils
from azure.cosmos import ContainerProxy
from openai import AzureOpenAI

logger = logging.getLogger(__name__)


class SessionState:
    """
    Represents an active session in memory.
    
    Attributes:
        orchestrator: The memory orchestrator for this session
        last_accessed: Last access timestamp for LRU eviction
        user_id: User identifier
        session_id: Session identifier
        dirty: Whether session has unsaved changes
    """
    
    def __init__(
        self,
        orchestrator: MemoryServiceOrchestrator,
        user_id: str,
        session_id: str
    ):
        self.orchestrator = orchestrator
        self.user_id = user_id
        self.session_id = session_id
        self.last_accessed = datetime.utcnow()
        self.dirty = False  # Track if session needs persistence
    
    def touch(self):
        """Update last accessed time (for LRU)."""
        self.last_accessed = datetime.utcnow()
    
    def mark_dirty(self):
        """Mark session as having unsaved changes."""
        self.dirty = True
    
    def mark_clean(self):
        """Mark session as fully persisted."""
        self.dirty = False


class SessionPool:
    """
    In-memory session pool with LRU eviction.
    
    Provides:
    - Fast session lookup (0ms vs 100ms CosmosDB query)
    - Shared resource management (single CosmosDB/OpenAI clients)
    - Automatic eviction based on TTL and capacity
    - Graceful session persistence on eviction
    
    Usage:
        pool = SessionPool(
            config=config,
            cosmos_utils=cosmos_utils,
            containers=containers,
            chat_client=chat_client,
            max_sessions=1000,
            session_ttl_minutes=30
        )
        
        # Get or create session (0ms if hot, 100ms if cold restore)
        session = await pool.get_or_create(user_id, session_id)
        
        # Use session
        await session.orchestrator.process_turn(user_msg, agent_msg)
        session.mark_dirty()  # Track changes
        
        # Automatic eviction handles persistence
        await pool.evict_stale_sessions()
    """
    
    def __init__(
        self,
        config: MemoryConfig,
        cosmos_utils: CosmosUtils,
        interactions_container: ContainerProxy,
        summaries_container: ContainerProxy,
        insights_container: ContainerProxy,
        chat_client: AzureOpenAI,
        max_sessions: int = 1000,
        session_ttl_minutes: int = 30
    ):
        """
        Initialize session pool with shared resources.
        
        Args:
            config: Memory configuration
            cosmos_utils: Shared CosmosDB utilities (with embeddings)
            interactions_container: Interactions container
            summaries_container: Session summaries container
            insights_container: Insights container
            chat_client: Shared Azure OpenAI client
            max_sessions: Maximum sessions to keep in memory
            session_ttl_minutes: Minutes before session is eligible for eviction
        """
        self.config = config
        self.cosmos_utils = cosmos_utils
        self.interactions_container = interactions_container
        self.summaries_container = summaries_container
        self.insights_container = insights_container
        self.chat_client = chat_client
        
        self.max_sessions = max_sessions
        self.session_ttl = timedelta(minutes=session_ttl_minutes)
        
        # LRU cache: {(user_id, session_id): SessionState}
        self.sessions: OrderedDict[tuple[str, str], SessionState] = OrderedDict()
        
        logger.info(
            f"SessionPool initialized: max_sessions={max_sessions}, "
            f"ttl={session_ttl_minutes}min"
        )
    
    def _make_key(self, user_id: str, session_id: str) -> tuple[str, str]:
        """Create cache key from user_id and session_id."""
        return (user_id, session_id)
    
    async def get_or_create(
        self,
        user_id: str,
        session_id: str,
        restore: bool = True
    ) -> SessionState:
        """
        Get existing session from pool or create new one.
        
        Performance:
        - Hot session (in pool): ~0ms (memory lookup)
        - Cold session (restore): ~100ms (CosmosDB query)
        - New session: ~50ms (CosmosDB upsert)
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            restore: If True, attempt to restore from CosmosDB if not in pool
        
        Returns:
            SessionState: Active session ready for use
        """
        key = self._make_key(user_id, session_id)
        
        # Hot path: Session already in pool
        if key in self.sessions:
            session_state = self.sessions[key]
            session_state.touch()  # Update LRU
            self.sessions.move_to_end(key)  # Move to end of OrderedDict (most recent)
            logger.debug(f"✓ Hot session: {user_id}/{session_id} (0ms)")
            return session_state
        
        # Cold path: Create or restore session
        orchestrator = MemoryServiceOrchestrator(
            user_id=user_id,
            session_id=session_id,
            config=self.config,
            cosmos_utils=self.cosmos_utils,
            interactions_container=self.interactions_container,
            summaries_container=self.summaries_container,
            insights_container=self.insights_container,
            chat_client=self.chat_client
        )
        
        # Attempt restoration if requested
        if restore:
            try:
                await orchestrator.restore_session(session_id)
                logger.info(f"✓ Cold session restored: {user_id}/{session_id} (~100ms)")
            except ValueError as e:
                # Session not found or inactive, initialize as new
                logger.info(f"Session not found, creating new: {e}")
                await orchestrator.initialize_session()
        else:
            # Create brand new session
            await orchestrator.initialize_session()
            logger.info(f"✓ New session created: {user_id}/{session_id} (~50ms)")
        
        # Add to pool
        session_state = SessionState(orchestrator, user_id, session_id)
        self.sessions[key] = session_state
        self.sessions.move_to_end(key)
        
        # Evict if over capacity
        await self._evict_if_needed()
        
        return session_state
    
    async def remove(self, user_id: str, session_id: str, persist: bool = True):
        """
        Remove session from pool (typically called on explicit session end).
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            persist: If True, persist session state before removal
        """
        key = self._make_key(user_id, session_id)
        
        if key not in self.sessions:
            logger.warning(f"Session not in pool: {user_id}/{session_id}")
            return
        
        session_state = self.sessions[key]
        
        # Persist if dirty
        if persist and session_state.dirty:
            await self._persist_session(session_state)
        
        # Remove from pool
        del self.sessions[key]
        logger.info(f"Session removed from pool: {user_id}/{session_id}")
    
    async def evict_stale_sessions(self):
        """
        Evict sessions that haven't been accessed within TTL.
        
        This should be called periodically (e.g., every minute) via background task.
        """
        now = datetime.utcnow()
        to_evict = []
        
        # Find stale sessions
        for key, session_state in self.sessions.items():
            age = now - session_state.last_accessed
            if age > self.session_ttl:
                to_evict.append(key)
        
        # Evict stale sessions
        for key in to_evict:
            user_id, session_id = key
            session_state = self.sessions[key]
            
            # Persist if dirty
            if session_state.dirty:
                await self._persist_session(session_state)
            
            del self.sessions[key]
            logger.info(f"Evicted stale session: {user_id}/{session_id} (age: {age})")
        
        if to_evict:
            logger.info(f"Evicted {len(to_evict)} stale sessions")
    
    async def _evict_if_needed(self):
        """Evict oldest session if pool is at capacity (LRU eviction)."""
        if len(self.sessions) <= self.max_sessions:
            return
        
        # Remove oldest (first in OrderedDict)
        key, session_state = self.sessions.popitem(last=False)
        user_id, session_id = key
        
        # Persist if dirty
        if session_state.dirty:
            await self._persist_session(session_state)
        
        logger.info(
            f"Evicted LRU session: {user_id}/{session_id} "
            f"(pool size: {len(self.sessions) + 1} -> {len(self.sessions)})"
        )
    
    async def _persist_session(self, session_state: SessionState):
        """
        Persist session state to CosmosDB.
        
        Updates session metadata in summaries container:
        - cumulative_summary
        - turn_count
        - last_updated
        """
        orchestrator = session_state.orchestrator
        
        # Update session metadata
        await orchestrator.memory_keeper.update_session_metadata(
            cumulative_summary=orchestrator.memory_keeper.cumulative_summary,
            turn_count=len(orchestrator.memory_keeper.turn_buffer)
        )
        
        session_state.mark_clean()
        logger.debug(
            f"Persisted session: {session_state.user_id}/{session_state.session_id}"
        )
    
    async def shutdown(self):
        """
        Gracefully shutdown pool by persisting all dirty sessions.
        
        Should be called on server shutdown.
        """
        logger.info(f"Shutting down session pool ({len(self.sessions)} sessions)...")
        
        persist_tasks = []
        for session_state in self.sessions.values():
            if session_state.dirty:
                persist_tasks.append(self._persist_session(session_state))
        
        if persist_tasks:
            await asyncio.gather(*persist_tasks)
            logger.info(f"Persisted {len(persist_tasks)} dirty sessions")
        
        self.sessions.clear()
        logger.info("Session pool shutdown complete")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get pool statistics for monitoring.
        
        Returns:
            Dictionary with pool metrics
        """
        now = datetime.utcnow()
        dirty_count = sum(1 for s in self.sessions.values() if s.dirty)
        
        ages = [
            (now - s.last_accessed).total_seconds()
            for s in self.sessions.values()
        ]
        
        return {
            "total_sessions": len(self.sessions),
            "dirty_sessions": dirty_count,
            "max_capacity": self.max_sessions,
            "utilization": len(self.sessions) / self.max_sessions,
            "ttl_seconds": self.session_ttl.total_seconds(),
            "avg_age_seconds": sum(ages) / len(ages) if ages else 0,
            "oldest_age_seconds": max(ages) if ages else 0
        }
