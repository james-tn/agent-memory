"""
FastAPI Memory Service - RESTful API for Agent Memory.

Wraps the AgentMemory class to provide HTTP endpoints for:
- Session management (start, end, get context)
- Turn storage (user + assistant messages)
- Memory search
- Background processing (reflection, synthesis)

Client applications own the agent/chat logic, this service handles memory.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import AzureOpenAI

from memory import AgentMemory, AgentMemoryConfig
from memory.db import DatabaseType
from server.config import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _server_database_type() -> DatabaseType:
    """Resolve the configured database backend for the server."""
    db_type = get_config().agent_memory_db_type.strip().lower()
    return DatabaseType(db_type)


# =============================================================================
# Request/Response Models
# =============================================================================

class StartSessionRequest(BaseModel):
    """Request to start a new session."""
    user_id: str
    agent_id: str = "default"
    session_id: Optional[str] = None
    restore: bool = False


class StartSessionResponse(BaseModel):
    """Response from starting a session."""
    session_id: str
    user_id: str
    agent_id: str
    context: str
    insights_loaded: bool
    recent_sessions_count: int


class StoreTurnRequest(BaseModel):
    """Request to store a conversation turn."""
    user_id: str
    agent_id: str = "default"
    session_id: str
    user_message: str
    assistant_message: str


class StoreTurnResponse(BaseModel):
    """Response from storing a turn."""
    success: bool
    turn_count: int
    pruning_triggered: bool


class GetContextResponse(BaseModel):
    """Response with current context."""
    context: str
    turn_count: int


class EndSessionRequest(BaseModel):
    """Request to end a session."""
    user_id: str
    agent_id: str = "default"
    session_id: str
    trigger_reflection: bool = True


class EndSessionResponse(BaseModel):
    """Response from ending a session."""
    success: bool
    summary: str
    insights_count: int
    synthesis_triggered: bool


class SearchRequest(BaseModel):
    """Request to search memory."""
    user_id: str
    agent_id: str = "default"
    query: str
    top_k: int = 5
    search_interactions: bool = True
    search_insights: bool = True
    search_summaries: bool = False
    search_mode: str = "auto"


class SearchResponse(BaseModel):
    """Response from memory search."""
    results: str
    query: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    active_sessions: int
    uptime_seconds: float


# =============================================================================
# Session Pool - Manages active AgentMemory instances
# =============================================================================

class SessionPool:
    """
    Pool of active AgentMemory sessions.
    
    - Caches sessions by (user_id, agent_id, session_id)
    - Handles TTL-based eviction
    - Shares OpenAI client across sessions
    """
    
    def __init__(
        self,
        openai_client: AzureOpenAI,
        db_type: DatabaseType = DatabaseType.SQLITE,
        db_path: str = "agent_memory_server.db",
        connection_string: Optional[str] = None,
        cosmos_endpoint: Optional[str] = None,
        search_endpoint: Optional[str] = None,
        search_api_key: Optional[str] = None,
        search_index_prefix: str = "agent-memory",
        postgres_connection_string: Optional[str] = None,
        database_name: str = "agent_memory_db",
        max_sessions: int = 1000,
        session_ttl_minutes: int = 30
    ):
        self.openai_client = openai_client
        self.db_type = db_type
        self.db_path = db_path
        self.connection_string = connection_string
        self.cosmos_endpoint = cosmos_endpoint
        self.search_endpoint = search_endpoint
        self.search_api_key = search_api_key
        self.search_index_prefix = search_index_prefix
        self.postgres_connection_string = postgres_connection_string
        self.database_name = database_name
        self.max_sessions = max_sessions
        self.session_ttl = timedelta(minutes=session_ttl_minutes)
        
        # Active sessions: {(user_id, agent_id, session_id): {"memory": AgentMemory, "last_access": datetime}}
        self._sessions: Dict[tuple, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _build_memory(self, user_id: str, agent_id: str, session_id: Optional[str]) -> AgentMemory:
        """Construct an AgentMemory instance with the server's shared config."""
        config = AgentMemoryConfig(
            auto_manage_sessions=False,
            include_longterm_insights=True,
            include_recent_sessions=True,
            include_cumulative_summary=True,
            database_name=self.database_name,
        )

        return AgentMemory(
            user_id=user_id,
            agent_id=agent_id,
            openai_client=self.openai_client,
            db_type=self.db_type,
            db_path=self.db_path,
            connection_string=self.connection_string,
            cosmos_endpoint=self.cosmos_endpoint,
            search_endpoint=self.search_endpoint,
            search_api_key=self.search_api_key,
            search_index_prefix=self.search_index_prefix,
            postgres_connection_string=self.postgres_connection_string,
            config=config,
            session_id=session_id,
            auto_start_session=False,
        )
    
    def _session_key(self, user_id: str, agent_id: str, session_id: str) -> tuple:
        return (user_id, agent_id, session_id)
    
    async def get_or_create(
        self,
        user_id: str,
        agent_id: str,
        session_id: Optional[str] = None,
        start_session: bool = True,
        restore: bool = False,
    ) -> AgentMemory:
        """Get existing session or create new one."""
        session_id = session_id or str(uuid.uuid4())
        key = self._session_key(user_id, agent_id, session_id)
        
        eviction_candidate: Optional[tuple[str, str, str]] = None
        async with self._lock:
            if key in self._sessions:
                self._sessions[key]["last_access"] = _utcnow()
                return self._sessions[key]["memory"]

            if len(self._sessions) >= self.max_sessions:
                eviction_candidate = min(
                    self._sessions.keys(),
                    key=lambda k: self._sessions[k]["last_access"]
                )

        if eviction_candidate is not None:
            await self.remove(eviction_candidate[0], eviction_candidate[1], eviction_candidate[2], end_session=True)

        memory = self._build_memory(user_id, agent_id, session_id)
        if start_session:
            await memory.start_session(restore=restore)

        async with self._lock:
            actual_key = self._session_key(user_id, agent_id, memory.session_id)
            self._sessions[actual_key] = {
                "memory": memory,
                "last_access": _utcnow(),
                "created_at": _utcnow(),
            }

        logger.info(f"Created session: user={user_id}, session={memory.session_id}")
        return memory
    
    async def get(self, user_id: str, agent_id: str, session_id: str) -> Optional[AgentMemory]:
        """Get existing session or None."""
        key = self._session_key(user_id, agent_id, session_id)
        
        async with self._lock:
            if key in self._sessions:
                self._sessions[key]["last_access"] = _utcnow()
                return self._sessions[key]["memory"]
            return None
    
    async def remove(self, user_id: str, agent_id: str, session_id: str, *, end_session: bool = False) -> bool:
        """Remove session from pool."""
        key = self._session_key(user_id, agent_id, session_id)

        memory = None
        async with self._lock:
            if key in self._sessions:
                memory = self._sessions[key]["memory"]
                del self._sessions[key]
            else:
                return False

        if memory is not None:
            try:
                if end_session:
                    await memory.end_session(trigger_reflection=False)
            finally:
                await memory.close()
            logger.info(f"Removed session: user={user_id}, session={session_id}")
        return True
    
    async def _evict_oldest(self) -> None:
        """Evict oldest session to make room."""
        if not self._sessions:
            return

        oldest_key = min(
            self._sessions.keys(),
            key=lambda k: self._sessions[k]["last_access"]
        )
        await self.remove(oldest_key[0], oldest_key[1], oldest_key[2], end_session=True)
        logger.info(f"Evicted session: {oldest_key}")

    async def create_ephemeral(self, user_id: str, agent_id: str, session_id: Optional[str] = None) -> AgentMemory:
        """Create a lightweight memory instance that is not pooled."""
        return self._build_memory(user_id, agent_id, session_id)
    
    async def evict_stale(self) -> int:
        """Evict sessions that have exceeded TTL."""
        now = _utcnow()
        stale_keys = []
        
        async with self._lock:
            for key, data in self._sessions.items():
                if now - data["last_access"] > self.session_ttl:
                    stale_keys.append(key)
        
        for key in stale_keys:
            await self.remove(key[0], key[1], key[2])
        
        return len(stale_keys)
    
    @property
    def active_count(self) -> int:
        return len(self._sessions)
    
    async def close_all(self) -> None:
        """Close all sessions gracefully."""
        async with self._lock:
            sessions = list(self._sessions.items())
            self._sessions.clear()

        for key, data in sessions:
            memory = data["memory"]
            try:
                await memory.end_session(trigger_reflection=False)
                await memory.close()
            except Exception as e:
                logger.warning(f"Error closing session {key}: {e}")


