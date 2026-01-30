"""
Database-agnostic Fact Retrieval for Agent Memory Service.

This module implements an intelligent retrieval layer that searches across
memory documents (interactions, session summaries, insights) using Agent Framework.
The CFR agent can operate in:
- Synchronous mode: Auto-triggered when user references past information
- On-demand mode: Exposed as a tool the main agent can invoke

The agent has three search tools:
1. search_interactions - Search past conversation chunks
2. search_summaries - Search session summaries
3. search_insights - Search long-term insights
"""

from typing import List, Dict, Optional, Any, Annotated
from dataclasses import dataclass

from agent_framework import ChatAgent, tool
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

from memory.db.base import ContainerType, MemoryDatabase, SearchResult
from memory.providers.embedding import EmbeddingProvider


@dataclass
class FactRetrievalConfig:
    """Configuration for fact retrieval."""
    REASONING_MODEL: str = "gpt-4o"  # Model for agent reasoning
    DEFAULT_INTERACTIONS_LIMIT: int = 5
    DEFAULT_SUMMARIES_LIMIT: int = 3
    DEFAULT_INSIGHTS_LIMIT: int = 3


class FactRetrieval:
    """
    Database-agnostic Fact Retrieval for intelligent memory retrieval.
    
    Uses the MemoryDatabase interface to work with any backend
    (SQLite, CosmosDB, PostgreSQL).
    
    The agent uses three search tools to intelligently retrieve memory:
    1. search_interactions: Search past conversation chunks
    2. search_summaries: Search session summaries  
    3. search_insights: Search long-term insights
    """
    
    def __init__(
        self,
        user_id: str,
        database: MemoryDatabase,
        embedding_provider: EmbeddingProvider,
        config: Optional[FactRetrievalConfig] = None
    ):
        """
        Initialize fact retrieval with Agent Framework.
        
        Args:
            user_id: User identifier for memory retrieval
            database: Database backend implementing MemoryDatabase interface
            embedding_provider: Provider for generating embeddings
            config: Configuration settings (uses defaults if not provided)
        """
        self.user_id = user_id
        self.database = database
        self.embedding_provider = embedding_provider
        self.config = config or FactRetrievalConfig()
        
        # Create search tool functions with closure over self
        @tool(
            name="search_interactions",
            description="Search past conversation interactions for specific topics or details"
        )
        async def search_interactions_tool(
            query: Annotated[str, "The search query to find relevant past conversations"],
            max_results: Annotated[int, "Maximum number of results to return (default 5)"] = 5
        ) -> str:
            """Search past conversation interactions."""
            print(f"\n  🔎 [CFR] Searching interactions for: '{query}'")
            results = await self._search_interactions(query, max_results)
            formatted = self._format_interactions_results(results)
            print(f"     ✓ Found {len(results)} interactions")
            if results:
                print(f"     Results preview: {formatted[:150]}...")
            return formatted
        
        @tool(
            name="search_summaries",
            description="Search session summaries to find information from previous sessions"
        )
        async def search_summaries_tool(
            query: Annotated[str, "The search query to find relevant session summaries"],
            max_results: Annotated[int, "Maximum number of results to return (default 3)"] = 3
        ) -> str:
            """Search session summaries."""
            print(f"\n  📋 [CFR] Searching summaries for: '{query}'")
            results = await self._search_summaries(query, max_results)
            formatted = self._format_summaries_results(results)
            print(f"     ✓ Found {len(results)} summaries")
            if results:
                print(f"     Results preview: {formatted[:150]}...")
            return formatted
        
        @tool(
            name="search_insights",
            description="Search long-term insights about user preferences, knowledge level, and patterns"
        )
        async def search_insights_tool(
            query: Annotated[str, "The search query to find relevant user insights"],
            max_results: Annotated[int, "Maximum number of results to return (default 3)"] = 3
        ) -> str:
            """Search long-term insights."""
            print(f"\n  💡 [CFR] Searching insights for: '{query}'")
            results = await self._search_insights(query, max_results)
            formatted = self._format_insights_results(results)
            print(f"     ✓ Found {len(results)} insights")
            if results:
                print(f"     Results preview: {formatted[:150]}...")
            return formatted
        
        # Store tool references for dynamic selection
        self._search_interactions_tool = search_interactions_tool
        self._search_summaries_tool = search_summaries_tool
        self._search_insights_tool = search_insights_tool
        
        # Create the Agent Framework agent with search_interactions tool by default
        self.agent = ChatAgent(
            chat_client=AzureOpenAIChatClient(
                credential=DefaultAzureCredential(),
                deployment_name=self.config.REASONING_MODEL
            ),
            instructions="""You are a memory retrieval assistant. Your job is to search through past conversations, 
session summaries, and long-term insights to find relevant information for the user's query.

Use the available search tools to find the most relevant information:
- search_interactions: For detailed conversation history
- search_summaries: For session-level context (if available)
- search_insights: For long-term patterns and preferences (if available)

After searching, synthesize the findings into a clear, concise response.""",
            name="CFR_Agent",
            tools=[search_interactions_tool]  # Default: only search interactions
        )
    
    async def retrieve(
        self, 
        query: str, 
        include_summaries: bool = False,
        include_insights: bool = False
    ) -> str:
        """
        Retrieve relevant memory context for a query using the Agent Framework agent.
        
        The agent will intelligently decide which search tools to use based on the query
        and synthesize the results into a coherent response.
        
        Args:
            query: User query or context description
            include_summaries: Whether to search session summaries (default: False)
            include_insights: Whether to search long-term insights (default: False)
            
        Returns:
            Synthesized response from the agent with relevant memory context
        """
        # Build list of available tools based on parameters
        tools = [self._search_interactions_tool]
        if include_summaries:
            tools.append(self._search_summaries_tool)
        if include_insights:
            tools.append(self._search_insights_tool)
        
        # Update agent tools dynamically
        self.agent.tools = tools
        
        result = await self.agent.run(query)
        return result.text
    
    async def _search_interactions(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """
        Search past conversation interactions using vector search.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of SearchResult with similarity scores
        """
        try:
            # Generate embedding for query
            query_embedding = self.embedding_provider.get_embedding(query)
            
            # Use database abstraction layer for vector search
            results = await self.database.vector_search(
                container=ContainerType.INTERACTIONS,
                query_embedding=query_embedding,
                vector_field="summary_vector",
                top_k=max_results,
                filters={"user_id": self.user_id}
            )
            
            return results
        except Exception as e:
            print(f"Error searching interactions: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _format_interactions_results(self, results: List[SearchResult]) -> str:
        """Format interaction search results for the agent."""
        if not results:
            return "No relevant past conversations found."
        
        formatted = ["Found relevant past conversations:\n"]
        for idx, result in enumerate(results, 1):
            # Extract metadata fields (they're nested in metadata object)
            metadata = result.get('metadata', {})
            topics = metadata.get('mentioned_topics', []) if isinstance(metadata, dict) else []
            entities = metadata.get('entities', []) if isinstance(metadata, dict) else []
            
            formatted.append(
                f"{idx}. {result.get('summary', 'N/A')}\n"
                f"   Topics: {', '.join(topics) if topics else 'None'}\n"
                f"   Entities: {', '.join(entities) if entities else 'None'}\n"
                f"   Similarity: {result.score:.4f}\n"
            )
        return "\n".join(formatted)
    
    async def _search_summaries(self, query: str, max_results: int = 3) -> List[SearchResult]:
        """
        Search session summaries using vector search.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of SearchResult with similarity scores
        """
        try:
            # Generate embedding for query
            query_embedding = self.embedding_provider.get_embedding(query)
            
            # Use database abstraction layer for vector search
            results = await self.database.vector_search(
                container=ContainerType.SESSION_SUMMARIES,
                query_embedding=query_embedding,
                vector_field="summary_vector",
                top_k=max_results,
                filters={"user_id": self.user_id}
            )
            
            return results
        except Exception as e:
            print(f"Error searching summaries: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _format_summaries_results(self, results: List[SearchResult]) -> str:
        """Format session summary search results for the agent."""
        if not results:
            return "No relevant session summaries found."
        
        formatted = ["Found relevant session summaries:\n"]
        for idx, result in enumerate(results, 1):
            key_topics = result.get('key_topics', [])
            formatted.append(
                f"{idx}. {result.get('summary', 'N/A')}\n"
                f"   Session: {result.get('session_id', result.id)}\n"
                f"   Topics: {', '.join(key_topics) if key_topics else 'None'}\n"
                f"   Similarity: {result.score:.4f}\n"
            )
        return "\n".join(formatted)
    
    async def _search_insights(self, query: str, max_results: int = 3) -> List[SearchResult]:
        """
        Search long-term insights using vector search.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of SearchResult with similarity scores
        """
        try:
            # Generate embedding for query
            query_embedding = self.embedding_provider.get_embedding(query)
            
            # Use database abstraction layer for vector search
            results = await self.database.vector_search(
                container=ContainerType.INSIGHTS,
                query_embedding=query_embedding,
                vector_field="insight_vector",
                top_k=max_results,
                filters={"user_id": self.user_id}
            )
            
            return results
        except Exception as e:
            print(f"Error searching insights: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _format_insights_results(self, results: List[SearchResult]) -> str:
        """Format insight search results for the agent."""
        if not results:
            return "No relevant long-term insights found."
        
        formatted = ["Found relevant user insights:\n"]
        for idx, result in enumerate(results, 1):
            confidence = result.get('confidence', 0)
            formatted.append(
                f"{idx}. {result.get('insight_text', 'N/A')}\n"
                f"   Category: {result.get('category', 'N/A')}\n"
                f"   Confidence: {confidence:.2f if isinstance(confidence, (int, float)) else 'N/A'}\n"
                f"   Similarity: {result.score:.4f}\n"
            )
        return "\n".join(formatted)


# Backward compatibility alias
ContextualFactRetrieval = FactRetrieval
