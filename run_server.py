"""
Run Memory Service Server.

This script starts the FastAPI memory service with uvicorn.
Configure via environment variables or .env file.
"""

import uvicorn
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from server.config import get_config


if __name__ == "__main__":
    config = get_config()
    
    print("=" * 60)
    print("🚀 Starting Agent Memory Service")
    print("=" * 60)
    print(f"Host: {config.host}:{config.port}")
    print(f"Session Pool: max={config.max_sessions}, ttl={config.session_ttl_minutes}min")
    print(f"cosmos_db_name: {config.cosmos_db_name}")
    print(f"azure_openai_reasoning_model: {config.azure_openai_reasoning_model}")
    print("=" * 60)
    
    uvicorn.run(
        "server.main:app",
        host=config.host,
        port=config.port,
        reload=config.reload,
        log_level=config.log_level.lower()
    )
