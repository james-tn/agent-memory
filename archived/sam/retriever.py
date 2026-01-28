"""
SAM Spreading Activation Retriever

Core retrieval algorithm that mimics human memory retrieval:
1. Anchor Search: Find initial nodes via hybrid lexical + vector search
2. Spreading Activation: Spread activation along edges with decay
3. Context Assembly: Collect and format activated nodes for LLM

This is the key differentiator from pure vector search - we traverse
the graph to find related knowledge, not just similar embeddings.
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime
import heapq
import math

from sam.config import SAMConfig
from sam.stores.base import MemoryStore
from sam.llm_client import LLMClient
from sam.embeddings import EmbeddingsService
from sam.models.graph import (
    NodeType, EdgeType, Episode, Entity, Claim, Insight, Procedure,
    AnchorResult, ActivatedNode, RetrievalResult
)
from sam.anchor_selection import (
    analyze_query, QueryPlan, suggest_activation_params, get_optimized_search_query
)


@dataclass
class ActivationState:
    """Tracks activation state during spreading."""
    node_id: str
    node_type: NodeType
    activation: float
    depth: int
    path: List[str] = field(default_factory=list)  # Path from anchor
    
    def __lt__(self, other):
        """For heap ordering - higher activation first."""
        return self.activation > other.activation


class SpreadingActivationRetriever:
    """
    Retriever using spreading activation through the memory graph.
    
    Algorithm:
    1. ANCHOR: Find seed nodes via hybrid search (lexical + vector)
    2. SPREAD: Propagate activation along edges with decay factor
    3. COLLECT: Gather nodes above activation threshold
    4. ASSEMBLE: Format into context for LLM
    
    Key parameters:
    - activation_decay: How much activation decreases per hop (default 0.7)
    - max_depth: Maximum hops from anchor (default 3)
    - activation_threshold: Minimum activation to include (default 0.1)
    """
    
    def __init__(
        self,
        store: MemoryStore,
        llm_client: Optional[LLMClient] = None,
        embeddings: Optional[EmbeddingsService] = None,
        config: Optional[SAMConfig] = None
    ):
        """
        Initialize retriever.
        
        Args:
            store: MemoryStore backend
            llm_client: LLM client for embeddings (optional if embeddings provided)
            embeddings: Embeddings service
            config: SAM configuration
        """
        self.store = store
        self.config = config or SAMConfig()
        
        if llm_client:
            self.llm_client = llm_client
            self.embeddings = embeddings or EmbeddingsService(llm_client)
        else:
            self.llm_client = None
            self.embeddings = embeddings
    
    async def _extract_entities_from_database(
        self,
        query: str,
        tenant_id: str
    ) -> List[str]:
        """
        Extract entity names by matching query text against database entities.
        
        This improves on regex-based extraction by finding actual entity names
        like "muscle cramps" that exist in the database.
        
        Args:
            query: The query text to search for entity mentions
            tenant_id: Tenant identifier
            
        Returns:
            List of entity names found in the query
        """
        if not hasattr(self.store, '_get_conn'):
            return []
        
        conn = self.store._get_conn()
        query_lower = query.lower()
        found_entities = []
        
        # Get all entity names for this tenant
        rows = conn.execute("""
            SELECT DISTINCT name FROM entities WHERE tenant_id = ?
        """, (tenant_id,)).fetchall()
        
        # Check each entity name against the query
        for row in rows:
            entity_name = row['name']
            entity_lower = entity_name.lower()
            
            # Check if entity name appears in query (word boundary matching)
            # Use simple substring matching with word boundaries
            if entity_lower in query_lower:
                # Verify it's a word boundary match (not part of another word)
                import re
                pattern = r'\b' + re.escape(entity_lower) + r'\b'
                if re.search(pattern, query_lower):
                    found_entities.append(entity_name)
        
        # Sort by length descending (prefer longer matches like "muscle cramps" over "muscle")
        found_entities.sort(key=len, reverse=True)
        
        return found_entities

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        goal: Optional[str] = None,
        max_results: int = 10,
        include_types: Optional[List[NodeType]] = None,
        use_spreading: bool = True,
        return_paths: bool = False
    ) -> RetrievalResult:
        """
        Retrieve relevant memory nodes for a query.
        
        Args:
            query: Natural language query
            tenant_id: Tenant identifier
            goal: Optional goal/intent for goal-directed activation (Tier 2)
            max_results: Maximum nodes to return
            include_types: Node types to include (default: all)
            use_spreading: Whether to use spreading activation (vs just anchor search)
            return_paths: Whether to include activation paths in results
            
        Returns:
            RetrievalResult with activated nodes and metadata
        """
        print(f"[Retriever] Query: '{query[:50]}...'")
        
        # Default to all node types
        if include_types is None:
            include_types = [NodeType.ENTITY, NodeType.CLAIM, NodeType.INSIGHT]
        
        # 0. Analyze query to extract entity names for entity-centric anchoring
        query_plan = analyze_query(query)
        entity_names = query_plan.extracted_entities
        
        # 0b. ENHANCED: Also look up entity names from the database
        # This catches entities like "muscle cramps" that regex patterns miss
        db_entities = await self._extract_entities_from_database(query, tenant_id)
        for ent in db_entities:
            if ent not in entity_names:
                entity_names.append(ent)
        
        if entity_names:
            print(f"  [Entity] Extracted entities: {entity_names}")
        
        # 1. Generate query embedding
        query_embedding = None
        if self.embeddings:
            try:
                query_embedding = self.embeddings.embed_text(query)
            except Exception as e:
                print(f"  ⚠ Embedding failed: {e}, using lexical only")
        
        # 1b. Generate goal embedding for goal-directed activation (Tier 2)
        goal_embedding = None
        if goal and self.embeddings:
            try:
                goal_embedding = self.embeddings.embed_text(goal)
                print(f"  🎯 Goal-directed: '{goal[:30]}...'")
            except Exception as e:
                print(f"  ⚠ Goal embedding failed: {e}")
        
        # 2. Find anchor nodes via hybrid search with entity boosting
        anchors = await self._find_anchors(
            query_text=query,
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            node_types=include_types,
            limit=self.config.anchor_top_k,
            entity_names=entity_names  # Pass extracted entities for boosting
        )
        
        if not anchors:
            print(f"  ⚠ No anchors found")
            return RetrievalResult(
                query=query,
                activated_nodes=[],
                total_activation=0.0
            )
        
        print(f"  🎯 Found {len(anchors)} anchors")
        
        # 3. Spread activation (or just use anchors)
        if use_spreading:
            activated = await self._spread_activation(
                anchors=anchors,
                tenant_id=tenant_id,
                include_types=include_types,
                goal_embedding=goal_embedding
            )
        else:
            # Just convert anchors to activated nodes
            activated = [
                ActivatedNode(
                    node_id=a.node_id,
                    node_type=a.node_type,
                    activation=a.score,
                    hops_from_anchor=0,
                    path=[a.node_id]
                )
                for a in anchors
            ]
        
        # 4. Apply recency weighting (Tier 2)
        activated = await self._apply_recency_weighting(activated, tenant_id)
        
        # 5. Sort by activation and limit
        activated.sort(key=lambda n: n.activation, reverse=True)
        activated = activated[:max_results]
        
        # 6. Calculate total activation
        total_activation = sum(n.activation for n in activated)
        
        print(f"  ✓ Retrieved {len(activated)} nodes (total activation: {total_activation:.2f})")
        
        return RetrievalResult(
            query=query,
            anchors=anchors,
            activated_nodes=activated
        )
    
    async def retrieve_with_analysis(
        self,
        query: str,
        tenant_id: str,
        goal: Optional[str] = None,
        max_results: int = 10,
        include_types: Optional[List[NodeType]] = None,
        auto_tune: bool = True
    ) -> Tuple[RetrievalResult, QueryPlan]:
        """
        Retrieve with query analysis for improved multi-hop handling.
        
        This method analyzes the query to:
        1. Extract named entities for better anchor matching
        2. Detect multi-hop requirements
        3. Adjust parameters dynamically
        
        Args:
            query: Natural language query
            tenant_id: Tenant identifier
            goal: Optional goal for goal-directed activation
            max_results: Maximum nodes to return
            include_types: Node types to include
            auto_tune: Whether to auto-tune parameters based on query
            
        Returns:
            Tuple of (RetrievalResult, QueryPlan)
        """
        # Analyze query
        query_plan = analyze_query(query)
        
        # ENHANCED: Also look up entity names from the database
        db_entities = await self._extract_entities_from_database(query, tenant_id)
        for ent in db_entities:
            if ent not in query_plan.extracted_entities:
                query_plan.extracted_entities.append(ent)
        
        # Create optimized search query using extracted entities
        optimized_query = get_optimized_search_query(query_plan)
        
        print(f"[Retriever] Query Analysis:")
        print(f"  Entities: {query_plan.extracted_entities}")
        print(f"  Multi-hop: {query_plan.requires_multi_hop} (est. {query_plan.estimated_hops} hops)")
        print(f"  Optimized search: '{optimized_query[:50]}...'")
        
        # Get suggested parameters
        if auto_tune and query_plan.requires_multi_hop:
            suggested = suggest_activation_params(query_plan)
            print(f"  Auto-tuned params: depth={suggested['max_depth']}, "
                  f"threshold={suggested['activation_threshold']}, "
                  f"decay={suggested['activation_decay']}")
            
            # Temporarily apply suggested parameters
            original_depth = self.config.max_activation_depth
            original_threshold = self.config.activation_threshold
            original_anchor_k = self.config.anchor_top_k
            original_decay = self.config.activation_decay
            
            self.config.max_activation_depth = suggested["max_depth"]
            self.config.activation_threshold = suggested["activation_threshold"]
            self.config.anchor_top_k = suggested["anchor_top_k"]
            self.config.activation_decay = suggested["activation_decay"]
            
            try:
                # Use optimized query for anchor search
                result = await self._retrieve_with_custom_query(
                    original_query=query,
                    search_query=optimized_query,
                    tenant_id=tenant_id,
                    goal=goal,
                    max_results=max_results,
                    include_types=include_types,
                    entity_names=query_plan.extracted_entities
                )
            finally:
                # Restore original parameters
                self.config.max_activation_depth = original_depth
                self.config.activation_threshold = original_threshold
                self.config.anchor_top_k = original_anchor_k
                self.config.activation_decay = original_decay
        else:
            result = await self.retrieve(
                query=query,
                tenant_id=tenant_id,
                goal=goal,
                max_results=max_results,
                include_types=include_types,
                use_spreading=True
            )
        
        return result, query_plan
    
    async def _retrieve_with_custom_query(
        self,
        original_query: str,
        search_query: str,
        tenant_id: str,
        goal: Optional[str] = None,
        max_results: int = 10,
        include_types: Optional[List[NodeType]] = None,
        entity_names: Optional[List[str]] = None
    ) -> RetrievalResult:
        """
        Retrieve using a custom optimized search query for anchors.
        
        Uses search_query for anchor finding but original_query for embeddings.
        This allows us to use extracted entities for better lexical matching
        while keeping semantic similarity from the full query.
        """
        print(f"[Retriever] Custom query retrieval")
        
        # Default to all node types
        if include_types is None:
            include_types = [NodeType.ENTITY, NodeType.CLAIM, NodeType.INSIGHT]
        
        # Generate embedding from ORIGINAL query (for semantic similarity)
        query_embedding = None
        if self.embeddings:
            try:
                query_embedding = self.embeddings.embed_text(original_query)
            except Exception as e:
                print(f"  ⚠ Embedding failed: {e}")
        
        # Goal embedding
        goal_embedding = None
        if goal and self.embeddings:
            try:
                goal_embedding = self.embeddings.embed_text(goal)
                print(f"  🎯 Goal-directed: '{goal[:30]}...'")
            except Exception as e:
                print(f"  ⚠ Goal embedding failed: {e}")
        
        # Find anchors using OPTIMIZED search query (entity-focused)
        anchors = await self._find_anchors(
            query_text=search_query,  # Use optimized query
            query_embedding=query_embedding,  # But original embedding
            tenant_id=tenant_id,
            node_types=include_types,
            limit=self.config.anchor_top_k,
            entity_names=entity_names  # Pass extracted entities for boosting
        )
        
        if not anchors:
            print(f"  ⚠ No anchors found")
            return RetrievalResult(
                query=original_query,
                activated_nodes=[],
                total_activation=0.0
            )
        
        print(f"  🎯 Found {len(anchors)} anchors")
        
        # Spread activation
        activated = await self._spread_activation(
            anchors=anchors,
            tenant_id=tenant_id,
            include_types=include_types,
            goal_embedding=goal_embedding
        )
        
        # Apply recency weighting
        activated = await self._apply_recency_weighting(activated, tenant_id)
        
        # Sort by activation and limit
        activated.sort(key=lambda n: n.activation, reverse=True)
        activated = activated[:max_results]
        
        # Calculate total activation
        total_activation = sum(n.activation for n in activated)
        
        print(f"  ✓ Retrieved {len(activated)} nodes (total activation: {total_activation:.2f})")
        
        return RetrievalResult(
            query=original_query,
            anchors=anchors,
            activated_nodes=activated
        )
    
    async def _find_anchors(
        self,
        query_text: str,
        query_embedding: Optional[List[float]],
        tenant_id: str,
        node_types: List[NodeType],
        limit: int,
        entity_names: Optional[List[str]] = None
    ) -> List[AnchorResult]:
        """
        Find anchor nodes via hybrid search with entity boosting.
        
        When entity_names are provided (from query analysis), we explicitly
        search for Entity nodes matching those names and boost their scores.
        This ensures entity-to-entity edges get traversed by starting from
        the right Entity nodes.
        """
        results = []
        
        # 1. First, explicitly find Entity nodes matching extracted entity names
        if entity_names and NodeType.ENTITY in node_types:
            entity_anchors = await self._find_entity_anchors_by_name(
                entity_names=entity_names,
                tenant_id=tenant_id
            )
            # Give entity anchors a high score boost (0.9 base)
            for anchor in entity_anchors:
                anchor.score = 0.9  # High base score for exact entity matches
                results.append(anchor)
                print(f"    🎯 Entity anchor: {anchor.content_preview} (boosted)")
        
        # 2. Standard hybrid search for other anchors
        hybrid_results = await self.store.hybrid_anchor_search(
            query_text=query_text,
            query_embedding=query_embedding or [0.0] * 1536,
            tenant_id=tenant_id,
            node_types=node_types,
            limit=limit
        )
        results.extend(hybrid_results)
        
        # 3. Dedupe by node_id, keeping highest score
        seen: Dict[str, AnchorResult] = {}
        for r in results:
            if r.node_id not in seen or r.score > seen[r.node_id].score:
                seen[r.node_id] = r
        
        # Sort by score and return top limit
        final_results = sorted(seen.values(), key=lambda x: x.score, reverse=True)
        return final_results[:limit]
    
    async def _find_entity_anchors_by_name(
        self,
        entity_names: List[str],
        tenant_id: str
    ) -> List[AnchorResult]:
        """
        Find Entity nodes by exact or fuzzy name matching.
        
        This is the key to making entity-to-entity edges useful:
        we need to start spreading from the actual Entity nodes.
        """
        results = []
        
        # Use the store's connection to find entities by name
        if hasattr(self.store, '_get_conn'):
            conn = self.store._get_conn()
            
            for name in entity_names:
                # Exact case-insensitive match first
                rows = conn.execute("""
                    SELECT id, name 
                    FROM entities 
                    WHERE tenant_id = ? AND LOWER(name) = LOWER(?)
                """, (tenant_id, name)).fetchall()
                
                for row in rows:
                    results.append(AnchorResult(
                        node_id=row["id"],
                        node_type=NodeType.ENTITY,
                        score=1.0,  # Perfect match
                        content_preview=row["name"]
                    ))
                
                # If no exact match, try fuzzy (contains)
                if not rows:
                    rows = conn.execute("""
                        SELECT id, name 
                        FROM entities 
                        WHERE tenant_id = ? AND LOWER(name) LIKE ?
                        LIMIT 3
                    """, (tenant_id, f"%{name.lower()}%")).fetchall()
                    
                    for row in rows:
                        results.append(AnchorResult(
                            node_id=row["id"],
                            node_type=NodeType.ENTITY,
                            score=0.8,  # Fuzzy match
                            content_preview=row["name"]
                        ))
        
        return results
    
    def _compute_degree_penalty(self, degree: int) -> float:
        """
        Compute degree penalty for hub dampening (Tier 2).
        
        High-degree "hub" nodes get penalized to prevent flooding
        the graph with irrelevant activations.
        
        Formula: min(1.0, max(0.1, scale / sqrt(degree)))
        """
        if degree <= 1:
            return 1.0
        penalty = self.config.degree_penalty_base / math.sqrt(degree)
        return max(0.1, min(1.0, penalty))
    
    def _compute_goal_relevance(
        self,
        node_embedding: Optional[List[float]],
        goal_embedding: Optional[List[float]],
        weight: float = 0.5
    ) -> float:
        """
        Compute goal-directed boost for a node (Tier 2).
        
        Nodes semantically similar to the goal get boosted.
        Formula: (1 - weight) + weight * cosine_sim(node, goal)
        
        Returns 1.0 if either embedding is missing.
        """
        if goal_embedding is None or node_embedding is None:
            return 1.0
        
        # Cosine similarity
        dot = sum(a * b for a, b in zip(node_embedding, goal_embedding))
        norm_a = math.sqrt(sum(a * a for a in node_embedding))
        norm_b = math.sqrt(sum(b * b for b in goal_embedding))
        
        if norm_a == 0 or norm_b == 0:
            return 1.0
        
        sim = dot / (norm_a * norm_b)
        return (1.0 - weight) + (weight * max(0.0, sim))
    
    async def _compute_dead_end_penalty(
        self,
        node_id: str,
        node_type: NodeType,
        tenant_id: str
    ) -> float:
        """
        Compute penalty for dead-end nodes (Tier 2).
        
        Entities with no outgoing edges are "dead ends" that cannot
        contribute to multi-hop reasoning. They consume activation
        without leading to useful facts.
        
        Returns config.dead_end_penalty (default 0.3) for dead-end entities,
        1.0 for all other nodes.
        """
        # Only penalize entities - claims are often leaf nodes by design
        if node_type != NodeType.ENTITY:
            return 1.0
        
        # Check if this entity has any outgoing edges
        outgoing_edges = await self.store.get_edges_from(node_id, tenant_id)
        
        if len(outgoing_edges) == 0:
            return self.config.dead_end_penalty
        
        return 1.0
    
    async def _apply_recency_weighting(
        self,
        activated: List[ActivatedNode],
        tenant_id: str
    ) -> List[ActivatedNode]:
        """
        Apply recency boost to activated nodes (Tier 2).
        
        Formula: activation *= exp(-days_old / half_life)
        Default half-life is 30 days from config.
        """
        now = datetime.utcnow()
        half_life = self.config.decay_half_life_days
        
        for node in activated:
            full_node = await self.store.get_node(node.node_id, tenant_id)
            if full_node and hasattr(full_node, 'last_accessed'):
                days_old = (now - full_node.last_accessed).total_seconds() / 86400
                recency_factor = math.exp(-days_old / half_life)
                node.activation *= recency_factor
        
        return activated
    
    async def _spread_activation(
        self,
        anchors: List[AnchorResult],
        tenant_id: str,
        include_types: List[NodeType],
        goal_embedding: Optional[List[float]] = None
    ) -> List[ActivatedNode]:
        """
        Spread activation from anchors through the graph.
        
        Uses a priority queue (max-heap by activation) to process nodes
        in order of activation strength, spreading to neighbors with decay.
        
        Tier 2 enhancements:
        - Degree penalty (hub dampening): High-degree nodes spread less
        - Goal-directed activation: Nodes matching goal get boosted
        """
        # Track activation levels and visited nodes
        activations: Dict[str, float] = {}
        node_info: Dict[str, Tuple[NodeType, int, List[str]]] = {}  # id -> (type, depth, path)
        visited: Set[str] = set()
        
        # Initialize with anchors
        heap: List[ActivationState] = []
        for anchor in anchors:
            state = ActivationState(
                node_id=anchor.node_id,
                node_type=anchor.node_type,
                activation=anchor.score,
                depth=0,
                path=[anchor.node_id]
            )
            heapq.heappush(heap, state)
            activations[anchor.node_id] = anchor.score
            node_info[anchor.node_id] = (anchor.node_type, 0, [anchor.node_id])
        
        # Process nodes in order of activation
        while heap:
            current = heapq.heappop(heap)
            
            # Skip if already visited with higher activation
            if current.node_id in visited:
                continue
            visited.add(current.node_id)
            
            # Stop if below threshold or too deep
            if current.activation < self.config.activation_threshold:
                continue
            if current.depth >= self.config.max_activation_depth:
                continue
            
            # Get neighbors
            neighbors = await self.store.get_neighbors(
                current.node_id,
                tenant_id,
                direction="both"
            )
            
            # Tier 2: Apply degree penalty (hub dampening)
            degree_penalty = self._compute_degree_penalty(len(neighbors))
            
            for neighbor_id in neighbors:
                if neighbor_id in visited:
                    continue
                
                # Get edge weight and type for prioritization
                edge_weight, edge_type = await self._get_edge_weight_and_type(
                    current.node_id,
                    neighbor_id,
                    tenant_id
                )
                
                # Boost semantic relationship edges (entity-to-entity)
                # ALLERGIC_TO, TAKES, TREATS, etc. are more valuable than ABOUT/MENTIONS
                # Only apply boost from anchors (depth 0) to prevent compounding across hops
                if current.depth == 0:
                    edge_type_boost = self._compute_edge_type_boost(edge_type)
                else:
                    edge_type_boost = 1.0
                
                # Get neighbor node for type and embedding
                neighbor_node = await self.store.get_node(neighbor_id, tenant_id)
                if neighbor_node is None:
                    continue
                
                neighbor_type = neighbor_node.node_type
                
                # Filter by included types
                if neighbor_type not in include_types:
                    continue
                
                # Tier 2: Goal-directed activation boost
                goal_boost = self._compute_goal_relevance(
                    getattr(neighbor_node, 'embedding', None),
                    goal_embedding
                )
                
                # Tier 2: Dead-end penalty for entities with no outgoing edges
                dead_end_penalty = await self._compute_dead_end_penalty(
                    neighbor_id, neighbor_type, tenant_id
                )
                
                # Tier 2: Claim boost - claims contain facts and shouldn't be overshadowed by entities
                claim_boost = self.config.claim_boost if neighbor_type == NodeType.CLAIM else 1.0
                
                # Calculate new activation with decay + Tier 2 factors + edge type boost
                new_activation = (
                    current.activation 
                    * self.config.activation_decay 
                    * edge_weight
                    * edge_type_boost  # Boost semantic relationships
                    * degree_penalty   # Tier 2: Hub dampening
                    * goal_boost       # Tier 2: Goal-directed boost
                    * dead_end_penalty # Tier 2: Dead-end penalty
                    * claim_boost      # Tier 2: Claim boost
                )
                
                # Apply node strength as multiplier
                new_activation *= neighbor_node.strength
                
                # Only process if above threshold
                if new_activation < self.config.activation_threshold:
                    continue
                
                # Update if this is higher activation than before
                if neighbor_id not in activations or new_activation > activations[neighbor_id]:
                    activations[neighbor_id] = new_activation
                    new_path = current.path + [neighbor_id]
                    node_info[neighbor_id] = (neighbor_type, current.depth + 1, new_path)
                    
                    state = ActivationState(
                        node_id=neighbor_id,
                        node_type=neighbor_type,
                        activation=new_activation,
                        depth=current.depth + 1,
                        path=new_path
                    )
                    heapq.heappush(heap, state)
        
        # Convert to ActivatedNode list
        result = []
        for node_id, activation in activations.items():
            if activation >= self.config.activation_threshold:
                node_type, depth, path = node_info[node_id]
                result.append(ActivatedNode(
                    node_id=node_id,
                    node_type=node_type,
                    activation=activation,
                    hops_from_anchor=depth,
                    path=path
                ))
        
        return result
    
    async def _get_edge_weight(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str
    ) -> float:
        """Get edge weight between two nodes."""
        # Try both directions
        edges = await self.store.get_edges_from(source_id, tenant_id)
        for edge in edges:
            if edge.target_id == target_id:
                return edge.weight
        
        edges = await self.store.get_edges_to(target_id, tenant_id)
        for edge in edges:
            if edge.source_id == source_id:
                return edge.weight
        
        return 1.0  # Default weight
    
    async def _get_edge_weight_and_type(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str
    ) -> Tuple[float, Optional[EdgeType]]:
        """
        Get edge weight and type between two nodes.
        
        When multiple edges exist between the same nodes (e.g., Michael -> HCTZ
        has both RELATED_TO and TAKES edges), select the edge with the highest
        effective weight (weight × edge_type_boost) to prioritize semantic edges.
        """
        best_weight = 1.0
        best_type = None
        best_effective = 0.0
        
        # Check edges from source to target
        edges = await self.store.get_edges_from(source_id, tenant_id)
        for edge in edges:
            if edge.target_id == target_id:
                boost = self._compute_edge_type_boost(edge.edge_type)
                effective = edge.weight * boost
                if effective > best_effective:
                    best_effective = effective
                    best_weight = edge.weight
                    best_type = edge.edge_type
        
        # Also check reverse direction
        edges = await self.store.get_edges_to(target_id, tenant_id)
        for edge in edges:
            if edge.source_id == source_id:
                boost = self._compute_edge_type_boost(edge.edge_type)
                effective = edge.weight * boost
                if effective > best_effective:
                    best_effective = effective
                    best_weight = edge.weight
                    best_type = edge.edge_type
        
        if best_effective > 0:
            return best_weight, best_type
        
        return 1.0, None  # Default weight, unknown type
    
    def _compute_edge_type_boost(self, edge_type: Optional[EdgeType]) -> float:
        """
        Compute boost factor based on edge type.
        
        Semantic relationship edges (entity-to-entity) get a boost
        to prioritize them over structural edges (ABOUT, MENTIONS, PRODUCED).
        
        This is key to making multi-hop retrieval work - we want to follow
        paths like Michael -> ALLERGIC_TO -> penicillin rather than
        Michael <- ABOUT <- Claim.
        """
        if edge_type is None:
            return 1.0
        
        # Semantic relationship edges - boost these
        SEMANTIC_EDGES = {
            EdgeType.ALLERGIC_TO: 2.0,      # Critical safety info
            EdgeType.TAKES: 1.8,            # Medication relationships
            EdgeType.TREATS: 1.8,           # Treatment relationships
            EdgeType.CAUSES: 1.7,           # Causal relationships
            EdgeType.CONTRAINDICATED_WITH: 2.0,  # Drug interactions
            EdgeType.PRESCRIBED: 1.5,
            EdgeType.DIAGNOSED_WITH: 1.6,
            EdgeType.EXPERIENCES: 1.5,
            EdgeType.SIDE_EFFECT_OF: 1.7,
            EdgeType.TREATED_BY: 1.4,
            EdgeType.SPECIALIST_FOR: 1.4,
            EdgeType.AFFECTS: 1.5,
            EdgeType.INDICATES: 1.4,
            EdgeType.MEASURED: 1.3,
            EdgeType.ORDERED: 1.3,
            EdgeType.REPLACES: 1.4,
            EdgeType.WORKS_WITH: 1.3,
            EdgeType.WORKS_ON: 1.3,
            EdgeType.MANAGES: 1.3,
            EdgeType.MEMBER_OF: 1.2,
            EdgeType.CREATED: 1.2,
            EdgeType.PREFERS: 1.2,
            EdgeType.INTERESTED_IN: 1.1,
            EdgeType.LOCATED_IN: 1.2,
            EdgeType.LIVES_IN: 1.2,
        }
        
        # Check if it's a semantic edge
        if edge_type in SEMANTIC_EDGES:
            return SEMANTIC_EDGES[edge_type]
        
        # Structural edges - no boost (or slight reduction)
        if edge_type in (EdgeType.ABOUT, EdgeType.MENTIONS, EdgeType.PRODUCED):
            return 0.8  # Slight reduction for structural edges
        
        # RELATED_TO is a weak semantic edge
        if edge_type == EdgeType.RELATED_TO:
            return 1.1
        
        return 1.0  # Default

    async def retrieve_and_format(
        self,
        query: str,
        tenant_id: str,
        max_results: int = 10,
        max_tokens: Optional[int] = None,
        include_types: Optional[List[NodeType]] = None
    ) -> str:
        """
        Retrieve and format memory into context string.
        
        Args:
            query: Natural language query
            tenant_id: Tenant identifier
            max_results: Maximum nodes to retrieve
            max_tokens: Maximum tokens in formatted output
            include_types: Node types to include
            
        Returns:
            Formatted context string for LLM
        """
        result = await self.retrieve(
            query=query,
            tenant_id=tenant_id,
            max_results=max_results,
            include_types=include_types
        )
        
        if not result.activated_nodes:
            return ""
        
        return await self._format_context(
            result,
            tenant_id,
            max_tokens or self.config.max_context_tokens
        )
    
    async def _format_context(
        self,
        result: RetrievalResult,
        tenant_id: str,
        max_tokens: int
    ) -> str:
        """Format retrieval result into context string."""
        sections = []
        
        # Group by node type
        by_type: Dict[NodeType, List[ActivatedNode]] = defaultdict(list)
        for node in result.activated_nodes:
            by_type[node.node_type].append(node)
        
        # Format each type
        if by_type.get(NodeType.INSIGHT):
            section = await self._format_insights(
                by_type[NodeType.INSIGHT], tenant_id
            )
            if section:
                sections.append(section)
        
        if by_type.get(NodeType.CLAIM):
            section = await self._format_claims(
                by_type[NodeType.CLAIM], tenant_id
            )
            if section:
                sections.append(section)
        
        if by_type.get(NodeType.ENTITY):
            section = await self._format_entities(
                by_type[NodeType.ENTITY], tenant_id
            )
            if section:
                sections.append(section)
        
        if by_type.get(NodeType.EPISODE):
            section = await self._format_episodes(
                by_type[NodeType.EPISODE], tenant_id
            )
            if section:
                sections.append(section)
        
        if by_type.get(NodeType.PROCEDURE):
            section = await self._format_procedures(
                by_type[NodeType.PROCEDURE], tenant_id
            )
            if section:
                sections.append(section)
        
        context = "\n\n".join(sections)
        
        # Truncate if needed (rough estimate: 4 chars per token)
        max_chars = max_tokens * 4
        if len(context) > max_chars:
            context = context[:max_chars] + "..."
        
        return context
    
    async def _format_insights(
        self,
        nodes: List[ActivatedNode],
        tenant_id: str
    ) -> str:
        """Format insight nodes."""
        lines = ["### Long-term Insights"]
        
        for node in sorted(nodes, key=lambda n: n.activation, reverse=True):
            insight = await self.store.get_insight(node.node_id, tenant_id)
            if insight:
                conf = f"({insight.confidence:.0%})" if insight.confidence else ""
                lines.append(f"• {insight.content} {conf}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    async def _format_claims(
        self,
        nodes: List[ActivatedNode],
        tenant_id: str
    ) -> str:
        """Format claim nodes."""
        lines = ["### Known Facts"]
        
        for node in sorted(nodes, key=lambda n: n.activation, reverse=True):
            claim = await self.store.get_claim(node.node_id, tenant_id)
            if claim:
                lines.append(f"• {claim.content}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    async def _format_entities(
        self,
        nodes: List[ActivatedNode],
        tenant_id: str
    ) -> str:
        """Format entity nodes with their claims."""
        lines = ["### Relevant Entities"]
        
        for node in sorted(nodes, key=lambda n: n.activation, reverse=True):
            entity = await self.store.get_entity(node.node_id, tenant_id)
            if entity:
                lines.append(f"\n**{entity.name}** ({entity.entity_type})")
                
                # Get claims about this entity
                claims = await self.store.get_claims_for_entity(
                    node.node_id, tenant_id
                )
                for claim in claims[:3]:  # Limit claims per entity
                    lines.append(f"  - {claim.content}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    async def _format_episodes(
        self,
        nodes: List[ActivatedNode],
        tenant_id: str
    ) -> str:
        """Format episode nodes."""
        lines = ["### Relevant Conversations"]
        
        for node in sorted(nodes, key=lambda n: n.activation, reverse=True):
            episode = await self.store.get_episode(node.node_id, tenant_id)
            if episode and episode.summary:
                lines.append(f"• {episode.summary}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    async def _format_procedures(
        self,
        nodes: List[ActivatedNode],
        tenant_id: str
    ) -> str:
        """Format procedure nodes."""
        lines = ["### Known Procedures"]
        
        for node in sorted(nodes, key=lambda n: n.activation, reverse=True):
            procedure = await self.store.get_procedure(node.node_id, tenant_id)
            if procedure:
                lines.append(f"\n**{procedure.name}**")
                lines.append(f"  {procedure.description}")
                for i, step in enumerate(procedure.steps[:5], 1):
                    lines.append(f"  {i}. {step}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    async def get_entity_profile(
        self,
        entity_name: str,
        tenant_id: str
    ) -> Optional[str]:
        """
        Get a formatted profile for a specific entity.
        
        Useful for getting all known information about a person, topic, etc.
        
        Args:
            entity_name: Name of the entity
            tenant_id: Tenant identifier
            
        Returns:
            Formatted profile or None if entity not found
        """
        entity = await self.store.find_entity_by_name(entity_name, tenant_id)
        if not entity:
            return None
        
        lines = [f"## Profile: {entity.name}"]
        lines.append(f"Type: {entity.entity_type}")
        lines.append(f"Mentioned: {entity.mention_count} times")
        
        if entity.aliases:
            lines.append(f"Also known as: {', '.join(entity.aliases)}")
        
        # Get claims
        claims = await self.store.get_claims_for_entity(entity.id, tenant_id)
        if claims:
            lines.append("\n### Known Facts")
            for claim in claims:
                # Handle both string and enum claim_kind
                if claim.claim_kind:
                    kind_str = claim.claim_kind.value if hasattr(claim.claim_kind, 'value') else claim.claim_kind
                    kind = f"[{kind_str}]"
                else:
                    kind = ""
                lines.append(f"• {claim.content} {kind}")
        
        return "\n".join(lines)
