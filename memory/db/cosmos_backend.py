"""
Azure CosmosDB Backend for Agent Memory Service.

This backend provides enterprise-grade memory storage using Azure CosmosDB
for NoSQL with native vector search and hybrid search (RRF) capabilities.

Features:
- Native vector search with VectorDistance
- Hybrid search with RRF (Reciprocal Rank Fusion)
- Full-text search with FullTextScore
- Global distribution and high availability
- Automatic scaling

Requires:
- Azure CosmosDB for NoSQL account
- Database and containers with vector indexing policies
"""

import os
from typing import Any, Dict, List, Optional

from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from memory.db.base import (
    ContainerType,
    DatabaseCapabilities,
    EmbeddingProvider,
    MemoryDatabase,
    SearchResult,
)

VECTOR_SEARCH_FIELDS = {
    ContainerType.INTERACTIONS: [
        "id",
        "user_id",
        "session_id",
        "timestamp",
        "content",
        "summary",
        "metadata",
        "created_at",
        "updated_at",
    ],
    ContainerType.INSIGHTS: [
        "id",
        "user_id",
        "session_ids",
        "insight_type",
        "insight_text",
        "category",
        "confidence",
        "importance",
        "processed",
        "source_insight_ids",
        "source_session_ids",
        "date_added",
        "last_accessed",
        "access_count",
        "created_at",
        "updated_at",
    ],
    ContainerType.SESSION_SUMMARIES: [
        "id",
        "user_id",
        "start_time",
        "end_time",
        "summary",
        "key_topics",
        "extracted_insights",
        "status",
        "reflection_status",
        "cumulative_summary",
        "turn_count",
        "created_at",
        "updated_at",
    ],
}


