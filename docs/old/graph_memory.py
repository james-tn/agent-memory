"""
Graph-Based Memory System - Prototype Implementation

This module provides the foundation for a knowledge graph-based memory system
with spreading activation retrieval, inspired by human associative memory.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Set, Tuple, Any, Annotated
from pydantic import BaseModel, Field
import uuid
import asyncio
import math


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class NodeType(str, Enum):
    """Types of nodes in the knowledge graph."""
    ENTITY = "entity"       # People, places, things
    CONCEPT = "concept"     # Topics, categories, ideas
    FACT = "fact"           # Statements, claims
    EPISODE = "episode"     # Events, sessions, conversations
    BELIEF = "belief"       # Preferences, values, opinions


class EntityType(str, Enum):
    """Subtypes for entity nodes."""
    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    PRODUCT = "product"
    EVENT = "event"
    OTHER = "other"


class EdgeType(str, Enum):
    """Types of relationships between nodes."""
    # Temporal
    HAPPENED_BEFORE = "happened_before"
    HAPPENED_AFTER = "happened_after"
    HAPPENED_DURING = "happened_during"
    
    # Causal
    CAUSED_BY = "caused_by"
    LEADS_TO = "leads_to"
    INFLUENCED_BY = "influenced_by"
    
    # Semantic
    RELATED_TO = "related_to"
    SIMILAR_TO = "similar_to"
    CONTRASTS_WITH = "contrasts_with"
    
    # Hierarchical
    IS_A = "is_a"
    PART_OF = "part_of"
    CONTAINS = "contains"
    GENERALIZES = "generalizes"
    SPECIALIZES = "specializes"
    
    # Evidential
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    
    # Possession/Association
    HAS_PROPERTY = "has_property"
    HAS_GOAL = "has_goal"
    OWNS = "owns"
    WORKS_AT = "works_at"
    LIVES_IN = "lives_in"
    
    # User-specific
    PREFERS = "prefers"
    DISLIKES = "dislikes"
    INTERESTED_IN = "interested_in"
    
    # Associative
    MENTIONED_WITH = "mentioned_with"
    ASSOCIATED_WITH = "associated_with"
    REMINDS_OF = "reminds_of"


# Default weights for different edge types in spreading activation
DEFAULT_EDGE_WEIGHTS = {
    EdgeType.IS_A: 0.9,
    EdgeType.PART_OF: 0.85,
    EdgeType.HAS_PROPERTY: 0.8,
    EdgeType.RELATED_TO: 0.75,
    EdgeType.CAUSED_BY: 0.7,
    EdgeType.LEADS_TO: 0.7,
    EdgeType.SIMILAR_TO: 0.7,
    EdgeType.SUPPORTS: 0.65,
    EdgeType.MENTIONED_WITH: 0.5,
    EdgeType.ASSOCIATED_WITH: 0.5,
    EdgeType.HAPPENED_BEFORE: 0.4,
    EdgeType.HAPPENED_AFTER: 0.4,
}


# ============================================================================
# DATA MODELS
# ============================================================================

class GraphNode(BaseModel):
    """Base model for all graph nodes."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: NodeType
    user_id: str
    content: str  # Main text content
    embedding: List[float] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    
    # Importance and activation
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    activation_level: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Temporal
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)
    access_count: int = 0
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EntityNode(GraphNode):
    """Node representing an entity (person, place, thing)."""
    type: NodeType = NodeType.ENTITY
    name: str
    entity_type: EntityType
    attributes: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class ConceptNode(GraphNode):
    """Node representing a concept or topic."""
    type: NodeType = NodeType.CONCEPT
    name: str
    domain: Optional[str] = None  # e.g., "finance", "health", "education"
    synonyms: List[str] = Field(default_factory=list)
    abstraction_level: int = 0  # 0 = specific, higher = more abstract


class FactNode(GraphNode):
    """Node representing a factual statement."""
    type: NodeType = NodeType.FACT
    statement: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    temporal_scope: str = "current"  # "permanent", "temporary", "past", "current"
    evidence_source_ids: List[str] = Field(default_factory=list)