# =============================================================================
# Global State
# =============================================================================

session_pool: Optional[SessionPool] = None
start_time: Optional[datetime] = None


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    global session_pool, start_time
    from dotenv import load_dotenv
    
    load_dotenv()
    config = get_config()
    
    logger.info("🚀 Starting Memory Service...")
    start_time = _utcnow()
    
    # Initialize Azure OpenAI client
    openai_client = AzureOpenAI(
        azure_endpoint=config.azure_openai_endpoint,
        api_key=config.azure_openai_api_key,
        api_version=config.azure_openai_api_version or "2024-08-01-preview"
    )
    logger.info("✓ Azure OpenAI client initialized")
    
    # Initialize session pool
    session_pool = SessionPool(
        openai_client=openai_client,
        db_type=_server_database_type(),
        db_path=config.agent_memory_db_path,
        connection_string=config.cosmos_connection_string or config.azure_cosmos_connection_string,
        cosmos_endpoint=config.COSMOS_ENDPOINT,
        search_endpoint=config.azure_ai_search_endpoint,
        search_api_key=config.azure_ai_search_api_key,
        search_index_prefix=config.azure_ai_search_index_prefix,
        postgres_connection_string=config.postgres_connection_string,
        database_name=config.cosmos_db_name,
        max_sessions=config.max_sessions,
        session_ttl_minutes=config.session_ttl_minutes
    )
    logger.info("✓ Session pool initialized")
    
    # Start background eviction task
    eviction_task = asyncio.create_task(background_eviction_loop())
    
    logger.info("✅ Memory Service ready!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Memory Service...")
    eviction_task.cancel()
    await session_pool.close_all()
    logger.info("✓ All sessions closed")


