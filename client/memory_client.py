"""
Memory Service Client.

HTTP client for the Agent Memory Service API. Works with any language
that can make HTTP requests. For Python apps, provides async interface.

The client manages sessions and memory operations via REST API:
- Session lifecycle (start, end)
- Turn storage (user + assistant messages)
- Context retrieval
- Memory search
- Insights and session history
"""

import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import uuid
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """Context returned when starting or getting session state."""
    session_id: str
    user_id: str
    context: str
    turn_count: int = 0
    insights_loaded: bool = False
    recent_sessions_count: int = 0


@dataclass 
class TurnResult:
    """Result from storing a conversation turn."""
    success: bool
    turn_count: int
    pruning_triggered: bool = False


@dataclass
class EndSessionResult:
    """Result from ending a session."""
    success: bool
    summary: str
    insights_count: int
    synthesis_triggered: bool = False


class MemoryServiceClient:
    """
    HTTP client for Agent Memory Service.
    
    Usage:
        async with MemoryServiceClient("http://localhost:8000", "user123") as client:
            # Start session - get initial context
            ctx = await client.start_session()
            print(f"Session: {ctx.session_id}")
            print(f"Context: {ctx.context}")
            
            # Your agent handles the conversation...
            user_msg = "What is a 401k?"
            assistant_msg = your_agent.respond(user_msg, context=ctx.context)
            
            # Store the turn
            result = await client.store_turn(user_msg, assistant_msg)
            
            # Get updated context for next turn
            ctx = await client.get_context()
            
            # End session (triggers reflection/synthesis)
            end = await client.end_session()
            print(f"Insights extracted: {end.insights_count}")
    """
    
    def __init__(
        self,
        service_url: str,
        user_id: str,
        session_id: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize memory service client.
        
        Args:
            service_url: Base URL of memory service (e.g., "http://localhost:8000")
            user_id: User identifier
            session_id: Optional session ID (auto-generated if not provided)
            timeout: HTTP request timeout in seconds
        """
        self.service_url = service_url.rstrip("/")
        self.user_id = user_id
        self.session_id = session_id
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(f"MemoryServiceClient initialized: user={user_id}")
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close HTTP client."""
        await self.close()
    
    async def close(self):
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    # ========================================================================
    # Health Check
    # ========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check if memory service is healthy.
        
        Returns:
            Health status with active_sessions and uptime_seconds
        """
        response = await self.client.get(f"{self.service_url}/health")
        response.raise_for_status()
        return response.json()
    
    # ========================================================================
    # Session Management
    # ========================================================================
    
    async def start_session(self, restore: bool = False) -> SessionContext:
        """
        Start a new session or restore existing one.
        
        Args:
            restore: If True, attempt to restore previous session state
        
        Returns:
            SessionContext with initial context for prompt injection
        """
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "restore": restore
        }
        
        response = await self.client.post(
            f"{self.service_url}/sessions/start",
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        self.session_id = data["session_id"]
        
        logger.info(f"Session started: {self.session_id}")
        
        return SessionContext(
            session_id=data["session_id"],
            user_id=data["user_id"],
            context=data["context"],
            insights_loaded=data.get("insights_loaded", False),
            recent_sessions_count=data.get("recent_sessions_count", 0)
        )
    
    async def get_context(self) -> SessionContext:
        """
        Get current session context for prompt injection.
        
        Returns:
            SessionContext with current context and turn count
        """
        if not self.session_id:
            raise RuntimeError("No active session. Call start_session() first.")
        
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id
        }
        
        response = await self.client.post(
            f"{self.service_url}/sessions/context",
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        return SessionContext(
            session_id=self.session_id,
            user_id=self.user_id,
            context=data["context"],
            turn_count=data.get("turn_count", 0)
        )
    
    async def store_turn(
        self, 
        user_message: str, 
        assistant_message: str
    ) -> TurnResult:
        """
        Store a conversation turn (user message + assistant response).
        
        Args:
            user_message: User's message
            assistant_message: Assistant's response
        
        Returns:
            TurnResult with turn count and pruning status
        """
        if not self.session_id:
            raise RuntimeError("No active session. Call start_session() first.")
        
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "user_message": user_message,
            "assistant_message": assistant_message
        }
        
        response = await self.client.post(
            f"{self.service_url}/sessions/turn",
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        logger.debug(f"Turn stored: session={self.session_id}")
        
        return TurnResult(
            success=data["success"],
            turn_count=data["turn_count"],
            pruning_triggered=data.get("pruning_triggered", False)
        )
    
    async def end_session(self, trigger_reflection: bool = True) -> EndSessionResult:
        """
        End the current session.
        
        This triggers reflection (insight extraction) and long-term synthesis.
        
        Args:
            trigger_reflection: Whether to extract insights (default: True)
        
        Returns:
            EndSessionResult with summary and insights count
        """
        if not self.session_id:
            raise RuntimeError("No active session. Call start_session() first.")
        
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "trigger_reflection": trigger_reflection
        }
        
        response = await self.client.post(
            f"{self.service_url}/sessions/end",
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"Session ended: {self.session_id}")
        
        # Clear session ID after ending
        self.session_id = None
        
        return EndSessionResult(
            success=data["success"],
            summary=data.get("summary", ""),
            insights_count=data.get("insights_count", 0),
            synthesis_triggered=data.get("synthesis_triggered", False)
        )
    
    # ========================================================================
    # Memory Search
    # ========================================================================
    
    async def search(
        self, 
        query: str, 
        top_k: int = 5,
        search_interactions: bool = True,
        search_insights: bool = True,
        search_summaries: bool = False
    ) -> str:
        """
        Search memory for relevant information.
        
        Args:
            query: Search query
            top_k: Number of results to retrieve
            search_interactions: Search past conversation chunks
            search_insights: Search long-term insights
            search_summaries: Search session summaries
        
        Returns:
            Formatted search results string
        """
        payload = {
            "user_id": self.user_id,
            "query": query,
            "top_k": top_k,
            "search_interactions": search_interactions,
            "search_insights": search_insights,
            "search_summaries": search_summaries
        }
        
        response = await self.client.post(
            f"{self.service_url}/search",
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("results", "")
    
    # ========================================================================
    # User Data
    # ========================================================================
    
    async def get_insights(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get long-term insights for this user.
        
        Args:
            limit: Maximum number of insights to retrieve
        
        Returns:
            List of insight dictionaries
        """
        response = await self.client.get(
            f"{self.service_url}/users/{self.user_id}/insights",
            params={"limit": limit}
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("insights", [])
    
    async def get_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent sessions for this user.
        
        Args:
            limit: Maximum number of sessions to retrieve
        
        Returns:
            List of session dictionaries
        """
        response = await self.client.get(
            f"{self.service_url}/users/{self.user_id}/sessions",
            params={"limit": limit}
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("sessions", [])
