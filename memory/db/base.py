"""
Abstract Base Class for Memory Database Backends.

This module defines the interface that all database backends must implement.
The abstraction enables switching between SQLite, CosmosDB, and PostgreSQL
without changing the memory service logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Import EmbeddingProvider from the unified providers module
from memory.providers.embedding import EmbeddingProvider


class ContainerType(Enum):
    """Types of containers/tables in the memory database."""
    INTERACTIONS = "interactions"
    INSIGHTS = "insights"
    SESSION_SUMMARIES = "session_summaries"


@dataclass
class SearchResult:
    """Unified search result across all backends."""
    id: str
    document: Dict[str, Any]
    score: float = 0.0
    score_type: str = "similarity"  # "similarity", "hybrid", "text"
    
    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access to document fields."""
        if key == "id":
            return self.id
        if key == "score":
            return self.score
        return self.document.get(key)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get method."""
        if key == "id":
            return self.id
        if key == "score":
            return self.score
        return self.document.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {"id": self.id, "score": self.score, **self.document}
        return result


@dataclass
class DatabaseCapabilities:
    """Describes what features a database backend supports."""
    supports_vector_search: bool = False
    supports_hybrid_search: bool = False
    supports_full_text_search: bool = False
    supports_transactions: bool = False
    vector_dimensions: int = 1536
    max_batch_size: int = 100
    
    # Backend-specific info
    backend_name: str = "unknown"
    backend_version: str = "0.0.0"


class MemoryDatabase(ABC):
    """
    Abstract base class for memory database backends.
    
    All database implementations (SQLite, CosmosDB, PostgreSQL) must
    implement this interface to work with the Agent Memory Service.
    """
    
    def __init__(self, embedding_provider: Optional[EmbeddingProvider] = None):
        """
        Initialize the database backend.
        
        Args:
            embedding_provider: Provider for generating embeddings.
                              If None, embeddings must be provided with documents.
        """
        self._embedding_provider = embedding_provider
    
    @property
    def embedding_provider(self) -> Optional[EmbeddingProvider]:
        """Get the embedding provider."""
        return self._embedding_provider
    
    @embedding_provider.setter
    def embedding_provider(self, provider: EmbeddingProvider) -> None:
        """Set the embedding provider."""
        self._embedding_provider = provider
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding using the configured provider.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
            
        Raises:
            ValueError: If no embedding provider is configured
        """
        if self._embedding_provider is None:
            raise ValueError("No embedding provider configured")
        return self._embedding_provider.get_embedding(text)
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if self._embedding_provider is None:
            raise ValueError("No embedding provider configured")
        return self._embedding_provider.get_embeddings_batch(texts)
    
    # ==================== Abstract Methods ====================
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the database, creating tables/containers if needed.
        
        This should be called once before using the database.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close database connections and cleanup resources.
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> DatabaseCapabilities:
        """
        Get the capabilities of this database backend.
        
        Returns:
            DatabaseCapabilities describing supported features
        """
        pass
    
    # ==================== Document Operations ====================
    
    @abstractmethod
    async def upsert(
        self,
        container: ContainerType,
        document: Dict[str, Any],
        partition_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Insert or update a document.
        
        Args:
            container: Which container/table to use
            document: Document data (must include 'id')
            partition_key: Partition key value (e.g., user_id)
            
        Returns:
            The upserted document
        """
        pass
    
    @abstractmethod
    async def batch_upsert(
        self,
        container: ContainerType,
        documents: List[Dict[str, Any]],
        partition_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Insert or update multiple documents.
        
        Args:
            container: Which container/table to use
            documents: List of documents (each must include 'id')
            partition_key: Partition key value
            
        Returns:
            List of upserted documents
        """
        pass
    
    @abstractmethod
    async def get_by_id(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by ID.
        
        Args:
            container: Which container/table to use
            document_id: Document ID
            partition_key: Partition key value
            
        Returns:
            Document if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def delete(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None
    ) -> bool:
        """
        Delete a document by ID.
        
        Args:
            container: Which container/table to use
            document_id: Document ID
            partition_key: Partition key value
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def query(
        self,
        container: ContainerType,
        filters: Dict[str, Any],
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query documents with filters.
        
        Args:
            container: Which container/table to use
            filters: Field-value pairs to filter by
            order_by: Field to order by (prefix with '-' for descending)
            limit: Maximum number of results
            
        Returns:
            List of matching documents
        """
        pass
    
    # ==================== Search Operations ====================
    
    @abstractmethod
    async def vector_search(
        self,
        container: ContainerType,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Perform vector similarity search.
        
        Args:
            container: Which container/table to search
            query_embedding: Query vector
            vector_field: Name of the vector field to search
            top_k: Number of results to return
            filters: Optional filters to apply
            
        Returns:
            List of SearchResult ordered by similarity
        """
        pass
    
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
        Perform hybrid search combining vector and text search.
        
        Default implementation falls back to vector search if
        hybrid search is not supported by the backend.
        
        Args:
            container: Which container/table to search
            query_text: Query text for text search
            query_embedding: Query vector for similarity search
            vector_field: Name of the vector field
            text_fields: Fields to search with text
            top_k: Number of results to return
            filters: Optional filters to apply
            
        Returns:
            List of SearchResult with combined scores
        """
        # Default: fallback to vector search
        return await self.vector_search(
            container=container,
            query_embedding=query_embedding,
            vector_field=vector_field,
            top_k=top_k,
            filters=filters
        )
    
    # ==================== Context Manager Support ====================
    
    async def __aenter__(self) -> "MemoryDatabase":
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
