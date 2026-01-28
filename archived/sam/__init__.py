"""
SAM: Spreading Activation Memory

A cognitive-inspired memory architecture for AI agents that mimics how human memory works:
retrieval through spreading activation from cue-based anchors, not just vector similarity search.

Ontology: Episode → Entity → Claim → Insight → Procedure
"""

from sam.config import SAMConfig
from sam.models.graph import (
    NodeType,
    EdgeType,
    Episode,
    Entity,
    Claim,
    Insight,
    Procedure,
    Edge,
)
from sam.stores.factory import create_store
from sam.llm_client import LLMClient
from sam.embeddings import EmbeddingsService
from sam.extractor import Extractor
from sam.ingestion import IngestionPipeline, create_pipeline
from sam.working_memory import WorkingMemory
from sam.retriever import SpreadingActivationRetriever, RetrievalResult, ActivatedNode
from sam.vector_baseline import SimpleVectorRetriever
from sam.consolidation import InsightDistiller, ConsolidationResult, run_consolidation
from sam.anchor_selection import analyze_query, QueryPlan, extract_entities, detect_multi_hop
from sam.tuning import (
    TuningProfile, get_profile, list_profiles, select_profile_for_query,
    create_custom_profile, print_profile_comparison, PROFILES
)

__version__ = "0.1.0"

__all__ = [
    # Config
    "SAMConfig",
    # Graph types
    "NodeType",
    "EdgeType",
    "Episode",
    "Entity",
    "Claim",
    "Insight",
    "Procedure",
    "Edge",
    # Core components
    "create_store",
    "LLMClient",
    "EmbeddingsService",
    "Extractor",
    "IngestionPipeline",
    "create_pipeline",
    "WorkingMemory",
    # Retrieval
    "SpreadingActivationRetriever",
    "RetrievalResult",
    "ActivatedNode",
    # Baseline comparison
    "SimpleVectorRetriever",
    # Consolidation
    "InsightDistiller",
    "ConsolidationResult",
    "run_consolidation",
    # Anchor selection
    "analyze_query",
    "QueryPlan",
    "extract_entities",
    "detect_multi_hop",
    # Tuning
    "TuningProfile",
    "get_profile",
    "list_profiles",
    "select_profile_for_query",
    "create_custom_profile",
    "print_profile_comparison",
    "PROFILES",
]
