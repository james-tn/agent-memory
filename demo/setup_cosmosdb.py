"""
CosmosDB Setup Script for Agent Memory Service.

This script creates the database and containers with proper indexing policies
for vector search and full-text search.
"""

import os
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import ClientSecretCredential
from openai import AzureOpenAI, OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_cosmos_client() -> CosmosClient:
    """Create and return CosmosDB client using service principal authentication."""
    cosmos_uri = os.getenv("COSMOSDB_ENDPOINT")
    aad_client_id = os.getenv("AAD_CLIENT_ID")
    aad_client_secret = os.getenv("AAD_CLIENT_SECRET")
    aad_tenant_id = os.getenv("AAD_TENANT_ID")
    
    if not all([cosmos_uri, aad_client_id, aad_client_secret, aad_tenant_id]):
        raise ValueError("Missing required environment variables for CosmosDB authentication")
    
    credential = ClientSecretCredential(
        tenant_id=aad_tenant_id,
        client_id=aad_client_id,
        client_secret=aad_client_secret
    )
    
    return CosmosClient(cosmos_uri, credential=credential)


def get_openai_client() -> OpenAI:
    """Create and return Azure OpenAI client."""
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")+"/openai/v1/"
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    # Use 2024-08-01-preview or later for structured outputs support
    
    if not all([azure_endpoint, api_key]):
        raise ValueError("Missing required environment variables for Azure OpenAI")
    
    return OpenAI(
        base_url =azure_endpoint,
        api_key=api_key,
    )


def create_database(client: CosmosClient, db_name: str) -> None:
    """Create database if it doesn't exist."""
    try:
        database = client.create_database_if_not_exists(id=db_name)
        print(f"✓ Database '{db_name}' ready")
        return database
    except exceptions.CosmosHttpResponseError as e:
        print(f"✗ Error creating database: {e}")
        raise


def create_interactions_container(database, container_name: str):
    """
    Create interactions container with:
    - 2 vector embeddings (content_vector, summary_vector)
    - Full-text indexing on content, mentioned_topics, entities
    """
    print(f"\nCreating container: {container_name}")
    
    # Check if container exists and drop it
    try:
        container = database.get_container_client(container_name)
        database.delete_container(container_name)
        print(f"  - Dropped existing container")
    except exceptions.CosmosResourceNotFoundError:
        print(f"  - Container doesn't exist, creating new")
    
    # Vector embedding policy
    vector_embedding_policy = {
        "vectorEmbeddings": [
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
        ]
    }
    
    # Indexing policy (only 1 diskANN allowed, use quantizedFlat for second vector)
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [
            {"path": "/_etag/?"},
            {"path": "/content_vector/*"},
            {"path": "/summary_vector/*"}
        ],
        "vectorIndexes": [
            {"path": "/content_vector", "type": "diskANN"},
            {"path": "/summary_vector", "type": "quantizedFlat"}
        ]
    }
    
    # Full-text policy
    full_text_policy = {
        "defaultLanguage": "en-US",
        "fullTextPaths": [
            {"path": "/content", "language": "en-US"},
            {"path": "/metadata/mentioned_topics", "language": "en-US"},
            {"path": "/metadata/entities", "language": "en-US"}
        ]
    }
    
    # Create container
    container = database.create_container(
        id=container_name,
        partition_key=PartitionKey(path="/user_id"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy,
        full_text_policy=full_text_policy
    )
    
    print(f"✓ Container '{container_name}' created with:")
    print(f"  - 2 vector embeddings (content_vector, summary_vector)")
    print(f"  - Full-text indexing on 3 fields")
    print(f"  - Partition key: /user_id")


def create_insights_container(database, container_name: str):
    """
    Create insights container with:
    - 1 vector embedding (insight_vector)
    - Partition key: user_id
    """
    print(f"\nCreating container: {container_name}")
    
    # Check if container exists and drop it
    try:
        container = database.get_container_client(container_name)
        database.delete_container(container_name)
        print(f"  - Dropped existing container")
    except exceptions.CosmosResourceNotFoundError:
        print(f"  - Container doesn't exist, creating new")
    
    # Vector embedding policy
    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/insight_vector",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": 1536
            }
        ]
    }
    
    # Indexing policy
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [
            {"path": "/_etag/?"},
            {"path": "/insight_vector/*"}
        ],
        "vectorIndexes": [
            {"path": "/insight_vector", "type": "diskANN"}
        ]
    }
    
    # Create container
    container = database.create_container(
        id=container_name,
        partition_key=PartitionKey(path="/user_id"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy
    )
    
    print(f"✓ Container '{container_name}' created with:")
    print(f"  - 1 vector embedding (insight_vector)")
    print(f"  - Partition key: /user_id")


def create_session_summaries_container(database, container_name: str):
    """
    Create session summaries container with:
    - 1 vector embedding (summary_vector)
    - Partition key: user_id
    """
    print(f"\nCreating container: {container_name}")
    
    # Check if container exists and drop it
    try:
        container = database.get_container_client(container_name)
        database.delete_container(container_name)
        print(f"  - Dropped existing container")
    except exceptions.CosmosResourceNotFoundError:
        print(f"  - Container doesn't exist, creating new")
    
    # Vector embedding policy
    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/summary_vector",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": 1536
            }
        ]
    }
    
    # Indexing policy
    indexing_policy = {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [
            {"path": "/_etag/?"},
            {"path": "/summary_vector/*"}
        ],
        "vectorIndexes": [
            {"path": "/summary_vector", "type": "diskANN"}
        ]
    }
    
    # Create container
    container = database.create_container(
        id=container_name,
        partition_key=PartitionKey(path="/user_id"),
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy
    )
    
    print(f"✓ Container '{container_name}' created with:")
    print(f"  - 1 vector embedding (summary_vector)")
    print(f"  - Partition key: /user_id")


def main():
    """Main setup function."""
    print("=" * 60)
    print("Agent Memory Service - CosmosDB Setup")
    print("=" * 60)
    
    # Configuration - use database from .env if available
    DB_NAME = os.getenv("COSMOS_DB_NAME", "financial_advisor_memory")
    INTERACTIONS_CONTAINER = "interactions"
    INSIGHTS_CONTAINER = "insights"
    SUMMARIES_CONTAINER = "session_summaries"
    
    try:
        # Create client
        print("\n1. Connecting to CosmosDB...")
        client = get_cosmos_client()
        print("✓ Connected successfully")
        
        # Create database
        print(f"\n2. Creating database: {DB_NAME}")
        database = create_database(client, DB_NAME)
        
        # Create containers
        print("\n3. Creating containers...")
        create_interactions_container(database, INTERACTIONS_CONTAINER)
        create_insights_container(database, INSIGHTS_CONTAINER)
        create_session_summaries_container(database, SUMMARIES_CONTAINER)
        
        print("\n" + "=" * 60)
        print("✓ Setup completed successfully!")
        print("=" * 60)
        print(f"\nDatabase: {DB_NAME}")
        print(f"Containers:")
        print(f"  - {INTERACTIONS_CONTAINER}")
        print(f"  - {INSIGHTS_CONTAINER}")
        print(f"  - {SUMMARIES_CONTAINER}")
        
    except Exception as e:
        print(f"\n✗ Setup failed: {e}")
        raise


if __name__ == "__main__":
    main()
