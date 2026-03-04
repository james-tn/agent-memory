"""
Long-Term Memory Prioritization Demo (CosmosDB)
================================================

This is the CosmosDB version of the memory prioritization demo.
Uses Azure CosmosDB for production-grade storage with vector search.

Same concepts as the SQLite version:
1. RECENCY: Recent insights are prioritized
2. FREQUENCY: Frequently accessed insights are strengthened
3. FORGETTING: Old, unused insights decay over time
4. BOUNDED CAPACITY: Only top-N insights are retained

Requirements:
- Azure CosmosDB account with vector indexing enabled
- Set COSMOS_ENDPOINT and COSMOS_KEY environment variables

Run: uv run python demo/09_itemized_insights_cosmos.py
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

from openai import AzureOpenAI
from azure.cosmos import CosmosClient
from memory.db.cosmos_backend import CosmosDBDatabase
from memory.db.base import ContainerType
from memory.providers.embedding import OpenAIEmbeddingProvider
from memory.core.reflection import Reflection, ReflectionConfig
from memory.core.insight_items import (
    LongTermInsightItem,
    InsightIdGenerator,
    rank_insights,
    calculate_retention_score,
    get_top_insights,
    SessionAnalysisWithCitations,
    build_context_with_ids,
)


# ============================================================================
# Configuration
# ============================================================================

USER_ID = "memory_priority_demo_cosmos"
MAX_INSIGHTS = 5  # Limited memory capacity

# Azure OpenAI client
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
    api_version="2024-10-21"
)


# ============================================================================
# Timeline Simulation (same as SQLite version)
# ============================================================================

TIMELINE = [
    {
        "session_id": "month-1",
        "simulated_date": datetime(2025, 1, 15),
        "title": "Month 1: Initial Consultation",
        "summary": """
            Alex is 28, software engineer earning $120k. Wants to start investing.
            Very risk-averse due to parents' 2008 losses. Prefers bonds and savings.
            Has $10,000 in emergency fund. Single, no major expenses planned.
            Interested in learning about Roth IRA.
        """,
        "turns": [
            ("user", "I'm Alex, 28, making $120k. I want to start investing but I'm scared of losing money."),
            ("assistant", "That's understandable. Let's start with your risk tolerance and goals."),
            ("user", "My parents lost a lot in 2008. I want safe investments - bonds, savings accounts."),
            ("assistant", "With your fear of losses, we can start conservatively. You mentioned a Roth IRA?"),
            ("user", "Yes, I want to learn about Roth IRAs. I have $10k saved for emergencies."),
        ],
    },
    {
        "session_id": "month-2",
        "simulated_date": datetime(2025, 2, 20),
        "title": "Month 2: Roth IRA Setup",
        "summary": """
            Alex opened a Roth IRA last month. Asking about contribution limits.
            Still very conservative - chose money market fund inside IRA.
            Mentions sister's wedding coming up, needs to save for gift/travel.
        """,
        "turns": [
            ("user", "I opened the Roth IRA! How much can I contribute this year?"),
            ("assistant", "Great! The 2025 limit is $7,000. Given your conservative preference, what did you choose?"),
            ("user", "I put it in a money market fund. I know it's low return but I can't handle volatility."),
            ("assistant", "That's fine to start. Any other financial goals coming up?"),
            ("user", "My sister's wedding is in April. I need to save about $2,000 for travel and gift."),
        ],
    },
    {
        "session_id": "month-3",
        "simulated_date": datetime(2025, 3, 25),
        "title": "Month 3: Tax Season Questions",
        "summary": """
            Alex asking about tax implications of Roth IRA contributions.
            Still conservative. Sister's wedding next month - on track with savings.
            Considering maxing out Roth IRA this year.
        """,
        "turns": [
            ("user", "Quick tax question - do my Roth IRA contributions reduce my taxable income?"),
            ("assistant", "No, Roth contributions are post-tax. But withdrawals in retirement are tax-free."),
            ("user", "Got it. I think I want to max out my Roth this year. I'm on track for the wedding savings."),
            ("assistant", "Good plan! With your income, maxing the Roth makes sense. Still comfortable with the money market?"),
            ("user", "Yes, I'm not ready for stocks yet. Maybe next year when I feel more confident."),
        ],
    },
    {
        "session_id": "month-4",  
        "simulated_date": datetime(2025, 5, 10),
        "title": "Month 4: Post-Wedding, Promotion News",
        "summary": """
            Wedding is over - Alex had a great time. Got a big promotion to $150k!
            Feeling more confident financially. Starting to reconsider risk tolerance.
            Asking about target-date funds as a middle ground.
        """,
        "turns": [
            ("user", "Big news! Wedding was great, and I just got promoted to $150k!"),
            ("assistant", "Congratulations! That's a significant increase. How are you feeling about your finances now?"),
            ("user", "Much more confident! With more money coming in, maybe I can handle some risk?"),
            ("assistant", "That's a natural progression. Would you like to explore some middle-ground options?"),
            ("user", "Yes, I've heard about target-date funds. They seem balanced - not too risky."),
        ],
    },
    {
        "session_id": "month-5",
        "simulated_date": datetime(2025, 6, 15),
        "title": "Month 5: Risk Tolerance Shift",
        "summary": """
            Alex moved Roth IRA from money market to target-date 2060 fund.
            Feeling good about the change. Now interested in taxable brokerage.
            Mentions wanting to save for a house in 3-4 years.
        """,
        "turns": [
            ("user", "I did it! Moved my Roth to a 2060 target-date fund. Feels right."),
            ("assistant", "That's a big step! How do you feel about it?"),
            ("user", "Good actually. The diversification makes sense. Now I want a taxable account too."),
            ("assistant", "Smart thinking. Any specific goals for the taxable account?"),
            ("user", "I'm thinking about buying a house in 3-4 years. That would be my down payment fund."),
        ],
    },
    {
        "session_id": "month-6",
        "simulated_date": datetime(2025, 7, 20),
        "title": "Month 6: Current State & Planning",
        "summary": """
            Alex now has diversified investments. No longer risk-averse for long-term.
            House down payment fund started - conservative allocation for that.
            Asking about increasing 401k contributions now that income is higher.
        """,
        "turns": [
            ("user", "I started the house fund with $5,000. Keeping that conservative since I need it in 3 years."),
            ("assistant", "Smart! Different time horizons need different strategies. How's the 401k?"),
            ("user", "That's what I wanted to ask - should I increase my 401k contributions now?"),
            ("assistant", "At $150k, maxing your 401k ($23,500) would be ideal. You'd still have plenty to live on."),
            ("user", "I'll do that. Retirement is aggressive, house fund is conservative. I get it now!"),
        ],
    },
]


# ============================================================================
# Demo Functions (same as SQLite version, adapted for CosmosDB)
# ============================================================================

def print_section(title: str, char: str = "="):
    """Print a section header."""
    width = 70
    print(f"\n{char*width}")
    print(f" {title}")
    print(f"{char*width}")


def print_insight_table(items: List[LongTermInsightItem], now: datetime, title: str = "Current Insights"):
    """Print insights as a formatted table with scores."""
    print(f"\n{title}:")
    print("-" * 95)
    print(f"{'ID':<10} {'Score':>6} {'Access':>7} {'Age':>8} {'Importance':>10}  {'Text':<40}")
    print("-" * 95)
    
    ranked = rank_insights(items, now)
    for item, score in ranked:
        age_days = (now - item.date_added).days
        age_str = f"{age_days}d" if age_days < 30 else f"{age_days//30}m {age_days%30}d"
        text = item.insight_text[:38] + ".." if len(item.insight_text) > 38 else item.insight_text
        print(f"{item.id:<10} {score:>6.2f} {item.access_count:>7} {age_str:>8} {item.importance:>10}  {text}")
    print("-" * 95)


async def prune_insights(db: CosmosDBDatabase, user_id: str, items: List[LongTermInsightItem], max_items: int, now: datetime) -> tuple:
    """Prune insights to keep only top-N by retention score."""
    if len(items) <= max_items:
        return items, []
    
    ranked = rank_insights(items, now)
    kept = [item for item, score in ranked[:max_items]]
    pruned = [item for item, score in ranked[max_items:]]
    
    # Delete pruned items from database
    for item in pruned:
        await db.delete(
            container=ContainerType.INSIGHTS,
            document_id=item.id,
            partition_key=user_id
        )
    
    return kept, pruned


async def get_insight_items(db: CosmosDBDatabase, user_id: str) -> List[LongTermInsightItem]:
    """Get all long-term insight items for a user."""
    items = await db.query(
        container=ContainerType.INSIGHTS,
        filters={"user_id": user_id, "insight_type": "long_term_item"},
        order_by="-created_at"
    )
    
    result = []
    for item_data in items:
        try:
            result.append(LongTermInsightItem.from_dict(item_data))
        except Exception as e:
            print(f"  Warning: Could not parse insight item: {e}")
    
    return result


async def cleanup_demo_data(db: CosmosDBDatabase, user_id: str):
    """Clean up demo data from previous runs."""
    items = await db.query(
        container=ContainerType.INSIGHTS,
        filters={"user_id": user_id}
    )
    for item in items:
        await db.delete(
            container=ContainerType.INSIGHTS,
            document_id=item["id"],
            partition_key=user_id
        )
    print(f"[Cleaned up {len(items)} existing insights for demo user]")


async def run_demo():
    print_section("LONG-TERM MEMORY PRIORITIZATION DEMO (CosmosDB)")
    print(f"""
