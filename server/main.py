"""
FastAPI Memory Service - RESTful API for Agent Memory.

Provides memory-only endpoints that can be called from any language.
Manages session pooling and shared resources (CosmosDB, OpenAI clients).

Client applications own the agent/chat logic, this service only provides memory state.
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import AzureOpenAI, OpenAI
from azure.cosmos import CosmosClient

from server.config import get_config
from memory.config import MemoryConfig
from memory.cosmos_utils import CosmosUtils
from memory.session_pool import SessionPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global resources (shared across all sessions)
session_pool: Optional[SessionPool] = None
background_tasks_running = False
ending_sessions: Dict[str, Dict[str, Any]] = {}  # Track sessions ending in background: {session_id: {status, start_time, user_id}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle:
    - Startup: Initialize shared resources and session pool
    - Shutdown: Gracefully persist sessions and cleanup
    """
    global session_pool, background_tasks_running
    
    logger.info("🚀 Starting Memory Service...")
    
    # Load configuration
    server_config = get_config()
    
    # Initialize Azure OpenAI client (shared) - uses v1 endpoint for new SDK
    chat_client = OpenAI(
        base_url=server_config.azure_openai_endpoint_v1,
        api_key=server_config.azure_openai_api_key,
    )
    logger.info(f"✓ Azure OpenAI client initialized: {server_config.azure_openai_reasoning_model}")
    
    # Initialize Cosmos DB client (shared)
    # Try authentication methods in order: Key -> Service Principal -> Managed Identity
    if server_config.cosmos_key:
        # Option 1: Key-based authentication
        cosmos_client = CosmosClient(
            server_config.COSMOS_ENDPOINT,
            server_config.cosmos_key
        )
        logger.info("✓ CosmosDB using key-based authentication")
    elif all([server_config.aad_client_id, server_config.aad_client_secret, server_config.aad_tenant_id]):
        # Option 2: Service Principal authentication
        from azure.identity import ClientSecretCredential
        credential = ClientSecretCredential(
            tenant_id=server_config.aad_tenant_id,
            client_id=server_config.aad_client_id,
            client_secret=server_config.aad_client_secret
        )
        cosmos_client = CosmosClient(server_config.COSMOS_ENDPOINT, credential=credential)
        logger.info("✓ CosmosDB using Service Principal authentication")
    else:
        # Option 3: Managed Identity / Default Azure Credential
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        cosmos_client = CosmosClient(server_config.COSMOS_ENDPOINT, credential=credential)
        logger.info("✓ CosmosDB using Managed Identity authentication")
    
    database = cosmos_client.get_database_client(server_config.cosmos_db_name)
    
    interactions_container = database.get_container_client(
        server_config.cosmos_interactions_container
    )
    summaries_container = database.get_container_client(
        server_config.cosmos_summaries_container
    )
    insights_container = database.get_container_client(
        server_config.cosmos_insights_container
    )
    logger.info(f"✓ Cosmos DB containers initialized: {server_config.cosmos_db_name}")
    
    # Initialize embeddings client (same endpoint and key)
    embedding_client = OpenAI(
        base_url=server_config.azure_openai_endpoint_v1,
        api_key=server_config.azure_openai_api_key,
    )
    
    # Initialize CosmosUtils with embeddings
    cosmos_utils = CosmosUtils(
        embedding_client=embedding_client,
        embedding_deployment=server_config.azure_openai_emb_deployment
    )
    logger.info(f"✓ CosmosUtils initialized with embeddings: {server_config.azure_openai_emb_deployment}")
    
    # Create memory config
    memory_config = MemoryConfig(
        buffer_size=server_config.K_TURN_BUFFER,
        active_turns=server_config.K_TURN_BUFFER,
        num_recent_sessions_for_init=server_config.M_SESSIONS_RECENT,
        database_name=server_config.cosmos_db_name,
        interactions_container=server_config.cosmos_interactions_container,
        summaries_container=server_config.cosmos_summaries_container,
        insights_container=server_config.cosmos_insights_container,
        reasoning_model=server_config.azure_openai_reasoning_model,
        processing_model=server_config.azure_openai_processing_model,
        longterm_synthesis_frequency=server_config.longterm_synthesis_frequency
    )
    
    # Initialize session pool
    session_pool = SessionPool(
        config=memory_config,
        cosmos_utils=cosmos_utils,
        interactions_container=interactions_container,
        summaries_container=summaries_container,
        insights_container=insights_container,
        chat_client=chat_client,
        max_sessions=server_config.max_sessions,
        session_ttl_minutes=server_config.session_ttl_minutes
    )
    logger.info(
        f"✓ Session pool initialized: max={server_config.max_sessions}, "
        f"ttl={server_config.session_ttl_minutes}min"
    )
    
    # Start background eviction task
    background_tasks_running = True
    eviction_task = asyncio.create_task(
        background_eviction_loop(server_config.eviction_interval_seconds)
    )
    
    logger.info("✅ Memory Service ready!")
    
    yield  # Server runs here
    
    # Shutdown
    logger.info("🛑 Shutting down Memory Service...")
    background_tasks_running = False
    await eviction_task
    
    if session_pool:
        await session_pool.shutdown()
    
    logger.info("✅ Memory Service shutdown complete")


