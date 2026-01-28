"""
SAM Domain-Specific Evaluation Demo

Evaluates SAM with domain-specific ontology against vector baseline.
Supports different domains (generic, healthcare) for comparison.

Usage:
    python demo_evaluation_domain.py --domain healthcare           # Run healthcare eval
    python demo_evaluation_domain.py --domain generic              # Run generic eval  
    python demo_evaluation_domain.py --domain healthcare --skip-ingest
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
from sam.domains import get_domain_config, list_domains

# Load environment variables
load_dotenv()


# Data paths by domain
DATA_DIR = Path(__file__).parent / "data"

DOMAIN_DATA = {
    "generic": {
        "conversations": DATA_DIR / "sample_conversations.json",
        "evaluation": DATA_DIR / "evaluation_dataset.json",
        "database": DATA_DIR / "sam_demo.db",
        "results": DATA_DIR / "evaluation_results.json",
    },
    "healthcare": {
        "conversations": DATA_DIR / "healthcare_conversations.json",
        "evaluation": DATA_DIR / "healthcare_evaluation.json",
        "database": DATA_DIR / "sam_healthcare.db",
        "results": DATA_DIR / "healthcare_results.json",
    }
}


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


async def check_persistence(store, tenant_id: str) -> bool:
    """Check if data has already been ingested."""
    try:
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
                print(f"[OK] Found existing data: {entity_count} entities, {claim_count} claims")
                return True
        
        return False
    except Exception as e:
        print(f"[Warn] Persistence check failed: {e}")
        return False


async def ingest_conversations(
    store,
    llm_client,
    config,
    tenant_id: str,
    conversations: dict,
    domain_config
) -> dict:
    """Ingest all conversation sessions with domain-aware extraction."""
    sessions = conversations["sessions"]
    total_turns = 0
    total_entities = 0
    total_claims = 0
    total_relationships = 0
    
    print(f"\n{'─'*70}")
    print(f"Ingesting Conversation History ({domain_config.display_name})")
    print(f"{'─'*70}")
    
    for i, session in enumerate(sessions, 1):
        print(f"\n📝 Session {i}/{len(sessions)}: {session['topic']} ({session['date']})")
        
        # Create pipeline for this session with domain support
        pipeline = await create_pipeline(
            config=config,
            tenant_id=tenant_id,
            llm_client=llm_client,
            store=store,
            domain=domain_config.domain_id,  # Pass domain for relationship extraction
            extract_relationships=True        # Enable entity-to-entity relationship edges
        )
        
        # Add turns
        for turn in session["turns"]:
            await pipeline.add_turn(turn["role"], turn["content"])
            total_turns += 1
        
        # Close session and extract
        result = await pipeline.close_session(run_extraction=True)
        extraction = result.get("extraction_result", {})
        if extraction:
            total_entities += len(extraction.get("entities", []))
            total_claims += len(extraction.get("claims", []))
            total_relationships += len(extraction.get("relationships", []))
        
        print(f"   ✓ Ingested {len(session['turns'])} turns")
    
    return {
        "sessions": len(sessions),
        "turns": total_turns,
        "entities": total_entities,
        "claims": total_claims,
        "relationships": total_relationships
    }


async def main():
    """Run the domain-specific evaluation."""
    parser = argparse.ArgumentParser(description="SAM Domain-Specific Evaluation")
    parser.add_argument("--domain", type=str, default="healthcare",
                        choices=list_domains(),
                        help="Domain to evaluate (default: healthcare)")
    parser.add_argument("--skip-ingest", action="store_true", 
                        help="Skip ingestion if data exists")
    parser.add_argument("--force-ingest", action="store_true",
                        help="Force re-ingestion even if data exists")
    parser.add_argument("--quick", action="store_true",
                        help="Run only 5 test cases")
    parser.add_argument("--compare", action="store_true",
                        help="Run both domains and compare results")
    args = parser.parse_args()
    
    domains_to_run = list_domains() if args.compare else [args.domain]
    
    for domain_id in domains_to_run:
        await run_domain_evaluation(domain_id, args)
        print("\n" + "="*70 + "\n")


async def run_domain_evaluation(domain_id: str, args):
    """Run evaluation for a specific domain."""
    
    # Get domain config
    domain_config = get_domain_config(domain_id)
    domain_data = DOMAIN_DATA.get(domain_id)
    
    if not domain_data:
        print(f"❌ No data configured for domain: {domain_id}")
        return
    
    print("=" * 70)
    print(f"SAM {domain_config.display_name} Evaluation")
    print("=" * 70)
    print(f"\nDomain: {domain_id}")
    print(f"Description: {domain_config.description[:100]}...")
    print(f"Entity types: {domain_config.get_entity_type_names()}")
    print(f"Relationship types: {domain_config.get_relationship_type_names()[:5]}...")
    
    # Check for data files
    if not domain_data["conversations"].exists():
        print(f"❌ Conversations not found: {domain_data['conversations']}")
        return
    
    if not domain_data["evaluation"].exists():
        print(f"❌ Evaluation dataset not found: {domain_data['evaluation']}")
        return
    
    conversations = load_json(domain_data["conversations"])
    evaluation_data = load_json(domain_data["evaluation"])
    
    print(f"\n[Files] Loaded {len(conversations['sessions'])} conversation sessions")
    print(f"[Files] Loaded {len(evaluation_data['test_cases'])} evaluation test cases")
    
    # Check Azure credentials
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    processing_model = os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4")
    embeddings_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    
    if not endpoint or not api_key:
        print("\n[Error] Azure OpenAI credentials not found in .env")
        return
    
    print(f"\n[OK] Using Azure OpenAI at {endpoint}")
    
    # Database path
    db_path = f"sqlite:///{domain_data['database']}"
    print(f"[DB] Database: {domain_data['database']}")
    
    # Create configuration with domain-specific defaults
    config = SAMConfig(
        storage_engine="sqlite",
        database_url=db_path,
        azure_openai_endpoint=endpoint,
        azure_openai_api_key=api_key,
        azure_openai_processing_model=processing_model,
        azure_openai_embeddings_model=embeddings_model,
        activation_decay=domain_config.default_activation_decay,
        max_activation_depth=domain_config.default_max_depth,
        activation_threshold=domain_config.default_activation_threshold
    )
    
    # Create store
    store = create_store(config)
    await store.initialize()
    
    tenant_id = f"{domain_id}-tenant"
    
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
            print("[Skip] Skipping ingestion (--skip-ingest flag)")
        else:
            print("\n[Note] Data already exists. Skipping ingestion...")
            should_ingest = False
    
    # Ingest if needed
    if should_ingest:
        stats = await ingest_conversations(
            store, llm_client, config, tenant_id, conversations, domain_config
        )
        rel_count = stats.get('relationships', 0)
        print(f"\n[OK] Ingestion complete: {stats['entities']} entities, {stats['claims']} claims, {rel_count} relationships")
    
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
        print(f"\n[Quick] Quick mode: running {len(evaluation_data['test_cases'])} test cases")
    
    # Run evaluation
    summary = await run_evaluation(
        store=store,
        sam_retriever=sam_retriever,
        vector_retriever=vector_retriever,
        llm_client=llm_client,
        evaluation_data=evaluation_data,
        tenant_id=tenant_id,
        use_enhanced_retrieval=True
    )
    
    # Print and save results
    print_evaluation_report(summary)
    save_evaluation_results(summary, str(domain_data["results"]))
    
    # Print domain-specific insights
    print_domain_insights(summary, domain_config, evaluation_data)
    
    print(f"\n{'='*70}")
    print(f"{domain_config.display_name} Evaluation Complete!")
    print(f"{'='*70}")


def print_domain_insights(summary, domain_config, evaluation_data):
    """Print domain-specific insights about the evaluation."""
    
    print(f"\n{'─'*70}")
    print(f"DOMAIN-SPECIFIC INSIGHTS: {domain_config.display_name}")
    print(f"{'─'*70}")
    
    # Analyze by category
    category_stats = {}
    for result in summary.results:
        cat = result.category
        if cat not in category_stats:
            category_stats[cat] = {"sam_wins": 0, "vector_wins": 0, "ties": 0, "total": 0}
        category_stats[cat]["total"] += 1
        
        if result.sam_wins:
            category_stats[cat]["sam_wins"] += 1
        elif result.vector_llm_score > result.sam_llm_score:
            category_stats[cat]["vector_wins"] += 1
        else:
            category_stats[cat]["ties"] += 1
    
    # Identify multi-hop categories
    multi_hop_cats = [cat for cat in category_stats.keys() if "multi_hop" in cat.lower()]
    basic_cats = [cat for cat in category_stats.keys() if "multi_hop" not in cat.lower()]
    
    print("\n📊 Multi-hop Query Performance (where SAM should excel):")
    mh_sam = sum(category_stats[c]["sam_wins"] for c in multi_hop_cats)
    mh_vec = sum(category_stats[c]["vector_wins"] for c in multi_hop_cats)
    mh_tie = sum(category_stats[c]["ties"] for c in multi_hop_cats)
    mh_total = sum(category_stats[c]["total"] for c in multi_hop_cats)
    
    if mh_total > 0:
        print(f"   SAM wins: {mh_sam}/{mh_total} ({100*mh_sam/mh_total:.0f}%)")
        print(f"   Vector wins: {mh_vec}/{mh_total} ({100*mh_vec/mh_total:.0f}%)")
        print(f"   Ties: {mh_tie}/{mh_total} ({100*mh_tie/mh_total:.0f}%)")
    
    print("\n📊 Basic Query Performance:")
    b_sam = sum(category_stats[c]["sam_wins"] for c in basic_cats)
    b_vec = sum(category_stats[c]["vector_wins"] for c in basic_cats)
    b_tie = sum(category_stats[c]["ties"] for c in basic_cats)
    b_total = sum(category_stats[c]["total"] for c in basic_cats)
    
    if b_total > 0:
        print(f"   SAM wins: {b_sam}/{b_total} ({100*b_sam/b_total:.0f}%)")
        print(f"   Vector wins: {b_vec}/{b_total} ({100*b_vec/b_total:.0f}%)")
        print(f"   Ties: {b_tie}/{b_total} ({100*b_tie/b_total:.0f}%)")
    
    # Highlight where SAM performed well
    sam_strong_cats = [cat for cat, stats in category_stats.items() 
                       if stats["sam_wins"] > stats["vector_wins"]]
    
    if sam_strong_cats:
        print(f"\n✅ Categories where SAM outperformed Vector:")
        for cat in sam_strong_cats:
            stats = category_stats[cat]
            print(f"   - {cat}: SAM {stats['sam_wins']}/{stats['total']}")
    
    # Highlight where improvements are needed
    vec_strong_cats = [cat for cat, stats in category_stats.items() 
                       if stats["vector_wins"] > stats["sam_wins"]]
    
    if vec_strong_cats:
        print(f"\n⚠️ Categories needing improvement:")
        for cat in vec_strong_cats:
            stats = category_stats[cat]
            print(f"   - {cat}: Vector {stats['vector_wins']}/{stats['total']}")


if __name__ == "__main__":
    asyncio.run(main())
