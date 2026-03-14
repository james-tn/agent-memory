"""
Agent-Driven Memory Demo
=========================

This demo showcases an alternative memory pattern where the AGENT decides
when to search memory, rather than having the context provider automatically
inject recalled facts.

Two Approaches Compared:
------------------------

1. MANAGED CONTEXT (demos 01-05):
   - Context provider calls `before_run()` before each turn
   - System automatically decides when to search memory (LLM or keyword detection)
   - Agent receives pre-enriched context
   - Agent is passive - doesn't control memory access

2. AGENT-DRIVEN (this demo):
   - Agent has explicit `search_memory` tool
   - Agent decides WHEN to search based on conversation needs
   - No automatic context enrichment
   - Agent is in control of its own memory retrieval

When to use Agent-Driven:
-------------------------
- When you want the agent to reason about memory needs
- When automatic enrichment adds too much noise/latency
- When memory searches are expensive (CosmosDB, many sessions)
- When you want transparent memory access (visible tool calls)
- For agents that need to explain their reasoning

Run: uv run python demo/06_agent_driven_memory.py
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

from azure.identity import DefaultAzureCredential
from agent_framework import Agent, tool
from agent_framework.azure import AzureOpenAIChatClient
from openai import AzureOpenAI

from memory import AgentMemory, AgentMemoryConfig


# ============================================================================
# Configuration
# ============================================================================

USER_ID = "patient_demo"
DB_PATH = "demo_agent_driven_memory.db"


# ============================================================================
# Memory Tool Factory
# ============================================================================

def create_memory_tools(memory: AgentMemory):
    """
    Create memory tools that the agent can use to search its memory.
    
    These tools give the agent explicit control over when to access memory,
    rather than having context automatically injected.
    """
    
    @tool(
        name="search_memory",
        description=(
            "Search long-term memory for information from past conversations with this patient. "
            "Use this tool when you need to recall: allergies, medications, medical history, "
            "preferences, or anything discussed in previous sessions. "
            "Always search before prescribing medications or making recommendations that "
            "depend on patient history."
        )
    )
    async def search_memory(
        query: Annotated[str, "What to search for in patient history (e.g., 'allergies', 'medications', 'blood pressure history')"]
    ) -> str:
        """Search the patient's medical history in long-term memory."""
        print(f"\n  🔍 [Agent Tool] search_memory('{query}')")
        
        try:
            result = await memory.search(
                query,
                top_k=5,
                search_interactions=True,
                search_insights=True,
                search_summaries=True
            )
            
            if result and result.strip():
                print(f"  ✓ Found {len(result)} chars of relevant information")
                return result
            else:
                return "No relevant information found in patient history."
                
        except Exception as e:
            print(f"  ⚠ Search error: {e}")
            return f"Unable to search memory: {e}"
    
    @tool(
        name="get_patient_profile",
        description=(
            "Get the patient's long-term profile including known preferences, conditions, "
            "and important medical information synthesized from all past sessions."
        )
    )
    async def get_patient_profile() -> str:
        """Get the synthesized patient profile from long-term insights."""
        print(f"\n  📋 [Agent Tool] get_patient_profile()")
        
        try:
            insights = await memory.get_insights(limit=10)
            
            if not insights:
                return "No patient profile available yet. This may be a new patient."
            
            # Format insights into a readable profile
            profile_parts = ["## Patient Profile\n"]
            for insight in insights:
                text = insight.get('insight_text', '')
                category = insight.get('category', 'general')
                confidence = insight.get('confidence', 0)
                if text:
                    profile_parts.append(f"- [{category}] {text} (confidence: {confidence:.0%})")
            
            result = "\n".join(profile_parts)
            print(f"  ✓ Retrieved profile with {len(insights)} insights")
            return result
            
        except Exception as e:
            print(f"  ⚠ Profile error: {e}")
            return f"Unable to retrieve patient profile: {e}"
    
    return [search_memory, get_patient_profile]


# ============================================================================
# Demo Session Runner
# ============================================================================

async def run_session(agent: Agent, memory: AgentMemory, queries: list[str], session_name: str):
    """Run a conversation session."""
    print(f"\n{'='*70}")
    print(f"🏥 SESSION: {session_name}")
    print(f"{'='*70}")
    
    await memory.start_session()
    print(f"Session ID: {memory.session_id[:8]}...")
    
    for query in queries:
        print(f"\n👤 Patient: {query}")
        
        # Run the agent - it will decide if it needs to search memory
        response = await agent.run(query)
        
        # Show response (truncated)
        response_text = response.text[:400] + "..." if len(response.text) > 400 else response.text
        print(f"\n👨‍⚕️ Doctor: {response_text}")
    
    # End session
    result = await memory.end_session()
    print(f"\n✅ Session complete")
    print(f"   Summary: {result.get('session_summary', 'N/A')[:80]}...")
    print(f"   Insights extracted: {len(result.get('insights_extracted', []))}")


