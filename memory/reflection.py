"""
Reflection Process for Agent Memory Service.

This module implements reflection capabilities that extract insights from:
1. Session Reflection: Extract insights from a completed session
2. Long-term Synthesis: Identify evolving patterns across multiple sessions

The reflection process uses structured outputs to extract actionable insights
about user preferences, knowledge level, goals, and behavioral patterns.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid
from azure.cosmos import ContainerProxy
from openai import AzureOpenAI
from pydantic import BaseModel, Field

from memory.cosmos_utils import CosmosUtils
from memory.config import MemoryConfig


# Pydantic models for structured LLM outputs
class SessionInsight(BaseModel):
    """Structured output for a single insight from session reflection."""
    insight_text: str = Field(description="Clear, actionable insight about the user")
    category: str = Field(description="Category: preferences, knowledge_level, goals, behavior_patterns, or learning_progress")
    confidence: float = Field(description="Confidence score 0.0-1.0", ge=0.0, le=1.0)
    importance: str = Field(description="Importance level: high, medium, or low")


class ComprehensiveSessionAnalysis(BaseModel):
    """Combined structured output for session end - generates summary, topics, and insights in one call."""
    session_summary: str = Field(description="Comprehensive 2-4 sentence session summary capturing main discussion points and outcomes")
    key_topics: List[str] = Field(description="3-5 key topics discussed in the session", min_length=1, max_length=5)
    insights: List[SessionInsight] = Field(description="0-5 actionable insights about the user extracted from the session", max_length=5)
    has_meaningful_insights: bool = Field(description="True if significant insights were found, False if session was too brief or trivial")


class LongTermSynthesisOutput(BaseModel):
    """Structured output for long-term pattern synthesis."""
    synthesized_insight: str = Field(description="Synthesized insight combining multiple related insights")
    category: str = Field(description="Category of the synthesized insight")
    confidence: float = Field(description="Confidence score 0.0-1.0", ge=0.0, le=1.0)
    source_count: int = Field(description="Number of source insights used in synthesis")


class ReflectionProcess:
    """
    Reflection Process for extracting insights from sessions and synthesizing long-term patterns.
    
    Capabilities:
    - Session Reflection: Extract insights from a completed session
    - Long-term Synthesis: Combine related insights into higher-level patterns
    - Insight Storage: Store and update insights in CosmosDB
    """
    
    def __init__(
        self,
        config: MemoryConfig,
        cosmos_utils: CosmosUtils,
        insights_container: ContainerProxy,
        summaries_container: ContainerProxy,
        interactions_container: ContainerProxy,
        chat_client: AzureOpenAI
    ):
        """
        Initialize Reflection Process.
        
        Args:
            config: Memory configuration
            cosmos_utils: Cosmos utilities for embeddings
            insights_container: Container for storing insights
            summaries_container: Container for session summaries
            interactions_container: Container for interactions
            chat_client: Azure OpenAI client for LLM
        """
        self.config = config
        self.cosmos_utils = cosmos_utils
        self.insights_container = insights_container
        self.summaries_container = summaries_container
        self.interactions_container = interactions_container
        self.chat_client = chat_client
    
    async def reflect_on_session(
        self,
        user_id: str,
        session_id: str,
        cumulative_summary: str,
        recent_turns: List[tuple] = None
    ) -> Dict[str, Any]:
        """
        Perform comprehensive session analysis at session end.
        
        Uses single LLM call to generate:
        - Session summary (2-4 sentences)
        - Key topics (3-5 items)
        - Insights (0-5 actionable insights)
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            cumulative_summary: Cumulative summary of the session
            recent_turns: Optional list of recent (role, content) tuples for additional context
            
        Returns:
            Dict with session_summary, key_topics, and insights
        """
        import time
        start_time = time.time()
        print(f"[Reflection] Starting comprehensive session analysis for session: {session_id}")
        
        # Build full session context
        context_start = time.time()
        
        # Filter recent_turns to only include user and assistant messages
        # (exclude any system messages that might have been injected)
        filtered_turns = []
        if recent_turns:
            for role, content in recent_turns[-10:]:  # Last 10 turns
                # Only include user and assistant turns
                if role in ("user", "assistant") and content and content.strip():
                    filtered_turns.append((role, content))
        
        # Build context from cumulative summary and filtered turns
        full_context = cumulative_summary if cumulative_summary else ""
        if filtered_turns:
            recent_turns_text = "\n".join([
                f"{role}: {content}" 
                for role, content in filtered_turns
            ])
            if full_context:
                full_context += f"\n\nRecent turns:\n{recent_turns_text}"
            else:
                full_context = f"Recent turns:\n{recent_turns_text}"
        
        context_duration = time.time() - context_start
        print(f"  ⏱ Build context: {context_duration:.2f}s")
        
        # Skip reflection if no meaningful content
        if not full_context or len(full_context.strip()) < 10:
            print(f"  ⚠ Skipping reflection - insufficient content (session too brief)")
            return {
                "session_summary": "Brief session with minimal interaction.",
                "key_topics": ["minimal interaction"],
                "insights": [],
                "has_meaningful_insights": False
            }
        
        # Single comprehensive analysis call (summary + topics + insights)
        llm_start = time.time()
        analysis = await self._generate_comprehensive_analysis(full_context)
        llm_duration = time.time() - llm_start
        print(f"  ⏱ Comprehensive analysis (LLM): {llm_duration:.2f}s")
        
        # Fallback if LLM returns empty
        session_summary_text = analysis.session_summary
        if not session_summary_text or session_summary_text.strip() == "":
            session_summary_text = "Session completed with discussion."
            print(f"  ⚠ Using fallback summary (LLM returned empty)")
        
        # Convert insights to storage format
        insights_list = []
        if analysis.has_meaningful_insights:
            for insight in analysis.insights:
                insights_list.append({
                    "id": str(uuid.uuid4()),
                    "insight_text": insight.insight_text,
                    "category": insight.category,
                    "confidence": insight.confidence,
                    "importance": insight.importance,
                    "extracted_at": datetime.utcnow().isoformat()
                })
        
        total_duration = time.time() - start_time
        print(f"  ✓ Session analysis complete (total: {total_duration:.2f}s)")
        print(f"    - Summary: {session_summary_text[:100]}...")
        print(f"    - Topics: {analysis.key_topics}")
        print(f"    - Insights: {len(insights_list)} extracted")
        if insights_list:
            for idx, insight in enumerate(insights_list, 1):
                print(f"       {idx}. {insight.get('insight_text', '')[:80]}...")
        
        return {
            "session_summary": session_summary_text,
            "key_topics": analysis.key_topics,
            "insights": insights_list,
            "has_meaningful_insights": analysis.has_meaningful_insights
        }
    
    async def synthesize_long_term_patterns(
        self,
        user_id: str,
        category: Optional[str] = None,
        min_insights: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Synthesize long-term patterns from multiple related insights.
        
        This looks at existing insights and combines related ones into
        higher-level patterns or evolving preferences.
        
        Args:
            user_id: User identifier
            category: Optional category to focus on (e.g., "preferences")
            min_insights: Minimum number of insights needed for synthesis
            
        Returns:
            Synthesized insight document, or None if insufficient data
        """
        print(f"[Reflection] Starting long-term synthesis for user: {user_id}")
        
        # Get existing insights
        insights = await self._get_user_insights(user_id, category)
        
        if len(insights) < min_insights:
            print(f"  ℹ Insufficient insights for synthesis ({len(insights)} < {min_insights})")
            return None
        
        # Build synthesis context
        context = self._build_synthesis_context(insights)
        
        # Synthesize using LLM
        synthesis_output = await self._synthesize_insights(context, category)
        
        if not synthesis_output:
            print(f"  ℹ No synthesis generated")
            return None
        
        # Store synthesized insight
        synthesized_insight = SessionInsight(
            insight_text=synthesis_output.synthesized_insight,
            category=synthesis_output.category,
            confidence=synthesis_output.confidence,
            supporting_evidence=f"Synthesized from {synthesis_output.source_count} insights"
        )
        
        insight_doc = await self._store_insight(
            user_id,
            synthesized_insight,
            session_id=None,  # Not from a specific session
            is_synthesized=True
        )
        
        print(f"  ✓ Long-term synthesis complete. Created synthesized insight with confidence {synthesis_output.confidence:.2f}")
        return insight_doc
    
    async def _get_session_summary(self, user_id: str, session_id: str) -> Optional[Dict]:
        """Get session summary document."""
        try:
            return self.summaries_container.read_item(
                item=session_id,
                partition_key=user_id
            )
        except Exception as e:
            print(f"  Error reading session summary: {e}")
            return None
    
    async def _get_session_interactions(self, user_id: str, session_id: str) -> List[Dict]:
        """Get all interactions from a session."""
        query = """
        SELECT c.id, c.summary, c.mentioned_topics, c.entities, c.turn_count
        FROM c
        WHERE c.user_id = @user_id AND c.session_id = @session_id
        ORDER BY c.start_time
        """
        parameters = [
            {"name": "@user_id", "value": user_id},
            {"name": "@session_id", "value": session_id}
        ]
        
        try:
            results = list(self.interactions_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=False
            ))
            return results
        except Exception as e:
            print(f"  Error querying interactions: {e}")
            return []
    
    async def _get_user_insights(
        self,
        user_id: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Get existing insights for a user."""
        if category:
            query = """
            SELECT * FROM c
            WHERE c.user_id = @user_id AND c.category = @category
            ORDER BY c.last_updated DESC
            """
            parameters = [
                {"name": "@user_id", "value": user_id},
                {"name": "@category", "value": category}
            ]
        else:
            query = """
            SELECT * FROM c
            WHERE c.user_id = @user_id
            ORDER BY c.last_updated DESC
            """
            parameters = [{"name": "@user_id", "value": user_id}]
        
        try:
            results = list(self.insights_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=False
            ))
            return results
        except Exception as e:
            print(f"  Error querying insights: {e}")
            return []
    
    def _build_reflection_context(
        self,
        session_summary: Dict,
        interactions: List[Dict]
    ) -> str:
        """Build context text for session reflection."""
        parts = ["# Session Reflection Context\n"]
        
        # Session summary
        parts.append(f"## Session Summary")
        parts.append(f"Session ID: {session_summary.get('session_id', 'N/A')}")
        parts.append(f"Summary: {session_summary.get('summary', 'N/A')}")
        parts.append(f"Key Topics: {', '.join(session_summary.get('key_topics', []))}")
        parts.append("")
        
        # Interactions
        if interactions:
            parts.append("## Conversation Details")
            for idx, interaction in enumerate(interactions, 1):
                parts.append(f"{idx}. {interaction.get('summary', 'N/A')}")
                topics = interaction.get('mentioned_topics', [])
                if topics:
                    parts.append(f"   Topics: {', '.join(topics)}")
            parts.append("")
        
        return "\n".join(parts)
    
    def _build_synthesis_context(self, insights: List[Dict]) -> str:
        """Build context text for long-term synthesis."""
        parts = ["# Long-term Insights to Synthesize\n"]
        
        for idx, insight in enumerate(insights, 1):
            parts.append(f"{idx}. {insight.get('insight_text', 'N/A')}")
            parts.append(f"   Category: {insight.get('category', 'N/A')}")
            parts.append(f"   Confidence: {insight.get('confidence', 0.0):.2f}")
            parts.append("")
        
        return "\n".join(parts)
    
    async def _generate_comprehensive_analysis(self, session_content: str) -> ComprehensiveSessionAnalysis:
        """
        Generate comprehensive session analysis with single LLM call.
        
        Combines summary generation, topic extraction, and insight extraction.
        
        Args:
            session_content: Full session context (cumulative summary + recent turns)
            
        Returns:
            ComprehensiveSessionAnalysis with summary, topics, and insights
        """
        from memory.prompts import COMPREHENSIVE_SESSION_ANALYSIS_PROMPT
        
        prompt = COMPREHENSIVE_SESSION_ANALYSIS_PROMPT.format(session_content=session_content)
        
        try:
            response = self.chat_client.responses.parse(
                model=self.config.MINI_DEPLOYMENT,
                input=[
                    {"role": "system", "content": "You are an expert session analysis assistant."},
                    {"role": "user", "content": prompt}
                ],
                text_format=ComprehensiveSessionAnalysis
            )

            analysis = response.output_parsed
            if analysis:
                return analysis
        except Exception as e:
            print(f"  Error generating comprehensive analysis: {e}")
        
        # Fallback: empty analysis
        return ComprehensiveSessionAnalysis(
            session_summary="Session completed with discussion.",
            key_topics=["general discussion"],
            insights=[],
            has_meaningful_insights=False
        )
    
    async def _synthesize_insights(
        self,
        context: str,
        category: Optional[str]
    ) -> Optional[LongTermSynthesisOutput]:
        """Synthesize long-term patterns using structured output."""
        from memory.prompts import LONG_TERM_SYNTHESIS_PROMPT
        
        category_hint = f" Focus on {category} category." if category else ""
        prompt = LONG_TERM_SYNTHESIS_PROMPT.format(
            insights_context=context,
            category_hint=category_hint
        )
        
        try:
            response = self.chat_client.responses.parse(
                model=self.config.MINI_DEPLOYMENT,
                input=[
                    {"role": "system", "content": "You are a long-term pattern synthesis assistant for agent memory."},
                    {"role": "user", "content": prompt}
                ],
                text_format=LongTermSynthesisOutput
            )

            synthesis_output = response.output_parsed
            return synthesis_output
        except Exception as e:
            print(f"  Error synthesizing insights: {e}")
            return None
    
    async def _store_insight(
        self,
        user_id: str,
        insight: SessionInsight,
        session_id: Optional[str],
        is_synthesized: bool = False
    ) -> Dict[str, Any]:
        """Store an insight in CosmosDB."""
        insight_id = str(uuid.uuid4())
        
        # Generate embedding for the insight text
        embedding = self.cosmos_utils.get_embedding(insight.insight_text)
        
        insight_doc = {
            "id": insight_id,
            "user_id": user_id,
            "insight_text": insight.insight_text,
            "insight_embedding": embedding,
            "category": insight.category,
            "confidence": insight.confidence,
            "supporting_evidence": insight.supporting_evidence,
            "source_session_id": session_id,
            "is_synthesized": is_synthesized,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat()
        }
        
        self.insights_container.create_item(body=insight_doc)
        return insight_doc
