"""
SAM Retrieval Demo

Demonstrates the spreading activation retrieval algorithm:
1. Ingests sample conversations about a user
2. Retrieves relevant context via spreading activation
3. Shows how the algorithm traverses the graph
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from sam import (
    SAMConfig,
    create_store,
    IngestionPipeline,
    create_pipeline,
    SpreadingActivationRetriever,
    LLMClient,
    EmbeddingsService,
    NodeType
)

# Load environment variables
load_dotenv()


async def main():
    """Run the retrieval demo."""
    print("=" * 60)
    print("SAM Spreading Activation Retrieval Demo")
    print("=" * 60)
    
    # Check for Azure OpenAI credentials
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    processing_model = os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4")
    embeddings_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    
    if not endpoint or not api_key:
        print("\n⚠️  Azure OpenAI credentials not found in .env")
        print("   Demo will use mock embeddings instead")
        use_embeddings = False
    else:
        use_embeddings = True
        print(f"\n✓ Using Azure OpenAI at {endpoint}")
    
    # Create configuration
    config = SAMConfig(
        storage_engine="sqlite",
        database_url=":memory:",  # In-memory for demo
        azure_openai_endpoint=endpoint,
        azure_openai_api_key=api_key,
        azure_openai_processing_model=processing_model,
        azure_openai_embeddings_model=embeddings_model,
        activation_decay=0.7,
        max_activation_depth=3,
        activation_threshold=0.1
    )
    
    # Create store
    store = create_store(config)
    await store.initialize()
    
    tenant_id = "demo-tenant"
    
    # Create LLM client and embeddings service if available
    llm_client = None
    embeddings = None
    if use_embeddings:
        llm_client = LLMClient(
            api_key=api_key,
            endpoint=endpoint,
            processing_model=processing_model,
            embedding_model=embeddings_model
        )
        embeddings = EmbeddingsService(llm_client)
    
    print("\n" + "-" * 60)
    print("Phase 1: Ingesting Sample Conversations")
    print("-" * 60)
    
    # Create ingestion pipeline - pass the store so data persists
    pipeline = await create_pipeline(
        config=config,
        tenant_id=tenant_id,
        llm_client=llm_client,
        store=store
    )
    
    # Sample conversations about Alice
    conversations = [
        [
            {"role": "user", "content": "My name is Alice Chen and I'm a senior ML engineer at TechCorp."},
            {"role": "assistant", "content": "Nice to meet you Alice! As a senior ML engineer at TechCorp, what areas of machine learning do you focus on?"},
            {"role": "user", "content": "I primarily work on computer vision projects, especially object detection using PyTorch."},
            {"role": "assistant", "content": "That's great! PyTorch is excellent for computer vision research. What frameworks do you use for deployment?"}
        ],
        [
            {"role": "user", "content": "I'm Alice. We've been discussing moving our models to TensorFlow for production."},
            {"role": "assistant", "content": "Hi Alice! That's a common consideration. TensorFlow does offer strong production tooling."},
            {"role": "user", "content": "Yes, and we're also looking at ONNX for model portability between frameworks."},
            {"role": "assistant", "content": "ONNX is a great choice for framework interoperability. It works well with both PyTorch and TensorFlow."}
        ],
        [
            {"role": "user", "content": "Alice here again. I'm leading a new project on autonomous vehicle perception."},
            {"role": "assistant", "content": "Exciting! Autonomous vehicle perception is cutting-edge work. What sensors are you using?"},
            {"role": "user", "content": "We're using LiDAR and camera fusion for 3D object detection."},
            {"role": "assistant", "content": "LiDAR-camera fusion is the industry standard. Are you using any particular fusion architecture?"},
            {"role": "user", "content": "We're implementing a late fusion approach based on recent papers from Waymo."},
            {"role": "assistant", "content": "Waymo's research on late fusion has been influential. Great choice for your architecture!"}
        ]
    ]
    
    # Ingest each conversation
    for i, conv in enumerate(conversations, 1):
        print(f"\nIngesting conversation {i}/{len(conversations)}...")
        for turn in conv:
            await pipeline.add_turn(turn["role"], turn["content"])
        
        # Close session to finalize episode
        await pipeline.close_session()
        
        # Start new session for next conversation (reuse the same store)
        pipeline = await create_pipeline(
            config=config,
            tenant_id=tenant_id,
            llm_client=llm_client,
            store=store
        )
    
    print("\n✓ All conversations ingested")
    
    # Now demonstrate retrieval
    print("\n" + "-" * 60)
    print("Phase 2: Spreading Activation Retrieval")
    print("-" * 60)
    
    # Create retriever
    retriever = SpreadingActivationRetriever(
        store=store,
        llm_client=llm_client,
        embeddings=embeddings,
        config=config
    )
    
    # Test queries
    test_queries = [
        "What frameworks does Alice use?",
        "Tell me about the autonomous vehicle project",
        "What is Alice's job?",
        "What detection methods are being used?"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Query: \"{query}\"")
        print("-" * 40)
        
        # Retrieve with spreading activation
        result = await retriever.retrieve(
            query=query,
            tenant_id=tenant_id,
            use_spreading=True,
            max_results=5
        )
        
        # Show activated nodes by type
        by_type = {}
        for node in result.activated_nodes:
            type_name = node.node_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(node)
        
        for type_name, nodes in by_type.items():
            print(f"\n  {type_name.upper()}S ({len(nodes)}):")
            for node in nodes[:3]:  # Show top 3 per type
                print(f"    • {node.node_id[:8]}... (activation: {node.activation:.3f}, hops: {node.hops_from_anchor})")
        
        # Get formatted context
        context = await retriever.retrieve_and_format(
            query=query,
            tenant_id=tenant_id,
            max_tokens=200
        )
        
        if context:
            print(f"\n  FORMATTED CONTEXT:")
            # Indent and truncate the context
            for line in context.split('\n')[:5]:
                if line.strip():
                    print(f"    {line[:60]}{'...' if len(line) > 60 else ''}")
    
    # Demonstrate entity profile
    print("\n" + "-" * 60)
    print("Phase 3: Entity Profile")
    print("-" * 60)
    
    profile = await retriever.get_entity_profile(
        entity_name="Alice",
        tenant_id=tenant_id
    )
    
    if profile:
        print("\n📋 Alice's Profile:")
        for line in profile.split('\n'):
            print(f"   {line}")
    else:
        # Try to find the entity with a search
        print("\n   Searching for Alice via alternative method...")
        result = await retriever.retrieve(
            query="Alice Chen",
            tenant_id=tenant_id,
            include_types=[NodeType.ENTITY],
            use_spreading=False
        )
        if result.activated_nodes:
            print(f"   Found {len(result.activated_nodes)} entity matches")
    
    # Cleanup
    await pipeline.close_session()
    await store.close()
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nKey takeaways:")
    print("• Spreading activation retrieves related nodes, not just similar ones")
    print("• The algorithm traverses edges to find connected knowledge")
    print("• Activation decays with each hop, prioritizing close connections")
    print("• Entity profiles aggregate knowledge about specific entities")


if __name__ == "__main__":
    asyncio.run(main())
