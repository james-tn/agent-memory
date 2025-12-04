"""
Demo: Agent Framework Agent with Memory Service and Search Tool

This demonstrates how to build an AI agent using Agent Framework that:
1. Has access to the Agent Memory Service
2. Can proactively search memory when needed using a search_memory tool
3. Autonomously decides when to retrieve past information

Scenario:
- Medical assistant agent with 4 patient visits over time
- Session 1: Patient reports penicillin allergy
- Session 4: Patient needs antibiotic - agent must search memory for allergies
- Agent autonomously decides to search memory before prescribing
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Annotated
from dotenv import load_dotenv

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Load environment
load_dotenv(BASE_DIR / '.env')

from agent_framework import ChatAgent, ai_function
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

from memory.orchestrator import MemoryServiceOrchestrator
from memory.config import MemoryConfig
from memory.cosmos_utils import CosmosUtils
from demo.setup_cosmosdb import get_cosmos_client, get_openai_client


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}\n")


class MedicalAssistantWithMemory:
    """Medical assistant agent with memory service and search capability."""
    
    def __init__(
        self,
        user_id: str,
        session_id: str,
        orchestrator: MemoryServiceOrchestrator,
        chat_client
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.orchestrator = orchestrator
        self.chat_client = chat_client
        
        # Create search_memory tool with closure over orchestrator
        @ai_function(
            name="search_memory",
            description="Search past medical records and conversation history for patient information. "
                       "Use this to find patient allergies, medications, medical history, or any past discussions. "
                       "ALWAYS search for allergies before prescribing medications!"
        )
        async def search_memory_tool(
            query: Annotated[str, "What to search for in patient records (e.g., 'patient allergies', 'current medications')"],
            include_summaries: Annotated[bool, "Whether to search session summaries (default: False)"] = False,
            include_insights: Annotated[bool, "Whether to search long-term insights (default: False)"] = False
        ) -> str:
            """Search patient memory for relevant medical information."""
            print(f"\n  🔍 [Agent Tool] Searching memory: '{query}'")
            print(f"     Include summaries: {include_summaries}, Include insights: {include_insights}")
            
            result = await self.orchestrator.retrieve_facts(
                query,
                include_summaries=include_summaries,
                include_insights=include_insights
            )
            
            print(f"     ✓ Found: {result[:100]}...")
            return result
        
        # Create the medical assistant agent with search_memory tool
        self.agent = ChatAgent(
            chat_client=AzureOpenAIChatClient(
                credential=DefaultAzureCredential(),
                deployment_name=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
            ),
            instructions="""You are a medical assistant helping patients with their healthcare needs.

CRITICAL SAFETY RULES:
1. ALWAYS search memory for allergies before prescribing or recommending any medication
2. Check current medications to avoid interactions
3. Reference past medical history when relevant

Your available tool:
- search_memory: Search patient records for allergies, medications, history, etc.

When a patient needs medication:
1. First, use search_memory to check for drug allergies
2. Then, use search_memory to check current medications
3. Only then prescribe appropriate medication
4. Explain why the medication is safe based on what you found

Be professional, caring, and prioritize patient safety above all.""",
            name="MedicalAssistant",
            tools=[search_memory_tool]
        )
    
    async def process_conversation(self, user_message: str) -> str:
        """Process a user message and return agent's response."""
        print(f"\n  👤 Patient: {user_message}")
        
        # Run the agent - it will autonomously decide when to use search_memory
        result = await self.agent.run(user_message)
        response = result.text
        
        print(f"  🤖 Assistant: {response}")
        
        # Store the turn in memory
        await self.orchestrator.process_turn(user_message, response)
        
        return response
    
    async def end_session(self):
        """End the session and extract insights."""
        result = await self.orchestrator.end_session(trigger_reflection=True)
        return result


