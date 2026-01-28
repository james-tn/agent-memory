"""
SAM Parameter Tuning Module

Provides parameter tuning guidance based on:
1. Query characteristics
2. Graph structure
3. Evaluation feedback
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


class QueryType(Enum):
    """Types of queries for parameter selection."""
    FACTUAL = "factual"           # Simple fact lookup
    RELATIONAL = "relational"     # Relationship between entities
    MULTI_HOP = "multi_hop"       # Requires traversing multiple nodes
    TEMPORAL = "temporal"         # Time-based queries
    AGGREGATION = "aggregation"   # Combining multiple facts


@dataclass
class TuningProfile:
    """A named parameter profile for different use cases."""
    name: str
    description: str
    
    # Spreading activation parameters
    activation_decay: float = 0.7
    activation_threshold: float = 0.05
    max_activation_depth: int = 3
    
    # Anchor search parameters
    anchor_top_k: int = 10
    lexical_weight: float = 0.3
    vector_weight: float = 0.7
    
    # Degree penalty (hub dampening)
    degree_penalty_base: float = 5.0
    
    # Recency weighting
    decay_half_life_days: float = 30.0
    
    def to_config_dict(self) -> Dict[str, Any]:
        """Convert to SAMConfig-compatible dict."""
        return {
            "activation_decay": self.activation_decay,
            "activation_threshold": self.activation_threshold,
            "max_activation_depth": self.max_activation_depth,
            "max_hops": self.max_activation_depth,
            "anchor_top_k": self.anchor_top_k,
            "lexical_weight": self.lexical_weight,
            "vector_weight": self.vector_weight,
            "degree_penalty_base": self.degree_penalty_base,
            "decay_half_life_days": self.decay_half_life_days,
        }


# Pre-defined tuning profiles
PROFILES: Dict[str, TuningProfile] = {
    "default": TuningProfile(
        name="default",
        description="Balanced defaults for general use",
        activation_decay=0.7,
        activation_threshold=0.05,
        max_activation_depth=3,
        anchor_top_k=10,
        lexical_weight=0.3,
        vector_weight=0.7,
        degree_penalty_base=5.0,
    ),
    
    "precise": TuningProfile(
        name="precise",
        description="Higher precision, fewer but more relevant results",
        activation_decay=0.6,           # Faster decay = fewer hops
        activation_threshold=0.1,       # Higher threshold = fewer nodes
        max_activation_depth=2,         # Shallower search
        anchor_top_k=5,                 # Fewer anchors
        lexical_weight=0.4,             # More emphasis on exact matches
        vector_weight=0.6,
        degree_penalty_base=3.0,        # Stronger hub penalty
    ),
    
    "recall": TuningProfile(
        name="recall",
        description="Higher recall, more results for exploration",
        activation_decay=0.8,           # Slower decay = more spread
        activation_threshold=0.02,      # Lower threshold = more nodes
        max_activation_depth=4,         # Deeper search
        anchor_top_k=15,                # More anchors
        lexical_weight=0.3,
        vector_weight=0.7,
        degree_penalty_base=8.0,        # Weaker hub penalty
    ),
    
    "multi_hop": TuningProfile(
        name="multi_hop",
        description="Optimized for multi-hop reasoning queries",
        activation_decay=0.75,          # Moderate decay for multi-hop
        activation_threshold=0.03,      # Low threshold for deeper exploration
        max_activation_depth=4,         # Deep search for chains
        anchor_top_k=12,                # More anchors
        lexical_weight=0.25,            # More semantic matching
        vector_weight=0.75,
        degree_penalty_base=6.0,
    ),
    
    "conversational": TuningProfile(
        name="conversational",
        description="Optimized for conversational memory (recency matters)",
        activation_decay=0.7,
        activation_threshold=0.05,
        max_activation_depth=3,
        anchor_top_k=10,
        lexical_weight=0.35,            # Slightly more lexical for names
        vector_weight=0.65,
        degree_penalty_base=5.0,
        decay_half_life_days=7.0,       # Strong recency preference
    ),
    
    "knowledge_graph": TuningProfile(
        name="knowledge_graph",
        description="Optimized for dense knowledge graphs",
        activation_decay=0.65,          # Faster decay to control flood
        activation_threshold=0.08,      # Higher threshold
        max_activation_depth=3,
        anchor_top_k=8,
        lexical_weight=0.3,
        vector_weight=0.7,
        degree_penalty_base=3.0,        # Strong hub penalty for dense graphs
    ),
}


def get_profile(name: str) -> Optional[TuningProfile]:
    """Get a tuning profile by name."""
    return PROFILES.get(name)


def list_profiles() -> List[str]:
    """List available profile names."""
    return list(PROFILES.keys())


def select_profile_for_query(
    query: str,
    requires_multi_hop: bool = False,
    estimated_hops: int = 1
) -> TuningProfile:
    """
    Automatically select best profile based on query characteristics.
    
    Args:
        query: The query string
        requires_multi_hop: Whether multi-hop was detected
        estimated_hops: Estimated number of hops needed
        
    Returns:
        Recommended TuningProfile
    """
    if requires_multi_hop or estimated_hops >= 2:
        return PROFILES["multi_hop"]
    
    # Check for relationship keywords
    relationship_keywords = [
        "relationship", "between", "connected", "related",
        "work with", "team", "colleague"
    ]
    if any(kw in query.lower() for kw in relationship_keywords):
        return PROFILES["multi_hop"]
    
    # Check for precision keywords
    precision_keywords = [
        "exactly", "specific", "precise", "what is the",
        "name of", "which specific"
    ]
    if any(kw in query.lower() for kw in precision_keywords):
        return PROFILES["precise"]
    
    # Check for exploration keywords
    exploration_keywords = [
        "all", "everything", "list", "tell me about",
        "what do you know", "summarize"
    ]
    if any(kw in query.lower() for kw in exploration_keywords):
        return PROFILES["recall"]
    
    # Default
    return PROFILES["default"]


@dataclass
class TuningResult:
    """Results from parameter tuning experiment."""
    profile_name: str
    precision: float
    recall: float
    f1_score: float
    avg_activation: float
    nodes_retrieved: int
    
    @property
    def score(self) -> float:
        """Combined score for ranking profiles."""
        return self.f1_score


def create_custom_profile(
    name: str,
    base_profile: str = "default",
    **overrides
) -> TuningProfile:
    """
    Create a custom profile based on an existing one.
    
    Args:
        name: Name for the new profile
        base_profile: Profile to use as base
        **overrides: Parameter overrides
        
    Returns:
        New TuningProfile with overrides applied
    """
    base = PROFILES.get(base_profile, PROFILES["default"])
    
    return TuningProfile(
        name=name,
        description=f"Custom profile based on {base_profile}",
        activation_decay=overrides.get("activation_decay", base.activation_decay),
        activation_threshold=overrides.get("activation_threshold", base.activation_threshold),
        max_activation_depth=overrides.get("max_activation_depth", base.max_activation_depth),
        anchor_top_k=overrides.get("anchor_top_k", base.anchor_top_k),
        lexical_weight=overrides.get("lexical_weight", base.lexical_weight),
        vector_weight=overrides.get("vector_weight", base.vector_weight),
        degree_penalty_base=overrides.get("degree_penalty_base", base.degree_penalty_base),
        decay_half_life_days=overrides.get("decay_half_life_days", base.decay_half_life_days),
    )


# Recommended parameter ranges for grid search
PARAMETER_RANGES = {
    "activation_decay": [0.5, 0.6, 0.7, 0.8, 0.9],
    "activation_threshold": [0.01, 0.03, 0.05, 0.08, 0.1],
    "max_activation_depth": [2, 3, 4, 5],
    "anchor_top_k": [5, 8, 10, 12, 15],
    "lexical_weight": [0.2, 0.3, 0.4, 0.5],
    "degree_penalty_base": [3.0, 5.0, 8.0, 10.0],
}


def suggest_next_params(
    current_profile: TuningProfile,
    current_result: TuningResult,
    optimization_goal: str = "f1"
) -> Dict[str, Any]:
    """
    Suggest parameter adjustments based on current results.
    
    Args:
        current_profile: Current parameter profile
        current_result: Evaluation result with current profile
        optimization_goal: What to optimize ("precision", "recall", "f1")
        
    Returns:
        Dict of suggested parameter changes
    """
    suggestions = {}
    
    # Low precision -> tighten parameters
    if current_result.precision < 0.3:
        suggestions["activation_threshold"] = min(0.15, current_profile.activation_threshold + 0.02)
        suggestions["activation_decay"] = max(0.5, current_profile.activation_decay - 0.1)
        suggestions["degree_penalty_base"] = max(3.0, current_profile.degree_penalty_base - 1.0)
    
    # Low recall -> loosen parameters  
    if current_result.recall < 0.3:
        suggestions["activation_threshold"] = max(0.01, current_profile.activation_threshold - 0.02)
        suggestions["max_activation_depth"] = min(5, current_profile.max_activation_depth + 1)
        suggestions["anchor_top_k"] = min(20, current_profile.anchor_top_k + 3)
    
    # Too many nodes -> tighten
    if current_result.nodes_retrieved > 30:
        suggestions["activation_threshold"] = min(0.15, current_profile.activation_threshold + 0.02)
        suggestions["anchor_top_k"] = max(5, current_profile.anchor_top_k - 2)
    
    # Too few nodes -> loosen
    if current_result.nodes_retrieved < 5:
        suggestions["activation_threshold"] = max(0.01, current_profile.activation_threshold - 0.01)
        suggestions["anchor_top_k"] = min(15, current_profile.anchor_top_k + 2)
    
    return suggestions


def print_profile_comparison(profiles: List[str] = None):
    """Print a comparison table of profiles."""
    if profiles is None:
        profiles = list(PROFILES.keys())
    
    print("\n" + "=" * 80)
    print("SAM Parameter Profiles Comparison")
    print("=" * 80)
    
    headers = ["Profile", "Decay", "Threshold", "Depth", "Anchors", "Lex/Vec", "Degree"]
    print(f"{headers[0]:<15} {headers[1]:<8} {headers[2]:<10} {headers[3]:<7} {headers[4]:<8} {headers[5]:<10} {headers[6]:<8}")
    print("-" * 80)
    
    for name in profiles:
        p = PROFILES.get(name)
        if p:
            print(f"{p.name:<15} {p.activation_decay:<8.2f} {p.activation_threshold:<10.3f} "
                  f"{p.max_activation_depth:<7} {p.anchor_top_k:<8} "
                  f"{p.lexical_weight:.1f}/{p.vector_weight:.1f}  {p.degree_penalty_base:<8.1f}")
    
    print("=" * 80)
