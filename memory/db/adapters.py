"""
Database Adapter for Agent Memory Service.

This module provides adapters that bridge the new abstract database interface
with the existing component interfaces (orchestrator, memory keeper, etc.).

The adapters allow gradual migration from CosmosDB-specific code to the
new database-agnostic interface.
"""

from typing import Any, Dict, List, Optional

from memory.db.base import ContainerType, MemoryDatabase, SearchResult


class ContainerAdapter:
    """
    Adapter that provides a ContainerProxy-like interface using MemoryDatabase.
    
    This allows existing components that expect ContainerProxy to work with
    the new abstract database interface.
    """
    
    def __init__(
        self,
        database: MemoryDatabase,
        container_type: ContainerType
    ):
        """
        Initialize container adapter.
        
        Args:
            database: The abstract database instance
            container_type: Which container this adapter represents
        """
        self._db = database
        self._container_type = container_type
    
    def upsert_item(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous upsert for compatibility."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._db.upsert(self._container_type, body)
        )
    
    async def upsert_item_async(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Async upsert."""
        return await self._db.upsert(self._container_type, body)
    
    def read_item(
        self,
        item: str,
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """Synchronous read for compatibility."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._db.get_by_id(self._container_type, item, partition_key)
        )
    
    async def read_item_async(
        self,
        item: str,
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """Async read."""
        return await self._db.get_by_id(self._container_type, item, partition_key)
    
    def delete_item(self, item: str, partition_key: str) -> bool:
        """Synchronous delete for compatibility."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._db.delete(self._container_type, item, partition_key)
        )
    
    async def delete_item_async(self, item: str, partition_key: str) -> bool:
        """Async delete."""
        return await self._db.delete(self._container_type, item, partition_key)
    
    def query_items(
        self,
        query: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        enable_cross_partition_query: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute a query - converts SQL-like query to filter-based query.
        
        Note: This is a simplified implementation that handles common patterns.
        Complex queries may need to be refactored to use the database interface directly.
        """
        import asyncio
        import re
        
        # Extract filters from simple queries
        filters = {}
        if parameters:
            for param in parameters:
                name = param.get("name", "").lstrip("@")
                value = param.get("value")
                if name and value is not None:
                    filters[name] = value
        
        # Extract limit from TOP clause
        limit = None
        top_match = re.search(r'TOP\s+(\d+)', query, re.IGNORECASE)
        if top_match:
            limit = int(top_match.group(1))
        
        # Extract order by
        order_by = None
        order_match = re.search(r'ORDER BY\s+c\.(\w+)(\s+DESC)?', query, re.IGNORECASE)
        if order_match:
            field = order_match.group(1)
            if order_match.group(2):
                order_by = f"-{field}"
            else:
                order_by = field
        
        return asyncio.get_event_loop().run_until_complete(
            self._db.query(self._container_type, filters, order_by, limit)
        )
    
    async def query_items_async(
        self,
        filters: Dict[str, Any],
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Async query using the native interface."""
        return await self._db.query(self._container_type, filters, order_by, limit)


class CosmosUtilsAdapter:
    """
    Adapter that provides a CosmosUtils-like interface using MemoryDatabase.
    
    This allows existing components that use CosmosUtils methods to work
    with the new abstract database interface.
    """
    
    def __init__(self, database: MemoryDatabase):
        """
        Initialize CosmosUtils adapter.
        
        Args:
            database: The abstract database instance
        """
        self._db = database
    
    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding using the database's embedding provider."""
        return self._db.get_embedding(text)
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return self._db.get_embeddings_batch(texts)
    
    def execute_vector_search(
        self,
        container: "ContainerAdapter",
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute vector search."""
        import asyncio
        
        results = asyncio.get_event_loop().run_until_complete(
            self._db.vector_search(
                container._container_type,
                query_embedding,
                vector_field,
                top_k,
                filters
            )
        )
        
        # Convert SearchResult to dict
        return [r.to_dict() for r in results]
    
    async def execute_vector_search_async(
        self,
        container_type: ContainerType,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Execute vector search asynchronously."""
        return await self._db.vector_search(
            container_type,
            query_embedding,
            vector_field,
            top_k,
            filters
        )
    
    def execute_hybrid_search(
        self,
        container: "ContainerAdapter",
        query_text: str,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        full_text_fields: Optional[List[str]] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        weights: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        """Execute hybrid search - falls back to vector search if not supported."""
        import asyncio
        
        caps = self._db.get_capabilities()
        
        if caps.supports_hybrid_search:
            results = asyncio.get_event_loop().run_until_complete(
                self._db.hybrid_search(
                    container._container_type,
                    query_text,
                    query_embedding,
                    vector_field,
                    full_text_fields,
                    top_k,
                    filters
                )
            )
        else:
            # Fallback to vector search
            results = asyncio.get_event_loop().run_until_complete(
                self._db.vector_search(
                    container._container_type,
                    query_embedding,
                    vector_field,
                    top_k,
                    filters
                )
            )
        
        return [r.to_dict() for r in results]
    
    async def execute_hybrid_search_async(
        self,
        container_type: ContainerType,
        query_text: str,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        text_fields: Optional[List[str]] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Execute hybrid search asynchronously."""
        caps = self._db.get_capabilities()
        
        if caps.supports_hybrid_search:
            return await self._db.hybrid_search(
                container_type,
                query_text,
                query_embedding,
                vector_field,
                text_fields,
                top_k,
                filters
            )
        else:
            return await self._db.vector_search(
                container_type,
                query_embedding,
                vector_field,
                top_k,
                filters
            )
    
    def upsert_document(
        self,
        container: "ContainerAdapter",
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upsert a document."""
        return container.upsert_item(document)
    
    def batch_upsert_documents(
        self,
        container: "ContainerAdapter",
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Upsert multiple documents."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._db.batch_upsert(container._container_type, documents)
        )
    
    def get_document_by_id(
        self,
        container: "ContainerAdapter",
        document_id: str,
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        return container.read_item(document_id, partition_key)
    
    def query_documents(
        self,
        container: "ContainerAdapter",
        query: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        enable_cross_partition: bool = True
    ) -> List[Dict[str, Any]]:
        """Query documents."""
        return container.query_items(query, parameters, enable_cross_partition)
    
    def delete_document(
        self,
        container: "ContainerAdapter",
        document_id: str,
        partition_key: str
    ) -> bool:
        """Delete a document."""
        return container.delete_item(document_id, partition_key)


class DatabaseBundle:
    """
    A bundle that provides all adapters needed by the memory service.
    
    Use this to create the necessary components for the orchestrator
    when using the abstract database interface.
    """
    
    def __init__(self, database: MemoryDatabase):
        """
        Initialize database bundle with adapters.
        
        Args:
            database: The abstract database instance
        """
        self.database = database
        
        # Create container adapters
        self.interactions_container = ContainerAdapter(
            database, ContainerType.INTERACTIONS
        )
        self.summaries_container = ContainerAdapter(
            database, ContainerType.SESSION_SUMMARIES
        )
        self.insights_container = ContainerAdapter(
            database, ContainerType.INSIGHTS
        )
        
        # Create utils adapter
        self.cosmos_utils = CosmosUtilsAdapter(database)
    
    async def initialize(self) -> None:
        """Initialize the underlying database."""
        await self.database.initialize()
    
    async def close(self) -> None:
        """Close the underlying database."""
        await self.database.close()
    
    async def __aenter__(self) -> "DatabaseBundle":
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