async def main():
    """Run the agent-driven memory demo."""
    print("=" * 70)
    print("🧠 Agent-Driven Memory Demo")
    print("   Pattern: Agent decides when to search memory (via tools)")
    print("   Context: Minimal passive injection")
    print("   Backend: SQLite")
    print("=" * 70)
    print()
    print("💡 Key difference from managed context:")
    print("   - Agent has explicit search_memory and get_patient_profile tools")
    print("   - No automatic context enrichment on each turn")
    print("   - Agent reasons about when memory access is needed")
    print("   - Memory searches are visible as tool calls")
    print()
    
    # Clean up previous demo (with retry for Windows file locks)
    import time
    for _ in range(5):
        try:
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            break
        except PermissionError:
            time.sleep(0.5)
    
    # =========================================================================
    # Setup
    # =========================================================================
    
    openai_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # IMPORTANT: Disable auto-enrichment - agent will search manually
    config = AgentMemoryConfig(
        # Disable automatic context enrichment
        auto_enrich_context=False,  # Agent controls memory access via tools

        # Session management
        auto_manage_sessions=False,
        longterm_synthesis_frequency=1,
    )
    
    memory = AgentMemory(
        user_id=USER_ID,
        openai_client=openai_client,
        db_path=DB_PATH,
        config=config,
    )
    
    # Create memory tools
    memory_tools = create_memory_tools(memory)
    
    # Create chat client
    credential = DefaultAzureCredential()
    chat_client = AzureOpenAIChatClient(
        credential=credential,
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        deployment_name=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
    )
    
    # Create agent with memory tools
    agent = Agent(
        client=chat_client,
        instructions="""You are a careful, thorough medical doctor.

CRITICAL SAFETY RULES:
1. Before prescribing ANY medication, you MUST search the patient's memory for allergies
2. Use search_memory to check for drug allergies, current medications, and contraindications
3. Use get_patient_profile to understand the patient's overall medical context
4. Never assume - always verify critical information from memory

When a patient asks for medication:
1. First, call search_memory("allergies medications") to check for allergies
2. Only after confirming no allergies, recommend a medication
3. Explain why you checked their history

Be thorough, safety-conscious, and explain your reasoning.""",
        tools=memory_tools,  # Explicit memory access tools
        context_providers=[memory],  # Minimal context (session summary only)
    )
    
    try:
        # =====================================================================
        # SESSION 1: Initial Consultation - Allergy Disclosure
        # =====================================================================
        print("\n" + "🔴" * 35)
        print("SESSION 1: Patient discloses critical allergy")
        print("Watch: Agent should store this for future sessions")
        print("🔴" * 35)
        
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Initial Consultation",
            queries=[
                "Hi doctor, I'm here for my annual checkup.",
                "I should mention - I have a severe allergy to penicillin. Last time I took it I had anaphylaxis and needed an EpiPen.",
                "Yes, I always carry an EpiPen now. Is there anything else you need to know about my history?",
            ]
        )
        
        await asyncio.sleep(1)
        
        # =====================================================================
        # SESSION 2: Routine Follow-up (No Allergy Discussion)
        # =====================================================================
        print("\n" + "🟡" * 35)
        print("SESSION 2: Routine follow-up (allergy NOT mentioned)")
        print("Watch: Agent may or may not search memory - not critical")
        print("🟡" * 35)
        
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Routine Follow-up",
            queries=[
                "I'm back for my blood pressure check.",
                "Everything feels fine, just routine monitoring.",
            ]
        )
        
        await asyncio.sleep(1)
        
        # =====================================================================
        # SESSION 3: CRITICAL - Antibiotic Request
        # =====================================================================
        print("\n" + "🚨" * 35)
        print("SESSION 3: Patient needs antibiotic!")
        print("CRITICAL: Agent MUST search memory for allergies before prescribing!")
        print("The penicillin allergy was mentioned in Session 1, NOT in this session!")
        print("🚨" * 35)
        
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Bacterial Infection",
            queries=[
                "Doctor, I have a really bad sinus infection. I think I need antibiotics.",
                # Note: Patient does NOT mention the allergy - agent must search memory!
            ]
        )
        
        # =====================================================================
        # Show Final State
        # =====================================================================
        print(f"\n{'='*70}")
        print("📊 FINAL MEMORY STATE")
        print(f"{'='*70}")
        
        await memory.start_session()
        
        insights = await memory.get_insights()
        print(f"\n💡 Stored Insights: {len(insights)}")
        for insight in insights[:5]:
            text = insight.get('insight_text', '')[:70]
            category = insight.get('category', 'unknown')
            print(f"   [{category}] {text}...")
        
        sessions = await memory.get_sessions()
        print(f"\n📅 Sessions: {len(sessions)}")
        for s in sessions:
            summary = s.get('summary', '')[:60]
            print(f"   • {summary}...")
        
        # Show what a memory search returns
        print(f"\n🔍 Manual search for 'allergy':")
        result = await memory.search("patient allergies medications")
        print(f"   {result[:300]}...")
        
        await memory.end_session()
        
    finally:
        await memory.close()
        
        # Clean up
        import time
        for _ in range(3):
            try:
                if os.path.exists(DB_PATH):
                    os.remove(DB_PATH)
                    print(f"\n🧹 Cleaned up: {DB_PATH}")
                break
            except PermissionError:
                time.sleep(0.5)
    
    print(f"\n{'='*70}")
    print("✅ Demo Complete!")
    print()
    print("🎯 What to observe:")
    print("   1. Session 1: Agent learns about penicillin allergy")
    print("   2. Session 2: Routine - agent may not need to search")
    print("   3. Session 3: Agent SHOULD call search_memory before prescribing")
    print("      - If it searched: ✅ Safe! Found the allergy")
    print("      - If it didn't: ⚠️  Potential safety issue!")
    print()
    print("💡 This pattern gives agents explicit control over memory,")
    print("   making memory access visible and reasoned.")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
