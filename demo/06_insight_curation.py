"""
Insight Curation Demo - Contradiction Resolution & Profile Evolution
=====================================================================

This demo showcases how long-term insights are curated over time:
- Outdated information is pruned
- Contradicting insights are resolved
- User profile evolves as new information arrives

Scenario: A user's financial situation and preferences CHANGE over time.
The final session uses REAL LLM responses to prove the profile affects behavior.

Key config: longterm_synthesis_frequency=1 (synthesize after EVERY session)

Run: uv run python demo/06_insight_curation.py
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

USER_ID = "evolving_user_demo"
DB_PATH = str(BASE_DIR / "demo_insight_curation.db")

# Azure OpenAI client for verification session
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
    api_version="2024-10-21"
)
MODEL = os.environ.get("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")


# ============================================================================
# Demo Sessions - User's situation CHANGES over time
# ============================================================================

# Sessions 1-2 are SIMULATED to quickly build profile history
SIMULATED_SESSIONS = [
    {
        "name": "Session 1: Initial Consultation - Risk-Averse Beginner",
        "description": "User is a new graduate, traumatized by 2008, avoids stocks completely",
        "conversation": [
            ("Hi, I'm Alex. I just graduated and started my first job making $55,000.",
             "Welcome Alex! Congratulations on your first job. At $55k, building good financial habits early is key. What are your main financial goals?"),
            
            ("I'm really nervous about investing. I saw my parents lose money in 2008. I want safe investments only.",
             "I completely understand - the 2008 crisis was traumatic for many families. Given your risk aversion, we should focus on: 1) Building an emergency fund, 2) High-yield savings accounts, 3) Very conservative options like bonds or CDs."),
            
            ("Yes, I want to avoid stocks completely. Just bonds and savings accounts for me. No stocks ever.",
             "That's a valid choice, especially starting out. We'll build your foundation with safe, stable investments. Your peace of mind matters most right now."),
        ]
    },
    {
        "name": "Session 2: Two Years Later - Major Life Change",
        "description": "User got promoted, now aggressive, comfortable with volatility",
        "conversation": [
            ("Big update! I got promoted to senior engineer - now making $120,000! I've also saved a year of expenses.",
             "Congratulations Alex! That's incredible progress. With a strong emergency fund and higher income, your financial situation has completely changed. How are you thinking about investing now?"),
            
            ("I've done a lot of research. I want to be AGGRESSIVE now - 90% stocks. I'm young and have 30 years until retirement.",
             "Great reasoning! With your long time horizon and financial security, an aggressive 90% stock allocation makes sense. You can ride out any market volatility. This is quite a shift from where we started!"),
            
            ("Exactly. I'm not scared of market drops anymore. I actually see them as buying opportunities now.",
             "That's a sophisticated mindset! You've completely transformed from someone who avoided stocks entirely to an aggressive growth investor. Your risk tolerance has fundamentally changed."),
        ]
    },
]

# Session 3 is a REAL conversation where the agent must use the evolved profile
VERIFICATION_SCENARIO = {
    "name": "Session 3: Testing if Agent Uses the Profile",
    "description": "Real LLM conversation - agent should know user is NOW aggressive, not conservative",
    "user_message": """I just got a $10,000 bonus. My dad is telling me to put it all in a savings account 
because the market has been volatile lately. He says I should play it safe. What do you think?""",
    "expectation": """The agent should:
- Know Alex is now an AGGRESSIVE investor (90% stocks), NOT conservative
- Know Alex sees market drops as buying opportunities  
- Respectfully disagree with the conservative advice
- Recommend investing the bonus according to Alex's CURRENT risk profile"""
}


# ============================================================================
# Demo Runner
# ============================================================================

async def run_session(memory: AgentMemory, session_data: dict, session_num: int):
    """Run a single session and show the insight evolution."""
    
    print(f"\n{'='*70}")
    print(f"SESSION {session_num}: {session_data['name']}")
    print(f"{'='*70}")
    print(f"Scenario: {session_data['description']}")
    print()
    
    async with memory:
        await memory.start_session()
        
        for user_msg, assistant_msg in session_data["conversation"]:
            print(f"User: {user_msg[:70]}...")
            print(f"Assistant: {assistant_msg[:70]}...")
            print()
            await memory.add_turn(user_msg, assistant_msg)
        
        # End session - triggers reflection AND long-term synthesis (every session)
        result = await memory.end_session()
        
        print(f"\n--- Session {session_num} Analysis ---")
        print(f"Summary: {result.get('session_summary', 'N/A')[:100]}...")
        insights = result.get('insights_extracted', [])
        print(f"New Insights Extracted: {len(insights)}")
        for insight in insights[:3]:
            if isinstance(insight, dict):
                print(f"  - {insight.get('insight', insight.get('insight_text', str(insight)))[:60]}...")
            else:
                print(f"  - {str(insight)[:60]}...")