async def background_eviction_loop(interval_seconds: int):
    """Background task to periodically evict stale sessions."""
    global session_pool, background_tasks_running
    
    logger.info(f"Starting background eviction task (interval: {interval_seconds}s)")
    
    while background_tasks_running:
        await asyncio.sleep(interval_seconds)
        
        if session_pool:
            try:
                await session_pool.evict_stale_sessions()
            except Exception as e:
                logger.error(f"Error during session eviction: {e}", exc_info=True)
    
    logger.info("Background eviction task stopped")


# Create FastAPI app
app = FastAPI(
    title="Agent Memory Service",
    description="RESTful memory-only API for conversational agents",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Request/Response Models
# ============================================================================

class SessionStartRequest(BaseModel):
    """Request to start a new session."""
    user_id: str
    session_id: Optional[str] = None  # Auto-generated if not provided
    restore: bool = True  # Attempt to restore if session exists


class SessionStartResponse(BaseModel):
    """Response containing initial session context."""
    session_id: str
    user_id: str
    active_context: List[Dict[str, str]]
    cumulative_summary: str
    insights: List[str]
    session_summaries: List[str]
    formatted_context: str
    restored: bool  # True if restored from CosmosDB


class SessionEndRequest(BaseModel):
    """Request to end a session."""
    user_id: str
    session_id: str


class StoreTurnRequest(BaseModel):
    """Request to store a conversation turn."""
    user_id: str
    session_id: str
    user_message: str
    agent_message: str


class GetContextRequest(BaseModel):
    """Request to get current session context."""
    user_id: str
    session_id: str
    # Optional configuration to control what context is returned
    include_longterm_insights: bool = True
    include_recent_sessions: bool = True
    include_cumulative_summary: bool = True
    include_active_turns: bool = True


class RetrieveFactsRequest(BaseModel):
    """Request to retrieve contextual facts."""
    user_id: str
    session_id: str
    query: str
    top_k: int = 5
    include_summaries: bool = False
    include_insights: bool = False


class GetInsightsRequest(BaseModel):
    """Request to get user insights."""
    user_id: str
    recent_only: bool = False


class GetSummariesRequest(BaseModel):
    """Request to get session summaries."""
    user_id: str
    limit: int = 5


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "agent-memory",
        "version": "1.0.0"
    }


@app.get("/stats")
async def get_stats():
    """Get session pool statistics."""
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    return session_pool.get_stats()


# ============================================================================
# Session Management
# ============================================================================

