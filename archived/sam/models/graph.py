"""
SAM Graph Data Models

Defines the 5-node ontology: Episode → Entity → Claim → Insight → Procedure
Plus typed edges for relationships.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


# =============================================================================
# Enums
# =============================================================================

class NodeType(str, Enum):
    """Types of nodes in the SAM graph."""
    EPISODE = "episode"
    ENTITY = "entity"
    CLAIM = "claim"
    INSIGHT = "insight"
    PROCEDURE = "procedure"


class EdgeType(str, Enum):
    """Types of edges connecting nodes.
    
    Structural edges (Episode/Claim/Insight relationships):
    - MENTIONS, PRODUCED, ABOUT, SUPPORTS, CONTRADICTS, DERIVED_FROM, SUPERSEDES, IMPLEMENTS
    
    Semantic relationship edges (Entity → Entity):
    - Use RELATIONSHIP for custom semantic types, store actual type in edge metadata
    - Common semantic types are pre-defined for convenience
    """
    # Episode edges
    MENTIONS = "MENTIONS"          # Episode → Entity (entity appeared in episode)
    PRODUCED = "PRODUCED"          # Episode → Claim (claim extracted from episode)
    
    # Claim edges
    ABOUT = "ABOUT"                # Claim → Entity (claim describes entity) - REQUIRED
    SUPPORTS = "SUPPORTS"          # Claim → Claim or Claim → Insight
    CONTRADICTS = "CONTRADICTS"    # Claim → Claim
    
    # Insight edges
    DERIVED_FROM = "DERIVED_FROM"  # Insight → Claim (source claims)
    SUPERSEDES = "SUPERSEDES"      # Insight → Insight (newer replaces older)
    
    # Procedure edges
    IMPLEMENTS = "IMPLEMENTS"      # Procedure → Insight
    
    # ==========================================================================
    # Semantic Relationship Edges (Entity → Entity)
    # These enable multi-hop traversal with meaningful connections
    # ==========================================================================
    
    # Generic relationships (fallback)
    RELATED_TO = "RELATED_TO"      # Generic association between entities
    
    # Person/Work relationships
    WORKS_WITH = "WORKS_WITH"      # Person → Person
    WORKS_ON = "WORKS_ON"          # Person → Project/Topic
    MANAGES = "MANAGES"            # Person → Person/Project
    MEMBER_OF = "MEMBER_OF"        # Person → Organization
    CREATED = "CREATED"            # Person/Org → Product/Project
    
    # Healthcare/Medical relationships (critical for safety)
    ALLERGIC_TO = "ALLERGIC_TO"    # Patient → Allergen (CRITICAL - high weight)
    TAKES = "TAKES"                # Patient → Medication
    PRESCRIBED = "PRESCRIBED"       # Provider → Medication (or Patient if passive)
    TREATS = "TREATS"              # Medication/Procedure → Condition
    DIAGNOSED_WITH = "DIAGNOSED_WITH"  # Patient → Condition
    EXPERIENCES = "EXPERIENCES"    # Patient → Symptom
    SIDE_EFFECT_OF = "SIDE_EFFECT_OF"  # Symptom → Medication
    CAUSES = "CAUSES"              # Entity → Symptom/Condition
    CONTRAINDICATED_WITH = "CONTRAINDICATED_WITH"  # Medication → Medication/Condition
    TREATED_BY = "TREATED_BY"      # Patient → Provider
    SPECIALIST_FOR = "SPECIALIST_FOR"  # Provider → Condition type
    ORDERED = "ORDERED"            # Provider → Procedure
    MEASURED = "MEASURED"          # Measurement value
    INDICATES = "INDICATES"        # Measurement → Condition status
    AFFECTS = "AFFECTS"            # Lifestyle → Condition
    REPLACES = "REPLACES"          # Medication → Medication (substitution)
    
    # Preference/Interest relationships
    PREFERS = "PREFERS"            # Person → Thing
    INTERESTED_IN = "INTERESTED_IN"  # Person → Topic
    DISLIKES = "DISLIKES"          # Person → Thing
    
    # Location relationships
    LOCATED_IN = "LOCATED_IN"      # Entity → Location
    LIVES_IN = "LIVES_IN"          # Person → Location
    
    # Custom relationship (stores actual type in metadata["relationship_type"])
    CUSTOM = "CUSTOM"              # For domain-specific types not in enum


class ClaimKind(str, Enum):
    """
    Claim temporal/durability classification.
    Affects decay rates and retrieval priority.
    """
    PERMANENT = "permanent"        # e.g., "User was born in 1985" - no decay
    STABLE = "stable"              # e.g., "User prefers email" - slow decay
    CONTEXTUAL = "contextual"      # e.g., "User is frustrated" - medium decay
    EPHEMERAL = "ephemeral"        # e.g., "User is on mobile" - fast decay


class ProcedureStatus(str, Enum):
    """Lifecycle status of a Procedure."""
    CANDIDATE = "candidate"        # Proposed, not yet validated
    ACTIVE = "active"              # Validated and in use
    DEPRECATED = "deprecated"      # Superseded or no longer applicable


# =============================================================================
# Base Node Model
# =============================================================================

class NodeBase(BaseModel):
    """Base class for all graph nodes."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(..., description="Tenant/user isolation")
    node_type: NodeType
    
    # Embeddings and search
    embedding: Optional[List[float]] = Field(None, description="Vector embedding")
    
    # Strength and decay
    strength: float = Field(default=1.0, ge=0.0, le=1.0, description="Node strength (decays over time)")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)
    
    # Extensible metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"use_enum_values": True}


