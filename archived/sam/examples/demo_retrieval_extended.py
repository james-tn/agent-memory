"""
SAM Retrieval Demo with External Conversation Data

Demonstrates the spreading activation retrieval algorithm with rich,
multi-session conversation history loaded from JSON.

This shows the true power of the memory system:
- Long-term memory across multiple sessions
- Entity relationships built over time
- Retrieval that connects information from different conversations
"""

import asyncio
import json
import os
import sys
from pathlib import Path

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


def load_conversations(json_path: str) -> dict:
    """Load conversations from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


async def main():
    """Run the retrieval demo with external data."""
    print("=" * 70)
    print("SAM Spreading Activation Retrieval Demo - Extended History")
    print("=" * 70)
    
    # Load conversation data
    data_path = Path(__file__).parent / "data" / "sample_conversations.json"
    if not data_path.exists():
        print(f"\n❌ Data file not found: {data_path}")
        print("   Please ensure sample_conversations.json exists in the data folder.")
        return
    
    data = load_conversations(str(data_path))
    sessions = data["sessions"]
    print(f"\n📁 Loaded {len(sessions)} conversation sessions from JSON")
    print(f"   User: {data['metadata']['user']}")
    print(f"   Date range: {data['metadata']['date_range']}")
    
    # Check for Azure OpenAI credentials
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    processing_model = os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4")
    embeddings_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    
    if not endpoint or not api_key:
        print("\n⚠️  Azure OpenAI credentials not found in .env")
        print("   Demo will not be able to extract entities and claims.")
        return
    
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
    
    # Create store (shared across all sessions)
    store = create_store(config)
    await store.initialize()
    
    tenant_id = "demo-tenant"
    
    # Create LLM client
    llm_client = LLMClient(
        api_key=api_key,
        endpoint=endpoint,
        processing_model=processing_model,
        embedding_model=embeddings_model
    )
    
    print("\n" + "-" * 70)
    print("Phase 1: Ingesting Conversation History")
    print("-" * 70)
    
    total_turns = 0
    total_entities = 0
    total_claims = 0
    
    for i, session in enumerate(sessions, 1):
        print(f"\n📝 Session {i}/{len(sessions)}: {session['topic']} ({session['date']})")
        
        # Create pipeline for this session
        pipeline = await create_pipeline(
            config=config,
            tenant_id=tenant_id,
            llm_client=llm_client,
            store=store
        )
        
        # Ingest all turns
        for turn in session["turns"]:
            await pipeline.add_turn(turn["role"], turn["content"])
            total_turns += 1
        
        # Close session to trigger extraction
        await pipeline.close_session()
        
        # Get extraction stats (from the print output)
        print(f"   ✓ Ingested {len(session['turns'])} turns")
    
    print(f"\n{'=' * 70}")
    print(f"Ingestion Complete!")
    print(f"  Total sessions: {len(sessions)}")
    print(f"  Total turns: {total_turns}")
    print(f"{'=' * 70}")
    
    # Now demonstrate retrieval
    print("\n" + "-" * 70)
    print("Phase 2: Spreading Activation Retrieval")
    print("-" * 70)
    
    # Create retriever
    retriever = SpreadingActivationRetriever(
        store=store,
        llm_client=llm_client,
        config=config
    )
    
    # Demonstrate different types of queries
    test_queries = [
        # Work-related queries
        ("What is Alice's job and where does she work?", "Career info"),
        ("Tell me about the autonomous vehicle project", "Project details"),
        ("What ML frameworks does Alice use?", "Technical preferences"),
        ("Who is on Alice's team?", "Team members"),
        ("What architecture did they choose for sensor fusion?", "Technical architecture"),
        
        # Personal queries (testing memory of personal details)
        ("What are Alice's hobbies?", "Personal interests"),
        ("Tell me about Alice's family", "Family info"),
        ("Where does Alice like to hike?", "Recreation"),
        
        # Cross-session queries (testing memory consolidation)
        ("What happened with the CVPR paper?", "Publication journey"),
        ("What are Alice's career goals?", "Career aspirations"),
    ]
    
    for query, category in test_queries:
        print(f"\n🔍 [{category}] \"{query}\"")
        print("-" * 50)
        
        # Get formatted context
        context = await retriever.retrieve_and_format(
            query=query,
            tenant_id=tenant_id,
            max_tokens=300
        )
        
        if context:
            # Print context with nice formatting
            lines = context.split('\n')
            for line in lines[:8]:  # Limit output
                if line.strip():
                    print(f"  {line[:75]}{'...' if len(line) > 75 else ''}")
            if len(lines) > 8:
                print(f"  ... and {len(lines) - 8} more lines")
        else:
            print("  No relevant information found.")
    
    # Demonstrate entity profiles
    print("\n" + "-" * 70)
    print("Phase 3: Entity Profiles")
    print("-" * 70)
    
    entities_to_profile = ["Alice", "Marcus", "Priya", "TechCorp", "PyTorch"]
    
    for entity_name in entities_to_profile:
        profile = await retriever.get_entity_profile(
            entity_name=entity_name,
            tenant_id=tenant_id
        )
        
        if profile:
            print(f"\n📋 {entity_name}:")
            lines = profile.split('\n')
            for line in lines[:6]:
                print(f"   {line[:70]}{'...' if len(line) > 70 else ''}")
            if len(lines) > 6:
                print(f"   ... and {len(lines) - 6} more facts")
        else:
            print(f"\n📋 {entity_name}: (not found in memory)")
    
    # Cleanup
    await store.close()
    
    print("\n" + "=" * 70)
    print("Demo Complete!")
    print("=" * 70)
    print("\nKey observations:")
    print("• Memory persists across multiple conversation sessions")
    print("• Entities (people, places, things) are extracted and linked")
    print("• Claims capture facts with confidence and temporal context")
    print("• Spreading activation finds related information across sessions")
    print("• Entity profiles aggregate all knowledge about specific entities")


if __name__ == "__main__":
    asyncio.run(main())
