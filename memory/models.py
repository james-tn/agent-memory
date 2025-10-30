"""
Pydantic models for Agent Memory Service.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class InteractionMetadata(BaseModel):
    """Metadata for interaction documents."""
    mentioned_topics: List[str] = Field(default_factory=list, description="Key topics discussed")
    entities: List[str] = Field(default_factory=list, description="Specific entities mentioned")


class InteractionDocument(BaseModel):
    """
    Represents a multi-turn conversation chunk stored in CosmosDB.
    """
    id: str = Field(..., description="Unique identifier (UUID)")
    user_id: str = Field(..., description="User identifier")
    session_id: str = Field(..., description="Session identifier")
    timestamp: str = Field(..., description="ISO 8601 timestamp of first turn")
    content: str = Field(..., description="Flattened conversation: 'user: ...\\nassistant: ...'")
    content_vector: List[float] = Field(..., description="Embedding vector for content")
    summary: str = Field(..., description="Concise summary of this chunk")
    summary_vector: List[float] = Field(..., description="Embedding vector for summary")
    metadata: InteractionMetadata = Field(default_factory=InteractionMetadata)


class SessionInsightDocument(BaseModel):
    """
    Represents a session-level insight extracted from one or more sessions.
    """
    id: str = Field(..., description="Unique identifier (UUID)")
    user_id: str = Field(..., description="User identifier")
    insight_type: Literal["session"] = "session"
    session_ids: List[str] = Field(..., description="Source session IDs")
    insight_text: str = Field(..., description="The extracted insight")
    insight_vector: List[float] = Field(..., description="Embedding vector for insight")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    importance: Literal["high", "medium", "low"] = Field(..., description="Importance level")
    category: str = Field(..., description="Insight category (e.g., demographics, financial_goals)")
    reflection_flag: Literal["insight", "no-insight"] = "insight"
    processed: bool = Field(default=False, description="Whether incorporated into long-term insight")
    created_at: str = Field(..., description="ISO 8601 timestamp")
    updated_at: str = Field(..., description="ISO 8601 timestamp")


class LongTermInsightDocument(BaseModel):
    """
    Represents the comprehensive long-term insight for a user.
    One document per user.
    """
    id: str = Field(..., description="Format: longterm-{user_id}")
    user_id: str = Field(..., description="User identifier")
    insight_type: Literal["long_term"] = "long_term"
    insight_text: str = Field(..., description="Comprehensive user profile")
    insight_vector: List[float] = Field(..., description="Embedding vector for insight")
    confidence: Optional[float] = None
    importance: Optional[str] = None
    category: Optional[str] = None
    source_insight_ids: List[str] = Field(default_factory=list, description="Session insight IDs used")
    created_at: str = Field(..., description="ISO 8601 timestamp")
    updated_at: str = Field(..., description="ISO 8601 timestamp")


class SessionSummaryDocument(BaseModel):
    """
    Represents session-level metadata and summary.
    """
    id: str = Field(..., description="Session UUID")
    user_id: str = Field(..., description="User identifier")
    start_time: str = Field(..., description="ISO 8601 timestamp")
    end_time: Optional[str] = Field(None, description="ISO 8601 timestamp")
    summary: str = Field(..., description="Session summary")
    summary_vector: List[float] = Field(..., description="Embedding vector for summary")
    key_topics: List[str] = Field(default_factory=list, description="Main topics discussed")
    extracted_insights: List[str] = Field(default_factory=list, description="Insight IDs extracted")
    status: Literal["active", "completed"] = "active"
    reflection_status: Literal["pending", "no-insight", "processed"] = "pending"


class ConversationTurn(BaseModel):
    """
    Represents a single conversation turn in memory buffer.
    """
    role: Literal["user", "assistant"]
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SessionInitContext(BaseModel):
    """
    Context loaded at session initialization.
    """
    longterm_insight: Optional[str] = None
    recent_summaries: List[dict] = Field(default_factory=list)
    formatted_context: str = ""