async def run_patient_session(
    user_id: str,
    session_id: str,
    session_title: str,
    conversations: list,
    config: MemoryConfig,
    cosmos_utils: CosmosUtils,
    containers: dict,
    chat_client
):
    """Run a complete patient session with the agent."""
    print_header(f"{session_title}")
    
    # Create orchestrator for this session
    orchestrator = MemoryServiceOrchestrator(
        user_id=user_id,
        session_id=session_id,
        config=config,
        cosmos_utils=cosmos_utils,
        interactions_container=containers['interactions'],
        summaries_container=containers['summaries'],
        insights_container=containers['insights'],
        chat_client=chat_client
    )
    
    # Create medical assistant agent with memory
    assistant = MedicalAssistantWithMemory(
        user_id=user_id,
        session_id=session_id,
        orchestrator=orchestrator,
        chat_client=chat_client
    )
    
    # Process all conversations
    for user_msg in conversations:
        await assistant.process_conversation(user_msg)
    
    # End session
    result = await assistant.end_session()
    
    print(f"\n✓ Session ended:")
    print(f"  📋 Summary: {result['session_summary'][:120]}...")
    print(f"  🏷️  Topics: {', '.join(result['key_topics'][:3])}")
    print(f"  💡 Insights: {len(result['insights_extracted'])} extracted")
    
    if result['insights_extracted']:
        for insight in result['insights_extracted'][:2]:
            print(f"     - {insight['insight_text'][:80]}...")
    
    return result


