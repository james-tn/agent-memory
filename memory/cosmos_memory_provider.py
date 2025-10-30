"""
CosmosMemoryProvider - Agent Framework Integration with Remote Memory Service.

This provider integrates the remote memory service with Microsoft's Agent Framework.
It implements the ContextProvider interface to provide memory context at appropriate
lifecycle points (invoking, invoked, thread_created).

The provider handles:
- Automatic session management (start/end)
- Context injection before agent invocation
- Turn storage after agent response
- HTTP communication with memory service
"""

import httpx
from typing import Optional, Dict, Any, List
import uuid
import logging
import asyncio

# Agent Framework imports
from agent_framework import ChatMessage, Context, ContextProvider, Role

logger = logging.getLogger(__name__)


class CosmosMemoryProvider(ContextProvider):
    """
    CosmosDB Memory Context Provider for Agent Framework (Remote Service Version).
    
    This provider communicates with a remote memory service that manages CosmosDB
    interactions, providing high-performance session pooling and shared resources.
    
    Usage:
        # Create provider
        memory_provider = CosmosMemoryProvider(
            service_url="http://localhost:8000",
            user_id="user123",
            session_id="optional-session-id",  # Auto-generated if not provided
            auto_manage_session=True  # Automatically start/end sessions
        )
        
        # Use with Agent Framework
        agent = ChatAgent(
            model="gpt-5-nano",
            context_providers=[memory_provider]
        )
        
        # Multi-turn conversation
        response1 = await agent.run("Tell me about 401k plans")
        response2 = await agent.run("What are the contribution limits?")
        
        # Session automatically ended when auto_manage_session=True
        # or call explicitly:
        await memory_provider.end_session()
    """
    
    def __init__(
        self,
        service_url: str,
        user_id: str,
        session_id: Optional[str] = None,
        auto_manage_session: bool = True,
        timeout: float = 30.0
    ):
        """
        Initialize CosmosDB memory provider (remote service version).
        
        Args:
            service_url: Base URL of memory service (e.g., "http://localhost:8000")
            user_id: User identifier
            session_id: Session identifier (auto-generated if not provided)
            auto_manage_session: If True, automatically start session on first call
                                and end on explicit call to end_session()
            timeout: HTTP request timeout in seconds
        """
        self.service_url = service_url.rstrip("/")
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.auto_manage_session = auto_manage_session
        self.timeout = timeout
        
        # Session state
        self.session_started = False
        self.session_ended = False
        
        # HTTP client - keep reference but don't rely on single instance
        self._client: Optional[httpx.AsyncClient] = None
        
        # Cache for last user message (needed for storing turn)
        self.last_user_message: Optional[str] = None
        
        # Track pending store operations to ensure they complete before session ends
        self._pending_stores: List[Any] = []  # List of asyncio.Task objects
        
        logger.info(
            f"CosmosMemoryProvider initialized: user={user_id}, "
            f"session={self.session_id}, auto_manage={auto_manage_session}"
        )
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - end session if auto-managed and close HTTP client."""
        if self.auto_manage_session and self.session_started and not self.session_ended:
            try:
                await self.end_session()
            except Exception as e:
                logger.warning(f"Failed to end session during context exit: {e}")
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
    
    async def close(self):
        """Close HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
    
    # ========================================================================
    # ContextProvider Interface (Agent Framework)
    # ========================================================================
    
    async def invoking(
        self, 
        messages: ChatMessage | list[ChatMessage],
        **kwargs: Any
    ) -> Context:
        """
        Called BEFORE agent invocation.
        
        This is where we:
        1. Start session (if auto_manage_session and not started)
        2. Get memory context
        3. Inject context into agent's system prompt
        
        Args:
            messages: Input messages to the AI
            **kwargs: Additional arguments
        
        Returns:
            Context with memory as instructions
        """
        # Start session if needed
        if self.auto_manage_session and not self.session_started:
            await self._start_session()
        
        # Extract user message from messages
        # Handle both single message and list of messages
        if isinstance(messages, list):
            message_list = messages
        else:
            message_list = [messages]
        
        for msg in reversed(message_list):
            if msg.role == Role.USER:
                self.last_user_message = msg.text
                break
        
        # Get memory context
        context = await self._get_context()
        
        # Return Context with instructions
        formatted_context = context.get("formatted_context", "")
        if formatted_context:
            return Context(instructions=formatted_context)
        
        return Context()
    
    async def invoked(
        self,
        request_messages: ChatMessage | list[ChatMessage],
        response_messages: ChatMessage | list[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called AFTER agent invocation.
        
        This is where we:
        1. Extract agent's response
        2. Store turn in memory (user message + agent response)
        
        Args:
            request_messages: Messages sent to the AI
            response_messages: Messages received from the AI
            invoke_exception: Exception if invocation failed
            **kwargs: Additional arguments
        """
        if not response_messages:
            return
            
        # Extract agent message from response
        # Handle both single message and list of messages
        if isinstance(response_messages, list):
            response_list = response_messages
        else:
            response_list = [response_messages]
        
        agent_message = ""
        for msg in reversed(response_list):
            if msg.role == Role.ASSISTANT:
                agent_message = msg.text
                break
        
        # Store turn if we have both messages
        if self.last_user_message and agent_message:
            logger.info(f"📤 Storing turn:")
            logger.info(f"   User: {self.last_user_message[:100]}...")
            logger.info(f"   Assistant: {agent_message[:100]}...")
            await self._store_turn(self.last_user_message, agent_message)
        else:
            logger.warning(
                f"Could not store turn - missing messages: "
                f"user={bool(self.last_user_message)}, agent={bool(agent_message)}"
            )
    
    async def thread_created(self, thread_id: str) -> None:
        """
        Called when a new thread is created.
        
        For memory service, we don't need to do anything special here
        since our sessions are independent of agent threads.
        """
        logger.debug(f"Thread created: {thread_id} (session: {self.session_id})")
    
    # ========================================================================
    # Memory Service API Calls
    # ========================================================================
    
    async def _start_session(self) -> Dict[str, Any]:
        """
        Start a new session or restore existing one.
        
        Returns:
            Initial session context
        """
        url = f"{self.service_url}/sessions/start"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "restore": True
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            self.session_started = True
            
            logger.info(
                f"Session started: {self.session_id} "
                f"(restored: {result.get('restored', False)})"
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to start session: {e}")
            raise RuntimeError(f"Failed to start memory session: {e}")
    
    async def _get_context(self) -> Dict[str, Any]:
        """
        Get current memory context for this session.
        
        Returns:
            Dictionary with context information
        """
        url = f"{self.service_url}/memory/context"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Log what context was retrieved
            insights_count = len(result.get("insights", []))
            summaries_count = len(result.get("session_summaries", []))
            active_turns = len(result.get("active_context", []))
            
            logger.info(f"📥 Context retrieved for session {self.session_id}")
            logger.info(f"   - Long-term insights: {insights_count}")
            logger.info(f"   - Session summaries: {summaries_count}")
            logger.info(f"   - Active turns: {active_turns}")
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to get context: {e}")
            # Return empty context rather than failing
            return {
                "active_context": [],
                "cumulative_summary": "",
                "insights": [],
                "session_summaries": [],
                "formatted_context": ""
            }
    
    async def _store_turn(self, user_message: str, agent_message: str) -> None:
        """
        Store a conversation turn in memory.
        
        Args:
            user_message: User's message
            agent_message: Agent's response
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
            logger.debug(f"Turn stored: session={self.session_id}")
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to store turn: {e}")
            # Don't fail the agent invocation if memory storage fails
    
    async def end_session(self) -> None:
        """
        End the current session and trigger reflection.
        
        This should be called when the conversation is complete.
        If auto_manage_session=True, this is the user's responsibility.
        """
        if self.session_ended:
            logger.warning(f"Session already ended: {self.session_id}")
            return
        
        # Give a small delay to ensure any pending invoked() calls complete
        # This handles the async timing where agent.run() returns but invoked() 
        # is still storing the turn in the background
        await asyncio.sleep(0.1)
        
        url = f"{self.service_url}/sessions/end"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            # Log session summary details
            result = response.json()
            logger.info(f"✅ Session ended: {self.session_id}")
            logger.info(f"   - Summary generated: {result.get('summary_generated', False)}")
            logger.info(f"   - Insights extracted: {result.get('insights_count', 0)}")
            logger.info(f"   - Turns processed: {result.get('turns_count', 0)}")
            
            self.session_ended = True
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to end session: {e}")
            raise RuntimeError(f"Failed to end memory session: {e}")
    
    # ========================================================================
    # Additional Memory Operations (Optional)
    # ========================================================================
    
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
            return []
    
    async def get_insights(self, recent_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get user insights (long-term learnings).
        
        Args:
            recent_only: If True, only return recent insights
        
        Returns:
            List of insights with content and metadata
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
            return []
    
    async def get_summaries(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get session summaries for this user.
        
        Args:
            limit: Maximum number of summaries to retrieve
        
        Returns:
            List of session summaries
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
            return []
    
    async def search_memory(self, query: str) -> str:
        """
        Search your past memory specific to this user for relevant facts.
        
        Use this tool when you need to recall specific information about the user
        that isn't in the current conversation context. The memory assistant will
        intelligently search across past conversations, session summaries, and 
        long-term insights to find relevant facts.
        
        This is particularly useful when:
        - User asks you to recall something specific
        - You need detailed historical information not in current context
        - You want to provide highly personalized recommendations
        - You need to verify or check past information
        
        Args:
            query: Description of the facts you want to retrieve.
                   Be specific about what information you're looking for.
                   Examples:
                   - "user's dietary restrictions and food allergies"
                   - "user's investment risk tolerance and retirement goals"
                   - "user's learning style and favorite subjects in math"
                   - "products the user has purchased in the past"
                   - "patient's medication history and known allergies"
        
        Returns:
            Retrieved facts and context relevant to your query, formatted as
            a readable string. Returns an error message if the session is not
            started or if no relevant information is found.
        """
        if not self.session_started:
            return "Error: Session not started. Cannot search memory."
        
        url = f"{self.service_url}/memory/retrieve"
        payload = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "query": query,
            "top_k": 5
        }
        
        try:
            print(f"\n🔍 [MEMORY SEARCH] Query: '{query}'")
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # The CFR agent returns synthesized facts as a string
            facts_text = result.get("facts", "")
            
            if not facts_text or facts_text.strip() == "":
                print(f"   ❌ No relevant information found")
                return f"No relevant information found in memory for: '{query}'"
            
            print(f"   ✅ Found relevant information:")
            print(f"   {facts_text[:200]}..." if len(facts_text) > 200 else f"   {facts_text}")
            print()
            
            return f"Memory search results for '{query}':\n\n{facts_text}"
        
        except httpx.HTTPError as e:
            logger.error(f"Failed to search memory: {e}")
            print(f"   ❌ Error searching memory: {e}\n")
            return "Error: Unable to search memory at this time. Please try again later."