# =============================================================================
# Episode
# =============================================================================

class EpisodeCreate(BaseModel):
    """Data required to create an Episode."""
    tenant_id: str
    source: str = Field(..., description="Source identifier (e.g., 'chat', 'ticket')")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Episode(NodeBase):
    """
    Episode: A chat session that accumulates flushed conversation turns.
    
    Lifecycle:
    - Working memory buffer holds active turns (in-memory)
    - Flushed turns are appended to the current open Episode
    - New Episode starts when size exceeds MAX_EPISODE_TOKENS (default 10,000)
    - Episode close triggers reflection (Entity/Claim extraction)
    """
    node_type: NodeType = NodeType.EPISODE
    
    # Episode content
    source: str = Field(..., description="Source identifier")
    raw_content: str = Field(default="", description="Accumulated conversation content")
    summary: Optional[str] = Field(None, description="Generated summary")
    
    # Size tracking
    token_count: int = Field(default=0, description="Approximate token count")
    turn_count: int = Field(default=0, description="Number of turns appended")
    
    # Status
    is_open: bool = Field(default=True, description="Whether Episode is still accepting content")
    
    # Key topics for quick filtering
    key_topics: List[str] = Field(default_factory=list)


# =============================================================================
# Entity
# =============================================================================

class EntityCreate(BaseModel):
    """Data required to create an Entity."""
    tenant_id: str
    name: str = Field(..., description="Canonical name")
    entity_type: str = Field(..., description="Type: user, account, product, concept, etc.")
    aliases: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Entity(NodeBase):
    """
    Entity: A stable reference to a person, system, object, or abstract concept.
    
    Examples:
    - User:Alice, Account:Acme, Product:Widget, Concept:BillingProcess
    """
    node_type: NodeType = NodeType.ENTITY
    
    name: str = Field(..., description="Canonical name")
    entity_type: str = Field(..., description="Type classification")
    aliases: List[str] = Field(default_factory=list, description="Alternative names")
    
    # Computed stats (updated on access)
    mention_count: int = Field(default=0, description="How often this entity is mentioned")


# =============================================================================
# Claim
# =============================================================================

