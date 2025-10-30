"""
Generic Memory Service Client.

This is a simple HTTP client for the memory service that can be used
without Agent Framework. Useful for:
- Non-Python clients (any language that can make HTTP requests)
- Python applications not using Agent Framework
- Testing and debugging

Unlike RemoteMemoryProvider, this does NOT integrate with agent lifecycle.
You must explicitly call methods to manage sessions and memory.
"""

import httpx
from typing import Optional, Dict, Any, List
import uuid
import logging

logger = logging.getLogger(__name__)


class MemoryServiceClient:
    """
    Simple HTTP client for Agent Memory Service.
    
    Usage:
        # Create client
        client = MemoryServiceClient(
            service_url="http://localhost:8000",
            user_id="user123"
        )
        
        # Start session
        context = await client.start_session()
        print(f"Session ID: {client.session_id}")
        
        # Store turns manually
        await client.store_turn(
            user_message="What is a 401k?",
            agent_message="A 401k is a retirement savings plan..."
        )
        
        # Get context for next turn
        context = await client.get_context()
        # Inject context['formatted_context'] into your agent's prompt
        
        # End session
        await client.end_session()
    """
    
    def __init__(
        self,
        service_url: str,
        user_id: str,
        session_id: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialize memory service client.
        
        Args:
            service_url: Base URL of memory service (e.g., "http://localhost:8000")
            user_id: User identifier
            session_id: Session identifier (auto-generated if not provided)
            timeout: HTTP request timeout in seconds
        """
        self.service_url = service_url.rstrip("/")
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.timeout = timeout
        
        # HTTP client
        self.client = httpx.AsyncClient(timeout=self.timeout)
        
        logger.info(
            f"MemoryServiceClient initialized: user={user_id}, session={self.session_id}"
        )
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close HTTP client."""
        await self.client.aclose()
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    # ========================================================================
    # Session Management
    # ========================================================================
    
    async def start_session(self, restore: bool = True) -> Dict[str, Any]:
        """
        Start a new session or restore existing one.
        
        Args:
            restore: If True, attempt to restore session from CosmosDB
        
        Returns:
            Dictionary with initial session context:
            - session_id: Session identifier
            - active_context: Recent turns
            - cumulative_summary: Summary of earlier conversation
            - insights: Relevant user insights
            - session_summaries: Recent session summaries
            - formatted_context: Ready-to-inject context string
            - restored: Whether session was restored from CosmosDB
        """
        url = f"{self.service_url}/sessions/start"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "restore": restore
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            self.session_id = result["session_id"]  # Update in case it was auto-generated
            
            logger.info(
                f"Session started: {self.session_id} "
                f"(restored: {result.get('restored', False)})"
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to start session: {e}")
            raise RuntimeError(f"Failed to start memory session: {e}")
    
    async def end_session(self) -> Dict[str, str]:
        """
        End the current session and trigger reflection.
        
        This persists the session state and extracts insights.
        
        Returns:
            Dictionary with status message
        """
        url = f"{self.service_url}/sessions/end"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Session ended: {self.session_id}")
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to end session: {e}")
            raise RuntimeError(f"Failed to end memory session: {e}")
    
    # ========================================================================
    # Memory Operations
    # ========================================================================
    
    async def get_context(self) -> Dict[str, Any]:
        """
        Get current memory context for this session.
        
        Returns:
            Dictionary with context information:
            - active_context: List of recent turns
            - cumulative_summary: Summary of earlier conversation
            - insights: Relevant user insights
            - session_summaries: Recent session summaries
            - formatted_context: Ready-to-inject context string
        """
        url = f"{self.service_url}/memory/context"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to get context: {e}")
            raise RuntimeError(f"Failed to get memory context: {e}")
    
    async def store_turn(self, user_message: str, agent_message: str) -> Dict[str, str]:
        """
        Store a conversation turn in memory.
        
        Args:
            user_message: User's message
            agent_message: Agent's response
        
        Returns:
            Dictionary with status message
        """
        url = f"{self.service_url}/memory/store"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "user_message": user_message,
            "agent_message": agent_message
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"Turn stored: session={self.session_id}")
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to store turn: {e}")
            raise RuntimeError(f"Failed to store memory turn: {e}")
    
    async def retrieve_facts(self, query: str, top_k: int = 5) -> List[str]:
        """
        Retrieve contextual facts using semantic search.
        
        Args:
            query: Search query
            top_k: Number of facts to retrieve
        
        Returns:
            List of relevant facts
        """
        url = f"{self.service_url}/memory/retrieve"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "query": query,
            "top_k": top_k
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            return result.get("facts", [])
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to retrieve facts: {e}")
            raise RuntimeError(f"Failed to retrieve facts: {e}")
    
    # ========================================================================
    # Insights & Summaries
    # ========================================================================
    
    async def get_insights(self, recent_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get user insights (long-term learnings).
        
        Args:
            recent_only: If True, only return recent insights (last 30 days)
        
        Returns:
            List of insights with content, timestamp, and session_id
        """
        url = f"{self.service_url}/insights"
        payload = {
            "user_id": self.user_id,
            "recent_only": recent_only
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            return result.get("insights", [])
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to get insights: {e}")
            raise RuntimeError(f"Failed to get insights: {e}")
    
    async def get_summaries(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get session summaries for this user.
        
        Args:
            limit: Maximum number of summaries to retrieve
        
        Returns:
            List of session summaries with:
            - session_id
            - start_time
            - end_time
            - cumulative_summary
            - turn_count
        """
        url = f"{self.service_url}/summaries"
        payload = {
            "user_id": self.user_id,
            "limit": limit
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            return result.get("summaries", [])
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to get summaries: {e}")
            raise RuntimeError(f"Failed to get summaries: {e}")
    
    # ========================================================================
    # Health & Stats
    # ========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check if memory service is healthy.
        
        Returns:
            Health status dictionary
        """
        url = f"{self.service_url}/health"
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPError as e:
            logger.error(f"Health check failed: {e}")
            raise RuntimeError(f"Memory service health check failed: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get session pool statistics.
        
        Returns:
            Pool statistics with:
            - total_sessions
            - dirty_sessions
            - max_capacity
            - utilization
            - avg_age_seconds
            - oldest_age_seconds
        """
        url = f"{self.service_url}/stats"
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to get stats: {e}")
            raise RuntimeError(f"Failed to get service stats: {e}")
