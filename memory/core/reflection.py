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

from typing import List, Dict, Optional, Any, Type, Literal
from datetime import datetime, timezone
import uuid
from dataclasses import dataclass
from pydantic import BaseModel, Field

from memory.db.base import ContainerType, MemoryDatabase
from memory.core.llm_json import call_llm_with_json
from memory.models import InsightMutationRecord
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


class ConflictResolutionAction(BaseModel):
    """A single conflict-resolution action."""

    id: Optional[str] = Field(default=None, description="Integer ID of the existing memory for UPDATE/DELETE/NONE")
    text: Optional[str] = Field(default=None, description="Final insight text for ADD/UPDATE")
    event: Literal["ADD", "UPDATE", "DELETE", "NONE"]
    category: Optional[str] = Field(default=None, description="Insight category for ADD/UPDATE")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    importance: Optional[str] = Field(default=None, description="Importance level for ADD/UPDATE")
    rationale: Optional[str] = Field(default=None, description="Short explanation of the action")
    old_memory: Optional[str] = Field(default=None, description="Existing memory text the action refers to")


class ConflictResolutionResult(BaseModel):
    """Structured output for conflict resolution."""

    memory: List[ConflictResolutionAction] = Field(default_factory=list)


# ==================== Configuration ====================

@dataclass
class ReflectionConfig:
    """Configuration for reflection process."""
    PROCESSING_MODEL: str = "gpt-4o-mini"  # Model for analysis
    insight_categories: List[str] = None
    custom_extraction_prompt: Optional[str] = None
    custom_conflict_resolution_prompt: Optional[str] = None
    max_conflict_candidates: int = 5


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
        agent_id: str,
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
        self.agent_id = agent_id
        self.database = database
        self.embedding_provider = embedding_provider
        self.chat_client = chat_client
        self.config = config or ReflectionConfig()
        if not self.config.insight_categories:
            self.config.insight_categories = [
                "preferences",
                "knowledge_level",
                "goals",
                "behavior_patterns",
                "learning_progress",
            ]
    
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
        return call_llm_with_json(
            self.chat_client,
            self.config.PROCESSING_MODEL,
            system_prompt,
            user_prompt,
            output_model,
        )
    
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
                    "extracted_at": self._utcnow_iso()
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
            filters={"user_id": user_id, "agent_id": self.agent_id, "session_id": session_id},
            order_by="timestamp"
        )
    
    async def _get_user_insights(
        self,
        user_id: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Get existing insights for a user."""
        filters = {"user_id": user_id, "agent_id": self.agent_id}
        if category:
            filters["category"] = category
        
        insights = await self.database.query(
            container=ContainerType.INSIGHTS,
            filters=filters,
            order_by="-updated_at"
        )
        return [insight for insight in insights if self._is_active_insight(insight)]
    
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

    def _category_instructions(self) -> str:
        """Render configured insight categories for prompt templates."""
        return "\n".join(
            f"- **{category}**: insights relevant to {category.replace('_', ' ')}"
            for category in self.config.insight_categories
        )

    def _format_prompt(self, template: str, **kwargs: Any) -> str:
        """Format a prompt template with best-effort placeholder support."""
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    def _is_active_insight(self, insight: Dict[str, Any]) -> bool:
        """Return True for active, searchable insight documents."""
        return (
            insight.get("insight_type") in {"session", "long_term_item"}
            and not insight.get("is_deleted", False)
        )

    def _make_mutation_record(
        self,
        *,
        event: str,
        session_id: Optional[str],
        old_text: Optional[str],
        new_text: Optional[str],
        rationale: Optional[str],
    ) -> Dict[str, Any]:
        return InsightMutationRecord(
            event=event,
            timestamp=self._utcnow_iso(),
            session_id=session_id,
            old_text=old_text,
            new_text=new_text,
            rationale=rationale,
        ).model_dump()

    def _longterm_doc_id(self, user_id: str) -> str:
        """Build the scoped long-term profile document ID."""
        return f"longterm-{self.agent_id}-{user_id}"
    
    async def _generate_comprehensive_analysis(self, session_content: str) -> ComprehensiveSessionAnalysis:
        """
        Generate comprehensive session analysis with single LLM call.
        
        Args:
            session_content: Full session context (cumulative summary + recent turns)
            
        Returns:
            ComprehensiveSessionAnalysis with summary, topics, and insights
        """
        from memory.prompts import COMPREHENSIVE_SESSION_ANALYSIS_PROMPT

        prompt_template = self.config.custom_extraction_prompt or COMPREHENSIVE_SESSION_ANALYSIS_PROMPT
        prompt = self._format_prompt(
            prompt_template,
            session_content=session_content,
            category_instructions=self._category_instructions(),
            category_list=", ".join(self.config.insight_categories),
        )
        
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

    async def reconcile_session_insights(
        self,
        user_id: str,
        session_id: str,
        extracted_insights: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Reconcile extracted insights against existing active memories."""
        normalized = [
            insight if isinstance(insight, SessionInsight) else SessionInsight(**insight)
            for insight in extracted_insights
            if insight
        ]
        if not normalized:
            return [], []

        candidates = await self._get_conflict_candidates(user_id, normalized)
        actions = await self._resolve_conflicts(candidates, normalized)
        stored_docs: List[Dict[str, Any]] = []
        mutation_records: List[Dict[str, Any]] = []
        candidate_by_id = {candidate["id"]: candidate for candidate in candidates}

        for action in actions:
            if action.event == "NONE":
                if action.id and action.id in candidate_by_id:
                    mutation_records.append(
                        self._make_mutation_record(
                            event="NONE",
                            session_id=session_id,
                            old_text=candidate_by_id[action.id].get("insight_text"),
                            new_text=candidate_by_id[action.id].get("insight_text"),
                            rationale=action.rationale,
                        )
                    )
                continue

            if action.event == "ADD":
                stored_doc = await self._create_session_insight_doc(
                    user_id=user_id,
                    session_id=session_id,
                    insight=SessionInsight(
                        insight_text=action.text or "",
                        category=action.category or normalized[0].category,
                        confidence=action.confidence if action.confidence is not None else normalized[0].confidence,
                        importance=action.importance or normalized[0].importance,
                    ),
                    rationale=action.rationale,
                )
                stored_docs.append(stored_doc)
                mutation_records.append(stored_doc["mutation_history"][-1])
                continue

            existing_doc = candidate_by_id.get(action.id or "")
            if not existing_doc:
                continue

            if action.event == "UPDATE":
                updated_doc = await self._update_existing_insight_doc(
                    existing_doc,
                    session_id=session_id,
                    text=action.text or existing_doc.get("insight_text", ""),
                    category=action.category or existing_doc.get("category", "general"),
                    confidence=action.confidence if action.confidence is not None else existing_doc.get("confidence", 0.5),
                    importance=action.importance or existing_doc.get("importance", "medium"),
                    rationale=action.rationale,
                )
                stored_docs.append(updated_doc)
                mutation_records.append(updated_doc["mutation_history"][-1])
                continue

            if action.event == "DELETE":
                deleted_doc = await self._soft_delete_insight_doc(
                    existing_doc,
                    session_id=session_id,
                    rationale=action.rationale,
                )
                mutation_records.append(deleted_doc["mutation_history"][-1])

        return stored_docs, mutation_records

    async def _get_conflict_candidates(
        self,
        user_id: str,
        extracted_insights: List[SessionInsight],
    ) -> List[Dict[str, Any]]:
        """Find existing insights that could conflict with new ones."""
        candidates: Dict[str, Dict[str, Any]] = {}

        for insight in extracted_insights:
            embedding = self.embedding_provider.get_embedding(insight.insight_text)
            results = await self.database.vector_search(
                container=ContainerType.INSIGHTS,
                query_embedding=embedding,
                vector_field="insight_vector",
                top_k=self.config.max_conflict_candidates,
                filters={"user_id": user_id, "agent_id": self.agent_id},
            )
            for result in results:
                doc = result.document
                if not self._is_active_insight(doc):
                    continue
                candidates[doc["id"]] = doc

        return list(candidates.values())

    async def _resolve_conflicts(
        self,
        existing_candidates: List[Dict[str, Any]],
        extracted_insights: List[SessionInsight],
    ) -> List[ConflictResolutionAction]:
        """Use the LLM to reconcile new insights with existing ones."""
        if not extracted_insights:
            return []

        from memory.prompts import CONFLICT_RESOLUTION_PROMPT

        id_map = {str(index): doc for index, doc in enumerate(existing_candidates)}
        existing_lines = []
        for mapped_id, doc in id_map.items():
            existing_lines.append(
                f"[{mapped_id}] {doc.get('insight_text', '')} | category={doc.get('category', 'general')} | "
                f"importance={doc.get('importance', 'medium')} | confidence={doc.get('confidence', 0.5)}"
            )
        new_lines = []
        for index, insight in enumerate(extracted_insights, start=1):
            new_lines.append(
                f"[N{index}] {insight.insight_text} | category={insight.category} | "
                f"importance={insight.importance} | confidence={insight.confidence}"
            )

        prompt_template = self.config.custom_conflict_resolution_prompt or CONFLICT_RESOLUTION_PROMPT
        prompt = self._format_prompt(
            prompt_template,
            existing_memories="\n".join(existing_lines) if existing_lines else "(none)",
            new_insights="\n".join(new_lines),
            category_list=", ".join(self.config.insight_categories),
        )

        try:
            result = self._call_llm_with_json(
                system_prompt="You reconcile memory insights and return structured mutation actions.",
                user_prompt=prompt,
                output_model=ConflictResolutionResult,
            )
            actions = result.memory
        except Exception as exc:
            print(f"  Error resolving insight conflicts: {exc}")
            actions = []

        if not actions:
            return [
                ConflictResolutionAction(
                    event="ADD",
                    text=insight.insight_text,
                    category=insight.category,
                    confidence=insight.confidence,
                    importance=insight.importance,
                    rationale="Fallback add after conflict resolution failure.",
                )
                for insight in extracted_insights
            ]

        for action in actions:
            if action.id is not None and action.id in id_map:
                action.id = id_map[action.id]["id"]
        return actions
    
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
            "agent_id": self.agent_id,
            "insight_text": insight.insight_text,
            "insight_vector": embedding,
            "category": insight.category,
            "confidence": insight.confidence,
            "importance": insight.importance,
            "source_session_id": session_id,
            "is_synthesized": is_synthesized,
            "is_deleted": False,
            "deleted_at": None,
            "mutation_history": [],
            "created_at": self._utcnow_iso(),
            "updated_at": self._utcnow_iso()
        }
        
        result = await self.database.upsert(
            container=ContainerType.INSIGHTS,
            document=insight_doc,
            partition_key=user_id
        )
        return result

    async def _create_session_insight_doc(
        self,
        *,
        user_id: str,
        session_id: str,
        insight: SessionInsight,
        rationale: Optional[str],
    ) -> Dict[str, Any]:
        """Create and persist a new session insight document."""
        now = self._utcnow_iso()
        mutation_history = [
            self._make_mutation_record(
                event="ADD",
                session_id=session_id,
                old_text=None,
                new_text=insight.insight_text,
                rationale=rationale,
            )
        ]
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "agent_id": self.agent_id,
            "session_ids": [session_id],
            "insight_type": "session",
            "insight_text": insight.insight_text,
            "insight_vector": self.embedding_provider.get_embedding(insight.insight_text),
            "category": insight.category,
            "confidence": insight.confidence,
            "importance": insight.importance,
            "processed": False,
            "is_deleted": False,
            "deleted_at": None,
            "mutation_history": mutation_history,
            "created_at": now,
            "updated_at": now,
        }
        return await self.database.upsert(
            container=ContainerType.INSIGHTS,
            document=doc,
            partition_key=user_id,
        )

    async def _update_existing_insight_doc(
        self,
        existing_doc: Dict[str, Any],
        *,
        session_id: str,
        text: str,
        category: str,
        confidence: float,
        importance: str,
        rationale: Optional[str],
    ) -> Dict[str, Any]:
        """Update an existing insight document in place."""
        updated_doc = dict(existing_doc)
        updated_doc["insight_text"] = text
        updated_doc["insight_vector"] = self.embedding_provider.get_embedding(text)
        updated_doc["category"] = category
        updated_doc["confidence"] = confidence
        updated_doc["importance"] = importance
        updated_doc["processed"] = False
        updated_doc["is_deleted"] = False
        updated_doc["deleted_at"] = None
        updated_doc["updated_at"] = self._utcnow_iso()

        if updated_doc.get("insight_type") == "session":
            session_ids = list(updated_doc.get("session_ids", []))
            if session_id not in session_ids:
                session_ids.append(session_id)
            updated_doc["session_ids"] = session_ids
        elif updated_doc.get("insight_type") == "long_term_item":
            source_session_ids = list(updated_doc.get("source_session_ids", []))
            if session_id not in source_session_ids:
                source_session_ids.append(session_id)
            updated_doc["source_session_ids"] = source_session_ids

        mutation_history = list(updated_doc.get("mutation_history", []))
        mutation_history.append(
            self._make_mutation_record(
                event="UPDATE",
                session_id=session_id,
                old_text=existing_doc.get("insight_text"),
                new_text=text,
                rationale=rationale,
            )
        )
        updated_doc["mutation_history"] = mutation_history

        return await self.database.upsert(
            container=ContainerType.INSIGHTS,
            document=updated_doc,
            partition_key=updated_doc["user_id"],
        )

    async def _soft_delete_insight_doc(
        self,
        existing_doc: Dict[str, Any],
        *,
        session_id: str,
        rationale: Optional[str],
    ) -> Dict[str, Any]:
        """Soft-delete an insight document to preserve audit history."""
        deleted_doc = dict(existing_doc)
        deleted_doc["is_deleted"] = True
        deleted_doc["deleted_at"] = self._utcnow_iso()
        deleted_doc["updated_at"] = deleted_doc["deleted_at"]
        deleted_doc["processed"] = True
        mutation_history = list(deleted_doc.get("mutation_history", []))
        mutation_history.append(
            self._make_mutation_record(
                event="DELETE",
                session_id=session_id,
                old_text=existing_doc.get("insight_text"),
                new_text=None,
                rationale=rationale,
            )
        )
        deleted_doc["mutation_history"] = mutation_history
        return await self.database.upsert(
            container=ContainerType.INSIGHTS,
            document=deleted_doc,
            partition_key=deleted_doc["user_id"],
        )
    
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
        
        # 4. Upsert longterm profile document
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
        longterm_id = self._longterm_doc_id(user_id)
        
        doc = await self.database.get_by_id(
            container=ContainerType.INSIGHTS,
            document_id=longterm_id,
            partition_key=user_id
        )
        
        if doc and doc.get("agent_id", "default") == self.agent_id and not doc.get("is_deleted", False):
            return doc.get("insight_text", "")
        return await self.synthesize_longterm_summary(user_id)
    
    async def _get_unprocessed_insights(self, user_id: str) -> List[Dict]:
        """Fetch all unprocessed session insights for a user."""
        # Get all session insights for the user
        all_insights = await self.database.query(
            container=ContainerType.INSIGHTS,
            filters={"user_id": user_id, "agent_id": self.agent_id, "insight_type": "session"},
            order_by="created_at"
        )
        
        # Filter for unprocessed (processed is not defined or False)
        return [
            insight for insight in all_insights
            if not insight.get("processed", False) and not insight.get("is_deleted", False)
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
        from memory.prompts import LONGTERM_PROFILE_CREATE_PROMPT, LONGTERM_PROFILE_UPDATE_PROMPT
        
        # Build prompt based on whether existing profile exists
        if existing_profile:
            prompt = LONGTERM_PROFILE_UPDATE_PROMPT.format(
                user_id=user_id,
                existing_profile=existing_profile,
                new_insights_context=new_insights_context,
            )
        else:
            prompt = LONGTERM_PROFILE_CREATE_PROMPT.format(
                user_id=user_id,
                new_insights_context=new_insights_context,
            )
        
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
        longterm_id = self._longterm_doc_id(user_id)
        
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
            existing_doc["agent_id"] = self.agent_id
            existing_doc["source_insight_ids"] = list(set(
                existing_doc.get("source_insight_ids", []) + source_insight_ids
            ))
            existing_doc["is_deleted"] = False
            existing_doc["deleted_at"] = None
            existing_doc["updated_at"] = self._utcnow_iso()
            
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
                "agent_id": self.agent_id,
                "insight_type": "long_term",
                "insight_text": profile_output.profile_text,
                "insight_vector": embedding,
                "confidence": profile_output.confidence,
                "source_insight_ids": source_insight_ids,
                "is_deleted": False,
                "deleted_at": None,
                "mutation_history": [],
                "created_at": self._utcnow_iso(),
                "updated_at": self._utcnow_iso()
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
                    insight_doc["updated_at"] = self._utcnow_iso()
                    
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
                agent_id=self.agent_id,
                insight_text=insight.insight_text,
                category=insight.category,
                confidence=insight.confidence,
                importance=insight.importance,
                date_added=datetime.now(timezone.utc),
                last_accessed=datetime.now(timezone.utc),
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
            filters={"user_id": user_id, "agent_id": self.agent_id, "insight_type": "long_term_item"},
            order_by="-created_at"  # Use created_at which is guaranteed to exist
        )
        
        result = []
        for item_data in items:
            if item_data.get("is_deleted", False):
                continue
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
                    doc["last_accessed"] = self._utcnow_iso()
                    
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
    def _utcnow_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