class CosmosDBDatabase(MemoryDatabase):
    """
    Azure CosmosDB backend for Agent Memory Service.
    
    Uses CosmosDB for NoSQL with vector search and hybrid search capabilities.
    Supports native RRF (Reciprocal Rank Fusion) for combining vector and
    full-text search results.
    """
    
    def __init__(
        self,
        cosmos_client: Optional[CosmosClient] = None,
        database_name: str = "agent_memory_db",
        embedding_provider: Optional[EmbeddingProvider] = None,
        connection_string: Optional[str] = None,
        endpoint: Optional[str] = None,
        key: Optional[str] = None,
        credential: Optional[Any] = None,
        vector_dimensions: int = 1536
    ):
        """
        Initialize CosmosDB backend.
        
        Args:
            cosmos_client: Existing CosmosClient instance
            database_name: Name of the database
            embedding_provider: Provider for generating embeddings
            connection_string: CosmosDB connection string (alternative to client)
            endpoint: CosmosDB endpoint (alternative to client/connection_string)
            key: CosmosDB key (used with endpoint)
            credential: Azure credential for AAD auth (used with endpoint)
            vector_dimensions: Dimension of embedding vectors
        """
        super().__init__(embedding_provider)
        
        self.database_name = database_name
        self.vector_dimensions = vector_dimensions
        
        # Container name mapping
        self._container_names = {
            ContainerType.INTERACTIONS: "interactions",
            ContainerType.INSIGHTS: "insights",
            ContainerType.SESSION_SUMMARIES: "session_summaries",
        }
        
        # Initialize client
        if cosmos_client:
            self._client = cosmos_client
            self._owns_client = False
        elif connection_string:
            self._client = CosmosClient.from_connection_string(connection_string)
            self._owns_client = True
        elif endpoint and credential:
            # AAD authentication
            self._client = CosmosClient(endpoint, credential=credential)
            self._owns_client = True
        elif endpoint and key:
            self._client = CosmosClient(endpoint, key)
            self._owns_client = True
        else:
            # Try environment variables
            endpoint = os.getenv("AZURE_COSMOS_ENDPOINT") or os.getenv("COSMOS_ENDPOINT")
            key = os.getenv("AZURE_COSMOS_KEY") or os.getenv("COSMOS_KEY")
            conn_str = os.getenv("AZURE_COSMOS_CONNECTION_STRING") or os.getenv("COSMOS_CONNECTION_STRING")
            
            if conn_str:
                self._client = CosmosClient.from_connection_string(conn_str)
                self._owns_client = True
            elif endpoint and key:
                self._client = CosmosClient(endpoint, key)
                self._owns_client = True
            elif endpoint:
                # Try AAD auth with DefaultAzureCredential
                try:
                    from azure.identity import DefaultAzureCredential
                    credential = DefaultAzureCredential()
                    self._client = CosmosClient(endpoint, credential=credential)
                    self._owns_client = True
                except ImportError:
                    raise ValueError(
                        "CosmosDB connection required. Provide cosmos_client, "
                        "connection_string, endpoint/key, or install azure-identity for AAD auth."
                    )
            else:
                raise ValueError(
                    "CosmosDB connection required. Provide cosmos_client, "
                    "connection_string, or endpoint/key."
                )
        
        self._database: Optional[DatabaseProxy] = None
        self._containers: Dict[ContainerType, ContainerProxy] = {}
    
    async def initialize(self) -> None:
        """Initialize database and get container references."""
        self._database = self._client.get_database_client(self.database_name)
        
        # Get container clients
        for container_type, name in self._container_names.items():
            self._containers[container_type] = self._database.get_container_client(name)
    
    async def close(self) -> None:
        """Close client if we own it."""
        if self._owns_client and self._client:
            await self._client.close()
            self._client = None
        self._database = None
        self._containers.clear()
    
    def get_capabilities(self) -> DatabaseCapabilities:
        """Get database capabilities."""
        return DatabaseCapabilities(
            supports_vector_search=True,
            supports_hybrid_search=True,  # CosmosDB supports RRF
            supports_full_text_search=True,
            supports_transactions=True,
            vector_dimensions=self.vector_dimensions,
            max_batch_size=100,
            backend_name="cosmosdb",
            backend_version="nosql"
        )
    
    def _get_container(self, container: ContainerType) -> ContainerProxy:
        """Get container client for container type."""
        if container not in self._containers:
            raise ValueError(f"Container {container} not initialized")
        return self._containers[container]
    
    async def upsert(
        self,
        container: ContainerType,
        document: Dict[str, Any],
        partition_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Insert or update a document."""
        if "id" not in document:
            raise ValueError("Document must have an 'id' field")
        
        container_client = self._get_container(container)
        result = await container_client.upsert_item(body=document)
        return result
    
    async def batch_upsert(
        self,
        container: ContainerType,
        documents: List[Dict[str, Any]],
        partition_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Insert or update multiple documents."""
        results = []
        container_client = self._get_container(container)
        
        for doc in documents:
            if "id" not in doc:
                raise ValueError("Document must have an 'id' field")
            result = await container_client.upsert_item(body=doc)
            results.append(result)
        
        return results
    
    async def get_by_id(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        container_client = self._get_container(container)
        
        try:
            result = await container_client.read_item(
                item=document_id,
                partition_key=partition_key
            )
            return result
        except CosmosResourceNotFoundError:
            return None
    
    async def delete(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None
    ) -> bool:
        """Delete document by ID."""
        container_client = self._get_container(container)
        
        try:
            await container_client.delete_item(
                item=document_id,
                partition_key=partition_key
            )
            return True
        except CosmosResourceNotFoundError:
            return False
    
    async def query(
        self,
        container: ContainerType,
        filters: Dict[str, Any],
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query documents with filters."""
        container_client = self._get_container(container)
        
        # Build query
        conditions = []
        params = []
        for key, value in filters.items():
            param_name = f"@{key}"
            conditions.append(f"c.{key} = {param_name}")
            params.append({"name": param_name, "value": value})
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        order_clause = ""
        if order_by:
            if order_by.startswith("-"):
                order_clause = f"ORDER BY c.{order_by[1:]} DESC"
            else:
                order_clause = f"ORDER BY c.{order_by} ASC"
        
        top_clause = ""
        if limit:
            top_clause = f"TOP {limit}"
        
        query = f"SELECT {top_clause} * FROM c {where_clause} {order_clause}"
        
        iterator = container_client.query_items(
            query=query,
            parameters=params,
        )
        return [item async for item in iterator]

    def _build_vector_select_clause(self, container: ContainerType) -> str:
        """Build an explicit field list for vector search results."""
        return ", ".join(f"c.{field}" for field in VECTOR_SEARCH_FIELDS[container])
    
    async def vector_search(
        self,
        container: ContainerType,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Perform vector similarity search using VectorDistance."""
        container_client = self._get_container(container)
        
        # Build WHERE clause for filters
        where_clause = ""
        # Note: TOP clause does not support parameterized values in CosmosDB
        params = [
            {"name": "@embedding", "value": query_embedding}
        ]
        
        if filters:
            conditions = []
            for key, value in filters.items():
                param_name = f"@{key}"
                conditions.append(f"c.{key} = {param_name}")
                params.append({"name": param_name, "value": value})
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # NOTE: CosmosDB vector search does NOT support SELECT c.* with VectorDistance.
        # We must explicitly select the fields we want, excluding the vector fields.
        # The query returns non-vector fields only to avoid the "One of the input values is invalid" error.
        select_clause = self._build_vector_select_clause(container)
        query = (
            f"SELECT TOP {top_k} {select_clause}, "
            f"VectorDistance(c.{vector_field}, @embedding) AS similarity_score "
            f"FROM c {where_clause} "
            f"ORDER BY VectorDistance(c.{vector_field}, @embedding)"
        )
        
        try:
            iterator = container_client.query_items(
                query=query,
                parameters=params,
            )
            results = [item async for item in iterator]
        except Exception as e:
            print(f"[CosmosDB] Vector search error: {e}")
            print(f"[CosmosDB] Container: {container}, Vector field: {vector_field}")
            # Return empty results instead of crashing
            return []
        
        # Convert to SearchResult
        search_results = []
        for doc in results:
            score = doc.pop("similarity_score", 0.0)
            # VectorDistance returns distance, convert to similarity
            similarity = 1.0 - score if score <= 1.0 else 1.0 / (1.0 + score)
            search_results.append(SearchResult(
                id=doc["id"],
                document=doc,
                score=similarity,
                score_type="similarity"
            ))
        
        return search_results
    
    async def hybrid_search(
        self,
        container: ContainerType,
        query_text: str,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        text_fields: Optional[List[str]] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Perform hybrid search using RRF (Reciprocal Rank Fusion).
        
        Combines vector similarity with full-text search for better results.
        """
        container_client = self._get_container(container)
        
        if text_fields is None:
            text_fields = ["content"]
        
        # Convert embedding to literal array format
        embedding_literal = "[" + ",".join(str(x) for x in query_embedding) + "]"
        
        # Escape single quotes in query text
        safe_query_text = query_text.replace("'", "''")
        
        # Build search terms for FullTextScore
        search_terms = [f'"{term}"' for term in safe_query_text.split() if term.strip()]
        search_terms_str = ", ".join(search_terms) if search_terms else f'"{safe_query_text}"'
        
        # Build WHERE clause for filters
        where_clause = ""
        params = []
        if filters:
            conditions = []
            for key, value in filters.items():
                param_name = f"@{key}"
                conditions.append(f"c.{key} = {param_name}")
                params.append({"name": param_name, "value": value})
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # Build full-text score
        primary_field = text_fields[0]
        full_text_score = f"FullTextScore(c.{primary_field}, {search_terms_str})"
        
        # Build RRF query
        query = f"""
            SELECT TOP {top_k} *
            FROM c
            {where_clause}
            ORDER BY RANK RRF(VectorDistance(c.{vector_field}, {embedding_literal}), {full_text_score})
        """
        
        iterator = container_client.query_items(
            query=query,
            parameters=params,
        )
        results = [item async for item in iterator]
        
        # Convert to SearchResult
        search_results = []
        for i, doc in enumerate(results):
            # RRF doesn't return explicit scores, use rank-based score
            score = 1.0 / (i + 1)  # Higher rank = higher score
            search_results.append(SearchResult(
                id=doc["id"],
                document=doc,
                score=score,
                score_type="hybrid"
            ))
        
        return search_results
