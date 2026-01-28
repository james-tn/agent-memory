"""
Simple Vector Baseline Retriever

A straightforward vector similarity search for comparison against SAM.
This represents the "naive" approach - just embed the query and find
the most similar claims/episodes by cosine similarity.

Used as a baseline to evaluate whether spreading activation provides
measurable improvements over simple vector retrieval.
"""

import math
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from sam.stores.base import MemoryStore
from sam.embeddings import EmbeddingsService
from sam.models.graph import NodeType, Claim, Entity


@dataclass
class VectorRetrievalResult:
    """Result from vector-based retrieval."""
    node_id: str
    node_type: NodeType
    content: str
    similarity: float
    metadata: Dict[str, Any] = None


class SimpleVectorRetriever:
    """
    Simple vector similarity retriever for baseline comparison.
    
    This retriever:
    1. Embeds the query
    2. Computes cosine similarity against all claim embeddings
    3. Returns top-K most similar claims
    
    No graph traversal, no spreading activation, no fancy stuff.
    Just: query → embed → similarity search → results
    """
    
    def __init__(
        self,
        store: MemoryStore,
        embeddings: EmbeddingsService
    ):
        """
        Initialize the simple vector retriever.
        
        Args:
            store: MemoryStore backend
            embeddings: EmbeddingsService for query embedding
        """
        self.store = store
        self.embeddings = embeddings
    
    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        max_results: int = 10,
        include_entities: bool = True,
        min_similarity: float = 0.3
    ) -> List[VectorRetrievalResult]:
        """
        Retrieve relevant claims using simple vector similarity.
        
        Args:
            query: Natural language query
            tenant_id: Tenant identifier
            max_results: Maximum number of results
            include_entities: Whether to also search entity names
            min_similarity: Minimum cosine similarity threshold
            
        Returns:
            List of VectorRetrievalResult sorted by similarity
        """
        print(f"[VectorBaseline] Query: '{query[:50]}...'")
        
        # 1. Embed the query
        query_embedding = self.embeddings.embed_text(query)
        
        results = []
        
        # 2. Search claims by vector similarity
        claims = await self._get_all_claims_with_embeddings(tenant_id)
        
        for claim in claims:
            if claim.embedding is None:
                continue
            
            similarity = self._cosine_similarity(query_embedding, claim.embedding)
            
            if similarity >= min_similarity:
                # Handle claim_kind that might be either enum or string
                claim_kind_value = None
                if claim.claim_kind:
                    claim_kind_value = claim.claim_kind.value if hasattr(claim.claim_kind, 'value') else claim.claim_kind
                
                results.append(VectorRetrievalResult(
                    node_id=claim.id,
                    node_type=NodeType.CLAIM,
                    content=claim.content,
                    similarity=similarity,
                    metadata={"claim_kind": claim_kind_value}
                ))
        
        # 3. Optionally search entities
        if include_entities:
            entities = await self._get_all_entities_with_embeddings(tenant_id)
            
            for entity in entities:
                if entity.embedding is None:
                    continue
                
                similarity = self._cosine_similarity(query_embedding, entity.embedding)
                
                if similarity >= min_similarity:
                    results.append(VectorRetrievalResult(
                        node_id=entity.id,
                        node_type=NodeType.ENTITY,
                        content=entity.name,
                        similarity=similarity,
                        metadata={"entity_type": entity.entity_type}
                    ))
        
        # 4. Sort by similarity and return top K
        results.sort(key=lambda x: x.similarity, reverse=True)
        results = results[:max_results]
        
        total_sim = sum(r.similarity for r in results)
        print(f"  ✓ Retrieved {len(results)} items (total similarity: {total_sim:.2f})")
        
        return results
    
    async def retrieve_and_format(
        self,
        query: str,
        tenant_id: str,
        max_results: int = 10
    ) -> str:
        """
        Retrieve and format results as context string.
        
        Returns a formatted string similar to SAM's format for fair comparison.
        """
        results = await self.retrieve(query, tenant_id, max_results)
        
        if not results:
            return ""
        
        lines = ["### Retrieved Facts (Vector Similarity)"]
        
        for r in results:
            if r.node_type == NodeType.CLAIM:
                lines.append(f"• {r.content} [sim: {r.similarity:.2f}]")
            elif r.node_type == NodeType.ENTITY:
                lines.append(f"• Entity: {r.content} [sim: {r.similarity:.2f}]")
        
        return "\n".join(lines)
    
    async def _get_all_claims_with_embeddings(
        self,
        tenant_id: str,
        limit: int = 1000
    ) -> List[Claim]:
        """Get all claims that have embeddings."""
        # This assumes the store has a method to list claims
        # If not available, we fall back to searching
        if hasattr(self.store, 'list_claims'):
            return await self.store.list_claims(tenant_id, limit=limit)
        
        # Fallback: use the connection directly (SQLite specific)
        if hasattr(self.store, '_get_conn'):
            from sam.stores.sqlite_store import _deserialize_embedding
            
            conn = self.store._get_conn()
            rows = conn.execute("""
                SELECT * FROM claims 
                WHERE tenant_id = ? AND embedding IS NOT NULL
                LIMIT ?
            """, (tenant_id, limit)).fetchall()
            
            return [self.store._row_to_claim(row) for row in rows]
        
        return []
    
    async def _get_all_entities_with_embeddings(
        self,
        tenant_id: str,
        limit: int = 500
    ) -> List[Entity]:
        """Get all entities that have embeddings."""
        if hasattr(self.store, 'list_entities'):
            return await self.store.list_entities(tenant_id, limit=limit)
        
        # Fallback: use connection directly
        if hasattr(self.store, '_get_conn'):
            conn = self.store._get_conn()
            rows = conn.execute("""
                SELECT * FROM entities 
                WHERE tenant_id = ? AND embedding IS NOT NULL
                LIMIT ?
            """, (tenant_id, limit)).fetchall()
            
            return [self.store._row_to_entity(row) for row in rows]
        
        return []
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)
