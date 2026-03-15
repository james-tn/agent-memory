"""
Server Configuration for Memory Service.

Loads settings from environment variables with sensible defaults.
Uses Pydantic for validation and type safety.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class ServerConfig(BaseSettings):
    """
    FastAPI Memory Service Configuration.
    
    All settings can be overridden via environment variables.
    """
    
    # Server Settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False  # Enable auto-reload in development
    
    # Session Pool Settings
    max_sessions: int = 1000
    session_ttl_minutes: int = 30
    eviction_interval_seconds: int = 60  # How often to check for stale sessions

    # Optional auth gate for production deployments
    auth_enabled: bool = False
    auth_api_key: Optional[str] = None
    auth_header_name: str = "x-api-key"
    
    # Azure OpenAI Settings (use existing .env variable names)
    azure_openai_endpoint_v1: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None

    azure_openai_api_key: Optional[str] = None
    azure_openai_reasoning_model: Optional[str] = None  # Main deployment for chat
    azure_openai_api_version: Optional[str] = None
    azure_openai_processing_model: Optional[str] = None
    azure_openai_emb_deployment: Optional[str] = None

    # Azure Cosmos DB Settings (use existing .env variable names)
    COSMOS_ENDPOINT: Optional[str] = None
    cosmos_connection_string: Optional[str] = None
    azure_cosmos_connection_string: Optional[str] = None
    cosmos_key: Optional[str] = None  # If not provided, will use AAD authentication
    cosmos_db_name: str = "agent_memory_db"
    cosmos_interactions_container: str = "interactions"
    cosmos_summaries_container: str = "session_summaries"
    cosmos_insights_container: str = "insights"

    # Azure AI Search Settings
    azure_ai_search_endpoint: Optional[str] = None
    azure_ai_search_api_key: Optional[str] = None
    azure_ai_search_index_prefix: str = "agent-memory"

    # PostgreSQL Settings
    postgres_connection_string: Optional[str] = None
    
    # AAD Settings (for CosmosDB authentication if cosmos_key not provided)
    aad_client_id: Optional[str] = None
    aad_client_secret: Optional[str] = None
    aad_tenant_id: Optional[str] = None
    
    # Azure OpenAI Embeddings (use existing .env variable names)
    agent_memory_db_type: str = "sqlite"
    agent_memory_db_path: str = "agent_memory_server.db"
    
    # Memory Service Settings
    K_TURN_BUFFER: int = 5
    L_TURN_CHUNKS: int = 10
    M_SESSIONS_RECENT: int = 2
    reflection_threshold_turns: int = 15
    longterm_synthesis_frequency: int = 2  # Synthesize long-term insights every N sessions
    
    # Logging
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton config instance
_config: Optional[ServerConfig] = None


def get_config() -> ServerConfig:
    """Get or create server configuration singleton."""
    global _config
    if _config is None:
        _config = ServerConfig()
    return _config