async def background_eviction_loop():
    """Periodically evict stale sessions."""
    interval = get_config().eviction_interval_seconds
    
    while True:
        try:
            await asyncio.sleep(interval)
            evicted = await session_pool.evict_stale()
            if evicted > 0:
                logger.info(f"Evicted {evicted} stale sessions")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Eviction error: {e}")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Agent Memory Service",
    description="RESTful API for agent memory management with CosmosDB backend",
    version="2.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def enforce_optional_auth(request: Request, call_next):
    """Apply a config-driven auth gate for production deployments."""
    config = get_config()
    if not config.auth_enabled or request.url.path == "/health":
        return await call_next(request)

    expected_key = config.auth_api_key
    if not expected_key:
        return await call_next(request)

    provided_key = request.headers.get(config.auth_header_name)
    if provided_key != expected_key:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return await call_next(request)


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    uptime = (_utcnow() - start_time).total_seconds() if start_time else 0
    return HealthResponse(
        status="healthy",
        active_sessions=session_pool.active_count if session_pool else 0,
        uptime_seconds=uptime
    )


@app.post("/sessions/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """
    Start a new session or restore an existing one.
    
    Returns initial context with long-term insights and recent session summaries.
    """
    try:
        memory = await session_pool.get_or_create(
            user_id=request.user_id,
            agent_id=request.agent_id,
            session_id=request.session_id,
            start_session=True,
            restore=request.restore,
        )
        
        context = await memory.get_context()
        
        return StartSessionResponse(
            session_id=memory.session_id,
            user_id=request.user_id,
            agent_id=request.agent_id,
            context=context,
            insights_loaded=memory.config.include_longterm_insights,
            recent_sessions_count=memory.config.num_recent_sessions_for_init
        )
    except Exception as e:
        logger.error(f"Error starting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions/turn", response_model=StoreTurnResponse)
async def store_turn(request: StoreTurnRequest):
    """
    Store a conversation turn (user message + assistant response).
    
    This triggers automatic pruning/summarization when buffer is full.
    """
    memory = await session_pool.get(request.user_id, request.agent_id, request.session_id)
    if not memory:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found: {request.session_id}"
        )
    
    try:
        result = await memory.add_turn(
            user_message=request.user_message,
            assistant_message=request.assistant_message
        )
        
        return StoreTurnResponse(
            success=True,
            turn_count=result.get("turn_count", 0),
            pruning_triggered=result.get("pruning_triggered", False)
        )
    except Exception as e:
        logger.error(f"Error storing turn: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/context", response_model=GetContextResponse)
async def get_context(user_id: str, session_id: str, agent_id: str = "default"):
    return await _get_context_response(user_id, agent_id, session_id)


async def _get_context_response(user_id: str, agent_id: str, session_id: str) -> GetContextResponse:
    """
    Get current session context for prompt injection.
    
    Returns formatted context including insights, summaries, and active turns.
    """
    memory = await session_pool.get(user_id, agent_id, session_id)
    if not memory:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found: {session_id}"
        )
    
    try:
        context = await memory.get_context()
        # Get turn count from orchestrator if available
        turn_count = 0
        if hasattr(memory, "_orchestrator") and memory._orchestrator:
            turn_count = memory._orchestrator.turn_count
        
        return GetContextResponse(
            context=context,
            turn_count=turn_count
        )
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions/end", response_model=EndSessionResponse)
async def end_session(request: EndSessionRequest, background_tasks: BackgroundTasks):
    """
    End a session.
    
    Triggers reflection (insight extraction) and long-term synthesis in background.
    """
    memory = await session_pool.get(request.user_id, request.agent_id, request.session_id)
    if not memory:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found: {request.session_id}"
        )
    
    try:
        # End session (triggers reflection + synthesis)
        result = await memory.end_session(
            trigger_reflection=request.trigger_reflection
        )
        
        # Remove from pool in background
        background_tasks.add_task(
            session_pool.remove,
            request.user_id,
            request.agent_id,
            request.session_id,
        )
        
        return EndSessionResponse(
            success=True,
            summary=result.get("session_summary", ""),
            insights_count=len(result.get("insights_extracted", [])),
            synthesis_triggered=result.get("synthesis_triggered", False)
        )
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", response_model=SearchResponse)
async def search_memory(request: SearchRequest):
    """
    Search memory for relevant information.
    
    Creates a temporary session if needed, searches, then cleans up.
    """
    try:
        memory = await session_pool.create_ephemeral(request.user_id, request.agent_id, session_id=f"search-{uuid.uuid4()}")
        try:
            results = await memory.search(
                query=request.query,
                top_k=request.top_k,
                search_interactions=request.search_interactions,
                search_insights=request.search_insights,
                search_summaries=request.search_summaries,
                search_mode=request.search_mode,
            )
        finally:
            await memory.close()
        
        return SearchResponse(
            results=results,
            query=request.query
        )
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/insights")
async def get_user_insights(user_id: str, limit: int = 10, agent_id: str = "default"):
    """Get long-term insights for a user."""
    try:
        memory = await session_pool.create_ephemeral(user_id, agent_id, session_id=f"insights-{uuid.uuid4()}")
        try:
            insights = await memory.get_insights(limit=limit)
        finally:
            await memory.close()
        
        return {"user_id": user_id, "insights": insights}
    except Exception as e:
        logger.error(f"Error getting insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/sessions")
async def get_user_sessions(user_id: str, limit: int = 10, agent_id: str = "default"):
    """Get recent sessions for a user."""
    try:
        memory = await session_pool.create_ephemeral(user_id, agent_id, session_id=f"sessions-{uuid.uuid4()}")
        try:
            sessions = await memory.get_sessions(limit=limit)
        finally:
            await memory.close()
        
        return {"user_id": user_id, "sessions": sessions}
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Run with uvicorn
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    config = get_config()

    uvicorn.run(
        "server.main:app",
        host=config.host,
        port=config.port,
        reload=config.reload
    )
