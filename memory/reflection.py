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


class LongTermProfileOutput(BaseModel):
    """Structured output for comprehensive long-term user profile."""
    profile_text: str = Field(description="Comprehensive narrative profile of the user organized by categories")
    categories_covered: List[str] = Field(description="List of categories included in the profile")
    confidence: float = Field(description="Overall confidence score 0.0-1.0", ge=0.0, le=1.0)
    insight_count: int = Field(description="Number of session insights synthesized into this profile")


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
                model=self.config.PROCESSING_MODEL,
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
                model=self.config.PROCESSING_MODEL,
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
    
    async def update_longterm_insight(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Update long-term insight by synthesizing all unprocessed session insights.
        
        This is the main synthesis function that:
        1. Fetches all unprocessed session insights for the user
        2. Groups insights by category
        3. Synthesizes into a comprehensive structured profile
        4. Upserts single longterm-{user_id} document
        5. Marks session insights as processed=True
        
        Args:
            user_id: User identifier
            
        Returns:
            Long-term insight document if synthesis succeeded, None otherwise
        """
        print(f"[LongTerm] Starting long-term insight synthesis for user: {user_id}")
        
        # 1. Fetch all unprocessed session insights
        unprocessed_insights = await self._get_unprocessed_insights(user_id)
        
        if not unprocessed_insights:
            print(f"  ℹ No unprocessed insights found for synthesis")
            return None
        
        print(f"  ✓ Found {len(unprocessed_insights)} unprocessed session insights")
        
        # 2. Group by category
        insights_by_category = {}
        for insight in unprocessed_insights:
            category = insight.get("category", "general")
            if category not in insights_by_category:
                insights_by_category[category] = []
            insights_by_category[category].append(insight)
        
        print(f"  ✓ Grouped into {len(insights_by_category)} categories: {list(insights_by_category.keys())}")
        
        # 3. Synthesize into structured profile
        profile_output = await self._synthesize_longterm_profile(user_id, insights_by_category)
        
        if not profile_output:
            print(f"  ℹ No profile generated from synthesis")
            return None
        
        # 4. Upsert longterm-{user_id} document
        longterm_doc = await self._upsert_longterm_document(
            user_id,
            profile_output,
            [insight["id"] for insight in unprocessed_insights]
        )
        
        # 5. Mark session insights as processed
        await self._mark_insights_processed(user_id, [insight["id"] for insight in unprocessed_insights])
        
        print(f"  ✓ Long-term insight synthesis complete. Confidence: {profile_output.confidence:.2f}")
        return longterm_doc
    
    async def get_longterm_insight(self, user_id: str) -> Optional[str]:
        """
        Retrieve the long-term insight profile text for a user.
        
        Simple fetch of longterm-{user_id} document that returns
        formatted profile text for injection into session context.
        
        Args:
            user_id: User identifier
            
        Returns:
            Formatted profile text, or None if no long-term insight exists
        """
        longterm_id = f"longterm-{user_id}"
        
        try:
            doc = self.insights_container.read_item(
                item=longterm_id,
                partition_key=user_id
            )
            return doc.get("insight_text", "")
        except Exception as e:
            # Document doesn't exist yet - this is normal for new users or before first synthesis
            error_msg = str(e)
            if "NotFound" in error_msg or "does not exist" in error_msg:
                # Expected case - no long-term insight created yet
                return None
            else:
                # Unexpected error
                print(f"  ⚠ Error fetching long-term insight for user {user_id}: {e}")
                return None
    
    async def _get_unprocessed_insights(self, user_id: str) -> List[Dict]:
        """Fetch all unprocessed session insights for a user."""
        query = """
        SELECT * FROM c
        WHERE c.user_id = @user_id
          AND c.insight_type = 'session'
          AND (NOT IS_DEFINED(c.processed) OR c.processed = false)
        ORDER BY c.created_at ASC
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
            print(f"  Error querying unprocessed insights: {e}")
            return []
    
    async def _synthesize_longterm_profile(
        self,
        user_id: str,
        insights_by_category: Dict[str, List[Dict]]
    ) -> Optional[LongTermProfileOutput]:
        """Synthesize all insights into a comprehensive user profile (incremental update)."""
        
        # Fetch existing long-term profile if it exists
        existing_profile = await self.get_longterm_insight(user_id)
        
        # Build context for synthesis
        context_parts = []
        total_insights = 0
        
        for category, insights in insights_by_category.items():
            context_parts.append(f"\n{category.upper()}:")
            for insight in insights:
                context_parts.append(f"- {insight.get('insight_text', '')} (confidence: {insight.get('confidence', 0):.2f})")
                total_insights += 1
        
        new_insights_context = "\n".join(context_parts)
        
        # Build prompt based on whether existing profile exists
        if existing_profile:
            # Incremental update: incorporate new insights into existing profile
            prompt = f"""You are updating an existing long-term user profile with new insights from recent sessions.

User ID: {user_id}

EXISTING USER PROFILE:
{existing_profile}

NEW SESSION INSIGHTS (to be incorporated):
{new_insights_context}

Task: Update the user profile by:
1. Integrating new insights into the existing profile
2. Identifying evolving patterns and changes over time
3. Updating or refining existing information with new data
4. Maintaining the structured, category-based format
5. Removing outdated or contradicted information (preferring higher confidence and more recent insights)
6. Highlighting any significant changes or new learnings

IMPORTANT: Keep the profile CONCISE and focused. Use brief, direct language. Organize into clear categories with 1-2 sentences each. Avoid verbose descriptions - capture only the essential, actionable information.

The updated profile should build upon the existing knowledge while incorporating new learnings, showing the evolution of our understanding of this user.
"""
        else:
            # First-time synthesis: create profile from scratch
            prompt = f"""You are creating an initial long-term user profile from session insights.

User ID: {user_id}

SESSION INSIGHTS (grouped by category):
{new_insights_context}

Task: Create a cohesive narrative profile that:
1. Synthesizes insights within each category into clear statements
2. Identifies patterns and trends across sessions
3. Presents information in a structured, easy-to-read format
4. Removes redundancies and conflicting information (preferring higher confidence insights)
5. Organizes by categories for easy reference

IMPORTANT: Keep the profile CONCISE. Use brief, direct language. Each category should be 1-2 sentences capturing the essential information only. Avoid verbose descriptions and unnecessary details.

The profile should be comprehensive but concise, focusing on actionable information that helps provide personalized assistance to this user.
"""
        
        try:
            response = self.chat_client.beta.chat.completions.parse(
                model=self.config.PROCESSING_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert at synthesizing user insights into comprehensive profiles."},
                    {"role": "user", "content": prompt}
                ],
                response_format=LongTermProfileOutput,
            )
            
            return response.choices[0].message.parsed
        except Exception as e:
            print(f"  Error during profile synthesis: {e}")
            return None
    
    async def _upsert_longterm_document(
        self,
        user_id: str,
        profile_output: LongTermProfileOutput,
        source_insight_ids: List[str]
    ) -> Dict[str, Any]:
        """Upsert the long-term insight document for a user."""
        longterm_id = f"longterm-{user_id}"
        
        # Generate embedding for the profile text
        embedding = self.cosmos_utils.get_embedding(profile_output.profile_text)
        
        # Check if document already exists
        try:
            existing_doc = self.insights_container.read_item(
                item=longterm_id,
                partition_key=user_id
            )
            # Update existing document
            existing_doc["insight_text"] = profile_output.profile_text
            existing_doc["insight_vector"] = embedding
            existing_doc["confidence"] = profile_output.confidence
            existing_doc["source_insight_ids"] = list(set(
                existing_doc.get("source_insight_ids", []) + source_insight_ids
            ))
            existing_doc["updated_at"] = datetime.utcnow().isoformat()
            
            self.insights_container.replace_item(
                item=longterm_id,
                body=existing_doc
            )
            print(f"  ✓ Updated existing long-term insight document")
            return existing_doc
        except Exception:
            # Create new document
            longterm_doc = {
                "id": longterm_id,
                "user_id": user_id,
                "insight_type": "long_term",
                "insight_text": profile_output.profile_text,
                "insight_vector": embedding,
                "confidence": profile_output.confidence,
                "source_insight_ids": source_insight_ids,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            self.insights_container.create_item(body=longterm_doc)
            print(f"  ✓ Created new long-term insight document")
            return longterm_doc
    
    async def _mark_insights_processed(self, user_id: str, insight_ids: List[str]) -> None:
        """Mark session insights as processed after synthesis."""
        for insight_id in insight_ids:
            try:
                insight_doc = self.insights_container.read_item(
                    item=insight_id,
                    partition_key=user_id
                )
                insight_doc["processed"] = True
                insight_doc["updated_at"] = datetime.utcnow().isoformat()
                
                self.insights_container.replace_item(
                    item=insight_id,
                    body=insight_doc
                )
            except Exception as e:
                print(f"  Warning: Could not mark insight {insight_id} as processed: {e}")

