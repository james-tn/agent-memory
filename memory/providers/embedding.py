"""
Unified Embedding Providers for Agent Memory Service.

This module provides a single source for embedding generation,
used across all database backends.
"""

from typing import List, Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    Protocol for embedding providers.
    
    Any class implementing get_embedding() and get_embeddings_batch()
    can be used as an embedding provider.
    """
    
    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        ...
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        ...


class OpenAIEmbeddingProvider:
    """
    Embedding provider using Azure OpenAI or OpenAI API.
    
    Supports both legacy models (text-embedding-ada-002) and newer models
    with configurable dimensions (text-embedding-3-large, text-embedding-3-small).
    
    Examples:
        # Azure OpenAI
        from openai import AzureOpenAI
        client = AzureOpenAI(...)
        provider = OpenAIEmbeddingProvider(
            client,
            model="text-embedding-3-large",
            dimensions=1536
        )
        
        # OpenAI
        from openai import OpenAI
        client = OpenAI(api_key="...")
        provider = OpenAIEmbeddingProvider(client, model="text-embedding-3-small")
    """
    
    # Models that support the dimensions parameter
    MODELS_WITH_DIMENSIONS = ["text-embedding-3-large", "text-embedding-3-small"]
    
    def __init__(
        self,
        openai_client,
        model: str = "text-embedding-3-large",
        dimensions: int = 1536
    ):
        """
        Initialize OpenAI embedding provider.
        
        Args:
            openai_client: OpenAI or AzureOpenAI client instance
            model: Embedding model deployment name
            dimensions: Vector dimensions (only for text-embedding-3-* models)
        """
        self.client = openai_client
        self.model = model
        self.dimensions = dimensions
        # Only use dimensions parameter for models that support it
        self._supports_dimensions = model in self.MODELS_WITH_DIMENSIONS
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        kwargs = {
            "input": text,
            "model": self.model,
        }
        if self._supports_dimensions:
            kwargs["dimensions"] = self.dimensions
        
        response = self.client.embeddings.create(**kwargs)
        return response.data[0].embedding
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a single API call.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        kwargs = {
            "input": texts,
            "model": self.model,
        }
        if self._supports_dimensions:
            kwargs["dimensions"] = self.dimensions
        
        response = self.client.embeddings.create(**kwargs)
        return [item.embedding for item in response.data]
