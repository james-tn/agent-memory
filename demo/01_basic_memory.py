"""
Basic Memory Demo - Simplest Usage
===================================

The simplest way to use AgentMemory - no Agent Framework required.
Demonstrates:
- Manual add_turn() and await get_context()
- Automatic buffer management for long conversations
- Semantic search across memory tiers
- Session summaries and insight extraction

Backend: SQLite (zero configuration)

Run: uv run python demo/01_basic_memory.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

from openai import AzureOpenAI
from memory import AgentMemory, AgentMemoryConfig


# ============================================================================
# Configuration
# ============================================================================

USER_ID = "basic_demo_user"
DB_PATH = str(BASE_DIR / "demo_basic.db")


# ============================================================================
# Demo
# ============================================================================

async def main():
    print("=" * 70)
    print("Basic Memory Demo")
    print("  Pattern: Manual add_turn() + await get_context()")
    print("  Backend: SQLite (zero configuration)")
    print("=" * 70)
    print()
    
    # Clean up previous demo
    import time
    for _ in range(5):
        try:
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            break
        except PermissionError:
            time.sleep(0.5)
    
    # Setup OpenAI client
    client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # =========================================================================
    # KEY CONCEPT: Buffer Management
    # =========================================================================
    print("\n" + "=" * 70)
    print("KEY CONCEPT: Automatic Buffer Management")
    print("=" * 70)
    print("""
For long conversations, you can't send all turns to the LLM (context limits).
AgentMemory automatically manages this:

  buffer_size=6     <- Trigger summarization when buffer reaches 6 turns
  active_turns=4    <- Keep last 4 turns after pruning

Example with 10-turn conversation:
  Turns 1-6:  [T1, T2, T3, T4, T5, T6]  <- Buffer full!
  Prune:      [T5, T6] + Summary("T1-T4: discussed X, Y, Z")
  Turns 7-8:  [T5, T6, T7, T8]
  Turns 9-10: [T5, T6, T7, T8, T9, T10] <- Buffer full again!
  Prune:      [T9, T10] + Summary("T1-T8: discussed X, Y, Z, then A, B")

