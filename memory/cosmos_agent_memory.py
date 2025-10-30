"""
Simplified CosmosDB Agent Memory Interface.

Provides a clean, easy-to-use API for agent memory with:
- Connection string initialization
- Auto-session management
- Intuitive method names
- Context manager support
"""

import uuid
import os
from typing import Dict, List, Optional, Any
from azure.cosmos import CosmosClient, DatabaseProxy, ContainerProxy
from openai import AzureOpenAI

from memory.config import MemoryConfig
from memory.cosmos_utils import CosmosUtils
from memory.orchestrator import MemoryServiceOrchestrator


class CosmosAgentMemory:
    """
    CosmosDB-backed agent memory with multi-tier storage:
    - Short-term: Active conversation buffer
    - Mid-term: Session summaries with vector search
    - Long-term: User insights and patterns
    
    Examples:
        # Simplest usage
        memory = CosmosAgentMemory(
            user_id="user123",
            cosmos_connection_string=os.getenv("COSMOS_CONNECTION_STRING"),
            openai_client=openai_client
        )
        await memory.start_session()
        await memory.add_turn("Hello", "Hi there!")
        context = memory.get_context()
        await memory.end_session()
        
        # Context manager (auto session management)
        async with CosmosAgentMemory(
            user_id="user123",
            cosmos_connection_string=connection_string,
            openai_client=openai_client
        ) as memory:
            await memory.add_turn("What's a Roth IRA?", "A Roth IRA is...")
            context = memory.get_context()
    """
    
    def __init__(
        self,
        user_id: str,
        *,
        # Simple connection options
        cosmos_connection_string: Optional[str] = None,
        cosmos_client: Optional[CosmosClient] = None,
        openai_client: Optional[AzureOpenAI] = None,
        
        # Or individual components (advanced)
        database: Optional[DatabaseProxy] = None,
        interactions_container: Optional[ContainerProxy] = None,
        summaries_container: Optional[ContainerProxy] = None,
        insights_container: Optional[ContainerProxy] = None,
        
        # Configuration
        config: Optional[MemoryConfig] = None,
        
        # Session management (optional - auto-generated if not provided)
        session_id: Optional[str] = None,
        auto_start_session: bool = False,
    ):
        """
        Initialize CosmosDB Agent Memory.
        
        Args:
            user_id: User identifier (required)
            cosmos_connection_string: Cosmos connection string (simplest option)
            cosmos_client: Pre-created CosmosClient
            openai_client: Azure OpenAI client for embeddings/chat
            database: Pre-created DatabaseProxy (advanced)
            interactions_container: Pre-created interactions container
            summaries_container: Pre-created summaries container
            insights_container: Pre-created insights container
            config: Memory configuration (uses defaults if not provided)
            session_id: Optional session ID (auto-generated if None)
            auto_start_session: Automatically start session on init
        
        Raises:
            ValueError: If insufficient connection information provided
        """
        self.user_id = user_id
        self.config = config or MemoryConfig()
        self.session_id = session_id
        self._session_started = False
        self._orchestrator: Optional[MemoryServiceOrchestrator] = None
        
        # Setup Cosmos connection
        if database:
            self._database = database
            self._own_client = False
        elif cosmos_client:
            self._database = cosmos_client.get_database_client(self.config.database_name)
            self._own_client = False
        elif cosmos_connection_string:
            self._cosmos_client = CosmosClient.from_connection_string(cosmos_connection_string)
            self._database = self._cosmos_client.get_database_client(self.config.database_name)
            self._own_client = True
        else:
            # Try environment variable
            connection_string = os.getenv("COSMOS_CONNECTION_STRING")
            if not connection_string:
                raise ValueError(
                    "Must provide either cosmos_connection_string, cosmos_client, or database. "
                    "Alternatively, set COSMOS_CONNECTION_STRING environment variable."
                )
            self._cosmos_client = CosmosClient.from_connection_string(connection_string)
            self._database = self._cosmos_client.get_database_client(self.config.database_name)
            self._own_client = True
        
        # Setup containers
        if interactions_container and summaries_container and insights_container:
            self._interactions_container = interactions_container
            self._summaries_container = summaries_container
            self._insights_container = insights_container
        else:
            # Get or create containers
            self._interactions_container = self._database.get_container_client(
                self.config.interactions_container
            )
            self._summaries_container = self._database.get_container_client(
                self.config.summaries_container
            )
            self._insights_container = self._database.get_container_client(
                self.config.insights_container
            )
        
        # Setup OpenAI client
        if openai_client:
            self._chat_client = openai_client
            self._own_openai_client = False
        else:
            # Try to create from environment
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            if not api_key or not endpoint:
                raise ValueError(
                    "Must provide openai_client or set AZURE_OPENAI_API_KEY and "
                    "AZURE_OPENAI_ENDPOINT environment variables."
                )
            self._chat_client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
            )
            self._own_openai_client = True
        
        # Setup CosmosUtils
        self._cosmos_utils = CosmosUtils(embedding_client=self._chat_client)
        
        # Auto-start session if requested
        if auto_start_session:
            # Note: Can't use await in __init__, so we store a flag
            self._auto_start_pending = True
        else:
            self._auto_start_pending = False
    
    async def _ensure_orchestrator(self) -> None:
        """Ensure orchestrator is initialized with current session_id."""
        if not self.session_id:
            self.session_id = str(uuid.uuid4())
        
        if not self._orchestrator or self._orchestrator.session_id != self.session_id:
            self._orchestrator = MemoryServiceOrchestrator(
                user_id=self.user_id,
                session_id=self.session_id,
                config=self.config,
                cosmos_utils=self._cosmos_utils,
                interactions_container=self._interactions_container,
                summaries_container=self._summaries_container,
                insights_container=self._insights_container,
                chat_client=self._chat_client
            )
    
    async def start_session(
        self, 
        session_id: Optional[str] = None,
        restore: bool = False
    ) -> Dict[str, Any]:
        """
        Start a new session or restore an existing one.
        
        Args:
            session_id: Optional session ID (auto-generated if None for new sessions)
            restore: If True, attempt to restore session state from CosmosDB
        
        Returns:
            Initial context with insights, recent summaries, and restored state
        
        Raises:
            ValueError: If restore=True but session_id not found in database
        """
        if session_id:
            self.session_id = session_id
        
        await self._ensure_orchestrator()
        
        if restore and session_id:
            # Restore existing session state
            result = await self._orchestrator.restore_session(session_id)
        else:
            # Initialize new session
            result = await self._orchestrator.initialize_session()
        
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
            metadata: Optional metadata
        
        Returns:
            Turn processing result with summarization status
        
        Raises:
            RuntimeError: If session not started
        """
        if not self._session_started:
            raise RuntimeError(
                "Session not started. Call start_session() first or use context manager."
            )
        
        return await self._orchestrator.process_turn(
            user_message=user_message,
            agent_message=assistant_message,
            metadata=metadata
        )
    
    async def end_session(self, trigger_reflection: bool = True) -> Dict[str, Any]:
        """
        End current session. Extracts summary, topics, and insights.
        
        Args:
            trigger_reflection: Whether to extract insights (default: True)
        
        Returns:
            Session summary, topics, and extracted insights
        """
        if not self._session_started:
            return {
                "session_id": self.session_id,
                "message": "Session was not started"
            }
        
        result = await self._orchestrator.end_session(
            trigger_reflection=trigger_reflection
        )
        self._session_started = False
        
        return result
    
    def get_context(self) -> str:
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
        
        init_context = self._orchestrator.memory_keeper.session_init_context
        cumulative = self._orchestrator.memory_keeper.cumulative_summary
        active_context = self._orchestrator.memory_keeper.get_active_context()
        
        parts = []
        
        # Long-term insights
        if init_context and init_context.longterm_insight:
            parts.append(f"## Long-term User Profile\n{init_context.longterm_insight}")
        
        # Recent sessions
        if init_context and init_context.recent_summaries:
            summaries_text = "\n".join([
                f"- Session {s.get('start_time', 'Unknown')}: {s.get('summary', '')}"
                for s in init_context.recent_summaries[:3]
            ])
            parts.append(f"## Recent Sessions\n{summaries_text}")
        
        # Cumulative summary of current session
        if cumulative:
            parts.append(f"## Current Session Summary\n{cumulative}")
        
        # Active conversation buffer
        if active_context:
            parts.append(f"## Recent Conversation\n{active_context}")
        
        return "\n\n".join(parts) if parts else ""
    
    async def search(self, query: str) -> str:
        """
        Search memory for relevant information.
        Uses CFR agent to search across interactions, summaries, and insights.
        
        Args:
            query: Natural language search query
        
        Returns:
            Synthesized response with relevant memory
        
        Raises:
            RuntimeError: If session not started
        """
        if not self._session_started or not self._orchestrator:
            raise RuntimeError(
                "Session not started. Call start_session() first or use context manager."
            )
        
        return await self._orchestrator.retrieve_facts(query)
    
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
        await self._ensure_orchestrator()
        return await self._orchestrator.get_user_insights(category, limit)
    
    async def get_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent session summaries.
        
        Args:
            limit: Maximum number of sessions to return
        
        Returns:
            List of session summary documents
        """
        query = """
            SELECT * FROM c 
            WHERE c.user_id = @user_id AND c.type = 'session_summary'
            ORDER BY c.end_time DESC
        """
        parameters = [{"name": "@user_id", "value": self.user_id}]
        
        items = list(self._summaries_container.query_items(
            query=query,
            parameters=parameters,
            max_item_count=limit
        ))
        
        return items
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current memory status.
        
        Returns:
            Status information including session state and buffer status
        """
        status = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "session_started": self._session_started,
        }
        
        if self._orchestrator:
            status["orchestrator_status"] = self._orchestrator.get_status()
        
        return status
    
    async def __aenter__(self):
        """Context manager entry - auto-starts session if not already started."""
        if not self._session_started:
            await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - auto-ends session if auto_manage_sessions=True."""
        if self._session_started and self.config.auto_manage_sessions:
            await self.end_session(
                trigger_reflection=self.config.trigger_reflection_on_end
            )
        
        # Cleanup if we own the client
        if self._own_client and hasattr(self, '_cosmos_client'):
            self._cosmos_client.close()
