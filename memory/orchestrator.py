"""
Memory Service Orchestrator.

This is the main integration layer that coordinates:
- Current Memory Keeper: Short-term working memory
- CFR Agent: Contextual fact retrieval
- Reflection Process: Insight extraction and synthesis

Provides a unified API for agent interactions with memory.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid
from azure.cosmos import ContainerProxy
from openai import AzureOpenAI

from memory.config import MemoryConfig
from memory.cosmos_utils import CosmosUtils
from memory.current_memory_keeper import CurrentMemoryKeeper
from memory.fact_retrieval import ContextualFactRetrieval
from memory.reflection import ReflectionProcess
from memory.models import ConversationTurn


class MemoryServiceOrchestrator:
    """
    Main orchestration layer for Agent Memory Service.
    
    This class provides the primary API for agents to:
    1. Initialize sessions with relevant context from previous sessions
    2. Process new turns and maintain working memory
    3. Retrieve contextual facts on-demand
    4. Trigger reflection at session end
    
    Usage:
        orchestrator = MemoryServiceOrchestrator(user_id, session_id, ...)
        
        # Session start
        initial_context = await orchestrator.initialize_session()
        
        # During conversation
        await orchestrator.process_turn(user_msg, agent_msg)
        context = await orchestrator.retrieve_facts("What did we discuss about 401k?")
        
        # Session end
        await orchestrator.end_session()
    """
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        config: MemoryConfig,
        cosmos_utils: CosmosUtils,
        interactions_container: ContainerProxy,
        summaries_container: ContainerProxy,
        insights_container: ContainerProxy,
        chat_client: AzureOpenAI
    ):
        """
        Initialize Memory Service Orchestrator.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            config: Memory configuration
            cosmos_utils: Cosmos utilities for embeddings
            interactions_container: Container for interactions
            summaries_container: Container for session summaries
            insights_container: Container for insights
            chat_client: Azure OpenAI client
        """
        self.user_id = user_id
        self.session_id = session_id
        self.config = config
        self.cosmos_utils = cosmos_utils
        
        # Store container references
        self.interactions_container = interactions_container
        self.summaries_container = summaries_container
        self.insights_container = insights_container
        
        # Initialize components
        self.memory_keeper = CurrentMemoryKeeper(
            user_id=user_id,
            session_id=session_id,
            interactions_container=interactions_container,
            summaries_container=summaries_container,
            insights_container=insights_container,
            cosmos_utils=cosmos_utils,
            chat_client=chat_client,
            config=config
        )
        
        self.cfr_agent = ContextualFactRetrieval(
            config=config,
            cosmos_utils=cosmos_utils,
            user_id=user_id,
            interactions_container=interactions_container,
            summaries_container=summaries_container,
            insights_container=insights_container
        )
        
        self.reflection = ReflectionProcess(
            config=config,
            cosmos_utils=cosmos_utils,
            insights_container=insights_container,
            summaries_container=summaries_container,
            interactions_container=interactions_container,
            chat_client=chat_client
        )
        
        print(f"[Orchestrator] Initialized for user {user_id}, session {session_id}")
    
    async def restore_session(self, session_id: str) -> Dict[str, Any]:
        """
        Restore an existing session from CosmosDB.
        
        This loads:
        1. Session metadata (cumulative summary, turn count)
        2. Active turns from most recent interaction chunks
        3. Long-term insights and recent session summaries
        
        Args:
            session_id: The session ID to restore
        
        Returns:
            Dictionary with restored session context
        
        Raises:
            ValueError: If session not found or not in active state
        """
        print(f"[Orchestrator] Restoring session {session_id}")
        
        # Query session metadata
        query = "SELECT * FROM c WHERE c.id = @session_id AND c.user_id = @user_id"
        parameters = [
            {"name": "@session_id", "value": session_id},
            {"name": "@user_id", "value": self.user_id}
        ]
        
        results = self.cosmos_utils.query_documents(
            container=self.summaries_container,
            query=query,
            parameters=parameters
        )
        
        if not results:
            raise ValueError(f"Session {session_id} not found for user {self.user_id}")
        
        session_meta = results[0]
        
        if session_meta.get("status") != "active":
            raise ValueError(
                f"Session {session_id} is not active (status: {session_meta.get('status')}). "
                f"Can only restore active sessions."
            )
        
        # Restore cumulative summary
        cumulative_summary = session_meta.get("cumulative_summary", "")
        self.memory_keeper.cumulative_summary = cumulative_summary
        
        # Restore turn buffer from most recent interaction chunks
        query = """
        SELECT * FROM c 
        WHERE c.user_id = @user_id 
          AND c.session_id = @session_id 
        ORDER BY c.timestamp DESC
        OFFSET 0 LIMIT 2
        """
        
        interaction_docs = self.cosmos_utils.query_documents(
            container=self.interactions_container,
            query=query,
            parameters=parameters
        )
        
        # Reconstruct turn buffer from interaction documents
        # Note: We only restore up to ~K turns from recent chunks
        restored_turns = []
        for doc in reversed(interaction_docs):  # Chronological order
            content = doc.get("content", "")
            # Parse the flattened format: "user: ...\nassistant: ...\n"
            for line in content.split("\n"):
                if line.startswith("user: "):
                    restored_turns.append(ConversationTurn(
                        role="user",
                        content=line[6:],  # Remove "user: " prefix
                        timestamp=doc.get("timestamp", "")
                    ))
                elif line.startswith("assistant: "):
                    restored_turns.append(ConversationTurn(
                        role="assistant",
                        content=line[11:],  # Remove "assistant: " prefix
                        timestamp=doc.get("timestamp", "")
                    ))
        
        # Keep only last K turns
        self.memory_keeper.turn_buffer = restored_turns[-self.config.K_TURN_BUFFER:]
        
        # Load standard session init context (insights + recent summaries)
        session_init_context = await self.memory_keeper.initialize_session_context()
        
        print(f"  ✓ Session restored")
        print(f"    - Cumulative summary: {len(cumulative_summary)} chars")
        print(f"    - Restored turns: {len(self.memory_keeper.turn_buffer)}")
        print(f"    - Insights: {1 if session_init_context.longterm_insight else 0}")
        print(f"    - Session summaries: {len(session_init_context.recent_summaries)}")
        
        return {
            "active_context": [
                {"role": t.role, "content": t.content}
                for t in self.memory_keeper.turn_buffer
            ],
            "cumulative_summary": cumulative_summary,
            "insights": [session_init_context.longterm_insight] if session_init_context.longterm_insight else [],
            "session_summaries": session_init_context.recent_summaries,
            "formatted_context": session_init_context.formatted_context,
            "restored": True,
            "turn_count": len(self.memory_keeper.turn_buffer)
        }
    
    async def initialize_session(self) -> Dict[str, Any]:
        """
        Initialize a new session with context from previous sessions.
        
        Returns:
            Dictionary containing:
            - active_context: List of recent turns to include in prompt
            - cumulative_summary: Summary of earlier parts of previous sessions
            - insights: Relevant long-term insights about the user
            - session_summaries: Summaries of recent complete sessions
        """
        print(f"[Orchestrator] Initializing session {self.session_id}")
        
        # Create "active" session marker in database for future restoration
        session_doc = {
            "id": self.session_id,
            "user_id": self.user_id,
            "start_time": datetime.utcnow().isoformat(),
            "status": "active",
            "cumulative_summary": "",
            "turn_count": 0
        }
        
        self.cosmos_utils.upsert_document(
            container=self.summaries_container,
            document=session_doc
        )
        
        # Use Current Memory Keeper to initialize
        session_init_context = await self.memory_keeper.initialize_session_context()
        
        # Convert to dict format for API
        initial_context = {
            "active_context": [],  # Empty at session start
            "cumulative_summary": None,  # None at session start
            "insights": [session_init_context.longterm_insight] if session_init_context.longterm_insight else [],
            "session_summaries": session_init_context.recent_summaries,
            "formatted_context": session_init_context.formatted_context
        }
        
        print(f"  ✓ Session initialized")
        print(f"    - Active turns: {len(initial_context.get('active_context', []))}")
        print(f"    - Cumulative_summary: {'Yes' if initial_context.get('cumulative_summary') else 'No'}")
        print(f"    - Insights: {len(initial_context.get('insights', []))}")
        print(f"    - Session summaries: {len(initial_context.get('session_summaries', []))}")
        
        return initial_context
    
    async def process_turn(
        self,
        user_message: str,
        agent_message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a new conversation turn.
        
        This:
        1. Adds the turn to working memory
        2. Generates metadata (topics, entities, summary)
        3. Stores the interaction with embeddings
        4. Triggers summarization if buffer threshold reached
        
        Args:
            user_message: User's message
            agent_message: Agent's response
            metadata: Optional metadata to attach to the turn
            
        Returns:
            Dictionary with status and any warnings/actions taken
        """
        print(f"[Orchestrator] Processing turn for session {self.session_id}")
        
        # Add user and agent turns to memory keeper
        # Note: role must be "assistant" (not "agent") per ConversationTurn model
        self.memory_keeper.add_turn(role="user", content=user_message)
        self.memory_keeper.add_turn(role="assistant", content=agent_message)
        
        # Check if summarization was triggered
        summarization_result = await self.memory_keeper.maybe_prune()
        
        status = {
            "turn_added": True,
            "interaction_id": None,  # Interactions are created during pruning or session end
            "summarization_triggered": summarization_result is not None,
            "active_turns_count": len(self.memory_keeper.turn_buffer)
        }
        
        if summarization_result:
            status["interaction_id"] = summarization_result.get("interaction_id")
        
        print(f"  ✓ Turn processed")
        if status['interaction_id']:
            print(f"    - Interaction ID: {status['interaction_id']}")
        print(f"    - Summarization: {'Yes' if status['summarization_triggered'] else 'No'}")
        print(f"    - Active turns: {status['active_turns_count']}")
        
        return status
    
    async def retrieve_facts(self, query: str) -> str:
        """
        Retrieve contextual facts using the CFR agent.
        
        The CFR agent intelligently searches across:
        - Past interactions
        - Session summaries
        - Long-term insights
        
        Args:
            query: Natural language query for retrieval
            
        Returns:
            Synthesized response from CFR agent
        """
        print(f"[Orchestrator] Retrieving facts for query: {query[:50]}...")
        
        # Use CFR agent for intelligent retrieval
        response = await self.cfr_agent.retrieve(query)
        
        print(f"  ✓ Facts retrieved")
        
        return response
    
    async def get_current_context(self) -> Dict[str, Any]:
        """
        Get the current working memory context.
        
        Returns:
            Dictionary containing:
            - active_turns: Recent conversation turns
            - cumulative_summary: Summary of older conversation
            - buffer_status: Current buffer usage
        """
        return {
            "active_turns": [
                {"role": turn.role, "content": turn.content}
                for turn in self.memory_keeper.turn_buffer
            ],
            "cumulative_summary": self.memory_keeper.cumulative_summary,
            "buffer_status": {
                "current_size": len(self.memory_keeper.turn_buffer),
                "max_size": self.config.K_TURN_BUFFER,
                "will_summarize_soon": len(self.memory_keeper.turn_buffer) >= self.config.K_TURN_BUFFER - 1
            }
        }
    
    async def end_session(self, trigger_reflection: bool = True) -> Dict[str, Any]:
        """
        End the current session.
        
        This:
        1. Performs comprehensive session analysis (summary + topics + insights via reflection)
        2. Stores session summary and insights to CosmosDB
        3. Returns complete analysis
        
        Args:
            trigger_reflection: Whether to trigger reflection process
            
        Returns:
            Dictionary containing:
            - session_summary: Summary of the entire session
            - key_topics: List of key topics discussed
            - insights_extracted: List of insights
            - total_turns: Number of turns in session
        """
        import time
        start_time = time.time()
        print(f"[Orchestrator] Ending session {self.session_id}")
        
        # IMPORTANT: Extract turns BEFORE final_prune clears the buffer
        recent_turns = [(turn.role, turn.content) for turn in self.memory_keeper.turn_buffer]
        
        # Final prune any remaining turns (this clears the buffer)
        await self.memory_keeper.final_prune()
        
        # Perform comprehensive session analysis via reflection
        analysis_start = time.time()
        
        analysis = await self.reflection.reflect_on_session(
            user_id=self.user_id,
            session_id=self.session_id,
            cumulative_summary=self.memory_keeper.cumulative_summary,
            recent_turns=recent_turns
        )
        analysis_duration = time.time() - analysis_start
        print(f"  ⏱ Session analysis took {analysis_duration:.2f}s")
        
        # Generate embedding for session summary
        embedding_start = time.time()
        summary_embedding = self.cosmos_utils.get_embedding(analysis["session_summary"])
        embedding_duration = time.time() - embedding_start
        print(f"  ⏱ Generate embedding: {embedding_duration:.2f}s")
        
        # Create session summary document
        summary_doc = {
            "id": self.session_id,
            "user_id": self.user_id,
            "start_time": datetime.utcnow().isoformat(),  # TODO: Track actual start time
            "end_time": datetime.utcnow().isoformat(),
            "summary": analysis["session_summary"],
            "summary_vector": summary_embedding,
            "key_topics": analysis["key_topics"],
            "extracted_insights": analysis["insights"],
            "status": "completed",
            "reflection_status": "completed" if analysis["has_meaningful_insights"] else "no_insights"
        }
        
        # Store session summary
        store_start = time.time()
        self.cosmos_utils.upsert_document(
            container=self.summaries_container,
            document=summary_doc
        )
        store_duration = time.time() - store_start
        print(f"  ⏱ Store session summary: {store_duration:.2f}s")
        
        # Store insights in insights container for retrieval
        if analysis["insights"] and trigger_reflection:
            insights_start = time.time()
            for insight in analysis["insights"]:
                # Generate embedding for insight
                insight_embedding = self.cosmos_utils.get_embedding(insight["insight_text"])
                
                # Create insight document
                insight_doc = {
                    "id": insight["id"],
                    "user_id": self.user_id,
                    "session_id": self.session_id,
                    "insight_text": insight["insight_text"],
                    "insight_vector": insight_embedding,
                    "category": insight["category"],
                    "confidence": insight["confidence"],
                    "importance": insight["importance"],
                    "extracted_at": insight["extracted_at"],
                    "evidence": {
                        "session_summary": analysis["session_summary"],
                        "key_topics": analysis["key_topics"]
                    }
                }
                
                # Store in insights container
                self.cosmos_utils.upsert_document(
                    container=self.insights_container,
                    document=insight_doc
                )
            
            insights_duration = time.time() - insights_start
            print(f"  ⏱ Store insights: {insights_duration:.2f}s")
            print(f"    ✓ Stored {len(analysis['insights'])} insights to CosmosDB")
        
        result = {
            "session_id": self.session_id,
            "session_summary": analysis["session_summary"],
            "key_topics": analysis["key_topics"],
            "total_turns": len(self.memory_keeper.turn_buffer),
            "insights_extracted": analysis["insights"]
        }
        
        total_duration = time.time() - start_time
        print(f"  ✓ Session ended (total time: {total_duration:.2f}s)")
        print(f"    - Summary: {result['session_summary'][:100]}...")
        print(f"    - Topics: {', '.join(result['key_topics'][:3])}")
        print(f"    - Insights: {len(analysis['insights'])} extracted")
        print(f"    - Turns: {result['total_turns']}")
        
        return result
    
    async def synthesize_long_term_patterns(
        self,
        category: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Manually trigger long-term pattern synthesis.
        
        This combines multiple related insights into higher-level patterns.
        Typically called periodically (e.g., weekly) rather than after each session.
        
        Args:
            category: Optional category to focus on (e.g., "preferences")
            
        Returns:
            Synthesized insight or None if insufficient data
        """
        print(f"[Orchestrator] Synthesizing long-term patterns for user {self.user_id}")
        
        synthesized = await self.reflection.synthesize_long_term_patterns(
            user_id=self.user_id,
            category=category
        )
        
        if synthesized:
            print(f"  ✓ Synthesized insight: {synthesized['insight_text'][:100]}...")
        else:
            print(f"  ℹ No synthesis created")
        
        return synthesized
    
    async def get_user_insights(
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
        query = """
        SELECT TOP @limit *
        FROM c
        WHERE c.user_id = @user_id
        """
        parameters = [
            {"name": "@limit", "value": limit},
            {"name": "@user_id", "value": self.user_id}
        ]
        
        if category:
            query += " AND c.category = @category"
            parameters.append({"name": "@category", "value": category})
        
        query += " ORDER BY c.last_updated DESC"
        
        insights = list(self.reflection.insights_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=False
        ))
        
        return insights
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the memory service.
        
        Returns:
            Dictionary with status information
        """
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "active_turns": len(self.memory_keeper.turn_buffer),
            "buffer_capacity": self.config.K_TURN_BUFFER,
            "has_cumulative_summary": bool(self.memory_keeper.cumulative_summary),
            "components": {
                "memory_keeper": "active",
                "cfr_agent": "active",
                "reflection": "active"
            }
        }