Result: Context is always bounded, older content is compressed.
""")
    
    # Create memory with explicit buffer settings
    config = AgentMemoryConfig(
        buffer_size=6,                        # Prune when buffer hits 6 turns
        active_turns=4,                       # Keep last 4 turns after pruning
        longterm_synthesis_frequency=1,       # Extract insights after each session
    )
    
    memory = AgentMemory(
        user_id=USER_ID,
        openai_client=client,
        db_path=DB_PATH,
        config=config,
    )
    
    # =========================================================================
    # SESSION 1: Long conversation to demonstrate buffer management
    # =========================================================================
    print("\n" + "=" * 70)
    print("SESSION 1: Long Conversation (watch buffer management)")
    print("=" * 70)
    
    # A longer conversation that will trigger buffer pruning
    conversation = [
        ("Hi! I'm looking for book recommendations.", 
         "Hello! I'd be happy to help. What genres interest you?"),
        
        ("I love science fiction, especially hard sci-fi with realistic science.",
         "Great choice! Hard sci-fi is wonderful. Do you prefer space exploration, near-future tech, or something else?"),
        
        ("Space exploration definitely. I'm fascinated by realistic depictions of space travel.",
         "Perfect! I'd recommend 'The Martian' by Andy Weir - incredibly realistic Mars survival. Also 'Seveneves' by Neal Stephenson about orbital mechanics."),
        
        ("I've read The Martian! Loved it. What else?",
         "Since you liked The Martian, try 'Project Hail Mary' also by Weir. For harder science, 'Aurora' by Kim Stanley Robinson is excellent - realistic interstellar travel."),
        
        ("I also enjoy philosophy. Any recommendations there?",
         "For philosophy, 'Meditations' by Marcus Aurelius is timeless Stoic wisdom. 'Godel, Escher, Bach' by Hofstadter blends logic, art, and consciousness."),
        
        ("Do you have any books that combine sci-fi and philosophy?",
         "Absolutely! 'Blindsight' by Peter Watts explores consciousness through alien contact. 'Permutation City' by Greg Egan is about simulated minds and identity."),
        
        ("I prefer longer novels - I like to immerse myself in worlds.",
         "Then you'll love 'Anathem' by Stephenson - long, philosophical, and set in a fascinating alternate world with monk-like scientists."),
        
        ("What about reading format? I usually read before bed.",
         "For bedtime reading, physical books or e-ink readers are best for sleep. Avoid backlit screens. Audiobooks are also great for winding down."),
    ]
    
    async with memory:
        await memory.start_session()
        print(f"Session ID: {memory.session_id[:8]}...")
        print(f"Buffer config: size={config.buffer_size}, active_turns={config.active_turns}")
        print()
        
        for i, (user_msg, assistant_msg) in enumerate(conversation, 1):
            print(f"\n--- Turn {i} ---")
            print(f"User: {user_msg[:50]}...")
            print(f"Assistant: {assistant_msg[:50]}...")
            
            # Add turn - watch for buffer pruning messages!
            await memory.add_turn(user_msg, assistant_msg)
        
        print("\n" + "-" * 70)
        print("BUFFER MANAGEMENT RESULT:")
        print("-" * 70)
        
        # Show what's in context now
        context = await memory.get_context()
        print(f"\nFinal context ({len(context)} chars):")
        print("-" * 40)
        # Show summary portion
        if "### Conversation Summary" in context:
            summary_start = context.find("### Conversation Summary")
            summary_end = context.find("###", summary_start + 1) if "###" in context[summary_start+1:] else len(context)
            print(context[summary_start:summary_end][:500])
        print("-" * 40)
        print("\nNote: Older turns were summarized, recent turns kept verbatim!")
        
        # End session
        result = await memory.end_session()
        print(f"\nSession complete!")
        print(f"  Summary: {result.get('session_summary', 'N/A')[:80]}...")
        print(f"  Insights extracted: {len(result.get('insights_extracted', []))}")
    
    # =========================================================================
    # SESSION 2: Demonstrate cross-session memory
    # =========================================================================
    print("\n" + "=" * 70)
    print("SESSION 2: Cross-Session Memory Recall")
    print("=" * 70)
    
    async with memory:
        await memory.start_session()
        print(f"Session ID: {memory.session_id[:8]}...")
        
        # Get context - should include Session 1 summary
        context = await memory.get_context()
        print(f"\nLoaded context from previous session ({len(context)} chars):")
        print("-" * 40)
        print(context[:600] + "..." if len(context) > 600 else context)
        print("-" * 40)
        
        await memory.end_session()
    
    # =========================================================================
    # Demonstrate semantic search
    # =========================================================================
    print("\n" + "=" * 70)
    print("SEMANTIC SEARCH: Find specific information")
    print("=" * 70)
    
    async with memory:
        # Search for specific topics
        queries = [
            "science fiction book recommendations",
            "philosophy books",
            "reading habits and preferences",
        ]
        
        for query in queries:
            print(f"\nSearching: '{query}'")
            results = await memory.search(
                query, 
                top_k=2,
                search_interactions=True,
                search_insights=True
            )
            print(f"  Found: {results[:200]}..." if len(results) > 200 else f"  Found: {results}")
    
    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("DEMO COMPLETE!")
    print("=" * 70)
    print("""
Key takeaways:

1. add_turn() - Store conversation pairs
2. await get_context() - Get formatted memory for LLM prompts  
3. search() - Find specific information semantically
4. end_session() - Trigger insight extraction

AUTOMATIC BUFFER MANAGEMENT:
- Long conversations don't overflow context
- Older turns are summarized automatically
- Recent turns kept verbatim for accuracy
- Configure with buffer_size and active_turns

NO FRAMEWORK REQUIRED - works with any LLM client!
""")


if __name__ == "__main__":
    asyncio.run(main())