class EpisodeNode(GraphNode):
    """Node representing an event or session."""
    type: NodeType = NodeType.EPISODE
    session_id: str
    summary: str
    timestamp: datetime
    participants: List[str] = Field(default_factory=list)
    emotional_tone: Optional[str] = None  # "positive", "negative", "neutral"


class BeliefNode(GraphNode):
    """Node representing a user preference or belief."""
    type: NodeType = NodeType.BELIEF
    belief_text: str
    category: str  # "financial", "lifestyle", "risk", "communication"
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    supporting_fact_ids: List[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    """Represents a relationship between two nodes."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    target_id: str
    relation_type: EdgeType
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    bidirectional: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# KNOWLEDGE EXTRACTION MODELS
# ============================================================================

class ExtractedEntity(BaseModel):
    """Entity extracted from conversation."""
    name: str
    entity_type: EntityType
    attributes: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class ExtractedRelation(BaseModel):
    """Relation extracted from conversation."""
    source: str  # Entity name
    target: str  # Entity name
    relation_type: EdgeType
    context: Optional[str] = None


class ExtractedFact(BaseModel):
    """Fact extracted from conversation."""
    statement: str
    entities_involved: List[str] = Field(default_factory=list)
    confidence: float = 0.8
    temporal_scope: str = "current"
    source_type: str = "user_stated"  # "user_stated", "inferred", "hypothetical"


class ExtractedBelief(BaseModel):
    """Belief/preference extracted from conversation."""
    belief: str
    category: str
    strength: float = 0.5
    evidence: Optional[str] = None


class KnowledgeExtractionResult(BaseModel):
    """Complete extraction result from a conversation."""
    entities: List[ExtractedEntity] = Field(default_factory=list)
    relations: List[ExtractedRelation] = Field(default_factory=list)
    facts: List[ExtractedFact] = Field(default_factory=list)
    beliefs: List[ExtractedBelief] = Field(default_factory=list)


# ============================================================================
# KNOWLEDGE GRAPH
# ============================================================================

class KnowledgeGraph:
    """
    In-memory knowledge graph with multi-modal indexing.
    
    This is a prototype implementation. For production, use CosmosDB
    with vector indexing and graph capabilities.
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        
        # Node storage
        self.nodes: Dict[str, GraphNode] = {}
        
        # Edge storage
        self.edges: List[GraphEdge] = []
        
        # Adjacency list for fast traversal
        # node_id -> [(neighbor_id, edge_type, weight)]
        self.adjacency: Dict[str, List[Tuple[str, EdgeType, float]]] = {}
        
        # Reverse adjacency for incoming edges
        self.reverse_adjacency: Dict[str, List[Tuple[str, EdgeType, float]]] = {}
        
        # Name/entity index for fast lookup
        self.entity_index: Dict[str, str] = {}  # name -> node_id
        
        # Type index
        self.type_index: Dict[NodeType, Set[str]] = {t: set() for t in NodeType}
    
    def add_node(self, node: GraphNode) -> str:
        """Add a node to the graph."""
        self.nodes[node.id] = node
        
        if node.id not in self.adjacency:
            self.adjacency[node.id] = []
        if node.id not in self.reverse_adjacency:
            self.reverse_adjacency[node.id] = []
        
        # Update type index
        self.type_index[node.type].add(node.id)
        
        # Update entity index if applicable
        if isinstance(node, EntityNode):
            self.entity_index[node.name.lower()] = node.id
        elif isinstance(node, ConceptNode):
            self.entity_index[node.name.lower()] = node.id
        
        return node.id
    
    def add_edge(self, edge: GraphEdge) -> str:
        """Add an edge to the graph."""
        self.edges.append(edge)
        
        # Update adjacency
        if edge.source_id not in self.adjacency:
            self.adjacency[edge.source_id] = []
        self.adjacency[edge.source_id].append(
            (edge.target_id, edge.relation_type, edge.weight)
        )
        
        # Update reverse adjacency
        if edge.target_id not in self.reverse_adjacency:
            self.reverse_adjacency[edge.target_id] = []
        self.reverse_adjacency[edge.target_id].append(
            (edge.source_id, edge.relation_type, edge.weight)
        )
        
        # If bidirectional, add reverse edge
        if edge.bidirectional:
            if edge.target_id not in self.adjacency:
                self.adjacency[edge.target_id] = []
            self.adjacency[edge.target_id].append(
                (edge.source_id, edge.relation_type, edge.weight)
            )
        
        return edge.id
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def find_entity(self, name: str) -> Optional[GraphNode]:
        """Find an entity by name."""
        node_id = self.entity_index.get(name.lower())
        return self.nodes.get(node_id) if node_id else None
    
    def get_neighbors(
        self, 
        node_id: str,
        direction: str = "outgoing"  # "outgoing", "incoming", "both"
    ) -> List[Tuple[str, EdgeType, float]]:
        """Get neighbors of a node."""
        neighbors = []
        
        if direction in ("outgoing", "both"):
            neighbors.extend(self.adjacency.get(node_id, []))
        
        if direction in ("incoming", "both"):
            neighbors.extend(self.reverse_adjacency.get(node_id, []))
        
        return neighbors
    
    def get_nodes_by_type(self, node_type: NodeType) -> List[GraphNode]:
        """Get all nodes of a specific type."""
        return [self.nodes[nid] for nid in self.type_index[node_type]]
    
    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_length: int = 4
    ) -> Optional[List[Tuple[str, EdgeType]]]:
        """Find shortest path between two nodes using BFS."""
        if source_id == target_id:
            return []
        
        visited = {source_id}
        queue = [(source_id, [])]
        
        while queue:
            current, path = queue.pop(0)
            
            if len(path) >= max_length:
                continue
            
            for neighbor_id, edge_type, _ in self.get_neighbors(current, "both"):
                if neighbor_id == target_id:
                    return path + [(neighbor_id, edge_type)]
                
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [(neighbor_id, edge_type)]))
        
        return None


