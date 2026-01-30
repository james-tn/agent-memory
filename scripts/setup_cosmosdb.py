#!/usr/bin/env python3
"""
Setup script for Agent Memory CosmosDB containers.

This script creates the required database and containers with proper 
vector embedding policies for the Agent Memory service.

Usage:
    python scripts/setup_cosmosdb.py

Environment variables:
    COSMOS_ENDPOINT: CosmosDB account endpoint
    COSMOS_DATABASE_NAME: Database name (default: agent_memory_db)
"""

import asyncio
import os
import sys

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def get_cosmos_client() -> CosmosClient:
    """Create CosmosDB client with Azure AD authentication."""
    endpoint = os.getenv("COSMOS_ENDPOINT") or os.getenv("AZURE_COSMOS_ENDPOINT")
    if not endpoint:
        print("❌ Error: COSMOS_ENDPOINT environment variable not set")
        sys.exit(1)
    
    print(f"   Endpoint: {endpoint}")
    
    # Try connection string first, then Azure AD
    conn_str = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("AZURE_COSMOS_CONNECTION_STRING")
    if conn_str:
        print("   Using connection string authentication")
        return CosmosClient.from_connection_string(conn_str)
    
    print("   Using Azure AD authentication")
    credential = DefaultAzureCredential()
    return CosmosClient(endpoint, credential=credential)


def setup_database():
    """Set up the Agent Memory database and containers."""
    print("=" * 60)
    print("Agent Memory Service - CosmosDB Setup")
    print("=" * 60)
    print()
    
    # Configuration
    database_name = os.getenv("COSMOS_DATABASE_NAME", "agent_memory_db")
    
    print(f"1. Connecting to CosmosDB...")
    client = get_cosmos_client()
    print("   ✓ Connected successfully")
    print()
    
    print(f"2. Creating database: {database_name}")
    try:
        database = client.create_database_if_not_exists(database_name)
        print(f"   ✓ Database '{database_name}' ready")
    except Exception as e:
        print(f"   ❌ Failed to create database: {e}")
        sys.exit(1)
    print()
    
    print("3. Creating containers with vector policies...")
    print()
    
    # Container definitions with vector policies
    containers = [
        {
            "name": "interactions",
            "partition_key": "/user_id",
            "vector_embeddings": [
                {
                    "path": "/content_vector",
                    "dataType": "float32",
                    "distanceFunction": "cosine",
                    "dimensions": 1536
                },
                {
                    "path": "/summary_vector",
                    "dataType": "float32",
                    "distanceFunction": "cosine",
                    "dimensions": 1536
                }
            ],
            "vector_indexes": [
                {"path": "/content_vector", "type": "diskANN"},
                {"path": "/summary_vector", "type": "quantizedFlat"}
            ],
            "excluded_paths": [
                {"path": "/content_vector/*"},
                {"path": "/summary_vector/*"},
                {"path": "/_etag/?"}
            ]
        },
        {
            "name": "session_summaries",
            "partition_key": "/user_id",
            "vector_embeddings": [
                {
                    "path": "/summary_vector",
                    "dataType": "float32",
                    "distanceFunction": "cosine",
                    "dimensions": 1536
                }
            ],
            "vector_indexes": [
                {"path": "/summary_vector", "type": "diskANN"}
            ],
            "excluded_paths": [
                {"path": "/summary_vector/*"},
                {"path": "/_etag/?"}
            ]
        },
        {
            "name": "insights",
            "partition_key": "/user_id",
            "vector_embeddings": [
                {
                    "path": "/insight_vector",
                    "dataType": "float32",
                    "distanceFunction": "cosine",
                    "dimensions": 1536
                }
            ],
            "vector_indexes": [
                {"path": "/insight_vector", "type": "diskANN"}
            ],
            "excluded_paths": [
                {"path": "/insight_vector/*"},
                {"path": "/_etag/?"}
            ]
        }
    ]
    
    for container_def in containers:
        name = container_def["name"]
        print(f"   Creating container: {name}")
        
        # Delete existing container if it exists
        try:
            container = database.get_container_client(name)
            container.read()
            database.delete_container(name)
            print(f"      - Dropped existing container (no vector policy)")
        except Exception:
            pass  # Container doesn't exist
        
        # Build indexing policy
        indexing_policy = {
            "indexingMode": "consistent",
            "automatic": True,
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": container_def["excluded_paths"],
            "vectorIndexes": container_def["vector_indexes"]
        }
        
        # Build vector embedding policy
        vector_embedding_policy = {
            "vectorEmbeddings": container_def["vector_embeddings"]
        }
        
        # Create container with vector policies
        try:
            database.create_container(
                id=name,
                partition_key={"paths": [container_def["partition_key"]], "kind": "Hash"},
                indexing_policy=indexing_policy,
                vector_embedding_policy=vector_embedding_policy
            )
            print(f"   ✓ Container '{name}' created with:")
            print(f"      - {len(container_def['vector_embeddings'])} vector embedding(s)")
            print(f"      - Partition key: {container_def['partition_key']}")
        except CosmosResourceExistsError:
            print(f"   ⚠ Container '{name}' already exists")
        except Exception as e:
            print(f"   ❌ Failed to create container: {e}")
            sys.exit(1)
        print()
    
    print("=" * 60)
    print("✓ Setup completed successfully!")
    print("=" * 60)
    print()
    print(f"Database: {database_name}")
    print("Containers:")
    for c in containers:
        print(f"  - {c['name']}")
    print()
    print("You can now run the CosmosDB demo:")
    print("  uv run python demos/03_financial_advisor_cosmosdb.py")


if __name__ == "__main__":
    setup_database()
