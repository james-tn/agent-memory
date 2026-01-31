"""
Database-agnostic Reflection Process for Agent Memory Service.

This module implements reflection capabilities that extract insights from:
1. Session Reflection: Extract insights from a completed session
2. Long-term Synthesis: Identify evolving patterns across multiple sessions

The reflection process uses structured outputs to extract actionable insights
about user preferences, knowledge level, goals, and behavioral patterns.

Uses the MemoryDatabase interface to work with any backend
(SQLite, CosmosDB, PostgreSQL).
"""

import json
from typing import List, Dict, Optional, Any, Type
from datetime import datetime
import uuid
from dataclasses import dataclass
from pydantic import BaseModel, Field

from memory.db.base import ContainerType, MemoryDatabase
from memory.providers.embedding import EmbeddingProvider


# ==================== Pydantic Models for Structured LLM Outputs ====================

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


# ==================== Configuration ====================

@dataclass
class ReflectionConfig:
    """Configuration for reflection process."""
    PROCESSING_MODEL: str = "gpt-4o-mini"  # Model for analysis


# ==================== Reflection Class ====================

class Reflection:
    """
    Database-agnostic Reflection Process for extracting insights and synthesizing patterns.
    
    Uses the MemoryDatabase interface to work with any backend
    (SQLite, CosmosDB, PostgreSQL).
    
    Capabilities:
    - Session Reflection: Extract insights from a completed session
    - Long-term Synthesis: Combine related insights into higher-level patterns
    - Insight Storage: Store and update insights in the database
    """
    
    def __init__(
        self,
        database: MemoryDatabase,
        embedding_provider: EmbeddingProvider,
        chat_client: Any,
        config: Optional[ReflectionConfig] = None
    ):
        """
        Initialize Reflection Process.
        
        Args:
            database: Database backend implementing MemoryDatabase interface
            embedding_provider: Provider for generating embeddings
            chat_client: Chat client for LLM calls
            config: Configuration settings (uses defaults if not provided)
        """
        self.database = database
        self.embedding_provider = embedding_provider
        self.chat_client = chat_client
        self.config = config or ReflectionConfig()
    
    def _call_llm_with_json(
        self,
        system_prompt: str,
        user_prompt: str,
        output_model: Type[BaseModel]
    ) -> BaseModel:
        """
        Call LLM with chat completions API and parse JSON response.
        
        Uses JSON mode for structured output, compatible with Azure OpenAI.
        
        Args:
            system_prompt: System message content
            user_prompt: User message content  
            output_model: Pydantic model class for output parsing
            
        Returns:
            Parsed Pydantic model instance
        """
        # Add JSON schema instructions to prompt
        schema_hint = f"\nRespond with valid JSON matching this schema: {output_model.model_json_schema()}"
        
        response = self.chat_client.chat.completions.create(
            model=self.config.PROCESSING_MODEL,
            messages=[
                {"role": "system", "content": system_prompt + schema_hint},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        parsed = json.loads(content)
        return output_model.model_validate(parsed)
    
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
        filtered_turns = []
        if recent_turns:
            for role, content in recent_turns[-10:]:  # Last 10 turns
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
            importance="high"
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
        return await self.database.get_by_id(
            container=ContainerType.SESSION_SUMMARIES,
            document_id=session_id,
            partition_key=user_id
        )
    
    async def _get_session_interactions(self, user_id: str, session_id: str) -> List[Dict]:
        """Get all interactions from a session."""
        return await self.database.query(
            container=ContainerType.INTERACTIONS,
            filters={"user_id": user_id, "session_id": session_id},
            order_by="timestamp"
        )
    
    async def _get_user_insights(
        self,
        user_id: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Get existing insights for a user."""
        filters = {"user_id": user_id}
        if category:
            filters["category"] = category
        
        return await self.database.query(
            container=ContainerType.INSIGHTS,
            filters=filters,
            order_by="-last_updated"
        )
    
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
        
        Args:
            session_content: Full session context (cumulative summary + recent turns)
            
        Returns:
            ComprehensiveSessionAnalysis with summary, topics, and insights
        """
        from memory.prompts import COMPREHENSIVE_SESSION_ANALYSIS_PROMPT
        
        prompt = COMPREHENSIVE_SESSION_ANALYSIS_PROMPT.format(session_content=session_content)
        
        try:
            analysis = self._call_llm_with_json(
                system_prompt="You are an expert session analysis assistant.",
                user_prompt=prompt,
                output_model=ComprehensiveSessionAnalysis
            )
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
            synthesis_output = self._call_llm_with_json(
                system_prompt="You are a long-term pattern synthesis assistant for agent memory.",
                user_prompt=prompt,
                output_model=LongTermSynthesisOutput
            )
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
        """Store an insight in the database."""
        insight_id = str(uuid.uuid4())
        
        # Generate embedding for the insight text
        embedding = self.embedding_provider.get_embedding(insight.insight_text)
        
        insight_doc = {
            "id": insight_id,
            "user_id": user_id,
            "insight_text": insight.insight_text,
            "insight_vector": embedding,
            "category": insight.category,
            "confidence": insight.confidence,
            "importance": insight.importance,
            "source_session_id": session_id,
            "is_synthesized": is_synthesized,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat()
        }
        
        result = await self.database.upsert(
            container=ContainerType.INSIGHTS,
            document=insight_doc,
            partition_key=user_id
        )
        return result
    
    async def update_longterm_insight(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Update long-term insight by synthesizing all unprocessed session insights.
        
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
        
        Args:
            user_id: User identifier
            
        Returns:
            Formatted profile text, or None if no long-term insight exists
        """
        longterm_id = f"longterm-{user_id}"
        
        doc = await self.database.get_by_id(
            container=ContainerType.INSIGHTS,
            document_id=longterm_id,
            partition_key=user_id
        )
        
        if doc:
            return doc.get("insight_text", "")
        return None
    
    async def _get_unprocessed_insights(self, user_id: str) -> List[Dict]:
        """Fetch all unprocessed session insights for a user."""
        # Get all session insights for the user
        all_insights = await self.database.query(
            container=ContainerType.INSIGHTS,
            filters={"user_id": user_id, "insight_type": "session"},
            order_by="created_at"
        )
        
        # Filter for unprocessed (processed is not defined or False)
        return [
            insight for insight in all_insights
            if not insight.get("processed", False)
        ]
    
    async def _synthesize_longterm_profile(
        self,
        user_id: str,
        insights_by_category: Dict[str, List[Dict]]
    ) -> Optional[LongTermProfileOutput]:
        """Synthesize all insights into a comprehensive user profile."""
        
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
5. Removing outdated or contradicted information
6. Highlighting any significant changes or new learnings

IMPORTANT: Keep the profile CONCISE and focused. Use brief, direct language.
"""
        else:
            prompt = f"""You are creating an initial long-term user profile from session insights.

User ID: {user_id}

SESSION INSIGHTS (grouped by category):
{new_insights_context}

Task: Create a cohesive narrative profile that:
1. Synthesizes insights within each category into clear statements
2. Identifies patterns and trends across sessions
3. Presents information in a structured, easy-to-read format
4. Removes redundancies and conflicting information
5. Organizes by categories for easy reference

IMPORTANT: Keep the profile CONCISE. Use brief, direct language.
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
        embedding = self.embedding_provider.get_embedding(profile_output.profile_text)
        
        # Check if document already exists
        existing_doc = await self.database.get_by_id(
            container=ContainerType.INSIGHTS,
            document_id=longterm_id,
            partition_key=user_id
        )
        
        if existing_doc:
            # Update existing document
            existing_doc["insight_text"] = profile_output.profile_text
            existing_doc["insight_vector"] = embedding
            existing_doc["confidence"] = profile_output.confidence
            existing_doc["source_insight_ids"] = list(set(
                existing_doc.get("source_insight_ids", []) + source_insight_ids
            ))
            existing_doc["updated_at"] = datetime.utcnow().isoformat()
            
            result = await self.database.upsert(
                container=ContainerType.INSIGHTS,
                document=existing_doc,
                partition_key=user_id
            )
            print(f"  ✓ Updated existing long-term insight document")
            return result
        else:
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
            
            result = await self.database.upsert(
                container=ContainerType.INSIGHTS,
                document=longterm_doc,
                partition_key=user_id
            )
            print(f"  ✓ Created new long-term insight document")
            return result
    
    async def _mark_insights_processed(self, user_id: str, insight_ids: List[str]) -> None:
        """Mark session insights as processed after synthesis."""
        for insight_id in insight_ids:
            try:
                insight_doc = await self.database.get_by_id(
                    container=ContainerType.INSIGHTS,
                    document_id=insight_id,
                    partition_key=user_id
                )
                if insight_doc:
                    insight_doc["processed"] = True
                    insight_doc["updated_at"] = datetime.utcnow().isoformat()
                    
                    await self.database.upsert(
                        container=ContainerType.INSIGHTS,
                        document=insight_doc,
                        partition_key=user_id
                    )
            except Exception as e:
                print(f"  Warning: Could not mark insight {insight_id} as processed: {e}")

    # ==================== Itemized Insight Methods (V2) ====================
    
    async def reflect_on_session_with_citations(
        self,
        user_id: str,
        session_id: str,
        cumulative_summary: str,
        recent_turns: List[tuple] = None
    ) -> Dict[str, Any]:
        """
        Perform session analysis that:
        1. Extracts NEW insights from the current session
        2. Cites EXISTING long-term insights that were relevant
        
        This enables tracking which insights are actually being used.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            cumulative_summary: Cumulative summary of the session
            recent_turns: Optional list of recent (role, content) tuples
            
        Returns:
            Dict with session_summary, key_topics, new_insights, cited_insight_ids
        """
        import time
        from memory.prompts import SESSION_ANALYSIS_WITH_CITATIONS_PROMPT
        from memory.core.insight_items import (
            SessionAnalysisWithCitations,
            LongTermInsightItem,
            InsightIdGenerator,
            build_context_with_ids,
        )
        
        start_time = time.time()
        print(f"[Reflection] Starting session analysis with citations for: {session_id}")
        
        # 1. Build session content
        filtered_turns = []
        if recent_turns:
            for role, content in recent_turns[-10:]:
                if role in ("user", "assistant") and content and content.strip():
                    filtered_turns.append((role, content))
        
        full_context = cumulative_summary or ""
        if filtered_turns:
            recent_turns_text = "\n".join([f"{role}: {content}" for role, content in filtered_turns])
            if full_context:
                full_context += f"\n\nRecent turns:\n{recent_turns_text}"
            else:
                full_context = f"Recent turns:\n{recent_turns_text}"
        
        if not full_context or len(full_context.strip()) < 10:
            print(f"  ⚠ Skipping - insufficient content")
            return {
                "session_summary": "Brief session.",
                "key_topics": [],
                "new_insights": [],
                "cited_insight_ids": [],
                "has_meaningful_content": False
            }
        
        # 2. Get existing long-term insight items
        existing_items = await self._get_longterm_insight_items(user_id)
        existing_context = build_context_with_ids(existing_items)
        print(f"  ✓ Loaded {len(existing_items)} existing long-term insights for citation")
        
        # 3. Build prompt
        prompt = SESSION_ANALYSIS_WITH_CITATIONS_PROMPT.format(
            existing_insights_context=existing_context,
            session_content=full_context
        )
        
        # 4. Call LLM with structured output
        llm_start = time.time()
        try:
            analysis = self._call_llm_with_json(
                system_prompt="You are an expert session analysis assistant with memory tracking.",
                user_prompt=prompt,
                output_model=SessionAnalysisWithCitations
            )
        except Exception as e:
            print(f"  Error in LLM call: {e}")
            return {
                "session_summary": "Session analysis failed.",
                "key_topics": [],
                "new_insights": [],
                "cited_insight_ids": [],
                "has_meaningful_content": False
            }
        
        llm_duration = time.time() - llm_start
        print(f"  ⏱ LLM analysis: {llm_duration:.2f}s")
        
        # 5. Process citations - update access counts
        cited_ids = []
        for citation in analysis.cited_insights:
            cited_ids.append(citation.insight_id)
            print(f"    📎 Cited: {citation.insight_id} - {citation.relevance[:50]}...")
        
        if cited_ids:
            await self._update_insight_access(user_id, cited_ids)
            print(f"  ✓ Updated access counts for {len(cited_ids)} cited insights")
        
        # 6. Create new insight items
        id_gen = InsightIdGenerator([item.id for item in existing_items])
        new_insight_items = []
        
        for insight in analysis.new_insights:
            item = LongTermInsightItem(
                id=id_gen.next_id(),
                user_id=user_id,
                insight_text=insight.insight_text,
                category=insight.category,
                confidence=insight.confidence,
                importance=insight.importance,
                date_added=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                access_count=0,
                source_session_ids=[session_id],
            )
            new_insight_items.append(item)
        
        # 7. Store new insight items
        for item in new_insight_items:
            await self._store_longterm_insight_item(item)
        
        if new_insight_items:
            print(f"  ✓ Created {len(new_insight_items)} new insight items: {[i.id for i in new_insight_items]}")
        
        total_duration = time.time() - start_time
        print(f"  ✓ Session analysis complete (total: {total_duration:.2f}s)")
        
        return {
            "session_summary": analysis.session_summary,
            "key_topics": analysis.key_topics,
            "new_insights": [i.to_dict() for i in new_insight_items],
            "cited_insight_ids": cited_ids,
            "has_meaningful_content": analysis.has_meaningful_content
        }
    
    async def _get_longterm_insight_items(self, user_id: str) -> List:
        """Get all long-term insight items for a user."""
        from memory.core.insight_items import LongTermInsightItem
        
        # Query all long_term_item insights for this user
        # Note: order_by uses 'created_at' which exists in the schema
        items = await self.database.query(
            container=ContainerType.INSIGHTS,
            filters={"user_id": user_id, "insight_type": "long_term_item"},
            order_by="-created_at"  # Use created_at which is guaranteed to exist
        )
        
        result = []
        for item_data in items:
            try:
                result.append(LongTermInsightItem.from_dict(item_data))
            except Exception as e:
                print(f"  Warning: Could not parse insight item {item_data.get('id')}: {e}")
        
        # Sort by last_accessed in Python (field stored in JSON)
        result.sort(key=lambda x: x.last_accessed, reverse=True)
        
        return result
    
    async def _store_longterm_insight_item(self, item) -> Dict[str, Any]:
        """Store a long-term insight item."""
        # Generate embedding
        embedding = self.embedding_provider.get_embedding(item.insight_text)
        item.embedding = embedding
        
        doc = item.to_dict()
        
        result = await self.database.upsert(
            container=ContainerType.INSIGHTS,
            document=doc,
            partition_key=item.user_id
        )
        return result
    
    async def _update_insight_access(self, user_id: str, insight_ids: List[str]) -> None:
        """Update access_count and last_accessed for cited insights."""
        for insight_id in insight_ids:
            try:
                doc = await self.database.get_by_id(
                    container=ContainerType.INSIGHTS,
                    document_id=insight_id,
                    partition_key=user_id
                )
                if doc and doc.get("insight_type") == "long_term_item":
                    doc["access_count"] = doc.get("access_count", 0) + 1
                    doc["last_accessed"] = datetime.utcnow().isoformat()
                    
                    await self.database.upsert(
                        container=ContainerType.INSIGHTS,
                        document=doc,
                        partition_key=user_id
                    )
            except Exception as e:
                print(f"  Warning: Could not update access for {insight_id}: {e}")
    
    async def synthesize_longterm_summary(
        self,
        user_id: str,
        top_n: int = 20
    ) -> Optional[str]:
        """
        Create a readable summary from top-N ranked insight items.
        
        Args:
            user_id: User identifier
            top_n: Number of top insights to include
            
        Returns:
            Formatted summary string for context injection
        """
        from memory.core.insight_items import rank_insights
        
        items = await self._get_longterm_insight_items(user_id)
        
        if not items:
            return None
        
        # Rank and get top N
        ranked = rank_insights(items)
        top_items = [item for item, score in ranked[:top_n]]
        
        # Group by category
        by_category = {}
        for item in top_items:
            if item.category not in by_category:
                by_category[item.category] = []
            by_category[item.category].append(item)
        
        # Build summary
        parts = []
        for category, cat_items in by_category.items():
            parts.append(f"\n{category.upper()}:")
            for item in cat_items:
                parts.append(f"- {item.insight_text}")
        
        return "\n".join(parts) if parts else None
    
    async def get_insight_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about a user's long-term insights."""
        from memory.core.insight_items import rank_insights
        
        items = await self._get_longterm_insight_items(user_id)
        
        if not items:
            return {"total_items": 0}
        
        ranked = rank_insights(items)
        
        # Calculate stats
        total_access = sum(item.access_count for item in items)
        by_category = {}
        for item in items:
            by_category[item.category] = by_category.get(item.category, 0) + 1
        
        return {
            "total_items": len(items),
            "total_access_count": total_access,
            "by_category": by_category,
            "top_5_by_rank": [(item.id, f"{score:.2f}") for item, score in ranked[:5]],
            "most_accessed": sorted(
                [(item.id, item.access_count) for item in items],
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }


# Backward compatibility alias
ReflectionProcess = Reflection