@app.post("/sessions/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """
    Start a new session or restore existing one.
    
    - If session_id is provided and exists in CosmosDB: restore it
    - If session_id is provided but not found: create new session with that ID
    - If session_id is not provided: auto-generate new session ID
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    # Auto-generate session_id if not provided
    import uuid
    session_id = request.session_id or str(uuid.uuid4())
    
    try:
        # Get or create session in pool
        session_state = await session_pool.get_or_create(
            user_id=request.user_id,
            session_id=session_id,
            restore=request.restore
        )
        
        # Get initial context
        orchestrator = session_state.orchestrator
        context = await orchestrator.get_current_context()
        
        # Determine if this was a restoration
        restored = len(context.get("active_turns", [])) > 0
        
        return SessionStartResponse(
            session_id=session_id,
            user_id=request.user_id,
            active_context=context.get("active_turns", []),
            cumulative_summary=context.get("cumulative_summary", ""),
            insights=[],  # Will be populated during session
            session_summaries=[],  # Will be populated during session
            formatted_context="",  # Not used in orchestrator
            restored=restored
        )
    
    except Exception as e:
        logger.error(f"Error starting session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions/end")
async def end_session(request: SessionEndRequest, background_tasks: BackgroundTasks):
    """
    End a session and trigger reflection in background.
    
    This:
    1. Triggers final reflection process (in background)
    2. Persists session state to CosmosDB (in background)
    3. Removes session from pool (in background)
    4. Returns immediately without waiting for synthesis
    
    Note: Long-term insight synthesis can take 30+ seconds, so we run it in background
    to avoid client timeouts. The session is still fully persisted and reflected.
    Use GET /sessions/status?session_id=... to check if background processing is complete.
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    try:
        # Get session from pool
        session_state = await session_pool.get_or_create(
            user_id=request.user_id,
            session_id=request.session_id,
            restore=False  # Don't restore, we're ending it
        )
        
        orchestrator = session_state.orchestrator
        
        # Get turn count before ending
        turns_count = len(orchestrator.memory_keeper.turn_buffer)
        
        # Track that this session is ending in background
        from datetime import datetime
        ending_sessions[request.session_id] = {
            "status": "processing",
            "start_time": datetime.utcnow().isoformat(),
            "user_id": request.user_id
        }
        
        # Define background task to end session
        async def _end_session_background():
            """Background task to end session with full reflection and synthesis."""
            try:
                logger.info(f"[Background] Ending session {request.session_id} for user {request.user_id}")
                summary_result = await orchestrator.end_session()
                
                # Remove from pool (no persistence needed - session just ended with full summary)
                await session_pool.remove(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    persist=False  # Session already fully persisted by end_session()
                )
                
                # Update status to complete
                ending_sessions[request.session_id] = {
                    "status": "complete",
                    "end_time": datetime.utcnow().isoformat(),
                    "user_id": request.user_id,
                    "insights_count": len(summary_result.get('insights', [])) if summary_result else 0
                }
                
                logger.info(
                    f"[Background] ✓ Session {request.session_id} ended. "
                    f"Insights: {len(summary_result.get('insights', [])) if summary_result else 0}"
                )
            except Exception as e:
                # Update status to error
                ending_sessions[request.session_id] = {
                    "status": "error",
                    "error": str(e),
                    "end_time": datetime.utcnow().isoformat(),
                    "user_id": request.user_id
                }
                logger.error(f"[Background] Error ending session {request.session_id}: {e}", exc_info=True)
        
        # Add to background tasks
        background_tasks.add_task(_end_session_background)
        
        # Return immediately
        return {
            "status": "ending",
            "message": f"Session {request.session_id} ending in background (reflection and synthesis may take 30+ seconds)",
            "turns_count": turns_count,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "check_status_url": f"/sessions/status?session_id={request.session_id}"
        }
    
    except Exception as e:
        logger.error(f"Error initiating session end: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/status")
async def get_session_status(session_id: str):
    """
    Check the status of a session ending in background.
    
    Returns:
        - status: "processing" | "complete" | "error" | "not_found"
        - Additional info about timing and results
    
    Use this to poll after calling POST /sessions/end to know when
    long-term synthesis has completed.
    """
    if session_id in ending_sessions:
        return ending_sessions[session_id]
    else:
        return {
            "status": "not_found",
            "message": f"Session {session_id} not found in background processing queue. It may have already completed and been cleaned up, or never started."
        }


# ============================================================================
# Memory Operations
# ============================================================================

@app.post("/memory/store")
async def store_turn(request: StoreTurnRequest):
    """
    Store a conversation turn in memory.
    
    This updates the session's working memory and may trigger chunking
    if the turn buffer is full.
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    try:
        # Get session
        session_state = await session_pool.get_or_create(
            user_id=request.user_id,
            session_id=request.session_id,
            restore=True
        )
        
        # Process turn
        orchestrator = session_state.orchestrator
        await orchestrator.process_turn(request.user_message, request.agent_message)
        
        # Mark dirty for persistence
        session_state.mark_dirty()
        
        return {
            "status": "success",
            "message": "Turn stored successfully"
        }
    
    except Exception as e:
        logger.error(f"Error storing turn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/context")
async def get_context(request: GetContextRequest):
    """
    Get current session context for prompt injection.
    
    Returns:
    - active_context: Recent turns to include in prompt
    - cumulative_summary: Summary of earlier conversation
    - insights: Relevant long-term insights
    - session_summaries: Summaries of recent sessions
    - formatted_context: Ready-to-inject formatted string
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    try:
        # Get session
        session_state = await session_pool.get_or_create(
            user_id=request.user_id,
            session_id=request.session_id,
            restore=True
        )
        
        # Get context from orchestrator
        orchestrator = session_state.orchestrator
        memory_keeper = orchestrator.memory_keeper
        context_dict = await orchestrator.get_current_context()
        
        # Build response with proper field names
        active_turns = context_dict.get("active_turns", [])
        cumulative_summary = context_dict.get("cumulative_summary", "")
        
        # Get session initialization context (insights and summaries)
        init_context = memory_keeper.session_init_context
        
        # Extract insights and session summaries from init_context
        insights = []
        session_summaries = []
        
        if init_context:
            # Long-term insights
            if init_context.longterm_insight:
                insights.append({
                    "content": init_context.longterm_insight,
                    "type": "longterm"
                })
            
            # Recent session summaries
            if init_context.recent_summaries:
                session_summaries = [
                    {
                        "session_id": s.get("session_id", ""),
                        "summary": s.get("summary", ""),
                        "timestamp": s.get("end_time", None),
                        "topics": s.get("key_topics", [])
                    }
                    for s in init_context.recent_summaries
                ]
        
        # Format the context string for injection (matching embedded provider format)
        # Respect client configuration for what to include
        formatted_parts = []
        
        # Add long-term insights (if enabled)
        if request.include_longterm_insights and init_context and init_context.longterm_insight:
            formatted_parts.append(f"### Long-term Context\n{init_context.longterm_insight}")
        
        # Add recent session summaries (if enabled)
        if request.include_recent_sessions and init_context and init_context.recent_summaries:
            formatted_parts.append("### Recent Sessions")
            for session in init_context.recent_summaries:
                session_id = session.get("session_id", "unknown")
                summary = session.get("summary", "")
                topics = session.get("key_topics", [])
                formatted_parts.append(f"- Session {session_id}: {summary}")
                if topics:
                    formatted_parts.append(f"  Topics: {', '.join(topics)}")
        
        # Add cumulative summary (if enabled)
        if request.include_cumulative_summary and cumulative_summary:
            formatted_parts.append(f"### Current Session Summary\n{cumulative_summary}")
        
        # Add active turns (if enabled)
        if request.include_active_turns and active_turns:
            formatted_parts.append("### Recent Conversation")
            for turn in active_turns:
                role = turn.get("role", "").upper()
                content = turn.get("content", "")
                formatted_parts.append(f"{role}: {content}")
        
        formatted_context = "\n\n".join(formatted_parts) if formatted_parts else ""
        
        return {
            "active_context": active_turns,
            "cumulative_summary": cumulative_summary,
            "insights": insights,
            "session_summaries": session_summaries,
            "formatted_context": formatted_context
        }
    
    except Exception as e:
        logger.error(f"Error getting context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/retrieve")
async def retrieve_facts(request: RetrieveFactsRequest):
    """
    Retrieve contextual facts using semantic search.
    
    Searches across:
    - Past interactions (always included)
    - Session summaries (optional, set include_summaries=true)
    - User insights (optional, set include_insights=true)
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    try:
        # Get session
        session_state = await session_pool.get_or_create(
            user_id=request.user_id,
            session_id=request.session_id,
            restore=True
        )
        
        # Retrieve facts
        orchestrator = session_state.orchestrator
        facts = await orchestrator.retrieve_facts(
            request.query,
            include_summaries=request.include_summaries,
            include_insights=request.include_insights
        )
        
        return {
            "query": request.query,
            "facts": facts,
            "count": len(facts)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving facts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Insights & Summaries
# ============================================================================

@app.get("/memory/insights")
async def get_insights_get(user_id: str, session_id: str = None, recent_only: bool = False):
    """
    Get user insights (long-term learnings about the user) via GET.
    
    Args:
        user_id: User identifier
        session_id: Optional session_id to filter insights to a specific session
        recent_only: If True, only return insights from recent sessions
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    try:
        # We need a temporary orchestrator to access insights
        # (insights are user-level, not session-specific)
        import uuid
        temp_session_id = str(uuid.uuid4())
        
        session_state = await session_pool.get_or_create(
            user_id=user_id,
            session_id=temp_session_id,
            restore=False
        )
        
        orchestrator = session_state.orchestrator
        
        # Query insights
        query = """
        SELECT * FROM c 
        WHERE c.user_id = @user_id
        ORDER BY c.timestamp DESC
        """
        
        parameters = [{"name": "@user_id", "value": user_id}]
        
        if session_id:
            query = query.replace(
                "ORDER BY",
                "AND c.session_id = @session_id ORDER BY"
            )
            parameters.append({"name": "@session_id", "value": session_id})
        
        if recent_only:
            query = query.replace(
                "ORDER BY",
                "AND c.timestamp > @cutoff ORDER BY"
            )
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
            parameters.append({"name": "@cutoff", "value": cutoff})
        
        insights = orchestrator.cosmos_utils.query_documents(
            container=orchestrator.insights_container,
            query=query,
            parameters=parameters
        )
        
        # Clean up temporary session
        await session_pool.remove(user_id, temp_session_id, persist=False)
        
        return [
            {
                "content": insight.get("content") or insight.get("insight_text", ""),
                "timestamp": insight.get("timestamp", ""),
                "session_id": insight.get("session_id", ""),
                "insight_type": insight.get("insight_type", "session"),
                "confidence": insight.get("confidence"),
                "category": insight.get("category")
            }
            for insight in insights
        ]
        
    except Exception as e:
        logger.error(f"Error getting insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/insights")
async def get_insights(request: GetInsightsRequest):
    """
    Get user insights (long-term learnings about the user).
    
    Args:
        user_id: User identifier
        recent_only: If True, only return insights from recent sessions
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    try:
        # We need a temporary orchestrator to access insights
        # (insights are user-level, not session-specific)
        import uuid
        temp_session_id = str(uuid.uuid4())
        
        session_state = await session_pool.get_or_create(
            user_id=request.user_id,
            session_id=temp_session_id,
            restore=False
        )
        
        orchestrator = session_state.orchestrator
        
        # Query insights
        query = """
        SELECT * FROM c 
        WHERE c.user_id = @user_id
        ORDER BY c.timestamp DESC
        """
        
        parameters = [{"name": "@user_id", "value": request.user_id}]
        
        if request.recent_only:
            query = query.replace(
                "ORDER BY",
                "AND c.timestamp > @cutoff ORDER BY"
            )
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
            parameters.append({"name": "@cutoff", "value": cutoff})
        
        insights = orchestrator.cosmos_utils.query_documents(
            container=orchestrator.insights_container,
            query=query,
            parameters=parameters
        )
        
        # Clean up temporary session
        await session_pool.remove(request.user_id, temp_session_id, persist=False)
        
        return {
            "user_id": request.user_id,
            "insights": [
                {
                    "content": insight.get("content", ""),
                    "timestamp": insight.get("timestamp", ""),
                    "session_id": insight.get("session_id", "")
                }
                for insight in insights
            ],
            "count": len(insights)
        }
    
    except Exception as e:
        logger.error(f"Error getting insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summaries")
async def get_summaries(request: GetSummariesRequest):
    """
    Get session summaries for a user.
    
    Returns summaries of completed sessions, ordered by recency.
    """
    if not session_pool:
        raise HTTPException(status_code=503, detail="Session pool not initialized")
    
    try:
        # We need a temporary orchestrator to access summaries
        import uuid
        temp_session_id = str(uuid.uuid4())
        
        session_state = await session_pool.get_or_create(
            user_id=request.user_id,
            session_id=temp_session_id,
            restore=False
        )
        
        orchestrator = session_state.orchestrator
        
        # Query summaries
        query = """
        SELECT * FROM c 
        WHERE c.user_id = @user_id
          AND c.status = 'completed'
        ORDER BY c.start_time DESC
        OFFSET 0 LIMIT @limit
        """
        
        parameters = [
            {"name": "@user_id", "value": request.user_id},
            {"name": "@limit", "value": request.limit}
        ]
        
        summaries = orchestrator.cosmos_utils.query_documents(
            container=orchestrator.summaries_container,
            query=query,
            parameters=parameters
        )
        
        # Clean up temporary session
        await session_pool.remove(request.user_id, temp_session_id, persist=False)
        
        return {
            "user_id": request.user_id,
            "summaries": [
                {
                    "session_id": s.get("id", ""),
                    "start_time": s.get("start_time", ""),
                    "end_time": s.get("end_time", ""),
                    "cumulative_summary": s.get("cumulative_summary", ""),
                    "turn_count": s.get("turn_count", 0)
                }
                for s in summaries
            ],
            "count": len(summaries)
        }
    
    except Exception as e:
        logger.error(f"Error getting summaries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )
