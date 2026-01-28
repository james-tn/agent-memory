"""
SAM Embeddings Service

Handles embedding generation and caching for SAM nodes.
"""

from typing import List, Optional, Dict, Any
from sam.llm_client import LLMClient


class EmbeddingsService:
    """
    Embeddings service for SAM.
    
    Provides:
    - Single and batch embedding generation
    - Text preparation for embedding
    - Optional caching (future enhancement)
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        embedding_dimensions: int = 1536
    ):
        """
        Initialize embeddings service.
        
        Args:
            llm_client: LLM client for embedding generation
            embedding_dimensions: Expected embedding dimensions
        """
        self.llm_client = llm_client
        self.embedding_dimensions = embedding_dimensions
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        return self.llm_client.get_embedding(text)
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        return self.llm_client.get_embeddings_batch(texts)
    
    def prepare_entity_text(
        self, 
        name: str, 
        entity_type: str,
        aliases: Optional[List[str]] = None
    ) -> str:
        """
        Prepare entity text for embedding.
        
        Args:
            name: Entity name
            entity_type: Entity type
            aliases: Optional aliases
            
        Returns:
            Prepared text for embedding
        """
        parts = [f"{name} ({entity_type})"]
        if aliases:
            parts.append(f"Also known as: {', '.join(aliases)}")
        return " | ".join(parts)
    
    def prepare_claim_text(
        self,
        content: str,
        entity_names: Optional[List[str]] = None
    ) -> str:
        """
        Prepare claim text for embedding.
        
        Args:
            content: Claim content
            entity_names: Optional entity names this claim is about
            
        Returns:
            Prepared text for embedding
        """
        if entity_names:
            return f"About {', '.join(entity_names)}: {content}"
        return content
    
    def prepare_episode_text(
        self,
        raw_content: str,
        summary: Optional[str] = None,
        key_topics: Optional[List[str]] = None
    ) -> str:
        """
        Prepare episode text for embedding.
        
        Uses summary if available, otherwise uses raw content (truncated).
        
        Args:
            raw_content: Raw episode content
            summary: Optional summary
            key_topics: Optional key topics
            
        Returns:
            Prepared text for embedding
        """
        parts = []
        
        if summary:
            parts.append(summary)
        
        if key_topics:
            parts.append(f"Topics: {', '.join(key_topics)}")
        
        if parts:
            return " | ".join(parts)
        
        # Fall back to truncated raw content
        max_chars = 2000
        if len(raw_content) > max_chars:
            return raw_content[:max_chars] + "..."
        return raw_content
    
    def embed_entity(
        self,
        name: str,
        entity_type: str,
        aliases: Optional[List[str]] = None
    ) -> List[float]:
        """
        Generate embedding for an entity.
        
        Args:
            name: Entity name
            entity_type: Entity type
            aliases: Optional aliases
            
        Returns:
            Embedding vector
        """
        text = self.prepare_entity_text(name, entity_type, aliases)
        return self.embed_text(text)
    
    def embed_claim(
        self,
        content: str,
        entity_names: Optional[List[str]] = None
    ) -> List[float]:
        """
        Generate embedding for a claim.
        
        Args:
            content: Claim content
            entity_names: Optional entity names
            
        Returns:
            Embedding vector
        """
        text = self.prepare_claim_text(content, entity_names)
        return self.embed_text(text)
    
    def embed_episode(
        self,
        raw_content: str,
        summary: Optional[str] = None,
        key_topics: Optional[List[str]] = None
    ) -> List[float]:
        """
        Generate embedding for an episode.
        
        Args:
            raw_content: Raw episode content
            summary: Optional summary
            key_topics: Optional key topics
            
        Returns:
            Embedding vector
        """
        text = self.prepare_episode_text(raw_content, summary, key_topics)
        return self.embed_text(text)