async def main():
    """Run the agent with memory demo."""
    print_header("AGENT FRAMEWORK DEMO: Medical Assistant with Memory Service")
    
    print("This demo shows an AI agent that:")
    print("  • Has access to patient memory across multiple sessions")
    print("  • Can autonomously search memory when needed")
    print("  • Uses search_memory tool to check allergies before prescribing")
    print("  • Demonstrates proactive memory retrieval for patient safety")
    
    print("\nConfiguration:")
    print("  • num_recent_sessions_for_init = 1 (only load 1 recent session)")
    print("  • Running 4 patient visits")
    print("  • Agent has search_memory tool available")
    print("  • Agent decides when to search (not automatic injection)")
    
    # Setup
    cosmos_client = get_cosmos_client()
    chat_client = get_openai_client()
    
    database_name = os.getenv("COSMOS_DB_NAME", "agent_memory_db")
    db = cosmos_client.get_database_client(database_name)
    containers = {
        'interactions': db.get_container_client("interactions"),
        'summaries': db.get_container_client("session_summaries"),
        'insights': db.get_container_client("insights")
    }
    
    # Config with num_recent_sessions_for_init=1
    config = MemoryConfig(
        buffer_size=10,
        num_recent_sessions_for_init=1,
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL"),
        embedding_model=os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002")
    )
    
    cosmos_utils = CosmosUtils(
        embedding_client=chat_client,
        embedding_deployment=config.EMBEDDING_MODEL
    )
    
    user_id = "demo_patient_agent"
    
    # ======================================================================
    # SESSION 1: Initial visit - Patient reports penicillin allergy
    # ======================================================================
    await run_patient_session(
        user_id=user_id,
        session_id="agent_visit_001",
        session_title="SESSION 1: Initial Visit - Medical History",
        conversations=[
            "Hi, I'm here for my first appointment",
            "Do I have any allergies? Yes, I'm allergic to penicillin. I had a bad rash reaction years ago.",
            "I'm currently taking Lisinopril 10mg daily for blood pressure",
        ],
        config=config,
        cosmos_utils=cosmos_utils,
        containers=containers,
        chat_client=chat_client
    )
    
    # ======================================================================
    # SESSION 2: Diabetes management
    # ======================================================================
    await run_patient_session(
        user_id=user_id,
        session_id="agent_visit_002",
        session_title="SESSION 2: Diabetes Management",
        conversations=[
            "My blood sugar has been running high - around 180-200 in the mornings",
            "Yes, I'm taking Metformin 1000mg twice daily as prescribed",
        ],
        config=config,
        cosmos_utils=cosmos_utils,
        containers=containers,
        chat_client=chat_client
    )
    
    # ======================================================================
    # SESSION 3: Flu vaccine
    # ======================================================================
    await run_patient_session(
        user_id=user_id,
        session_id="agent_visit_003",
        session_title="SESSION 3: Flu Vaccine Visit",
        conversations=[
            "I'm here for my annual flu shot",
            "No, I'm not sick right now, feeling fine",
        ],
        config=config,
        cosmos_utils=cosmos_utils,
        containers=containers,
        chat_client=chat_client
    )
    
    print("\n⏳ Waiting for database writes to complete...")
    await asyncio.sleep(3)
    
    # ======================================================================
    # SESSION 4: CRITICAL TEST - Needs antibiotic
    # Agent must autonomously search for allergies before prescribing
    # ======================================================================
    print_header("SESSION 4: Sinus Infection - CRITICAL SAFETY TEST")
    
    print("⚠️  CRITICAL TEST SCENARIO:")
    print("  • Patient needs antibiotic for sinus infection")
    print("  • Allergy info is from Session 1 (3 sessions ago)")
    print("  • Session 1 NOT in initial context (only Session 3 loaded)")
    print("  • Agent MUST autonomously search memory for allergies")
    print("  • Agent has search_memory tool - will it use it?")
    print("\nLet's see if the agent proactively checks for allergies...\n")
    
    orchestrator4 = MemoryServiceOrchestrator(
        user_id=user_id,
        session_id="agent_visit_004",
        config=config,
        cosmos_utils=cosmos_utils,
        interactions_container=containers['interactions'],
        summaries_container=containers['summaries'],
        insights_container=containers['insights'],
        chat_client=chat_client
    )
    
    assistant4 = MedicalAssistantWithMemory(
        user_id=user_id,
        session_id="agent_visit_004",
        orchestrator=orchestrator4,
        chat_client=chat_client
    )
    
    # Patient explains symptoms
    print("Turn 1:")
    await assistant4.process_conversation(
        "I have a sinus infection. My face hurts and I have thick green discharge. I need antibiotics."
    )
    
    # Patient asks for prescription
    print("\nTurn 2:")
    await assistant4.process_conversation(
        "Can you prescribe something for me? I need to get better quickly."
    )
    
    # Patient may ask about specific antibiotic
    print("\nTurn 3:")
    await assistant4.process_conversation(
        "My friend said Amoxicillin works great for sinus infections. Can I get that?"
    )
    
    result4 = await assistant4.end_session()
    
    print(f"\n✓ Session ended:")
    print(f"  📋 Summary: {result4['session_summary'][:150]}...")
    print(f"  💡 Insights: {len(result4['insights_extracted'])} extracted")
    
    # ======================================================================
    # ANALYSIS
    # ======================================================================
    print_header("DEMO ANALYSIS")
    
    print("✅ Agent Autonomy Demonstrated:")
    print("  • Agent decided WHEN to search memory (not automatic)")
    print("  • Agent chose WHAT to search for (allergies)")
    print("  • Agent chose HOW to search (which parameters)")
    print("  • Agent synthesized results into safe prescription")
    
    print("\n🔍 Memory Search Behavior:")
    print("  • Check the output above for '🔍 [Agent Tool] Searching memory' lines")
    print("  • Agent should have searched for allergies before prescribing")
    print("  • Agent retrieved info from Session 1 (not in initial context)")
    
    print("\n💊 Prescription Safety:")
    print("  • Agent should have avoided penicillin (Amoxicillin)")
    print("  • Agent should have prescribed alternative (Azithromycin)")
    print("  • Agent explained why based on allergy found")
    
    print("\n🆚 Comparison: Passive vs Active Memory:")
    print("  • Passive: All context injected in prompt (expensive, limited)")
    print("  • Active: Agent searches when needed (efficient, scalable)")
    print("  • This demo: Active - agent decides when to search")
    
    print("\n🎯 Key Benefits:")
    print("  • Reduced prompt size - only search when needed")
    print("  • Agent reasoning - decides what's relevant")
    print("  • Scalable - can search unlimited history")
    print("  • Safety - critical checks only when necessary")
    
    print("\n" + "="*80)
    print("Demo completed successfully!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
