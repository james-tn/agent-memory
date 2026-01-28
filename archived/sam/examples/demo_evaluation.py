"""
SAM Evaluation Demo

Compares SAM spreading activation retrieval against simple vector baseline.
Includes:
- Persistence check to skip re-ingestion
- Side-by-side comparison with ground truth
- LLM-as-judge scoring
- Detailed metrics report

Usage:
    python demo_evaluation.py                    # Full run
    python demo_evaluation.py --skip-ingest      # Skip ingestion if data exists
    python demo_evaluation.py --quick            # Run only 5 test cases
"""

import asyncio
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from sam import (
    SAMConfig,
    create_store,
    create_pipeline,
    SpreadingActivationRetriever,
    LLMClient,
    EmbeddingsService,
    NodeType
)
from sam.vector_baseline import SimpleVectorRetriever
from sam.evaluation import (
    run_evaluation,
    print_evaluation_report,
    save_evaluation_results
)

# Load environment variables
load_dotenv()


# Persistence paths
DATA_DIR = Path(__file__).parent / "data"
CONVERSATIONS_PATH = DATA_DIR / "sample_conversations.json"
EVALUATION_PATH = DATA_DIR / "evaluation_dataset.json"
PERSISTENCE_DB_PATH = DATA_DIR / "sam_demo.db"
RESULTS_PATH = DATA_DIR / "evaluation_results.json"


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


async def check_persistence(store, tenant_id: str) -> bool:
    """
    Check if data has already been ingested.
    
    Returns True if store has existing data for this tenant.
    """
    try:
        # Check if we have any entities (sign of ingestion)
        if hasattr(store, '_get_conn'):
            conn = store._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM entities WHERE tenant_id = ?",
                (tenant_id,)
            ).fetchone()
            entity_count = row["cnt"] if row else 0
            
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM claims WHERE tenant_id = ?",
                (tenant_id,)
            ).fetchone()
            claim_count = row["cnt"] if row else 0
            
            if entity_count > 0 and claim_count > 0:
                print(f"✓ Found existing data: {entity_count} entities, {claim_count} claims")
                return True
        
        return False
    except Exception as e:
        print(f"⚠ Persistence check failed: {e}")
        return False


async def ingest_conversations(
    store,
    llm_client,
    config,
    tenant_id: str,
    conversations: dict
) -> dict:
    """
    Ingest all conversation sessions.
    
    Returns statistics about ingestion.
    """
    sessions = conversations["sessions"]
    total_turns = 0
    total_entities = 0
    total_claims = 0
    
    print(f"\n{'─'*70}")
    print("Ingesting Conversation History")
    print(f"{'─'*70}")
    
    for i, session in enumerate(sessions, 1):
        print(f"\n📝 Session {i}/{len(sessions)}: {session['topic']} ({session['date']})")
        
        # Create pipeline for this session
        pipeline = await create_pipeline(
            config=config,
            tenant_id=tenant_id,
            llm_client=llm_client,
            store=store
        )
        
        # Add turns
        for turn in session["turns"]:
            await pipeline.add_turn(turn["role"], turn["content"])
            total_turns += 1
        
        # Close session and extract
        result = await pipeline.close_session(run_extraction=True)
        extraction = result.get("extraction_result", {})
        if extraction:
            total_entities += extraction.get("entities_extracted", 0)
            total_claims += extraction.get("claims_extracted", 0)
        
        print(f"   ✓ Ingested {len(session['turns'])} turns")
    
    return {
        "sessions": len(sessions),
        "turns": total_turns,
        "entities": total_entities,
        "claims": total_claims
    }


