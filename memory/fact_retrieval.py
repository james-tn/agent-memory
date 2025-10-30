"""
Contextual Fact Retrieval (CFR) Agent for Agent Memory Service.

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
from datetime import datetime
from azure.cosmos import ContainerProxy

from agent_framework import ChatAgent, ai_function
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

from memory.cosmos_utils import CosmosUtils
from memory.config import MemoryConfig


class ContextualFactRetrieval:
    """
    CFR Agent for intelligent memory retrieval using Agent Framework.
    
    The agent uses three search tools to intelligently retrieve memory:
    1. search_interactions: Search past conversation chunks
    2. search_summaries: Search session summaries  
    3. search_insights: Search long-term insights
    """
    
    def __init__(
        self,
        config: MemoryConfig,
        cosmos_utils: CosmosUtils,
        user_id: str,
        interactions_container: ContainerProxy,
        summaries_container: ContainerProxy,
        insights_container: ContainerProxy
    ):
        """
        Initialize CFR agent with Agent Framework.
        
        Args:
            config: Memory configuration
            cosmos_utils: Cosmos utilities for embeddings
            user_id: User identifier for memory retrieval
            interactions_container: CosmosDB container for interactions
            summaries_container: CosmosDB container for session summaries
            insights_container: CosmosDB container for insights
        """
        self.config = config
        self.cosmos_utils = cosmos_utils
        self.user_id = user_id
        self.interactions_container = interactions_container
        self.summaries_container = summaries_container
        self.insights_container = insights_container
        
        # Create search tool functions with closure over self
        # This allows the agent to use these as tools while maintaining access to cosmos_utils
        
        @ai_function(
            name="search_interactions",
            description="Search past conversation interactions for specific topics or details"
        )
        async def search_interactions_tool(
            query: Annotated[str, "The search query to find relevant past conversations"],
            max_results: Annotated[int, "Maximum number of results to return (default 5)"] = 5
        ) -> str:
            """Search past conversation interactions."""
            results = await self._search_interactions(query, max_results)
            return self._format_interactions_results(results)
        
        @ai_function(
            name="search_summaries",
            description="Search session summaries to find information from previous sessions"
        )
        async def search_summaries_tool(
            query: Annotated[str, "The search query to find relevant session summaries"],
            max_results: Annotated[int, "Maximum number of results to return (default 3)"] = 3
        ) -> str:
            """Search session summaries."""
            results = await self._search_summaries(query, max_results)
            return self._format_summaries_results(results)
        
        @ai_function(
            name="search_insights",
            description="Search long-term insights about user preferences, knowledge level, and patterns"
        )
        async def search_insights_tool(
            query: Annotated[str, "The search query to find relevant user insights"],
            max_results: Annotated[int, "Maximum number of results to return (default 3)"] = 3
        ) -> str:
            """Search long-term insights."""
            results = await self._search_insights(query, max_results)
            return self._format_insights_results(results)
        
        # Create the Agent Framework agent with the search tools
        self.agent = ChatAgent(
            chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
            instructions="""You are a memory retrieval assistant. Your job is to search through past conversations, 
session summaries, and long-term insights to find relevant information for the user's query.

Use the available search tools to find the most relevant information:
- search_interactions: For detailed conversation history
- search_summaries: For session-level context
- search_insights: For long-term patterns and preferences