This demo simulates 6 months of client sessions using Azure CosmosDB.

Key concepts demonstrated:
• RECENCY: New insights start with a "grace period" boost
• FREQUENCY: Cited insights gain strength (access_count increases)
• FORGETTING: Old, uncited insights decay over time
• BOUNDED MEMORY: Only {MAX_INSIGHTS} insights retained

Watch how insights compete for limited memory slots!
""")
    
    # Check for CosmosDB credentials
    cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT") or os.environ.get("AZURE_COSMOS_ENDPOINT")
    cosmos_key = os.environ.get("COSMOS_KEY") or os.environ.get("AZURE_COSMOS_KEY")
    
    if not cosmos_endpoint:
        print("ERROR: CosmosDB endpoint not found!")
        print("Please set COSMOS_ENDPOINT environment variable.")
        print("\nFalling back to SQLite demo (run demo/08_itemized_insights.py)")
        return
    
    # Initialize CosmosDB - try key auth first, then Azure AD
    print("[Connecting to Azure CosmosDB...]")
    
    if cosmos_key:
        print("  Using key-based authentication")
        db = CosmosDBDatabase(
            endpoint=cosmos_endpoint,
            key=cosmos_key,
            database_name=os.environ.get("COSMOS_DATABASE", os.environ.get("AZURE_COSMOS_DATABASE_NAME", "agent_memory_db")),
        )
    else:
        # Try Azure AD authentication
        print("  No key found, trying Azure AD authentication...")
        try:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            db = CosmosDBDatabase(
                endpoint=cosmos_endpoint,
                credential=credential,
                database_name=os.environ.get("COSMOS_DATABASE", os.environ.get("AZURE_COSMOS_DATABASE_NAME", "agent_memory_db")),
            )
        except ImportError:
            print("ERROR: azure-identity package not installed.")
            print("Please run: pip install azure-identity")
            return
        except Exception as e:
            print(f"ERROR: Azure AD authentication failed: {e}")
            print("Please set COSMOS_KEY or configure Azure AD credentials.")
            return
    
    try:
        await db.initialize()
    except Exception as exc:
        message = str(exc)
        if "CosmosHttpResponseError" in message or "Forbidden" in message or "firewall" in message.lower():
            print("\n⚠️ CosmosDB access is blocked in this environment (firewall/network restrictions).")
            print("   Demo skipped gracefully. Configure Cosmos DB firewall/network to run end-to-end.")
            return
        print(f"ERROR: Could not connect to CosmosDB: {exc}")
        return

    print("[Connected successfully]")
    
    # Clean up previous demo data
    await cleanup_demo_data(db, USER_ID)
    
    emb_provider = OpenAIEmbeddingProvider(
        openai_client=client,
        model=os.environ.get("AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002")
    )
    
    reflection = Reflection(
        database=db,
        embedding_provider=emb_provider,
        chat_client=client,
        config=ReflectionConfig()
    )
    
    # Track insights over time
    insight_history = []
    
    # Run through the timeline
    for month_idx, session in enumerate(TIMELINE, 1):
        simulated_now = session["simulated_date"]
        
        print_section(f"SESSION {month_idx}: {session['title']}", "=")
        print(f"Simulated Date: {simulated_now.strftime('%B %d, %Y')}")
        
        # Show current state BEFORE this session
        items_before = await get_insight_items(db, USER_ID)
        if items_before:
            print_insight_table(items_before, simulated_now, "Memory State BEFORE Session")
        else:
            print("\n[No existing insights - this is the first session]")
        
        # Run reflection with citations
        print(f"\n[Processing session...]")
        result = await run_session_with_simulated_time(
            reflection, db, emb_provider, USER_ID, session, simulated_now
        )
        
        # Show what happened
        print(f"\n📝 Summary: {result['session_summary'][:100]}...")
        print(f"🆕 New insights: {len(result['new_insights'])}")
        for ins in result['new_insights']:
            print(f"   • [{ins['id']}] {ins['insight_text'][:50]}...")
        
        if result['cited_insight_ids']:
            print(f"📎 Cited existing: {result['cited_insight_ids']}")
            print(f"   (These insights are STRENGTHENED)")
        
        # Get state after session
        items_after = await get_insight_items(db, USER_ID)
        
        # Check if we need to prune
        if len(items_after) > MAX_INSIGHTS:
            print(f"\n⚠️  Memory capacity exceeded! ({len(items_after)} > {MAX_INSIGHTS})")
            print(f"   Pruning to keep only top {MAX_INSIGHTS} insights...")
            
            kept, pruned = await prune_insights(db, USER_ID, items_after, MAX_INSIGHTS, simulated_now)
            
            print(f"\n   🗑️  FORGOTTEN:")
            for item in pruned:
                score = calculate_retention_score(item, simulated_now)
                age = (simulated_now - item.date_added).days
                print(f"      [{item.id}] score={score:.2f} age={age}d access={item.access_count}: {item.insight_text[:35]}...")
            
            print(f"\n   💾 RETAINED:")
            for item in kept:
                score = calculate_retention_score(item, simulated_now)
                age = (simulated_now - item.date_added).days
                print(f"      [{item.id}] score={score:.2f} age={age}d access={item.access_count}: {item.insight_text[:35]}...")
            
            items_after = kept
        
        print_insight_table(items_after, simulated_now, "Memory State AFTER Session (Top 5)")
        
        insight_history.append({
            "month": month_idx,
            "date": simulated_now,
            "insights": [(i.id, i.insight_text[:25] + "...", i.access_count, 
                         calculate_retention_score(i, simulated_now)) 
                        for i in sorted(items_after, key=lambda x: calculate_retention_score(x, simulated_now), reverse=True)]
        })
        
        print(f"\n{'─'*70}")
        if month_idx < len(TIMELINE):
            days_until_next = (TIMELINE[month_idx]["simulated_date"] - simulated_now).days
            print(f"⏳ {days_until_next} days pass until next session...")
    
    # Final Summary
    print_section("DEMO COMPLETE - MEMORY EVOLUTION SUMMARY", "=")
    
    print("\nHow insights evolved over 6 months:")
    print("-" * 80)
    for record in insight_history:
        print(f"\n📅 Month {record['month']} ({record['date'].strftime('%B %Y')}):")
        for id, text, access, score in record['insights']:
            print(f"   [{id}] score={score:.2f} access={access}: {text}")
    
    print("\n" + "=" * 70)
    print("KEY OBSERVATIONS (CosmosDB):")
    print("=" * 70)
    print("""
