"""
CosmosDB Utility Functions for Agent Memory Service.

This module provides common utilities for:
- Embedding generation
- Vector search operations
- Hybrid search (vector + full-text)
- Document upsert operations
"""

import os
from typing import List, Dict, Any, Optional
from openai import AzureOpenAI
from azure.cosmos import ContainerProxy
from dotenv import load_dotenv

load_dotenv()


class CosmosUtils:
    """Utility class for CosmosDB operations."""
    
    def __init__(self, embedding_client: AzureOpenAI, embedding_deployment: str = None):
        """
        Initialize CosmosDB utilities.
        
        Args:
            embedding_client: AzureOpenAI client for embeddings
            embedding_deployment: Deployment name for embeddings (default from .env)
        """
        self.embedding_client = embedding_client
        self.embedding_deployment = embedding_deployment or os.getenv(
            "AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002"
        )
        print("embedding model ", embedding_deployment)
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for given text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector (1536 dimensions)
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        response = self.embedding_client.embeddings.create(
            input=text,
            model=self.embedding_deployment
        )
        
        return response.data[0].embedding
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")
        
        # Filter out empty strings
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
        """
        Execute vector similarity search on a container.
        
        Args:
            container: CosmosDB container to search
            query_embedding: Query vector embedding
            vector_field: Name of the vector field to search (default: "content_vector")
            top_k: Number of results to return
            filters: Optional filters (e.g., {"user_id": "user123"})
            
        Returns:
            List of matching documents with similarity scores
        """
        # Build the query
        where_clause = ""
        if filters:
            conditions = [f"c.{key} = @{key}" for key in filters.keys()]
            where_clause = " WHERE " + " AND ".join(conditions)
        
        query = f"""
        SELECT TOP @top_k c.id, c.user_id, c.session_id, c.timestamp, c.content, 
               c.summary, c.metadata, c.insight_text, c.insight_type, c.category,
               VectorDistance(c.{vector_field}, @embedding) AS similarity_score
        FROM c
        {where_clause}
        ORDER BY VectorDistance(c.{vector_field}, @embedding)
        """
        
        # Build parameters
        parameters = [
            {"name": "@embedding", "value": query_embedding},
            {"name": "@top_k", "value": top_k}
        ]
        
        if filters:
            for key, value in filters.items():
                parameters.append({"name": f"@{key}", "value": value})
        
        # Execute query
        results = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        return results
    
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
        """
        Execute hybrid search combining vector similarity and full-text search using RRF.
        
        Uses Azure Cosmos DB's Reciprocal Rank Fusion (RRF) to combine vector search
        and full-text search results for improved relevance.
        
        Args:
            container: CosmosDB container to search
            query_text: Query text for full-text search
            query_embedding: Query vector embedding
            vector_field: Name of the vector field to search
            full_text_fields: Fields to search with full-text (default: ["content"])
            top_k: Number of results to return
            filters: Optional filters (e.g., {"user_id": "user123"})
            weights: Optional weights for RRF [vector_weight, fulltext_weight]
                    e.g., [2, 1] weights vector search 2x more than full-text
            
        Returns:
            List of matching documents with combined scores
        """
        if full_text_fields is None:
            full_text_fields = ["content"]
        
        # Convert embedding to literal array format for SQL
        embedding_literal = "[" + ",".join(str(x) for x in query_embedding) + "]"
        
        # Escape single quotes in query text for SQL safety
        safe_query_text = query_text.replace("'", "''")
        
        # Split query text into search terms for FullTextScore
        search_terms = [f'"{term}"' for term in safe_query_text.split() if term.strip()]
        search_terms_str = ", ".join(search_terms) if search_terms else f'"{safe_query_text}"'
        
        # Build WHERE clause for filters only
        where_clause = ""
        if filters:
            filter_conditions = [f"c.{key} = @{key}" for key in filters.keys()]
            where_clause = " WHERE " + " AND ".join(filter_conditions)
        
        # Build FullTextScore function call for the primary full-text field
        primary_field = full_text_fields[0]
        full_text_score = f"FullTextScore(c.{primary_field}, {search_terms_str})"
        
        # Build RRF function call
        rrf_args = f"VectorDistance(c.{vector_field}, {embedding_literal}), {full_text_score}"
        if weights:
            weights_str = "[" + ",".join(str(w) for w in weights) + "]"
            rrf_args += f", {weights_str}"
        
        # Build hybrid search query using ORDER BY RANK RRF
        query = f"""
        SELECT TOP {top_k} c.id, c.user_id, c.session_id, c.timestamp, c.content,
               c.summary, c.metadata, c.insight_text, c.insight_type, c.category,
               VectorDistance(c.{vector_field}, {embedding_literal}) AS vector_score
        FROM c
        {where_clause}
        ORDER BY RANK RRF({rrf_args})
        """
        
        # Build parameters (only for filters, not for embedding or text in this syntax)
        parameters = []
        if filters:
            for key, value in filters.items():
                parameters.append({"name": f"@{key}", "value": value})
        
        # Execute query
        results = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        return results
    
    def execute_full_text_search(
        self,
        container: ContainerProxy,
        query_text: str,
        full_text_fields: Optional[List[str]] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute full-text search only (no vector similarity).
        
        Args:
            container: CosmosDB container to search
            query_text: Query text for full-text search
            full_text_fields: Fields to search with full-text (default: ["content"])
            top_k: Number of results to return
            filters: Optional filters (e.g., {"user_id": "user123"})
            
        Returns:
            List of matching documents
        """
        if full_text_fields is None:
            full_text_fields = ["content"]
        
        # Build WHERE clause
        where_conditions = []
        if filters:
            where_conditions.extend([f"c.{key} = @{key}" for key in filters.keys()])
        
        # Add full-text search conditions
        full_text_conditions = " OR ".join(
            [f"CONTAINS(c.{field}, @query_text, true)" for field in full_text_fields]
        )
        where_conditions.append(f"({full_text_conditions})")
        
        where_clause = " WHERE " + " AND ".join(where_conditions)
        
        # Build query
        query = f"""
        SELECT TOP @top_k c.id, c.user_id, c.session_id, c.timestamp, c.content,
               c.summary, c.metadata, c.insight_text, c.insight_type, c.category,
               RANK FullTextScore(c.{full_text_fields[0]}) AS full_text_score
        FROM c
        {where_clause}
        ORDER BY RANK FullTextScore(c.{full_text_fields[0]})
        """
        
        # Build parameters
        parameters = [
            {"name": "@query_text", "value": query_text},
            {"name": "@top_k", "value": top_k}
        ]
        
        if filters:
            for key, value in filters.items():
                parameters.append({"name": f"@{key}", "value": value})
        
        # Execute query
        results = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        return results
    
    def upsert_document(
        self,
        container: ContainerProxy,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Insert or update a document in the container.
        
        Args:
            container: CosmosDB container
            document: Document to upsert (must include 'id' and partition key)
            
        Returns:
            The upserted document
        """
        if "id" not in document:
            raise ValueError("Document must have an 'id' field")
        
        result = container.upsert_item(body=document)
        return result
    
    def batch_upsert_documents(
        self,
        container: ContainerProxy,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Upsert multiple documents in batch.
        
        Args:
            container: CosmosDB container
            documents: List of documents to upsert
            
        Returns:
            List of upserted documents
        """
        if not documents:
            return []
        
        results = []
        for doc in documents:
            if "id" not in doc:
                raise ValueError(f"Document must have an 'id' field: {doc}")
            result = container.upsert_item(body=doc)
            results.append(result)
        
        return results
    
    def get_document_by_id(
        self,
        container: ContainerProxy,
        document_id: str,
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by ID and partition key.
        
        Args:
            container: CosmosDB container
            document_id: Document ID
            partition_key: Partition key value (e.g., user_id)
            
        Returns:
            Document if found, None otherwise
        """
        try:
            result = container.read_item(
                item=document_id,
                partition_key=partition_key
            )
            return result
        except Exception:
            return None
    
    def query_documents(
        self,
        container: ContainerProxy,
        query: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        enable_cross_partition: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute a custom SQL query on the container.
        
        Args:
            container: CosmosDB container
            query: SQL query string
            parameters: Query parameters
            enable_cross_partition: Whether to enable cross-partition query
            
        Returns:
            List of matching documents
        """
        results = list(container.query_items(
            query=query,
            parameters=parameters or [],
            enable_cross_partition_query=enable_cross_partition
        ))
        
        return results
    
    def delete_document(
        self,
        container: ContainerProxy,
        document_id: str,
        partition_key: str
    ) -> bool:
        """
        Delete a document by ID and partition key.
        
        Args:
            container: CosmosDB container
            document_id: Document ID
            partition_key: Partition key value
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            container.delete_item(
                item=document_id,
                partition_key=partition_key
            )
            return True
        except Exception:
            return False


def create_cosmos_utils(
    azure_openai_endpoint: str = None,
    azure_openai_key: str = None,
    embedding_deployment: str = None
) -> CosmosUtils:
    """
    Factory function to create CosmosUtils instance.
    
    Args:
        azure_openai_endpoint: Azure OpenAI endpoint (default from .env)
        azure_openai_key: Azure OpenAI API key (default from .env)
        embedding_deployment: Embedding deployment name (default from .env)
        
    Returns:
        CosmosUtils instance
    """
    endpoint = azure_openai_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = azure_openai_key or os.getenv("AZURE_OPENAI_API_KEY")
    
    if not endpoint or not api_key:
        raise ValueError("Azure OpenAI endpoint and API key are required")
    
    # Create embedding client
    embedding_client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-08-01-preview"  # Required for structured outputs
    )
    
    return CosmosUtils(
        embedding_client=embedding_client,
        embedding_deployment=embedding_deployment
    )
