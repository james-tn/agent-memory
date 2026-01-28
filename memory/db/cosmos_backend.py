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

from azure.cosmos import ContainerProxy, CosmosClient, DatabaseProxy
from dotenv import load_dotenv

from memory.db.base import (
    ContainerType,
    DatabaseCapabilities,
    EmbeddingProvider,
    MemoryDatabase,
    SearchResult,
)

load_dotenv()


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
            # CosmosClient doesn't have explicit close, but we can clean up
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
        result = container_client.upsert_item(body=document)
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
            result = container_client.upsert_item(body=doc)
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
            result = container_client.read_item(
                item=document_id,
                partition_key=partition_key
            )
            return result
        except Exception:
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
            container_client.delete_item(
                item=document_id,
                partition_key=partition_key
            )
            return True
        except Exception:
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
        
        results = list(container_client.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))
        
        return results
    
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
        params = [
            {"name": "@embedding", "value": query_embedding},
            {"name": "@top_k", "value": top_k}
        ]
        
        if filters:
            conditions = []
            for key, value in filters.items():
                param_name = f"@{key}"
                conditions.append(f"c.{key} = {param_name}")
                params.append({"name": param_name, "value": value})
            where_clause = "WHERE " + " AND ".join(conditions)
        
        query = f"""
            SELECT TOP @top_k c.*,
                   VectorDistance(c.{vector_field}, @embedding) AS similarity_score
            FROM c
            {where_clause}
            ORDER BY VectorDistance(c.{vector_field}, @embedding)
        """
        
        results = list(container_client.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))
        
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
        
        results = list(container_client.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))
        
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


# Backward compatibility: Wrapper around CosmosDBDatabase for existing code
class CosmosUtils:
    """
    Utility class for CosmosDB operations.
    
    This is a compatibility wrapper that maintains the existing API
    while using the new CosmosDBDatabase backend internally.
    """
    
    def __init__(self, embedding_client, embedding_deployment: str = None):
        """
        Initialize CosmosDB utilities.
        
        Args:
            embedding_client: AzureOpenAI client for embeddings
            embedding_deployment: Deployment name for embeddings
        """
        self.embedding_client = embedding_client
        self.embedding_deployment = embedding_deployment or os.getenv(
            "AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002"
        )
    
    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        response = self.embedding_client.embeddings.create(
            input=text,
            model=self.embedding_deployment
        )
        return response.data[0].embedding
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            raise ValueError("Texts list cannot be empty")
        
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            raise ValueError("All texts are empty")
        
        response = self.embedding_client.embeddings.create(
            input=valid_texts,
            model=self.embedding_deployment
        )
        return [data.embedding for data in response.data]
    
    def execute_vector_search(
        self,
        container: ContainerProxy,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute vector similarity search."""
        where_clause = ""
        params = [
            {"name": "@embedding", "value": query_embedding},
            {"name": "@top_k", "value": top_k}
        ]
        
        if filters:
            conditions = [f"c.{key} = @{key}" for key in filters.keys()]
            where_clause = " WHERE " + " AND ".join(conditions)
            for key, value in filters.items():
                params.append({"name": f"@{key}", "value": value})
        
        query = f"""
            SELECT TOP @top_k c.*,
                   VectorDistance(c.{vector_field}, @embedding) AS similarity_score
            FROM c
            {where_clause}
            ORDER BY VectorDistance(c.{vector_field}, @embedding)
        """
        
        return list(container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))
    
    def execute_hybrid_search(
        self,
        container: ContainerProxy,
        query_text: str,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        full_text_fields: Optional[List[str]] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        weights: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        """Execute hybrid search with RRF."""
        if full_text_fields is None:
            full_text_fields = ["content"]
        
        embedding_literal = "[" + ",".join(str(x) for x in query_embedding) + "]"
        safe_query_text = query_text.replace("'", "''")
        search_terms = [f'"{term}"' for term in safe_query_text.split() if term.strip()]
        search_terms_str = ", ".join(search_terms) if search_terms else f'"{safe_query_text}"'
        
        where_clause = ""
        params = []
        if filters:
            conditions = [f"c.{key} = @{key}" for key in filters.keys()]
            where_clause = " WHERE " + " AND ".join(conditions)
            for key, value in filters.items():
                params.append({"name": f"@{key}", "value": value})
        
        primary_field = full_text_fields[0]
        full_text_score = f"FullTextScore(c.{primary_field}, {search_terms_str})"
        
        rrf_args = f"VectorDistance(c.{vector_field}, {embedding_literal}), {full_text_score}"
        if weights:
            weights_str = "[" + ",".join(str(w) for w in weights) + "]"
            rrf_args += f", {weights_str}"
        
        query = f"""
            SELECT TOP {top_k} *
            FROM c
            {where_clause}
            ORDER BY RANK RRF({rrf_args})
        """
        
        return list(container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))
    
    def upsert_document(
        self,
        container: ContainerProxy,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upsert a document."""
        if "id" not in document:
            raise ValueError("Document must have an 'id' field")
        return container.upsert_item(body=document)
    
    def batch_upsert_documents(
        self,
        container: ContainerProxy,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Upsert multiple documents."""
        results = []
        for doc in documents:
            if "id" not in doc:
                raise ValueError("Document must have an 'id' field")
            results.append(container.upsert_item(body=doc))
        return results
    
    def get_document_by_id(
        self,
        container: ContainerProxy,
        document_id: str,
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        try:
            return container.read_item(item=document_id, partition_key=partition_key)
        except Exception:
            return None
    
    def query_documents(
        self,
        container: ContainerProxy,
        query: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        enable_cross_partition: bool = True
    ) -> List[Dict[str, Any]]:
        """Execute custom query."""
        return list(container.query_items(
            query=query,
            parameters=parameters or [],
            enable_cross_partition_query=enable_cross_partition
        ))
    
    def delete_document(
        self,
        container: ContainerProxy,
        document_id: str,
        partition_key: str
    ) -> bool:
        """Delete document."""
        try:
            container.delete_item(item=document_id, partition_key=partition_key)
            return True
        except Exception:
            return False


def create_cosmos_utils(
    azure_openai_endpoint: str = None,
    azure_openai_key: str = None,
    embedding_deployment: str = None
) -> CosmosUtils:
    """Factory function to create CosmosUtils instance."""
    from openai import AzureOpenAI
    
    endpoint = azure_openai_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = azure_openai_key or os.getenv("AZURE_OPENAI_API_KEY")
    
    if not endpoint or not api_key:
        raise ValueError("Azure OpenAI endpoint and API key are required")
    
    embedding_client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-08-01-preview"
    )
    
    return CosmosUtils(
        embedding_client=embedding_client,
        embedding_deployment=embedding_deployment
    )
