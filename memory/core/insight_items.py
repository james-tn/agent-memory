"""
Itemized Long-Term Insights with Citation Tracking

This module implements a more human-like memory system where:
1. Each insight is a discrete item with tracking metadata
2. Insights have recency (date_added, last_accessed) 
3. Insights have frequency (access_count via citation)
4. A ranking system prioritizes recent and frequently-used insights
5. Long-term memory is bounded - only top-N insights are retained

Data Model:
- LongTermInsightItem: Individual tracked insight
- InsightCitation: Record of an insight being referenced
- RankedInsightSet: Collection of insights with ranking scores
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import math
import uuid
from pydantic import BaseModel, Field


# ==================== Pydantic Models for Structured LLM Outputs ====================

class ExtractedInsight(BaseModel):
    """A new insight extracted from the current session."""
    insight_text: str = Field(description="Clear, actionable insight about the user")
    category: str = Field(description="Category: preferences, goals, behavior_patterns, knowledge_level, or learning_progress")
    confidence: float = Field(description="Confidence score 0.0-1.0", ge=0.0, le=1.0)
    importance: str = Field(description="Importance level: high, medium, or low")


class InsightCitation(BaseModel):
    """Citation of an existing long-term insight that was relevant in this session."""
    insight_id: str = Field(description="The ID of the existing insight (e.g., 'INS-001')")
    relevance: str = Field(description="Brief explanation of why this insight was relevant")


class SessionAnalysisWithCitations(BaseModel):
    """
    Comprehensive session analysis that extracts new insights AND cites existing ones.
    This enables tracking which long-term insights are actually being used.
    """
    session_summary: str = Field(
        description="Comprehensive 2-4 sentence session summary"
    )
    key_topics: List[str] = Field(
        description="3-5 key topics discussed",
        min_length=1,
        max_length=5
    )
    new_insights: List[ExtractedInsight] = Field(
        description="0-5 NEW insights extracted from this session",
        max_length=5
    )
    cited_insights: List[InsightCitation] = Field(
        description="IDs of existing long-term insights that were relevant/referenced in this session",
        default_factory=list
    )
    has_meaningful_content: bool = Field(
        description="True if session had meaningful content worth analyzing"
    )


# ==================== Data Classes for Storage ====================

@dataclass
class LongTermInsightItem:
    """
    An individual long-term insight with tracking metadata.
    
    This represents a discrete piece of learned information about the user
    that can be individually tracked, ranked, and pruned.
    """
    # Identity
    id: str                           # e.g., "INS-001", "INS-002"
    user_id: str                      # User this insight belongs to
    
    # Content
    insight_text: str                 # The actual insight
    category: str                     # preferences, goals, behavior_patterns, etc.
    confidence: float                 # How confident we are (0.0-1.0)
    importance: str                   # high, medium, low
    
    # Tracking metadata
    date_added: datetime              # When first captured
    last_accessed: datetime           # Last time it was cited as useful
    access_count: int = 0             # How many times cited
    
    # Source tracking
    source_session_ids: List[str] = field(default_factory=list)
    
    # Embedding for semantic search
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "insight_type": "long_term_item",  # Distinguish from old format
            "insight_text": self.insight_text,
            "insight_vector": self.embedding,
            "category": self.category,
            "confidence": self.confidence,
            "importance": self.importance,
            "date_added": self.date_added.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "source_session_ids": self.source_session_ids,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LongTermInsightItem":
        """Create from dictionary (e.g., from database)."""
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            insight_text=data["insight_text"],
            category=data.get("category", "general"),
            confidence=data.get("confidence", 0.5),
            importance=data.get("importance", "medium"),
            date_added=datetime.fromisoformat(data["date_added"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data.get("access_count", 0),
            source_session_ids=data.get("source_session_ids", []),
            embedding=data.get("insight_vector"),
        )


# ==================== Ranking Functions ====================

def calculate_retention_score(
    item: LongTermInsightItem,
    now: Optional[datetime] = None,
    base_decay_days: float = 30.0,
    recency_grace_days: int = 7,
    importance_weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate a retention score for an insight item.
    
    Inspired by Ebbinghaus forgetting curve, modified for our use case:
    - Higher access_count = slower decay (memories we use often persist)
    - Recency matters (but with a grace period for new items)
    - Importance provides a base boost
    
    Args:
        item: The insight item to score
        now: Current time (defaults to utcnow)
        base_decay_days: Base half-life in days
        recency_grace_days: Days of grace period for new items
        importance_weights: Weights for importance levels
        
    Returns:
        Retention score (higher = more likely to retain)
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    if importance_weights is None:
        importance_weights = {"high": 1.5, "medium": 1.0, "low": 0.7}
    
    # Days since last access
    days_since_access = (now - item.last_accessed).total_seconds() / 86400
    
    # Strength increases logarithmically with access count
    # This means frequently accessed items decay slower
    strength = 1.0 + math.log1p(item.access_count)
    
    # Decay based on time since last access, modulated by strength
    # Higher strength = slower decay
    decay_rate = base_decay_days * strength
    retention = math.exp(-days_since_access / decay_rate)
    
    # Recency boost for new items (grace period)
    days_since_added = (now - item.date_added).total_seconds() / 86400
    recency_boost = 0.3 if days_since_added < recency_grace_days else 0.0
    
    # Importance weight
    importance_weight = importance_weights.get(item.importance, 1.0)
    
    # Confidence factor
    confidence_factor = 0.5 + (item.confidence * 0.5)  # Range: 0.5 to 1.0
    
    # Final score
    score = (retention + recency_boost) * importance_weight * confidence_factor
    
    return score


def rank_insights(
    items: List[LongTermInsightItem],
    now: Optional[datetime] = None
) -> List[tuple]:
    """
    Rank insights by retention score.
    
    Args:
        items: List of insight items
        now: Current time
        
    Returns:
        List of (item, score) tuples sorted by score descending
    """
    scored = [(item, calculate_retention_score(item, now)) for item in items]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def get_top_insights(
    items: List[LongTermInsightItem],
    top_n: int = 20,
    now: Optional[datetime] = None
) -> List[LongTermInsightItem]:
    """
    Get the top-N insights by retention score.
    
    Args:
        items: List of insight items
        top_n: Number of insights to keep
        now: Current time
        
    Returns:
        Top N insights by retention score
    """
    ranked = rank_insights(items, now)
    return [item for item, score in ranked[:top_n]]


# ==================== ID Generation ====================

class InsightIdGenerator:
    """
    Generates sequential insight IDs for a user.
    Format: INS-{sequence_number:04d}
    """
    
    def __init__(self, existing_ids: List[str] = None):
        """
        Initialize with existing IDs to continue sequence.
        
        Args:
            existing_ids: List of existing insight IDs
        """
        self.current_seq = 0
        if existing_ids:
            for id_str in existing_ids:
                if id_str.startswith("INS-"):
                    try:
                        seq = int(id_str.split("-")[1])
                        self.current_seq = max(self.current_seq, seq)
                    except (ValueError, IndexError):
                        pass
    
    def next_id(self) -> str:
        """Generate the next insight ID."""
        self.current_seq += 1
        return f"INS-{self.current_seq:04d}"


# ==================== Prompt Building ====================

def build_context_with_ids(items: List[LongTermInsightItem]) -> str:
    """
    Build context string with insight IDs for citation.
    
    Args:
        items: List of insight items to include in context
        
    Returns:
        Formatted context string with [INS-XXX] references
    """
    if not items:
        return "(No existing long-term insights)"
    
    # Group by category
    by_category: Dict[str, List[LongTermInsightItem]] = {}
    for item in items:
        if item.category not in by_category:
            by_category[item.category] = []
        by_category[item.category].append(item)
    
    parts = ["EXISTING LONG-TERM INSIGHTS (cite IDs if relevant):"]
    
    for category, cat_items in by_category.items():
        parts.append(f"\n{category.upper()}:")
        for item in cat_items:
            parts.append(f"  [{item.id}] {item.insight_text}")
    
    return "\n".join(parts)
