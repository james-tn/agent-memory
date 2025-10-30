"""
Server Configuration for Memory Service.

Loads settings from environment variables with sensible defaults.
Uses Pydantic for validation and type safety.
"""

from pydantic_settings import BaseSettings
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
    
    # Azure OpenAI Settings (use existing .env variable names)
    azure_openai_endpoint_v1: str
    azure_openai_endpoint: str

    azure_openai_api_key: str
    azure_openai_chat_deployment_name: str  # Main deployment for chat
    azure_openai_api_version: str 
    
    # Azure Cosmos DB Settings (use existing .env variable names)
    cosmosdb_endpoint: str
    cosmos_key: Optional[str] = None  # If not provided, will use AAD authentication
    cosmos_db_name: str = "cosmosvector"
    cosmos_interactions_container: str = "interactions"
    cosmos_summaries_container: str = "session_summaries"
    cosmos_insights_container: str = "insights"
    
    # AAD Settings (for CosmosDB authentication if cosmos_key not provided)
    aad_client_id: Optional[str] = None
    aad_client_secret: Optional[str] = None
    aad_tenant_id: Optional[str] = None
    
    # Azure OpenAI Embeddings (use existing .env variable names)
    azure_openai_emb_deployment: str
    
    # Memory Service Settings
    K_TURN_BUFFER: int = 5
    L_TURN_CHUNKS: int = 10
    M_SESSIONS_RECENT: int = 5
    reflection_threshold_turns: int = 15
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env


# Singleton config instance
_config: Optional[ServerConfig] = None


def get_config() -> ServerConfig:
    """Get or create server configuration singleton."""
    global _config
    if _config is None:
        _config = ServerConfig()
    return _config
