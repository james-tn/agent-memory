"""
SAM MemoryStore Interface

Abstract interface for storage backends. Implementations must support:
- SQLite (default, local-first)
- PostgreSQL (production)
- CosmosDB (Azure scale)
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Protocol, runtime_checkable
from datetime import datetime

from sam.models.graph import (
    NodeType,
    EdgeType,
    Episode,
    EpisodeCreate,
    Entity,
    EntityCreate,
    Claim,
    ClaimCreate,
    Insight,
    InsightCreate,
    Procedure,
    ProcedureCreate,
    Edge,
    EdgeCreate,
    AnchorResult,
)


@runtime_checkable
class MemoryStore(Protocol):
    """
    Abstract interface for SAM storage backends.
    
    All methods are async to support both local (SQLite) and remote (Postgres, Cosmos) backends.
    Implementations must handle tenant isolation via tenant_id on all operations.
    """
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def initialize(self) -> None:
        """Initialize database schema, indexes, etc."""
        ...
    
    async def close(self) -> None:
        """Close connections and cleanup resources."""
        ...
    
    # =========================================================================
    # Episode Operations
    # =========================================================================
    
    async def create_episode(self, episode: EpisodeCreate) -> Episode:
        """Create a new Episode node."""
        ...
    
    async def get_episode(self, episode_id: str, tenant_id: str) -> Optional[Episode]:
        """Get Episode by ID."""
        ...
    
    async def get_open_episode(self, tenant_id: str) -> Optional[Episode]:
        """Get the current open Episode for a tenant, if any."""
        ...
    
    async def append_to_episode(
        self, 
        episode_id: str, 
        tenant_id: str,
        content: str, 
        token_count: int,
        turn_count: int = 1
    ) -> Episode:
        """
        Append content to an open Episode.
        
        Args:
            episode_id: Episode to append to
            tenant_id: Tenant isolation
            content: Content to append
            token_count: Tokens in the appended content
            turn_count: Number of turns being appended
        
        Returns:
            Updated Episode with new content appended
        """
        ...
    
    async def close_episode(
        self, 
        episode_id: str, 
        tenant_id: str,
        summary: Optional[str] = None,
        key_topics: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None
    ) -> Episode:
        """
        Close an Episode (no more content can be appended).
        
        Args:
            episode_id: Episode to close
            tenant_id: Tenant isolation
            summary: Generated summary
            key_topics: Extracted topics
            embedding: Vector embedding of summary
        
        Returns:
            Closed Episode
        """
        ...
    
    async def list_episodes(
        self, 
        tenant_id: str, 
        limit: int = 10,
        include_open: bool = True
    ) -> List[Episode]:
        """List recent Episodes for a tenant."""
        ...
    
    # =========================================================================
    # Entity Operations
    # =========================================================================
    
    async def create_entity(self, entity: EntityCreate) -> Entity:
        """Create a new Entity node."""
        ...
    
    async def get_entity(self, entity_id: str, tenant_id: str) -> Optional[Entity]:
        """Get Entity by ID."""
        ...
    
    async def find_entity_by_name(
        self, 
        name: str, 
        tenant_id: str,
        entity_type: Optional[str] = None
    ) -> Optional[Entity]:
        """Find Entity by name (case-insensitive) and optionally type."""
        ...
    
    async def get_or_create_entity(
        self,
        name: str,
        entity_type: str,
        tenant_id: str,
        aliases: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Entity:
        """Get existing Entity or create new one."""
        ...
    
    async def update_entity_embedding(
        self,
        entity_id: str,
        tenant_id: str,
        embedding: List[float]
    ) -> Entity:
        """Update Entity's embedding vector."""
        ...
    
    async def increment_entity_mention(
        self,
        entity_id: str,
        tenant_id: str
    ) -> Entity:
        """Increment Entity's mention count."""
        ...
    
    # =========================================================================
    # Claim Operations
    # =========================================================================
    
    async def create_claim(self, claim: ClaimCreate) -> Claim:
        """
        Create a new Claim node.
        
        Note: Caller must also create ABOUT edges to the referenced entities.
        """
        ...
    
    async def get_claim(self, claim_id: str, tenant_id: str) -> Optional[Claim]:
        """Get Claim by ID."""
        ...
    
    async def get_claims_for_entity(
        self, 
        entity_id: str, 
        tenant_id: str,
        limit: int = 50
    ) -> List[Claim]:
        """Get all Claims about a specific Entity."""
        ...
    
    async def find_similar_claims(
        self,
        embedding: List[float],
        tenant_id: str,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[tuple[Claim, float]]:
        """
        Find Claims similar to the given embedding.
        
        Returns:
            List of (Claim, similarity_score) tuples
        """
        ...
    
    async def update_claim_confidence(
        self,
        claim_id: str,
        tenant_id: str,
        confidence_delta: float,
        increment_evidence: bool = True
    ) -> Claim:
        """
        Update Claim confidence and optionally increment evidence count.
        
        Args:
            claim_id: Claim to update
            tenant_id: Tenant isolation
            confidence_delta: Amount to add to confidence (can be negative)
            increment_evidence: Whether to increment evidence_count
        """
        ...
    
    # =========================================================================
    # Insight Operations
    # =========================================================================
    
    async def create_insight(self, insight: InsightCreate) -> Insight:
        """Create a new Insight node."""
        ...
    
    async def get_insight(self, insight_id: str, tenant_id: str) -> Optional[Insight]:
        """Get Insight by ID."""
        ...
    
    async def list_insights(
        self,
        tenant_id: str,
        min_confidence: float = 0.0,
        limit: int = 50
    ) -> List[Insight]:
        """List Insights ordered by confidence."""
        ...
    
    async def find_similar_insights(
        self,
        embedding: List[float],
        tenant_id: str,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[tuple[Insight, float]]:
        """Find Insights similar to the given embedding."""
        ...
    
    # =========================================================================
    # Procedure Operations
    # =========================================================================
    
    async def create_procedure(self, procedure: ProcedureCreate) -> Procedure:
        """Create a new Procedure node."""
        ...
    
    async def get_procedure(self, procedure_id: str, tenant_id: str) -> Optional[Procedure]:
        """Get Procedure by ID."""
        ...
    
    async def list_active_procedures(
        self,
        tenant_id: str,
        limit: int = 20
    ) -> List[Procedure]:
        """List active Procedures."""
        ...
    
    # =========================================================================
    # Edge Operations
    # =========================================================================
    
    async def create_edge(self, edge: EdgeCreate) -> Edge:
        """Create a new Edge."""
        ...
    
    async def get_edges_from(
        self,
        source_id: str,
        tenant_id: str,
        edge_type: Optional[EdgeType] = None
    ) -> List[Edge]:
        """Get all edges originating from a node."""
        ...
    
    async def get_edges_to(
        self,
        target_id: str,
        tenant_id: str,
        edge_type: Optional[EdgeType] = None
    ) -> List[Edge]:
        """Get all edges pointing to a node."""
        ...
    
    async def get_neighbors(
        self,
        node_id: str,
        tenant_id: str,
        edge_type: Optional[EdgeType] = None,
        direction: str = "outgoing"  # "outgoing", "incoming", "both"
    ) -> List[str]:
        """Get neighbor node IDs."""
        ...
    
    async def get_node_degree(
        self,
        node_id: str,
        tenant_id: str
    ) -> int:
        """Get total number of edges connected to a node."""
        ...
    
    # =========================================================================
    # Generic Node Operations
    # =========================================================================
    
    async def get_node(
        self,
        node_id: str,
        tenant_id: str
    ) -> Optional[Episode | Entity | Claim | Insight | Procedure]:
        """Get any node by ID (auto-detects type)."""
        ...
    
    async def update_node_strength(
        self,
        node_id: str,
        tenant_id: str,
        strength: float
    ) -> None:
        """Update a node's strength value."""
        ...
    
    async def touch_node(
        self,
        node_id: str,
        tenant_id: str
    ) -> None:
        """Update last_accessed timestamp (for reinforcement on access)."""
        ...
    
    # =========================================================================
    # Retrieval Operations
    # =========================================================================
    
    async def hybrid_anchor_search(
        self,
        query_text: str,
        query_embedding: List[float],
        tenant_id: str,
        node_types: Optional[List[NodeType]] = None,
        limit: int = 10,
        lexical_weight: float = 0.3,
        vector_weight: float = 0.7
    ) -> List[AnchorResult]:
        """
        Hybrid lexical + vector search to find anchor nodes.
        
        Args:
            query_text: Text query for lexical search (FTS)
            query_embedding: Vector for similarity search
            tenant_id: Tenant isolation
            node_types: Filter by node types (default: all)
            limit: Max results
            lexical_weight: Weight for lexical score
            vector_weight: Weight for vector similarity
        
        Returns:
            List of AnchorResult with combined scores
        """
        ...
    
    # =========================================================================
    # Decay Operations
    # =========================================================================
    
    async def apply_decay(
        self,
        tenant_id: str,
        half_life_days: float = 30.0,
        min_strength: float = 0.01
    ) -> int:
        """
        Apply time-based decay to node strengths.
        
        Args:
            tenant_id: Tenant to apply decay to
            half_life_days: Days until strength halves (if not accessed)
            min_strength: Minimum strength before node is considered for pruning
        
        Returns:
            Number of nodes updated
        """
        ...
    
    async def prune_weak_nodes(
        self,
        tenant_id: str,
        strength_threshold: float = 0.01
    ) -> int:
        """
        Remove nodes below strength threshold.
        
        Returns:
            Number of nodes removed
        """
        ...


class BaseMemoryStore(ABC):
    """
    Abstract base class providing common functionality for MemoryStore implementations.
    """
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._initialized = False
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize database schema, indexes, etc."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources."""
        pass