async def show_longterm_profile(memory: AgentMemory, label: str):
    """Display the current long-term profile."""
    print(f"\n{'='*70}")
    print(f"LONG-TERM PROFILE: {label}")
    print(f"{'='*70}")
    
    async with memory:
        insights = await memory.get_insights(limit=10)
        
        # Find the longterm profile
        for insight in insights:
            if insight.get("id", "").startswith("longterm-"):
                profile = insight.get("insight_text", insight.get("insights", "No profile"))
                print(profile)
                return
        
        # If no longterm, show session insights
        print("No synthesized profile yet. Session insights:")
        for i, insight in enumerate(insights[:5], 1):
            text = insight.get("insight_text", insight.get("insight", str(insight)))
            print(f"  {i}. {text[:80]}...")


async def main():
    print("="*70)
    print("INSIGHT CURATION DEMO")
    print("  Focus: Contradiction Resolution & Profile Evolution")
    print("  Config: longterm_synthesis_frequency=1 (every session)")
    print("="*70)
    print()
    print("This demo shows:")
    print("  1. Session 1: Conservative investor (avoids stocks completely)")
    print("  2. Session 2: CONTRADICTS Session 1 - now aggressive (90% stocks)")
    print("  3. Session 3: REAL LLM test - does the agent know the current profile?")
    print()
    print("The final session proves the profile is actually being used!")
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
    
    # KEY CONFIG: Synthesize long-term insights after EVERY session
    config = AgentMemoryConfig(
        buffer_size=6,
        longterm_synthesis_frequency=1,  # Every session!
    )
    
    memory = AgentMemory(
        user_id=USER_ID,
        openai_client=client,
        db_path=DB_PATH,
        config=config,
    )
    
    # Run simulated sessions to build profile history
    for i, session_data in enumerate(SIMULATED_SESSIONS, 1):
        await run_session(memory, session_data, i)
        await show_longterm_profile(memory, f"After Session {i}")
        print("\n" + "-"*70)
        if i < len(SIMULATED_SESSIONS):
            print(">>> CONTRADICTION coming in next session...")
        print("-"*70 + "\n")
    
    # Now run the REAL verification session
    print("\n" + "="*70)
    print("SESSION 3: VERIFICATION - Real LLM Response")
    print("="*70)
    print(f"Scenario: {VERIFICATION_SCENARIO['description']}")
    print()
    print("EXPECTATION:")
    print(VERIFICATION_SCENARIO['expectation'])
    print()
    print("-"*70)
    
    await run_verification_session(memory)
    
    # Final profile
    await show_longterm_profile(memory, "FINAL")
    
    print("\n" + "="*70)
    print("DEMO COMPLETE")
    print("="*70)
    print("""
If the profile was used correctly, the agent should have:
✓ Known Alex is now AGGRESSIVE (not conservative like Session 1)
✓ Known Alex sees volatility as opportunity
✓ Recommended investing the bonus, not saving it

This proves the long-term profile actually influences agent behavior!
""")


async def run_verification_session(memory: AgentMemory):
    """Run a real LLM conversation to verify the profile is being used."""
    
    async with memory:
        await memory.start_session()
        
        # Get context that includes the long-term profile
        context = await memory.get_context()
        
        print("MEMORY CONTEXT PROVIDED TO AGENT:")
        print("-"*40)
        # Show the context (truncated for display)
        if context:
            print(context[:800] + "..." if len(context) > 800 else context)
        else:
            print("(No context available)")
        print("-"*40)
        print()
        
        # Build the system prompt with memory context
        system_prompt = f"""You are a helpful financial advisor assistant.

IMPORTANT - Here is what you know about this user from previous conversations:
{context}

Use this knowledge to personalize your response. Reference specific details you know about the user.
Be concise but show that you remember their preferences and situation."""

        user_msg = VERIFICATION_SCENARIO['user_message']
        
        print(f"USER: {user_msg}")
        print()
        
        # Get REAL response from LLM
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            max_completion_tokens=500,
        )
        
        assistant_msg = response.choices[0].message.content
        print(f"AGENT (Real LLM Response):")
        print(assistant_msg)
        print()
        
        # Store the turn
        await memory.add_turn(user_msg, assistant_msg)
        await memory.end_session()


if __name__ == "__main__":
    asyncio.run(main())
