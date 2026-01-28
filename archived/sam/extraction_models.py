"""
SAM Extraction Models

Pydantic models for structured LLM outputs during extraction.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

from sam.models.graph import ClaimKind


# =============================================================================
# Entity/Claim Extraction Output
# =============================================================================

class ExtractedEntity(BaseModel):
    """An entity extracted from conversation content."""
    name: str = Field(description="The entity name (normalized)")
    entity_type: str = Field(description="Type: person, organization, concept, location, product, etc.")
    aliases: List[str] = Field(
        default_factory=list,
        description="Alternative names or references used in the conversation"
    )


class ExtractedClaim(BaseModel):
    """A claim extracted from conversation content."""
    content: str = Field(description="The claim content - a single, atomic fact")
    entity_names: List[str] = Field(
        description="Names of entities this claim is about (must match extracted entities)",
        min_length=1
    )
    claim_kind: str = Field(
        default="stable",
        description="Type: permanent, stable, contextual, or ephemeral"
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence in this claim (0.0-1.0)"
    )


class EntityClaimExtractionResult(BaseModel):
    """Result of entity and claim extraction."""
    entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="Extracted entities"
    )
    claims: List[ExtractedClaim] = Field(
        default_factory=list,
        description="Extracted claims about entities"
    )


# =============================================================================
# Episode Summary Output
# =============================================================================

class EpisodeSummaryResult(BaseModel):
    """Result of episode summarization."""
    summary: str = Field(description="2-4 sentence summary of the conversation")
    key_topics: List[str] = Field(
        description="3-5 key topics discussed",
        min_length=1,
        max_length=7
    )


# =============================================================================
# Contradiction Detection Output
# =============================================================================

class ClaimRelationship(BaseModel):
    """Relationship between new claim and existing claim."""
    existing_claim_index: int = Field(description="Index of the existing claim")
    relationship: str = Field(description="CONTRADICTS, SUPPORTS, or NEUTRAL")
    explanation: str = Field(description="Brief explanation of the relationship")


class ContradictionDetectionResult(BaseModel):
    """Result of contradiction detection."""
    relationships: List[ClaimRelationship] = Field(
        default_factory=list,
        description="Relationships between new claim and existing claims"
    )
    has_contradiction: bool = Field(
        default=False,
        description="Whether any contradiction was found"
    )


# =============================================================================
# Insight Synthesis Output
# =============================================================================

class SynthesizedInsight(BaseModel):
    """An insight synthesized from multiple claims."""
    content: str = Field(description="The insight content")
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence in this insight"
    )
    source_claim_indices: List[int] = Field(
        default_factory=list,
        description="Indices of claims this insight was derived from"
    )


class InsightSynthesisResult(BaseModel):
    """Result of insight synthesis."""
    insights: List[SynthesizedInsight] = Field(
        default_factory=list,
        description="Synthesized insights"
    )
    has_meaningful_insights: bool = Field(
        default=False,
        description="Whether meaningful insights were found"
    )


# =============================================================================
# Procedure Extraction Output
# =============================================================================

class ExtractedProcedure(BaseModel):
    """A procedure extracted from conversation content."""
    name: str = Field(description="Name of the procedure")
    description: str = Field(description="When/why to use this procedure")
    steps: List[str] = Field(
        description="Ordered steps of the procedure",
        min_length=2
    )


class ProcedureExtractionResult(BaseModel):
    """Result of procedure extraction."""
    procedures: List[ExtractedProcedure] = Field(
        default_factory=list,
        description="Extracted procedures"
    )


# =============================================================================
# Relationship Triple Extraction Output
# =============================================================================

class ExtractedRelationship(BaseModel):
    """A relationship triple extracted from conversation content.
    
    Represents: (subject_entity) --[relationship_type]--> (object_entity)
    
    Examples:
        ("Michael", "ALLERGIC_TO", "Penicillin")
        ("Dr. Wilson", "PRESCRIBED", "Losartan")
        ("Metformin", "TREATS", "Type 2 Diabetes")
    """
    subject_name: str = Field(
        description="Name of the source entity (must match an extracted entity)"
    )
    relationship_type: str = Field(
        description="The relationship type (e.g., ALLERGIC_TO, PRESCRIBED, TREATS)"
    )
    object_name: str = Field(
        description="Name of the target entity (must match an extracted entity)"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence in this relationship (0.0-1.0)"
    )
    evidence: str = Field(
        default="",
        description="Brief quote or paraphrase supporting this relationship"
    )


class EntityRelationshipExtractionResult(BaseModel):
    """Result of entity and relationship extraction.
    
    This is the enhanced extraction format that produces:
    1. Entities (nodes in the graph)
    2. Claims (self-contained facts, also nodes)
    3. Relationships (entity-to-entity edges with semantic types)
    """
    entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="Extracted entities"
    )
    claims: List[ExtractedClaim] = Field(
        default_factory=list,
        description="Extracted claims about entities"
    )
    relationships: List[ExtractedRelationship] = Field(
        default_factory=list,
        description="Extracted relationships between entities (triples)"
    )