# ============================================================================
# SPREADING ACTIVATION
# ============================================================================

class SpreadingActivation:
    """
    Spreading Activation algorithm for graph-based memory retrieval.
    
    Inspired by Collins & Loftus (1975) semantic memory model.
    Simulates how human memory activates related concepts.
    """
    
    def __init__(
        self,
        decay_factor: float = 0.7,
        threshold: float = 0.1,
        max_hops: int = 3,
        edge_weights: Optional[Dict[EdgeType, float]] = None
    ):
        """
        Initialize spreading activation.
        
        Args:
            decay_factor: How much activation decays per hop (0-1)
            threshold: Minimum activation to continue spreading
            max_hops: Maximum propagation depth
            edge_weights: Custom weights for different edge types
        """
        self.decay = decay_factor
        self.threshold = threshold
        self.max_hops = max_hops
        self.edge_weights = edge_weights or DEFAULT_EDGE_WEIGHTS
    
    def activate(
        self,
        graph: KnowledgeGraph,
        anchor_node_ids: List[str],
        boost_factors: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Spread activation from anchor nodes through the graph.
        
        Args:
            graph: The knowledge graph to traverse
            anchor_node_ids: Starting nodes with full activation
            boost_factors: Optional per-node boost multipliers
        
        Returns:
            Dict mapping node_id -> activation_level
        """
        boost_factors = boost_factors or {}
        activations: Dict[str, float] = {}
        
        # Initialize anchor nodes with full activation
        frontier: List[Tuple[str, float, int]] = []
        for node_id in anchor_node_ids:
            initial_activation = 1.0 * boost_factors.get(node_id, 1.0)
            activations[node_id] = initial_activation
            frontier.append((node_id, initial_activation, 0))
        
        # BFS-style spreading
        while frontier:
            node_id, current_activation, depth = frontier.pop(0)
            
            if depth >= self.max_hops:
                continue
            
            # Get neighbors (both directions)
            neighbors = graph.get_neighbors(node_id, direction="both")
            
            for neighbor_id, edge_type, edge_weight in neighbors:
                # Get edge type weight
                type_weight = self.edge_weights.get(edge_type, 0.5)
                
                # Calculate new activation
                new_activation = (
                    current_activation * 
                    self.decay * 
                    type_weight * 
                    edge_weight *
                    boost_factors.get(neighbor_id, 1.0)
                )
                
                # Only propagate if above threshold
                if new_activation > self.threshold:
                    # Take max if already activated (don't accumulate)
                    if neighbor_id in activations:
                        if new_activation > activations[neighbor_id]:
                            activations[neighbor_id] = new_activation
                            # Re-add to frontier with higher activation
                            frontier.append((neighbor_id, new_activation, depth + 1))
                    else:
                        activations[neighbor_id] = new_activation
                        frontier.append((neighbor_id, new_activation, depth + 1))
        
        return activations
    
    def get_activated_subgraph(
        self,
        graph: KnowledgeGraph,
        activations: Dict[str, float],
        min_activation: float = 0.1
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """
        Get the subgraph of activated nodes and their connecting edges.
        
        Returns:
            Tuple of (activated_nodes, connecting_edges)
        """
        # Filter nodes by activation
        activated_ids = {
            nid for nid, act in activations.items()
            if act >= min_activation
        }
        
        activated_nodes = [
            graph.nodes[nid] for nid in activated_ids
            if nid in graph.nodes
        ]
        
        # Get edges between activated nodes
        connecting_edges = [
            edge for edge in graph.edges
            if edge.source_id in activated_ids and edge.target_id in activated_ids
        ]
        
        return activated_nodes, connecting_edges


# ============================================================================
# MEMORY RETRIEVAL RESULT
# ============================================================================

class ReasoningStep(BaseModel):
    """A step in the reasoning chain."""
    from_node_id: str
    from_node_content: str
    edge_type: EdgeType
    to_node_id: str
    to_node_content: str
    explanation: str


class MemoryRetrievalResult(BaseModel):
    """Result of memory retrieval with reasoning chain."""
    query: str
    anchor_nodes: List[Dict[str, Any]]
    activated_nodes: List[Dict[str, Any]]
    reasoning_chain: List[ReasoningStep] = Field(default_factory=list)
    summary: str
    confidence: float
    retrieval_time_ms: float


# ============================================================================
# KNOWLEDGE DISTILLER
# ============================================================================

KNOWLEDGE_EXTRACTION_PROMPT = """
Analyze this conversation and extract structured knowledge about the USER.

<conversation>
{conversation}
</conversation>

Extract the following in JSON format. Focus on information about the USER that would be useful for future conversations.

{{
  "entities": [
    {{
      "name": "string - entity name (person, place, organization, product)",
      "entity_type": "person|organization|place|product|event|other",
      "attributes": {{"key": "value - relevant attributes"}},
      "description": "brief description if mentioned"
    }}
  ],
  
  "relations": [
    {{
      "source": "entity name (often 'User')",
      "target": "entity name",
      "relation_type": "has_property|has_goal|owns|works_at|lives_in|prefers|interested_in|related_to|part_of|is_a",
      "context": "why this relation exists"
    }}
  ],
  
  "facts": [
    {{
      "statement": "factual statement about the user or their situation",
      "entities_involved": ["entity names"],
      "confidence": 0.0-1.0,
      "temporal_scope": "permanent|temporary|past|current",
      "source_type": "user_stated|inferred|hypothetical"
    }}
  ],
  
  "beliefs": [
    {{
      "belief": "user preference, value, or opinion",
      "category": "financial|lifestyle|communication|risk|health|education|career|other",
      "strength": 0.0-1.0,
      "evidence": "what in conversation supports this"
    }}
  ]
}}

Guidelines:
- Focus on USER-specific information, not general knowledge
- Extract relationships that connect entities
- Infer preferences and beliefs from what the user says
- Mark confidence appropriately (user_stated = high, inferred = medium)
- Do not extract trivial or generic information
"""


class KnowledgeDistiller:
    """
    Extracts structured knowledge from conversations using LLM.
    """
    
    def __init__(self, llm_client: Any):
        """
        Initialize knowledge distiller.
        
        Args:
            llm_client: Azure OpenAI client or similar
        """
        self.llm = llm_client
    
    async def extract(
        self,
        conversation: List[Dict[str, str]],
        existing_entities: Optional[List[str]] = None
    ) -> KnowledgeExtractionResult:
        """
        Extract knowledge from a conversation.
        
        Args:
            conversation: List of {"role": "user"|"assistant", "content": "..."}
            existing_entities: Known entity names for linking
        
        Returns:
            KnowledgeExtractionResult with entities, relations, facts, beliefs
        """
        # Format conversation
        formatted = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in conversation
        ])
        
        prompt = KNOWLEDGE_EXTRACTION_PROMPT.format(conversation=formatted)
        
        # Call LLM for structured extraction
        # This is a placeholder - implement with your LLM client
        response = await self._call_llm(prompt)
        
        # Parse response into structured format
        return self._parse_extraction(response)
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM for extraction. Override with actual implementation."""
        # Placeholder - implement with Azure OpenAI
        raise NotImplementedError("Implement with your LLM client")
    
    def _parse_extraction(self, response: str) -> KnowledgeExtractionResult:
        """Parse LLM response into structured result."""
        # Placeholder - implement JSON parsing
        raise NotImplementedError("Implement JSON parsing")


# ============================================================================
# MEMORY AGENT
# ============================================================================

class MemoryAgent:
    """
    Autonomous agent for intelligent memory retrieval.
    
    Unlike simple vector search, this agent:
    1. Finds relevant anchor points in the knowledge graph
    2. Spreads activation through relationships
    3. Reasons over paths between activated nodes
    4. Synthesizes a coherent summary with reasoning chain
    """
    
    def __init__(
        self,
        knowledge_graph: KnowledgeGraph,
        spreading_activation: SpreadingActivation,
        llm_client: Any,
        embedder: Any
    ):
        """
        Initialize memory agent.
        
        Args:
            knowledge_graph: The user's knowledge graph
            spreading_activation: Activation algorithm
            llm_client: LLM for reasoning
            embedder: Embedding model for similarity search
        """
        self.graph = knowledge_graph
        self.activation = spreading_activation
        self.llm = llm_client
        self.embedder = embedder
    
    async def retrieve(
        self,
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        max_nodes: int = 20,
        max_tokens: int = 2000
    ) -> MemoryRetrievalResult:
        """
        Retrieve relevant memories with reasoning.
        
        Args:
            query: The user's question or current context
            conversation_context: Recent conversation for context
            max_nodes: Maximum nodes to include in result
            max_tokens: Token budget for summary
        
        Returns:
            MemoryRetrievalResult with activated nodes and reasoning
        """
        import time
        start_time = time.time()
        
        # Step 1: Find anchor points
        anchors = await self._find_anchors(query, conversation_context)
        
        if not anchors:
            return MemoryRetrievalResult(
                query=query,
                anchor_nodes=[],
                activated_nodes=[],
                summary="No relevant memories found.",
                confidence=0.0,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )
        
        # Step 2: Spreading activation
        anchor_ids = [a['id'] for a in anchors]
        activations = self.activation.activate(self.graph, anchor_ids)
        
        # Step 3: Get activated subgraph
        activated_nodes, edges = self.activation.get_activated_subgraph(
            self.graph, activations
        )
        
        # Sort by activation and take top-k
        activated_with_scores = [
            (node, activations.get(node.id, 0))
            for node in activated_nodes
        ]
        activated_with_scores.sort(key=lambda x: x[1], reverse=True)
        top_nodes = activated_with_scores[:max_nodes]
        
        # Step 4: Find reasoning paths
        reasoning_chain = await self._build_reasoning_chain(
            anchors, top_nodes, edges
        )
        
        # Step 5: Synthesize summary
        summary = await self._synthesize_summary(
            query, top_nodes, reasoning_chain, max_tokens
        )
        
        # Build result
        return MemoryRetrievalResult(
            query=query,
            anchor_nodes=anchors,
            activated_nodes=[
                {"id": n.id, "type": n.type.value, "content": n.content, "activation": score}
                for n, score in top_nodes
            ],
            reasoning_chain=reasoning_chain,
            summary=summary,
            confidence=self._calculate_confidence(top_nodes),
            retrieval_time_ms=(time.time() - start_time) * 1000
        )
    
    async def _find_anchors(
        self,
        query: str,
        context: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, Any]]:
        """
        Find anchor nodes for the query.
        
        Combines:
        - Entity matching (exact/fuzzy)
        - Vector similarity search
        - Keyword matching
        """
        anchors = []
        
        # 1. Extract entities from query
        entities = self._extract_query_entities(query)
        for entity_name in entities:
            node = self.graph.find_entity(entity_name)
            if node:
                anchors.append({
                    "id": node.id,
                    "content": node.content,
                    "match_type": "entity",
                    "score": 1.0
                })
        
        # 2. Vector similarity search
        query_embedding = await self._embed(query)
        similar_nodes = self._vector_search(query_embedding, top_k=5)
        for node, score in similar_nodes:
            if node.id not in [a['id'] for a in anchors]:
                anchors.append({
                    "id": node.id,
                    "content": node.content,
                    "match_type": "semantic",
                    "score": score
                })
        
        # 3. Keyword matching
        keywords = self._extract_keywords(query)
        for node in self.graph.nodes.values():
            if any(kw in node.keywords for kw in keywords):
                if node.id not in [a['id'] for a in anchors]:
                    anchors.append({
                        "id": node.id,
                        "content": node.content,
                        "match_type": "keyword",
                        "score": 0.7
                    })
        
        return anchors[:10]  # Limit anchors
    
    def _extract_query_entities(self, query: str) -> List[str]:
        """Extract entity names from query. Simple implementation."""
        # In production, use NER or LLM
        words = query.lower().split()
        return [w for w in words if w in self.graph.entity_index]
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from query."""
        # Simple implementation - in production use proper keyword extraction
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'how', 'why', 'when', 'where', 'who', 'my', 'your', 'we', 'i', 'you', 'about', 'for', 'with', 'did', 'do', 'does'}
        words = query.lower().split()
        return [w for w in words if w not in stopwords and len(w) > 2]
    
    async def _embed(self, text: str) -> List[float]:
        """Get embedding for text."""
        # Placeholder - implement with your embedder
        raise NotImplementedError("Implement with your embedding model")
    
    def _vector_search(
        self,
        query_embedding: List[float],
        top_k: int = 5
    ) -> List[Tuple[GraphNode, float]]:
        """
        Search nodes by vector similarity.
        
        This is a simple brute-force implementation.
        In production, use HNSW index or CosmosDB vector search.
        """
        def cosine_similarity(a: List[float], b: List[float]) -> float:
            if not a or not b:
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)
        
        scored = [
            (node, cosine_similarity(query_embedding, node.embedding))
            for node in self.graph.nodes.values()
            if node.embedding
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
    
    async def _build_reasoning_chain(
        self,
        anchors: List[Dict],
        activated_nodes: List[Tuple[GraphNode, float]],
        edges: List[GraphEdge]
    ) -> List[ReasoningStep]:
        """Build reasoning chain showing how nodes connect."""
        chain = []
        
        # Find paths between high-activation nodes
        high_activation = [n for n, s in activated_nodes if s > 0.3]
        
        for i, node1 in enumerate(high_activation[:5]):
            for node2 in high_activation[i+1:5]:
                path = self.graph.find_path(node1.id, node2.id, max_length=3)
                if path:
                    current = node1
                    for next_id, edge_type in path:
                        next_node = self.graph.get_node(next_id)
                        if next_node:
                            chain.append(ReasoningStep(
                                from_node_id=current.id,
                                from_node_content=current.content[:100],
                                edge_type=edge_type,
                                to_node_id=next_node.id,
                                to_node_content=next_node.content[:100],
                                explanation=f"{current.content[:50]} {edge_type.value} {next_node.content[:50]}"
                            ))
                            current = next_node
        
        return chain[:10]  # Limit chain length
    
    async def _synthesize_summary(
        self,
        query: str,
        activated_nodes: List[Tuple[GraphNode, float]],
        reasoning_chain: List[ReasoningStep],
        max_tokens: int
    ) -> str:
        """Synthesize a coherent summary from activated nodes and reasoning."""
        # Build context from activated nodes
        node_summaries = []
        for node, score in activated_nodes[:10]:
            node_summaries.append(f"[{node.type.value}] {node.content}")
        
        # Build reasoning context
        reasoning_text = []
        for step in reasoning_chain[:5]:
            reasoning_text.append(
                f"• {step.from_node_content} → ({step.edge_type.value}) → {step.to_node_content}"
            )
        
        # In production, use LLM to synthesize
        # For now, return structured summary
        summary_parts = [
            "Retrieved memories:",
            *node_summaries[:5],
            "",
            "Connections found:" if reasoning_text else "",
            *reasoning_text
        ]
        
        return "\n".join(summary_parts)
    
    def _calculate_confidence(
        self,
        activated_nodes: List[Tuple[GraphNode, float]]
    ) -> float:
        """Calculate confidence based on activation levels."""
        if not activated_nodes:
            return 0.0
        
        # Average activation of top nodes
        top_activations = [score for _, score in activated_nodes[:5]]
        return sum(top_activations) / len(top_activations)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def example_usage():
    """Example of how to use the graph memory system."""
    
    # Create knowledge graph for a user
    user_id = "user_123"
    graph = KnowledgeGraph(user_id)
    
    # Add some nodes
    user_node = EntityNode(
        user_id=user_id,
        content="The user of this system",
        name="User",
        entity_type=EntityType.PERSON
    )
    graph.add_node(user_node)
    
    daughter_node = EntityNode(
        user_id=user_id,
        content="Emma, the user's 8-year-old daughter",
        name="Emma",
        entity_type=EntityType.PERSON,
        attributes={"age": 8, "relationship": "daughter"}
    )
    graph.add_node(daughter_node)
    
    college_goal = ConceptNode(
        user_id=user_id,
        content="Saving for Emma's college education",
        name="College Savings Goal",
        domain="finance"
    )
    graph.add_node(college_goal)
    
    plan_529 = ConceptNode(
        user_id=user_id,
        content="529 Education Savings Plan with tax advantages",
        name="529 Plan",
        domain="finance",
        keywords=["529", "education", "savings", "tax"]
    )
    graph.add_node(plan_529)
    
    tax_benefit = FactNode(
        user_id=user_id,
        content="529 plans offer tax-free growth for education expenses",
        statement="529 plans provide tax benefits",
        confidence=1.0
    )
    graph.add_node(tax_benefit)
    
    risk_preference = BeliefNode(
        user_id=user_id,
        content="User prefers moderate risk investments",
        belief_text="Moderate risk tolerance",
        category="financial",
        strength=0.8
    )
    graph.add_node(risk_preference)
    
    # Add edges
    graph.add_edge(GraphEdge(
        source_id=user_node.id,
        target_id=daughter_node.id,
        relation_type=EdgeType.HAS_PROPERTY
    ))
    
    graph.add_edge(GraphEdge(
        source_id=daughter_node.id,
        target_id=college_goal.id,
        relation_type=EdgeType.HAS_GOAL
    ))
    
    graph.add_edge(GraphEdge(
        source_id=college_goal.id,
        target_id=plan_529.id,
        relation_type=EdgeType.RELATED_TO
    ))
    
    graph.add_edge(GraphEdge(
        source_id=plan_529.id,
        target_id=tax_benefit.id,
        relation_type=EdgeType.HAS_PROPERTY
    ))
    
    graph.add_edge(GraphEdge(
        source_id=user_node.id,
        target_id=risk_preference.id,
        relation_type=EdgeType.HAS_PROPERTY
    ))
    
    # Test spreading activation
    activation = SpreadingActivation(
        decay_factor=0.7,
        threshold=0.1,
        max_hops=3
    )
    
    # Activate from daughter node
    activations = activation.activate(graph, [daughter_node.id])
    
    print("Spreading Activation Results:")
    print("-" * 50)
    for node_id, level in sorted(activations.items(), key=lambda x: -x[1]):
        node = graph.get_node(node_id)
        if node:
            print(f"  {node.content[:50]}: {level:.2f}")
    
    # Test path finding
    path = graph.find_path(daughter_node.id, tax_benefit.id)
    if path:
        print("\nPath from Emma to Tax Benefits:")
        print(f"  Emma", end="")
        for next_id, edge_type in path:
            node = graph.get_node(next_id)
            print(f" --[{edge_type.value}]--> {node.content[:30] if node else '?'}", end="")
        print()


if __name__ == "__main__":
    asyncio.run(example_usage())