After searching, synthesize the findings into a clear, concise response.""",
            name="CFR_Agent",
            tools=[search_interactions_tool, search_summaries_tool, search_insights_tool]
        )
    
    async def retrieve(self, query: str) -> str:
        """
        Retrieve relevant memory context for a query using the Agent Framework agent.
        
        The agent will intelligently decide which search tools to use based on the query
        and synthesize the results into a coherent response.
        
        Args:
            query: User query or context description
            
        Returns:
            Synthesized response from the agent with relevant memory context
        """
        result = await self.agent.run(query)
        return result.text
    
    async def _search_interactions(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Internal method to search past conversation interactions using hybrid search (vector + full-text).
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of interaction documents with similarity scores
        """
        # Generate embedding for query
        query_embedding = self.cosmos_utils.get_embedding(query)
        
        # Use hybrid search for better retrieval (combines vector + full-text)
        try:
            results = self.cosmos_utils.execute_hybrid_search(
                container=self.interactions_container,
                query_text=query,
                query_embedding=query_embedding,
                vector_field="summary_embedding",
                full_text_fields=["summary", "mentioned_topics", "entities"],
                top_k=max_results,
                filters={"user_id": self.user_id},
                weights=[2, 1]  # Weight vector search 2x more than full-text
            )
            
            # Add similarity field for consistency with formatting
            for result in results:
                if 'vector_score' in result:
                    result['similarity'] = 1 - result['vector_score']  # Convert distance to similarity
            
            return results
        except Exception as e:
            print(f"Error searching interactions: {e}")
            return []
    
    def _format_interactions_results(self, results: List[Dict]) -> str:
        """Format interaction search results for the agent."""
        if not results:
            return "No relevant past conversations found."
        
        formatted = ["Found relevant past conversations:\n"]
        for idx, interaction in enumerate(results, 1):
            formatted.append(
                f"{idx}. {interaction.get('summary', 'N/A')}\n"
                f"   Topics: {', '.join(interaction.get('mentioned_topics', []))}\n"
                f"   Entities: {', '.join(interaction.get('entities', []))}\n"
                f"   Similarity: {interaction.get('similarity', 'N/A'):.4f}\n"
            )
        return "\n".join(formatted)
    
    async def _search_summaries(self, query: str, max_results: int = 3) -> List[Dict]:
        """
        Internal method to search session summaries using hybrid search (vector + full-text).
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of session summary documents with similarity scores
        """
        # Generate embedding for query
        query_embedding = self.cosmos_utils.get_embedding(query)
        
        # Use hybrid search for better retrieval
        try:
            results = self.cosmos_utils.execute_hybrid_search(
                container=self.summaries_container,
                query_text=query,
                query_embedding=query_embedding,
                vector_field="summary_embedding",
                full_text_fields=["summary", "key_topics"],
                top_k=max_results,
                filters={"user_id": self.user_id},
                weights=[2, 1]  # Weight vector search 2x more than full-text
            )
            
            # Add similarity field for consistency
            for result in results:
                if 'vector_score' in result:
                    result['similarity'] = 1 - result['vector_score']
            
            return results
        except Exception as e:
            print(f"Error searching summaries: {e}")
            return []
    
    def _format_summaries_results(self, results: List[Dict]) -> str:
        """Format session summary search results for the agent."""
        if not results:
            return "No relevant session summaries found."
        
        formatted = ["Found relevant session summaries:\n"]
        for idx, summary in enumerate(results, 1):
            formatted.append(
                f"{idx}. {summary.get('summary', 'N/A')}\n"
                f"   Session: {summary.get('session_id', 'N/A')}\n"
                f"   Topics: {', '.join(summary.get('key_topics', []))}\n"
                f"   Similarity: {summary.get('similarity', 'N/A'):.4f}\n"
            )
        return "\n".join(formatted)
    
    async def _search_insights(self, query: str, max_results: int = 3) -> List[Dict]:
        """
        Internal method to search long-term insights using hybrid search (vector + full-text).
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of insight documents with similarity scores
        """
        # Generate embedding for query
        query_embedding = self.cosmos_utils.get_embedding(query)
        
        # Use hybrid search for better retrieval
        try:
            results = self.cosmos_utils.execute_hybrid_search(
                container=self.insights_container,
                query_text=query,
                query_embedding=query_embedding,
                vector_field="insight_embedding",
                full_text_fields=["insight_text", "category"],
                top_k=max_results,
                filters={"user_id": self.user_id},
                weights=[2, 1]  # Weight vector search 2x more than full-text
            )
            
            # Add similarity field for consistency
            for result in results:
                if 'vector_score' in result:
                    result['similarity'] = 1 - result['vector_score']
            
            return results
        except Exception as e:
            print(f"Error searching insights: {e}")
            return []
    
    def _format_insights_results(self, results: List[Dict]) -> str:
        """Format insight search results for the agent."""
        if not results:
            return "No relevant long-term insights found."
        
        formatted = ["Found relevant user insights:\n"]
        for idx, insight in enumerate(results, 1):
            formatted.append(
                f"{idx}. {insight.get('insight_text', 'N/A')}\n"
                f"   Category: {insight.get('category', 'N/A')}\n"
                f"   Confidence: {insight.get('confidence', 'N/A'):.2f}\n"
                f"   Similarity: {insight.get('similarity', 'N/A'):.4f}\n"
            )
        return "\n".join(formatted)
