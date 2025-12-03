"""
CosmosMemoryProvider - Agent Framework integration for CosmosDB Agent Memory.
"""

import sys
from collections.abc import MutableSequence, Sequence
from typing import Any, Optional

from agent_framework import ChatMessage, Context, ContextProvider, Role
from agent_framework.exceptions import ServiceInitializationError
from azure.cosmos import CosmosClient
from openai import AzureOpenAI

from memory.cosmos_agent_memory import CosmosAgentMemory
from memory.config import MemoryConfig
from memory.provider_config import CosmosMemoryProviderConfig

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover


class CosmosMemoryProvider(ContextProvider):
    """
    CosmosDB Memory Context Provider for Agent Framework (Embedded Version).
    
    Provides multi-tier memory with:
    - Long-term user insights (persistent across all sessions)
    - Session summaries (recent completed sessions)
    - Cumulative summary (current session compression)
    - Active turns (recent conversation buffer)
    
    Important: Session Management
    ------------------------------
    Due to Agent Framework lifecycle behavior, automatic session management via
    context managers (__aenter__/__aexit__) is NOT reliable. The framework exits
    the provider's context immediately after invoking(), which would end the session
    before invoked() can store conversation turns.
    
    Recommended Usage (Auto-start with Manual End):
        provider = CosmosMemoryProvider(
            user_id="user123",
            cosmos_connection_string=os.getenv("COSMOS_CONNECTION_STRING"),
            openai_client=openai_client,
            config=CosmosMemoryProviderConfig(
                auto_manage_session=True  # Auto-starts on first invoking()
            )
        )
        
        async with provider:
            agent = ChatAgent(
                chat_client=...,
                context_providers=[provider]
            )
            
            # Session starts automatically on first run
            result = await agent.run("What's a Roth IRA?")
            
            # Must explicitly end session when done
            await provider.end_session_explicit()
    
    Alternative (Full Manual Control):
        config = CosmosMemoryProviderConfig(
            auto_manage_session=False  # Full manual control
        )
        
        provider = CosmosMemoryProvider(
            user_id="user123",
            cosmos_connection_string=connection_string,
            openai_client=openai_client,
            config=config
        )
        
        async with provider:
            # Manually start session
            await provider._memory.start_session()
            provider._session_active = True
            
            agent = ChatAgent(..., context_providers=[provider])
            result = await agent.run("Hello")
            
            # Manually end session
            await provider.end_session_explicit()
    """
    
    def __init__(
        self,
        user_id: str,
        memory_config: MemoryConfig,
        *,
        # CosmosDB connection
        cosmos_connection_string: Optional[str] = None,
        cosmos_client: Optional[CosmosClient] = None,
        openai_client: Optional[AzureOpenAI] = None,
        
        # Agent Framework settings
        config: Optional[CosmosMemoryProviderConfig] = None,
        
        # Advanced: Pre-created memory instance
        cosmos_memory: Optional[CosmosAgentMemory] = None,
    ):
        """
        Initialize CosmosMemoryProvider.
        
        Args:
            user_id: User identifier
            memory_config: Core memory configuration (buffer size, reflection, etc.)
            cosmos_connection_string: Cosmos connection string
            cosmos_client: Pre-created CosmosClient
            openai_client: Azure OpenAI client for embeddings
            config: Agent Framework integration settings (context injection, auto-session).
                   If not provided, uses defaults with the provided memory_config.
            cosmos_memory: Pre-created CosmosAgentMemory instance (advanced).
                          Use this to share memory across providers.
        
        Raises:
            ServiceInitializationError: If user_id is missing or invalid connection
        """
        # Validation
        if not user_id:
            raise ServiceInitializationError("user_id is required")
        
        self.user_id = user_id
        self.config = config or CosmosMemoryProviderConfig(memory_config=memory_config)
        
        # Create or use provided CosmosAgentMemory
        if cosmos_memory:
            self._memory = cosmos_memory
            self._own_memory = False
        else:
            try:
                self._memory = CosmosAgentMemory(
                    user_id=user_id,
                    cosmos_connection_string=cosmos_connection_string,
                    cosmos_client=cosmos_client,
                    openai_client=openai_client,
                    config=self.config.memory_config,
                    auto_start_session=False  # We'll manage sessions via invoking()/thread_created()
                )
                self._own_memory = True
            except ValueError as e:
                raise ServiceInitializationError(f"Failed to initialize CosmosAgentMemory: {e}")
        
        # Thread tracking
        self._current_thread_id: Optional[str] = None
        self._session_active: bool = False
    
    async def __aenter__(self) -> Self:
        """Context manager entry."""
        if self._own_memory:
            await self._memory.__aenter__()
        return self
    
    async def __aexit__(
        self, 
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None, 
        exc_tb: Any
    ) -> None:
        """Context manager exit - only cleanup resources.
        
        Note: Session management is NOT handled here because the framework
        exits the context before invoked() is called. Sessions must be
        explicitly ended via end_session_explicit().
        
        We also don't call the underlying memory's __aexit__ because that
        would end the session, preventing invoked() from storing turns.
        """
        # Do NOT end session or call memory.__aexit__ here
        # Both would prevent invoked() from storing turns
        pass
    
    @override
    async def thread_created(self, thread_id: str | None = None) -> None:
        """
        Called when a new thread is created.
        Initialize session with thread_id.
        
        Args:
            thread_id: The thread ID from Agent Framework
        """
        self._current_thread_id = thread_id
        
        if self.config.auto_manage_session:
            # Determine session_id based on config
            if self.config.use_thread_as_session:
                # Use thread_id as session_id (one session per thread)
                session_id = thread_id
            else:
                # Generate unique session_id (new session each time)
                session_id = None  # Auto-generated
            
            try:
                # Start session and load context
                await self._memory.start_session(session_id=session_id)
                self._session_active = True
            except Exception as e:
                raise ServiceInitializationError(f"Failed to start session: {e}")
    
    @override
    async def invoking(
        self, 
        messages: ChatMessage | MutableSequence[ChatMessage], 
        **kwargs: Any
    ) -> Context:
        """
        Called BEFORE AI invocation - inject memory context.
        
        Builds context from:
        1. Long-term insights (user profile across all sessions)
        2. Recent session summaries (last N completed sessions)
        3. Cumulative summary (current session compression)
        4. Active turns (recent conversation buffer)
        
        Args:
            messages: Input messages to the AI
            **kwargs: Additional arguments
        
        Returns:
            Context with memory injected as messages or instructions
        """
        # Lazy session start for local threads (thread_created not called for them)
        if not self._session_active and self.config.auto_manage_session:
            try:
                # Determine session_id based on config
                if self.config.use_thread_as_session and self._current_thread_id:
                    session_id = self._current_thread_id
                else:
                    session_id = None  # Auto-generated
                
                await self._memory.start_session(session_id=session_id)
                self._session_active = True
                print(f"[Provider] Auto-started session in invoking()")
            except Exception as e:
                print(f"Warning: Failed to auto-start session: {e}")
                import traceback
                traceback.print_exc()
                return Context()
        
        if not self._session_active:
            # Session not started and auto-start failed - return empty context
            return Context()
        
        try:
            # Build context parts based on configuration
            context_parts = []
            
            # 1. Long-term insights
            if self.config.include_longterm_insights:
                init_context = self._memory._orchestrator.memory_keeper.session_init_context
                if init_context and hasattr(init_context, 'longterm_insight') and init_context.longterm_insight:
                    context_parts.append(
                        f"{self.config.longterm_insights_header}\n{init_context.longterm_insight}"
                    )
            
            # 2. Recent session summaries
            if self.config.include_recent_sessions:
                init_context = self._memory._orchestrator.memory_keeper.session_init_context
                if init_context and hasattr(init_context, 'recent_summaries') and init_context.recent_summaries:
                    summaries_text = "\n".join([
                        f"- Session {i+1} ({s.get('end_time', 'Unknown')[:10]}): {s.get('summary', '')}"
                        for i, s in enumerate(init_context.recent_summaries[:self.config.num_recent_sessions])
                    ])
                    if summaries_text:
                        context_parts.append(
                            f"{self.config.recent_sessions_header}\n{summaries_text}"
                        )
            
            # 3. Cumulative summary (current session)
            if self.config.include_cumulative_summary:
                cumulative = self._memory._orchestrator.memory_keeper.cumulative_summary
                if cumulative:
                    context_parts.append(
                        f"{self.config.cumulative_summary_header}\n{cumulative}"
                    )
            
            # 4. Active conversation turns
            if self.config.include_active_turns:
                active_context = self._memory._orchestrator.memory_keeper.get_current_context()
                if active_context:
                    context_parts.append(
                        f"{self.config.active_turns_header}\n{active_context}"
                    )
            
            # Combine all parts
            if context_parts:
                combined_context = "\n\n".join(context_parts)
                full_context = f"{self.config.context_prompt}\n\n{combined_context}"
                
                # Return based on injection mode
                if self.config.context_injection_mode == "messages":
                    return Context(
                        messages=[ChatMessage(role=Role.USER, text=full_context)]
                    )
                else:  # instructions
                    return Context(
                        instructions=full_context
                    )
            
            return Context()
            
        except Exception as e:
            # Log warning but don't fail - agent should continue
            print(f"Warning: Failed to build memory context: {e}")
            return Context()
    
    @override
    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called AFTER AI invocation - store conversation in memory.
        
        Extracts user and assistant messages and adds them to memory.
        Automatic summarization happens when buffer is full.
        
        Args:
            request_messages: Messages sent to the AI
            response_messages: Messages received from the AI
            invoke_exception: Exception if invocation failed
            **kwargs: Additional arguments
        """
        print(f"[Provider] invoked() called - provider session_active: {self._session_active}")
        if not self._session_active:
            return
        
        try:
            # Extract messages
            request_list = (
                [request_messages] if isinstance(request_messages, ChatMessage) 
                else list(request_messages)
            )
            response_list = (
                [response_messages] if isinstance(response_messages, ChatMessage)
                else list(response_messages) if response_messages
                else []
            )
            
            # Find user and assistant messages
            user_message = None
            assistant_message = None
            
            # Find user message (skip memory context messages)
            for msg in request_list:
                if msg.role == Role.USER and msg.text and msg.text.strip():
                    # Skip memory context messages we injected
                    # Check if it starts with the first line of context_prompt
                    context_marker = self.config.context_prompt.split('\n')[0]
                    if not msg.text.startswith(context_marker):
                        user_message = msg.text
                        break
            
            # Find assistant message
            for msg in response_list:
                if msg.role == Role.ASSISTANT and msg.text and msg.text.strip():
                    assistant_message = msg.text
                    break
            
            # Add turn to memory if we have both messages
            if user_message and assistant_message:
                print(f"[Provider] Storing turn in memory (user: {len(user_message)} chars, assistant: {len(assistant_message)} chars)")
                await self._memory.add_turn(
                    user_message=user_message,
                    assistant_message=assistant_message
                )
            else:
                print(f"[Provider] Skipping turn storage - user_message: {bool(user_message)}, assistant_message: {bool(assistant_message)}")
                
        except Exception as e:
            # Log warning but don't fail - agent should continue
            print(f"Warning: Failed to store turn in memory: {e}")
    
    async def end_session_explicit(self) -> dict[str, Any]:
        """
        Explicitly end the current session.
        
        This MUST be called when the conversation is complete, regardless of
        the auto_manage_session setting. The framework's context manager
        lifecycle does not align with session boundaries.
        
        Best practice: Call this after your final agent.run() in a conversation.
        
        Returns:
            Session summary, topics, and extracted insights
        """
        if self._session_active:
            result = await self._memory.end_session(
                trigger_reflection=self.config.memory_config.trigger_reflection_on_end
            )
            self._session_active = False
            return result
        return {"message": "No active session"}
    
    async def search_memory(self, query: str) -> str:
        """
        Search memory for relevant information.
        
        This can be exposed as a tool to the agent if needed.
        
        Args:
            query: Natural language search query
        
        Returns:
            Synthesized response with relevant memory
        """
        if not self._session_active:
            return "Memory not available - session not started"
        
        try:
            return await self._memory.search(query)
        except Exception as e:
            return f"Search failed: {str(e)}"
    
    def get_status(self) -> dict[str, Any]:
        """
        Get current provider status.
        
        Returns:
            Status information including session state and memory status
        """
        status = {
            "user_id": self.user_id,
            "thread_id": self._current_thread_id,
            "session_active": self._session_active,
            "config": {
                "auto_manage_session": self.config.auto_manage_session,
                "use_thread_as_session": self.config.use_thread_as_session,
                "include_longterm_insights": self.config.include_longterm_insights,
                "include_recent_sessions": self.config.include_recent_sessions,
                "include_cumulative_summary": self.config.include_cumulative_summary,
                "include_active_turns": self.config.include_active_turns,
            }
        }
        
        if self._session_active:
            status["memory_status"] = self._memory.get_status()
        
        return status
