import logging
from typing import Any, Dict, List

from agent_framework import Agent as AFAgent, AgentSession, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient

from agent.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class Agent(BaseAgent):
    """Agent Framework implementation of a single assistant loop."""

    def __init__(self, state_store: Dict[str, Any], session_id: str, access_token: str | None = None) -> None:
        super().__init__(state_store, session_id)
        self._agent: AFAgent | None = None
        self._session: AgentSession | None = None
        self._initialized = False
        self._access_token = access_token
        self._ws_manager = None  # WebSocket manager for streaming
        # Track conversation turn for tool call grouping - load from state store
        self._turn_key = f"{session_id}_current_turn"
        self._current_turn = state_store.get(self._turn_key, 0)

    def set_websocket_manager(self, manager: Any) -> None:
        """Allow backend to inject WebSocket manager for streaming events."""
        self._ws_manager = manager
        logger.info(f"[STREAMING] WebSocket manager set for single_agent, session_id={self.session_id}")

    async def _setup_single_agent(self) -> None:
        if self._initialized:
            return

        if not all([self.azure_openai_key, self.azure_deployment, self.azure_openai_endpoint, self.api_version]):
            raise RuntimeError(
                "Azure OpenAI configuration is incomplete. Ensure AZURE_OPENAI_API_KEY, "
                "AZURE_OPENAI_REASONING_MODEL, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_API_VERSION are set."
            )

        headers = self._build_headers()
        mcp_tools = await self._maybe_create_tools(headers)

        chat_client = AzureOpenAIChatClient(
            api_key=self.azure_openai_key,
            deployment_name=self.azure_deployment,
            endpoint=self.azure_openai_endpoint,
            api_version=self.api_version,
        )

        instructions = (
            "You are a helpful assistant. You can use multiple tools to find information and answer questions. "
            "Review the tools available to you and use them as needed. You can also ask clarifying questions if "
            "the user is not clear. If customer ask any operations that there's no tool to support, said that you cannot do it. "
            "Never hallucinate any operation that you do not actually do."
        )

        tools = mcp_tools if mcp_tools else None

        self._agent = AFAgent(
            name="ai_assistant",
            client=chat_client,
            instructions=instructions,
            tools=tools,
        )

        try:
            await self._agent.__aenter__()
        except Exception:
            self._agent = None
            raise

        if self.state and isinstance(self.state, dict):
            try:
                self._session = AgentSession.from_dict(self.state)
            except Exception:
                self._session = self._agent.create_session()
        else:
            self._session = self._agent.create_session()

        self._initialized = True

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _maybe_create_tools(self, headers: Dict[str, str]) -> List[MCPStreamableHTTPTool] | None:
        if not self.mcp_server_uri:
            logger.warning("MCP_SERVER_URI is not configured; agent will run without MCP tools.")
            return None

        tool = MCPStreamableHTTPTool(
            name="mcp-streamable",
            url=self.mcp_server_uri,
            headers=headers,
            timeout=30,
            request_timeout=30,
        )

        return [tool]

    async def chat_async(self, prompt: str) -> str:
        await self._setup_single_agent()

        if not self._agent or not self._session:
            raise RuntimeError("Agent Framework single agent failed to initialize correctly.")

        # Increment turn counter for this new conversation turn and persist to state store
        self._current_turn += 1
        self.state_store[self._turn_key] = self._current_turn

        # Use streaming if WebSocket manager is available
        if self._ws_manager:
            return await self._chat_async_streaming(prompt)
        
        # Non-streaming path
        response = await self._agent.run(prompt, session=self._session)
        assistant_response = response.text

        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": assistant_response},
        ]
        self.append_to_chat_history(messages)

        new_state = self._session.to_dict()
        self._setstate(new_state)

        return assistant_response

    async def close(self) -> None:
        """Close agent resources and persist session state."""
        if self._session is not None:
            self._setstate(self._session.to_dict())

        if self._agent is not None:
            await self._agent.__aexit__(None, None, None)

        self._agent = None
        self._session = None
        self._initialized = False

    async def _chat_async_streaming(self, prompt: str) -> str:
        """Handle chat with streaming support via WebSocket."""
        if not self._agent or not self._session:
            raise RuntimeError("Agent Framework single agent failed to initialize correctly.")

        # Notify UI that agent started - with convention flag
        if self._ws_manager:
            await self._ws_manager.broadcast(
                self.session_id,
                {
                    "type": "agent_start",
                    "agent_id": "single_agent",
                    "show_message_in_internal_process": False,  # Convention: don't show message in left panel
                },
            )

        # Stream the response
        full_response = []
        
        try:
            stream = self._agent.run(prompt, session=self._session, stream=True)
            async for chunk in stream:
                # Process contents in the chunk
                if hasattr(chunk, 'contents') and chunk.contents:
                    for content in chunk.contents:
                        # Check for tool/function calls - only broadcast the tool name
                        if content.type == "function_call":
                            if self._ws_manager:
                                await self._ws_manager.broadcast(
                                    self.session_id,
                                    {
                                        "type": "tool_called",
                                        "agent_id": "single_agent",
                                        "tool_name": content.name,
                                        "turn": self._current_turn,
                                    },
                                )
                
                # Extract text from chunk
                if hasattr(chunk, 'text') and chunk.text:
                    full_response.append(chunk.text)
                    
                    # Broadcast token to WebSocket
                    if self._ws_manager:
                        await self._ws_manager.broadcast(
                            self.session_id,
                            {
                                "type": "agent_token",
                                "agent_id": "single_agent",
                                "content": chunk.text,
                            },
                        )
        except Exception as exc:
            logger.error("[STREAMING] Error during single agent streaming: %s", exc, exc_info=True)
            raise

        final_response = await stream.get_final_response()

        assistant_response = ''.join(full_response) or final_response.text

        # Send final result
        if self._ws_manager:
            await self._ws_manager.broadcast(
                self.session_id,
                {
                    "type": "final_result",
                    "content": assistant_response,
                },
            )

        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": assistant_response},
        ]
        self.append_to_chat_history(messages)

        new_state = self._session.to_dict()
        self._setstate(new_state)

        return assistant_response