class ClaimCreate(BaseModel):
    """Data required to create a Claim."""
    tenant_id: str
    content: str = Field(..., description="The claim text")
    claim_kind: ClaimKind = Field(default=ClaimKind.STABLE)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    entity_ids: List[str] = Field(..., min_length=1, description="REQUIRED: Entities this claim is about")
    source_episode_id: Optional[str] = Field(None, description="Episode this claim was extracted from")
    embedding: Optional[List[float]] = Field(None, description="Embedding vector for similarity search")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Claim(NodeBase):
    """
    Claim: An atomic, descriptive statement about one or more Entities.
    
    CONSTRAINT: Every Claim MUST have at least one ABOUT edge to an Entity.
    
    Examples:
    - "User:Alice prefers email follow-ups" → ABOUT → Entity:Alice
    - "Account:Acme has 3 open tickets" → ABOUT → Entity:Acme
    """
    node_type: NodeType = NodeType.CLAIM
    
    content: str = Field(..., description="The claim text")
    claim_kind: ClaimKind = Field(default=ClaimKind.STABLE)
    
    # Confidence and evidence
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_count: int = Field(default=1, description="How many times this claim was observed")
    
    # Source tracking
    source_episode_id: Optional[str] = Field(None)


# =============================================================================
# Insight
# =============================================================================

class InsightCreate(BaseModel):
    """Data required to create an Insight."""
    tenant_id: str
    content: str = Field(..., description="The actionable insight")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_claim_ids: List[str] = Field(default_factory=list, description="Claims this insight derives from")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Insight(NodeBase):
    """
    Insight: A generalized, actionable heuristic derived from Claims.
    
    Insights are PRESCRIPTIVE (what should we do?) not DESCRIPTIVE (what is true?).
    
    Examples:
    - "Offer proactive outreach before 48h for billing issues"
    - "Send documentation links rather than summaries for technical users"
    """
    node_type: NodeType = NodeType.INSIGHT
    
    content: str = Field(..., description="The actionable insight")
    
    # Confidence and validation
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    validation_count: int = Field(default=0, description="How many times this insight was validated")
    
    # Source tracking
    source_claim_ids: List[str] = Field(default_factory=list)


# =============================================================================
# Procedure
# =============================================================================

class ProcedureCreate(BaseModel):
    """Data required to create a Procedure."""
    tenant_id: str
    name: str
    description: str
    steps: List[str]
    source_insight_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Procedure(NodeBase):
    """
    Procedure: A reusable, executable workflow derived from high-confidence Insights.
    
    Lifecycle: CANDIDATE → ACTIVE → DEPRECATED
    """
    node_type: NodeType = NodeType.PROCEDURE
    
    name: str
    description: str
    steps: List[str] = Field(default_factory=list)
    
    status: ProcedureStatus = Field(default=ProcedureStatus.CANDIDATE)
    
    # Source tracking
    source_insight_ids: List[str] = Field(default_factory=list)
    
    # Usage stats
    execution_count: int = Field(default=0)
    success_count: int = Field(default=0)


# =============================================================================
# Edge
# =============================================================================

class EdgeCreate(BaseModel):
    """Data required to create an Edge."""
    tenant_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = Field(default=1.0, ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    """
    Edge: A typed relationship between two nodes.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    source_id: str
    target_id: str
    edge_type: EdgeType
    
    weight: float = Field(default=1.0, ge=0.0, description="Edge weight for activation spreading")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {"use_enum_values": True}


# =============================================================================
# Retrieval Results
# =============================================================================

class AnchorResult(BaseModel):
    """Result from anchor search (hybrid lexical + vector)."""
    node_id: str
    node_type: NodeType
    score: float
    content_preview: str = ""


class ActivatedNode(BaseModel):
    """Node activated during spreading activation."""
    node_id: str
    node_type: NodeType
    activation: float
    hops_from_anchor: int
    path: List[str] = Field(default_factory=list, description="Path from anchor")


class RetrievalResult(BaseModel):
    """Complete retrieval result with subgraph."""
    query: str
    goal: Optional[str] = None
    anchors: List[AnchorResult] = Field(default_factory=list)
    activated_nodes: List[ActivatedNode] = Field(default_factory=list)
    formatted_context: str = ""
    reasoning_chain: str = ""
