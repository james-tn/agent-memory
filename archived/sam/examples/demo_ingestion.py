"""
SAM Demo: Ingestion Pipeline

Demonstrates the SAM ingestion pipeline with Azure OpenAI.

Usage:
    python -m sam.examples.demo_ingestion

Requires:
    - AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT environment variables
    - Or a .env file with these values
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from sam import IngestionPipeline, SAMConfig


async def main():
    """Demonstrate the SAM ingestion pipeline."""
    
    print("=" * 60)
    print("SAM Ingestion Pipeline Demo")
    print("=" * 60)
    
    # Create config with small buffer for demo
    config = SAMConfig(
        storage_engine="sqlite",
        database_url="sam_demo.db",
        buffer_size=5,
        max_episode_tokens=500
    )
    
    # Create and initialize pipeline
    async with IngestionPipeline(
        tenant_id="demo-user",
        config=config,
        extract_on_close=True,
        generate_embeddings=True
    ) as pipeline:
        
        print("\n📝 Adding conversation turns...\n")
        
        # Simulate a conversation
        conversation = [
            ("user", "Hi! I'm Sarah and I work as a software engineer at TechCorp."),
            ("assistant", "Nice to meet you, Sarah! How can I help you today?"),
            ("user", "I've been working with Python for about 5 years, mostly on data pipelines."),
            ("assistant", "That's great experience! Python is excellent for data work. What kind of pipelines?"),
            ("user", "Mostly ETL processes using Apache Airflow. I really prefer it over Luigi."),
            ("assistant", "Airflow is very popular! Are you looking to learn something new?"),
            ("user", "Yes, I'm interested in machine learning, especially NLP. Any suggestions?"),
            ("assistant", "For NLP, I'd recommend starting with Hugging Face Transformers. It's very accessible."),
        ]
        
        for role, content in conversation:
            print(f"  {role.upper()}: {content[:60]}...")
            await pipeline.add_turn(role, content)
        
        print("\n" + "-" * 60)
        print("💾 Closing session and running extraction...")
        print("-" * 60)
        
        # Close session and extract
        result = await pipeline.close_session(run_extraction=True)
        
        # Show results
        if result.get("extraction_result"):
            extraction = result["extraction_result"]
            
            print(f"\n✨ Extraction Results:")
            print(f"   Entities: {len(extraction.get('entities', []))}")
            print(f"   Claims: {len(extraction.get('claims', []))}")
            print(f"   Edges: {len(extraction.get('edges', []))}")
            
            if extraction.get("entities"):
                print("\n📦 Extracted Entities:")
                for entity in extraction["entities"]:
                    print(f"   - {entity.name} ({entity.entity_type})")
            
            if extraction.get("claims"):
                print("\n📋 Extracted Claims:")
                for claim in extraction["claims"][:5]:  # Show first 5
                    print(f"   - {claim.content[:70]}...")
            
            if extraction.get("summary"):
                print(f"\n📝 Episode Summary:")
                print(f"   {extraction['summary']}")
            
            if extraction.get("key_topics"):
                print(f"\n🏷️ Key Topics:")
                print(f"   {', '.join(extraction['key_topics'])}")
            
            if extraction.get("contradictions"):
                print(f"\n⚠️ Contradictions Found:")
                for c in extraction["contradictions"]:
                    print(f"   - {c['explanation']}")
        
        # Show what's in the database
        print("\n" + "-" * 60)
        print("📊 Database Contents:")
        print("-" * 60)
        
        store = pipeline.store
        
        # List entities
        entities = []
        # Get all entities by searching
        search_results = await store.hybrid_anchor_search(
            query_text="",
            query_embedding=[0.0] * 1536,
            tenant_id="demo-user",
            node_types=["entity"],
            limit=20
        )
        
        print(f"\n   Total graph nodes created from this conversation:")
        print(f"   - Episode closed and processed")
        print(f"   - Entities, Claims, and Edges stored in SQLite")
        
    print("\n✅ Demo complete! Database saved to: sam_demo.db")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
