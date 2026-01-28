"""
SAM Configuration

Configuration for SAM (Spreading Activation Memory) including:
- Storage engine settings
- Episode management
- Working memory buffer
- Spreading activation parameters
- Decay settings
- Model configurations
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class SAMConfig(BaseModel):
    """
    Configuration for SAM (Spreading Activation Memory).
    """
    
    # =========================================================================
    # Storage Engine
    # =========================================================================
    
    storage_engine: Literal["sqlite", "postgres", "cosmos"] = Field(
        default="sqlite",
        description="Storage backend to use"
    )
    
    database_url: str = Field(
        default="sqlite:///sam_memory.db",
        description="Database connection URL"
    )
    
    # =========================================================================
    # Episode Management
    # =========================================================================
    
    max_episode_tokens: int = Field(
        default=10_000,
        description="Start new Episode when current exceeds this token count"
    )
    
    # =========================================================================
    # Working Memory Buffer
    # =========================================================================
    
    buffer_size: int = Field(
        default=10,
        description="Number of turns to accumulate before flushing to Episode"
    )
    
    active_turns: int = Field(
        default=5,
        description="Number of recent turns to keep in active context"
    )
    
    # =========================================================================
    # Spreading Activation Parameters
    # =========================================================================
    
    activation_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Minimum activation to continue spreading (lower = more results)"
    )
    
    max_hops: int = Field(
        default=3,
        description="Maximum hops from anchor during spreading"
    )
    
    max_activation_depth: int = Field(
        default=3,
        description="Maximum depth for spreading activation (alias for max_hops)"
    )
    
    activation_decay: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Decay factor per hop during spreading (0.7 = 30% reduction per hop)"
    )
    
    anchor_top_k: int = Field(
        default=10,
        description="Number of top anchors to use for spreading"
    )
    
    max_activated_nodes: int = Field(
        default=50,
        description="Maximum nodes to activate during retrieval"
    )
    
    degree_penalty_base: float = Field(
        default=10.0,
        description="Base for degree penalty: min(1.0, base/sqrt(degree)). Higher = less aggressive dampening."
    )
    
    dead_end_penalty: float = Field(
        default=0.3,
        description="Penalty multiplier for dead-end nodes (entities with no outgoing edges)"
    )
    
    claim_boost: float = Field(
        default=2.0,
        description="Boost multiplier for claim nodes to balance against entity accumulation"
    )
    
    # =========================================================================
    # Hybrid Search Weights
    # =========================================================================
    
    lexical_weight: float = Field(
        default=0.3,
        description="Weight for lexical (FTS) search in anchor discovery"
    )
    
    vector_weight: float = Field(
        default=0.7,
        description="Weight for vector similarity in anchor discovery"
    )
    
    anchor_limit: int = Field(
        default=10,
        description="Maximum anchors from hybrid search"
    )
    
    # =========================================================================
    # Decay Settings
    # =========================================================================
    
    decay_half_life_days: float = Field(
        default=30.0,
        description="Days until node strength halves (if not accessed)"
    )
    
    min_strength: float = Field(
        default=0.01,
        description="Minimum strength before node is considered for pruning"
    )
    
    # Claim-kind specific decay multipliers
    claim_decay_multipliers: dict = Field(
        default_factory=lambda: {
            "permanent": 0.0,      # No decay
            "stable": 0.5,         # Half the normal decay rate
            "contextual": 1.0,     # Normal decay
            "ephemeral": 2.0,      # Double decay rate
        },
        description="Decay rate multipliers by claim_kind"
    )
    
    # =========================================================================
    # LLM Configuration
    # =========================================================================
    
    extraction_model: str = Field(
        default="gpt-4o-mini",
        description="Model for entity/claim extraction"
    )
    
    summary_model: str = Field(
        default="gpt-4o-mini",
        description="Model for episode summarization"
    )
    
    synthesis_model: str = Field(
        default="gpt-4o",
        description="Model for insight synthesis and reasoning"
    )
    
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Model for generating embeddings"
    )
    
    embedding_dimensions: int = Field(
        default=1536,
        description="Embedding vector dimensions"
    )
    
    # =========================================================================
    # Context Building
    # =========================================================================
    
    include_insights_in_context: bool = Field(
        default=True,
        description="Include long-term insights in context"
    )
    
    include_recent_episodes: bool = Field(
        default=True,
        description="Include recent episode summaries in context"
    )
    
    max_recent_episodes: int = Field(
        default=3,
        description="Maximum recent episodes to include in context"
    )
    
    max_context_tokens: int = Field(
        default=4000,
        description="Maximum tokens for formatted context"
    )
    
    model_config = {"extra": "allow"}  # Allow additional fields for extensibility


# Default configuration instance
default_config = SAMConfig()