✓ Same memory prioritization behavior as SQLite
✓ Scales to millions of users with CosmosDB global distribution
✓ Vector search for semantic memory retrieval
✓ Enterprise-grade reliability and security
""")
    
    # Cleanup
    await cleanup_demo_data(db, USER_ID)
    await db.close()
    print(f"\n[Demo data cleaned up]")


async def run_session_with_simulated_time(
    reflection: Reflection,
    db: CosmosDBDatabase,
    emb_provider: OpenAIEmbeddingProvider,
    user_id: str,
    session: Dict,
    simulated_now: datetime
) -> Dict:
    """Run a session and manually set timestamps to simulated date."""
    from memory.prompts import SESSION_ANALYSIS_WITH_CITATIONS_PROMPT
    
    # Get existing items
    existing_items = await get_insight_items(db, user_id)
    existing_context = build_context_with_ids(existing_items)
    
    # Build session content
    turns_text = "\n".join([f"{role}: {content}" for role, content in session["turns"]])
    full_context = f"{session['summary']}\n\nConversation:\n{turns_text}"
    
    # Build prompt
    prompt = SESSION_ANALYSIS_WITH_CITATIONS_PROMPT.format(
        existing_insights_context=existing_context,
        session_content=full_context
    )
    
    # Call LLM
    try:
        analysis = reflection._call_llm_with_json(
            system_prompt="You are an expert session analysis assistant with memory tracking.",
            user_prompt=prompt,
            output_model=SessionAnalysisWithCitations
        )
    except Exception as e:
        print(f"  Error: {e}")
        return {"session_summary": "Error", "key_topics": [], "new_insights": [], "cited_insight_ids": [], "has_meaningful_content": False}
    
    # Process citations - update access counts WITH simulated time
    cited_ids = []
    for citation in analysis.cited_insights:
        cited_ids.append(citation.insight_id)
        doc = await db.get_by_id(
            container=ContainerType.INSIGHTS,
            document_id=citation.insight_id,
            partition_key=user_id
        )
        if doc and doc.get("insight_type") == "long_term_item":
            doc["access_count"] = doc.get("access_count", 0) + 1
            doc["last_accessed"] = simulated_now.isoformat()
            await db.upsert(
                container=ContainerType.INSIGHTS,
                document=doc,
                partition_key=user_id
            )
    
    # Create new insights WITH simulated timestamps
    id_gen = InsightIdGenerator([item.id for item in existing_items])
    new_insight_items = []
    
    for insight in analysis.new_insights:
        item = LongTermInsightItem(
            id=id_gen.next_id(),
            user_id=user_id,
            insight_text=insight.insight_text,
            category=insight.category,
            confidence=insight.confidence,
            importance=insight.importance,
            date_added=simulated_now,
            last_accessed=simulated_now,
            access_count=0,
            source_session_ids=[session["session_id"]],
        )
        new_insight_items.append(item)
    
    # Store new items
    for item in new_insight_items:
        embedding = emb_provider.get_embedding(item.insight_text)
        item.embedding = embedding
        doc = item.to_dict()
        await db.upsert(
            container=ContainerType.INSIGHTS,
            document=doc,
            partition_key=user_id
        )
    
    return {
        "session_summary": analysis.session_summary,
        "key_topics": analysis.key_topics,
        "new_insights": [i.to_dict() for i in new_insight_items],
        "cited_insight_ids": cited_ids,
        "has_meaningful_content": analysis.has_meaningful_content
    }


if __name__ == "__main__":
    asyncio.run(run_demo())
