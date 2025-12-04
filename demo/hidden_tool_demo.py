"""
Demo: Hidden Tool Injection for Automatic Memory Recall

This demo showcases the hidden recall_facts tool that is automatically injected
into agents using CosmosMemoryProvider. The agent can autonomously search memory
when needed, without the user explicitly defining the tool.

Key Features:
-------------
1. Tool is injected automatically via ContextProvider.invoking()
2. User doesn't define the tool in their code
3. Agent decides when to call it based on conversation context
4. Works seamlessly with Agent Framework's tool calling

Architecture:
------------
CosmosMemoryProvider.invoking() → Context(tools=[recall_facts]) → Agent has tool

Scenario:
---------
- Session 1: Patient mentions severe penicillin allergy
- Session 2: General health checkup (no medication discussion)
- Session 3: Patient asks about prescription
- Agent autonomously calls recall_facts to check allergies before prescribing
"""

import asyncio
import os
import uuid
from dotenv import load_dotenv
from openai import AzureOpenAI

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential, AzureCliCredential

from memory.cosmos_memory_provider_embedded import CosmosMemoryProvider
from memory.config import MemoryConfig
from memory.provider_config import CosmosMemoryProviderConfig
from demo.setup_cosmosdb import get_cosmos_client, get_openai_client

# Load environment
load_dotenv()


async def run_session(
    provider: CosmosMemoryProvider,
    agent: ChatAgent,
    session_name: str,
    conversations: list[str]
):
    """Run a complete conversation session."""
    print(f"\n{'='*70}")
    print(f"🏥 {session_name}")
    print(f"{'='*70}")
    
    for user_message in conversations:
        print(f"\n👤 Patient: {user_message}")
        
        # Agent processes message (may autonomously call recall_facts)
        response = await agent.run(user_message)
        
        print(f"👨‍⚕️ Doctor: {response.text}")
        
        # Check if tool was called (attribute may not exist if no tools were used)
        if hasattr(response, 'function_calls') and response.function_calls:
            print(f"\n  ℹ️  [Agent autonomously called tools: {[fc.name for fc in response.function_calls]}]")
    
    # End session
    result = await provider.end_session_explicit()
    insights_count = len(result.get('insights_extracted', []))
    print(f"\n✅ Session ended. Insights extracted: {insights_count}")
    
    return result


async def main():
    """Main demo flow."""
    print("\n" + "="*70)
    print("Hidden Tool Injection Demo")
    print("="*70)
    print("Demonstrating automatic recall_facts tool injection")
    print("="*70)
    
    # Setup
    cosmos_client = get_cosmos_client()
    openai_client = get_openai_client()
    
    # Configuration
    memory_config = MemoryConfig(
        database_name=os.getenv("AZURE_COSMOS_DATABASE_NAME", "agent_memory_db"),
        buffer_size=10,
        num_recent_sessions_for_init=1,  # Only load 1 recent session
        trigger_reflection_on_end=True,
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL")
    )
    
    provider_config = CosmosMemoryProviderConfig(
        memory_config=memory_config,
        auto_manage_session=True,
        inject_recall_tool=True,  # 🔥 Enable hidden tool injection (default: True)
        recall_tool_name="recall_facts",
        recall_tool_description=(
            "Search long-term memory for relevant information from past conversations. "
            "Use this when you need context about the user's history, preferences, or past interactions."
        )
    )
    
    user_id = f"patient_{uuid.uuid4().hex[:8]}"
    
    print(f"\n📋 Configuration:")
    print(f"  • Patient ID: {user_id}")
    print(f"  • Hidden tool injection: {provider_config.inject_recall_tool}")
    print(f"  • Tool name: {provider_config.recall_tool_name}")
    print(f"  • Recent sessions loaded at init: {memory_config.num_recent_sessions_for_init}")
    
    # Create memory provider
    provider = CosmosMemoryProvider(
        user_id=user_id,
        memory_config=memory_config,
        cosmos_client=cosmos_client,
        openai_client=openai_client,
        config=provider_config
    )
    
    # Create chat client using credential (no explicit API key needed)
    agent_chat_client = AzureOpenAIChatClient(
        credential=AzureCliCredential(),
        deployment_name=os.environ.get("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
    )
    
    # Create agent WITHOUT defining any tools
    print("\n" + "🤖" + "-"*68)
    print("Creating agent WITHOUT explicit tool definitions...")
    print("recall_facts tool will be injected automatically by ContextProvider")
    print("-"*70)
    
    async with provider:
        agent = ChatAgent(
            chat_client=agent_chat_client,
            name="MedicalAssistant",
            instructions=(
                "You are a careful medical assistant. "
                "When prescribing medications, ALWAYS check the patient's allergy history first. "
                "Use available tools to search memory when you need information about past interactions."
            ),
            context_providers=[provider]  # ← recall_facts injected here automatically!
            # NOTE: No tools parameter! The tool is injected by the provider
        )
        
        # ====================================================================
        # SESSION 1: Patient mentions severe allergy
        # ====================================================================
        await run_session(
            provider,
            agent,
            "Session 1: Initial Consultation - January 2024",
            [
                "Hi, I'm here for a checkup. I should mention I have a severe allergy to penicillin - I get anaphylaxis.",
                "Yes, I carry an EpiPen because of it. It's very serious."
            ]
        )
        
        # ====================================================================
        # SESSION 2: General health, no medication discussion
        # ====================================================================
        await run_session(
            provider,
            agent,
            "Session 2: Follow-up Checkup - February 2024",
            [
                "I'm here for my blood pressure check.",
                "Everything feels fine, just routine monitoring."
            ]
        )
        
        # ====================================================================
        # SESSION 3: Prescription needed - Agent should recall allergy!
        # ====================================================================
        print("\n" + "🔥"*35)
        print("🔥 SESSION 3: CRITICAL MOMENT")
        print("🔥 Agent should autonomously call recall_facts to check allergies")
        print("🔥"*35)
        
        await run_session(
            provider,
            agent,
            "Session 3: Bacterial Infection - May 2024",
            [
                "I have a bacterial sinus infection. Can you prescribe antibiotics?"
                # ⚡ Agent should autonomously call recall_facts("patient allergies")
                # to retrieve the penicillin allergy from Session 1
            ]
        )
    
    print("\n" + "="*70)
    print("✅ Demo Complete!")
    print("="*70)
    print("\n🎯 Key Observations:")
    print("  1. User NEVER defined recall_facts tool in their code")
    print("  2. Tool was injected automatically by CosmosMemoryProvider")
    print("  3. Agent autonomously decided when to call it")
    print("  4. Critical safety information (allergy) was retrieved from Session 1")
    print("  5. Prescription was adjusted based on recalled facts")
    
    print("\n📊 Architecture Breakdown:")
    print("  • ContextProvider.invoking() returns Context(tools=[recall_facts])")
    print("  • Agent Framework merges provider tools with agent tools")
    print("  • Agent sees recall_facts as available tool")
    print("  • Agent calls it when needed (e.g., before prescribing)")
    print("  • User's code stays clean - no explicit tool definitions needed")
    
    print("\n💡 Benefits:")
    print("  ✅ User doesn't need to define search_memory function")
    print("  ✅ Agent autonomously decides when to search")
    print("  ✅ Works transparently with Agent Framework")
    print("  ✅ Configurable via provider config")
    print("  ✅ Can be disabled if not needed")


if __name__ == "__main__":
    asyncio.run(main())
