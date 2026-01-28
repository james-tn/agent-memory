"""
SAM Ingestion Pipeline

Orchestrates the ingestion of conversation content into the SAM graph.
Connects WorkingMemory -> Episode -> Extraction -> Graph nodes.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from sam.config import SAMConfig
from sam.stores.base import MemoryStore
from sam.stores.factory import create_and_initialize_store
from sam.working_memory import WorkingMemory
from sam.llm_client import LLMClient
from sam.embeddings import EmbeddingsService
from sam.extractor import Extractor
from sam.models.graph import Episode


class IngestionPipeline:
    """
    SAM Ingestion Pipeline.
    
    Orchestrates the full flow:
    1. Receive conversation turns
    2. Buffer in WorkingMemory
    3. Flush to Episodes when buffer is full
    4. Extract entities/claims/relationships when Episode is closed
    5. Build graph with edges
    
    This is the main entry point for adding data to SAM.
    """
    
    def __init__(
        self,
        tenant_id: str,
        store: Optional[MemoryStore] = None,
        llm_client: Optional[LLMClient] = None,
        config: Optional[SAMConfig] = None,
        extract_on_close: bool = True,
        generate_embeddings: bool = True,
        domain: Optional[str] = None,
        extract_relationships: bool = True
    ):
        """
        Initialize the ingestion pipeline.
        
        Args:
            tenant_id: Tenant/user identifier
            store: MemoryStore instance (created from config if not provided)
            llm_client: LLM client (created from env if not provided)
            config: SAM configuration
            extract_on_close: Whether to run extraction when Episode is closed
            generate_embeddings: Whether to generate embeddings for nodes
            domain: Domain for domain-specific extraction (e.g., "healthcare")
            extract_relationships: Whether to extract entity-to-entity relationships
        """
        self.tenant_id = tenant_id
        self.config = config or SAMConfig()
        self.extract_on_close = extract_on_close
        self.generate_embeddings = generate_embeddings
        self.domain = domain
        self.extract_relationships = extract_relationships
        
        # Store (will be initialized async)
        self._store = store
        self._store_owned = store is None
        
        # LLM client
        self._llm_client = llm_client
        self._llm_client_owned = llm_client is None
        
        # Components (created on initialize)
        self._working_memory: Optional[WorkingMemory] = None
        self._embeddings: Optional[EmbeddingsService] = None
        self._extractor: Optional[Extractor] = None
        
        # State
        self._initialized = False
        self._closed_episodes: List[str] = []  # Episodes pending extraction
    
    async def initialize(self) -> None:
        """
        Initialize the pipeline.
        
        Must be called before using the pipeline.
        """
        if self._initialized:
            return
        
        # Create store if needed
        if self._store is None:
            self._store = await create_and_initialize_store(self.config)
            self._store_owned = True
        
        # Create LLM client if needed
        if self._llm_client is None:
            self._llm_client = LLMClient()
            self._llm_client_owned = True
        
        # Create embeddings service
        self._embeddings = EmbeddingsService(self._llm_client)
        
        # Create extractor with domain support
        self._extractor = Extractor(
            store=self._store,
            llm_client=self._llm_client,
            embeddings=self._embeddings,
            generate_embeddings=self.generate_embeddings,
            domain=self.domain
        )
        
        # Create working memory
        self._working_memory = WorkingMemory(
            store=self._store,
            tenant_id=self.tenant_id,
            config=self.config
        )
        await self._working_memory.initialize()
        
        self._initialized = True
        print(f"[IngestionPipeline] Initialized for tenant: {self.tenant_id}")
    
    def _ensure_initialized(self) -> None:
        """Ensure pipeline is initialized."""
        if not self._initialized:
            raise RuntimeError("Pipeline not initialized. Call initialize() first.")
    
    async def add_turn(
        self,
        role: str,
        content: str,
        auto_flush: bool = True
    ) -> Dict[str, Any]:
        """
        Add a conversation turn to the pipeline.
        
        Args:
            role: Turn role ("user" or "assistant")
            content: Turn content
            auto_flush: Whether to auto-flush when buffer is full
            
        Returns:
            Dict with turn info and any flush results
        """
        self._ensure_initialized()
        
        # Add to working memory
        self._working_memory.add_turn(role, content)
        
        result = {
            "turn_added": True,
            "buffer_size": len(self._working_memory.turn_buffer),
            "flush_result": None
        }
        
        # Check for auto-flush
        if auto_flush:
            flush_result = await self._working_memory.maybe_flush()
            if flush_result:
                result["flush_result"] = flush_result
                
                # Check if Episode was closed
                if flush_result.get("episode_closed"):
                    old_episode_id = flush_result.get("episode_id")
                    if old_episode_id:
                        self._closed_episodes.append(old_episode_id)
                        
                        # Extract if configured
                        if self.extract_on_close:
                            await self._extract_from_episode(old_episode_id)
        
        return result
    
    async def flush(self) -> Dict[str, Any]:
        """
        Manually flush the working memory buffer.
        
        Returns:
            Flush result dict
        """
        self._ensure_initialized()
        
        flush_result = await self._working_memory.flush()
        
        # Check if Episode was closed
        if flush_result.get("episode_closed"):
            old_episode_id = flush_result.get("episode_id")
            if old_episode_id and self.extract_on_close:
                await self._extract_from_episode(old_episode_id)
        
        return flush_result
    
    async def close_session(
        self,
        summary: Optional[str] = None,
        run_extraction: bool = True
    ) -> Dict[str, Any]:
        """
        Close the current session.
        
        Flushes all remaining turns and closes the current Episode.
        
        Args:
            summary: Optional summary override
            run_extraction: Whether to run extraction on the closed Episode
            
        Returns:
            Dict with close results and extraction results
        """
        self._ensure_initialized()
        
        result = {
            "close_result": None,
            "extraction_result": None
        }
        
        # Close working memory (flushes and closes Episode)
        close_result = await self._working_memory.close()
        result["close_result"] = close_result
        
        # Run extraction on closed Episode
        if run_extraction and close_result.get("episode_id"):
            extraction_result = await self._extract_from_episode(
                close_result["episode_id"]
            )
            result["extraction_result"] = extraction_result
        
        return result
    
    async def _extract_from_episode(self, episode_id: str) -> Dict[str, Any]:
        """Extract entities, claims, and relationships from an Episode."""
        episode = await self._store.get_episode(episode_id, self.tenant_id)
        
        if not episode:
            print(f"  ⚠ Episode {episode_id} not found")
            return {}
        
        return await self._extractor.extract_from_episode(
            episode,
            extract_relationships=self.extract_relationships
        )
    
    def get_active_context(self) -> str:
        """
        Get formatted active context from working memory.
        
        Returns:
            Formatted context string for LLM
        """
        self._ensure_initialized()
        return self._working_memory.get_full_context()
    
    def update_summary(self, summary: str) -> None:
        """
        Update the cumulative summary in working memory.
        
        Args:
            summary: New cumulative summary
        """
        self._ensure_initialized()
        self._working_memory.update_cumulative_summary(summary)
    
    async def get_current_episode(self) -> Optional[Episode]:
        """
        Get the current open Episode.
        
        Returns:
            Current Episode or None
        """
        self._ensure_initialized()
        episode_id = self._working_memory.current_episode_id
        if episode_id:
            return await self._store.get_episode(episode_id, self.tenant_id)
        return None
    
    @property
    def store(self) -> MemoryStore:
        """Get the memory store."""
        self._ensure_initialized()
        return self._store
    
    @property
    def extractor(self) -> Extractor:
        """Get the extractor."""
        self._ensure_initialized()
        return self._extractor
    
    @property
    def working_memory(self) -> WorkingMemory:
        """Get the working memory."""
        self._ensure_initialized()
        return self._working_memory
    
    async def close(self) -> None:
        """
        Close the pipeline and release resources.
        """
        if self._llm_client_owned and self._llm_client:
            self._llm_client.close()
        
        if self._store_owned and self._store:
            await self._store.close()
        
        self._initialized = False
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


async def create_pipeline(
    tenant_id: str,
    config: Optional[SAMConfig] = None,
    **kwargs
) -> IngestionPipeline:
    """
    Create and initialize an ingestion pipeline.
    
    Convenience function for quick setup.
    
    Args:
        tenant_id: Tenant/user identifier
        config: SAM configuration
        **kwargs: Additional arguments for IngestionPipeline
        
    Returns:
        Initialized IngestionPipeline
    """
    pipeline = IngestionPipeline(
        tenant_id=tenant_id,
        config=config,
        **kwargs
    )
    await pipeline.initialize()
    return pipeline