async def main():
    """Run the evaluation demo."""
    parser = argparse.ArgumentParser(description="SAM Evaluation Demo")
    parser.add_argument("--skip-ingest", action="store_true", 
                        help="Skip ingestion if data exists")
    parser.add_argument("--force-ingest", action="store_true",
                        help="Force re-ingestion even if data exists")
    parser.add_argument("--quick", action="store_true",
                        help="Run only 5 test cases for quick evaluation")
    parser.add_argument("--memory", action="store_true",
                        help="Use in-memory database (no persistence)")
    args = parser.parse_args()
    
    print("=" * 70)
    print("SAM vs Vector Baseline Evaluation")
    print("=" * 70)
    
    # Check for data files
    if not CONVERSATIONS_PATH.exists():
        print(f"❌ Conversations not found: {CONVERSATIONS_PATH}")
        return
    
    if not EVALUATION_PATH.exists():
        print(f"❌ Evaluation dataset not found: {EVALUATION_PATH}")
        return
    
    conversations = load_json(CONVERSATIONS_PATH)
    evaluation_data = load_json(EVALUATION_PATH)
    
    print(f"\n📁 Loaded {len(conversations['sessions'])} conversation sessions")
    print(f"📁 Loaded {len(evaluation_data['test_cases'])} evaluation test cases")
    
    # Check Azure credentials
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    processing_model = os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4")
    embeddings_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    
    if not endpoint or not api_key:
        print("\n❌ Azure OpenAI credentials not found in .env")
        return
    
    print(f"\n✓ Using Azure OpenAI at {endpoint}")
    
    # Database path
    if args.memory:
        db_path = ":memory:"
        print("⚠ Using in-memory database (no persistence)")
    else:
        db_path = f"sqlite:///{PERSISTENCE_DB_PATH}"
        print(f"📦 Database: {PERSISTENCE_DB_PATH}")
    
    # Create configuration
    config = SAMConfig(
        storage_engine="sqlite",
        database_url=db_path,
        azure_openai_endpoint=endpoint,
        azure_openai_api_key=api_key,
        azure_openai_processing_model=processing_model,
        azure_openai_embeddings_model=embeddings_model,
        activation_decay=0.7,
        max_activation_depth=3,
        activation_threshold=0.05
    )
    
    # Create store
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
    
    # Check persistence
    has_data = await check_persistence(store, tenant_id)
    
    should_ingest = True
    if has_data and not args.force_ingest:
        if args.skip_ingest:
            should_ingest = False
            print("⏭ Skipping ingestion (--skip-ingest flag)")
        else:
            print("\n⚠ Data already exists. Options:")
            print("   --skip-ingest  : Use existing data")
            print("   --force-ingest : Re-ingest from scratch")
            print("   --memory       : Use fresh in-memory database")
            print("\nContinuing with existing data...")
            should_ingest = False
    
    # Ingest if needed
    if should_ingest:
        stats = await ingest_conversations(
            store, llm_client, config, tenant_id, conversations
        )
        print(f"\n✓ Ingestion complete: {stats['entities']} entities, {stats['claims']} claims")
    
    # Create retrievers
    embeddings = EmbeddingsService(llm_client)
    
    sam_retriever = SpreadingActivationRetriever(
        store=store,
        llm_client=llm_client,
        embeddings=embeddings,
        config=config
    )
    
    vector_retriever = SimpleVectorRetriever(
        store=store,
        embeddings=embeddings
    )
    
    # Limit test cases if quick mode
    if args.quick:
        evaluation_data["test_cases"] = evaluation_data["test_cases"][:5]
        print(f"\n⚡ Quick mode: running {len(evaluation_data['test_cases'])} test cases")
    
    # Run evaluation
    summary = await run_evaluation(
        store=store,
        sam_retriever=sam_retriever,
        vector_retriever=vector_retriever,
        llm_client=llm_client,
        evaluation_data=evaluation_data,
        tenant_id=tenant_id
    )
    
    # Print and save results
    print_evaluation_report(summary)
    save_evaluation_results(summary, str(RESULTS_PATH))
    
    print(f"\n{'='*70}")
    print("Evaluation Complete!")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
