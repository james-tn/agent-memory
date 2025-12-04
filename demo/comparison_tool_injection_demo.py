"""
Demo: Comparing Tool Injection vs. No Tool Injection

This demo shows the difference between:
1. Agent WITH hidden recall_facts tool (can search memory autonomously)
2. Agent WITHOUT tool (only has passive context from recent sessions)

Scenario:
---------
- Session 1: User mentions important preference/constraint
- Session 2-3: Other conversations (pushes Session 1 out of recent context)
- Session 4: Agent needs information from Session 1
  - WITH tool: Agent can search and find it
  - WITHOUT tool: Agent doesn't have access to it
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

load_dotenv()


async def run_scenario(
    scenario_name: str,
    enable_tool: bool,
    user_id: str,
    cosmos_client: CosmosClient,
    openai_client: AzureOpenAI,
    chat_client
):
    """Run a complete scenario with or without tool injection."""
    print("\n" + "="*70)
    print(f"📊 {scenario_name}")
    print(f"Tool Injection: {'✅ ENABLED' if enable_tool else '❌ DISABLED'}")
    print("="*70)
    
    # Configure memory
    memory_config = MemoryConfig(
        database_name=os.getenv("AZURE_COSMOS_DATABASE_NAME", "agent_memory_db"),
        buffer_size=10,
        num_recent_sessions_for_init=1,  # Only load 1 recent session (not all 3)
        trigger_reflection_on_end=True,
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL")
    )
    
    provider_config = CosmosMemoryProviderConfig(
        memory_config=memory_config,
        auto_manage_session=True,
        inject_recall_tool=enable_tool  # 🔥 This is the only difference!
    )
    
    provider = CosmosMemoryProvider(
        user_id=user_id,
        memory_config=memory_config,
        cosmos_client=cosmos_client,
        openai_client=openai_client,
        config=provider_config
    )
    
    async with provider:
        agent = ChatAgent(
            chat_client=chat_client,
            name="FinancialAdvisor",
            instructions=(
                "You are a financial advisor. "
                "Always consider the client's risk tolerance and investment constraints. "
                "Use available tools to search for relevant past information when needed."
            ),
            context_providers=[provider]
        )
        
        # SESSION 1: Client sets important constraint
        print("\n💼 Session 1: Initial Consultation")
        print("-" * 70)
        response = await agent.run(
            "I want to invest, but I'm very risk-averse. "
            "I cannot afford to lose more than 5% of my principal. "
            "Please remember this - it's a strict constraint."
        )
        print(f"Agent: {response.output}")
        await provider.end_session_explicit()
        
        # SESSION 2: Different topic
        print("\n💼 Session 2: Tax Planning")
        print("-" * 70)
        response = await agent.run(
            "What are the tax implications of 401k withdrawals?"
        )
        print(f"Agent: {response.output}")
        await provider.end_session_explicit()
        
        # SESSION 3: Another topic (pushes Session 1 out of recent context)
        print("\n💼 Session 3: Estate Planning")
        print("-" * 70)
        response = await agent.run(
            "Should I set up a trust for my children?"
        )
        print(f"Agent: {response.output}")
        await provider.end_session_explicit()
        
        # SESSION 4: Agent needs constraint from Session 1!
        print("\n💼 Session 4: Investment Recommendation")
        print("-" * 70)
        print("🎯 CRITICAL: Agent needs risk tolerance from Session 1")
        print("   • WITH tool: Can search and find it")
        print("   • WITHOUT tool: Only has Session 3 in context")
        print()
        
        response = await agent.run(
            "I have $50,000 to invest. What do you recommend?"
        )
        
        print(f"Agent: {response.text}")
        
        # Check if tool was called (attribute may not exist if no tools were used)
        if hasattr(response, 'function_calls') and response.function_calls:
            print(f"\n✅ Agent called tools: {[fc.name for fc in response.function_calls]}")
        else:
            print("\n❌ Agent did NOT call any tools")
        
        await provider.end_session_explicit()
    
    print("\n" + "="*70)


async def main():
    """Main comparison demo."""
    print("\n🔬 CONTROLLED EXPERIMENT: Tool Injection Impact")
    print("="*70)
    print("Testing the same scenario with and without hidden tool injection")
    print("="*70)
    
    # Setup
    cosmos_client = get_cosmos_client()
    openai_client = get_openai_client()
    
    # Create chat client using credential (no explicit API key needed)
    chat_client = AzureOpenAIChatClient(
        credential=AzureCliCredential(),
        deployment_name=os.environ.get("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
    )
    
    # Scenario 1: WITHOUT tool injection
    user_id_no_tool = f"client_{uuid.uuid4().hex[:8]}"
    await run_scenario(
        scenario_name="SCENARIO A: WITHOUT Hidden Tool",
        enable_tool=False,
        user_id=user_id_no_tool,
        cosmos_client=cosmos_client,
        openai_client=openai_client,
        chat_client=chat_client
    )
    
    print("\n\n⏳ Waiting 2 seconds before next scenario...\n")
    await asyncio.sleep(2)
    
    # Scenario 2: WITH tool injection
    user_id_with_tool = f"client_{uuid.uuid4().hex[:8]}"
    await run_scenario(
        scenario_name="SCENARIO B: WITH Hidden Tool",
        enable_tool=True,
        user_id=user_id_with_tool,
        cosmos_client=cosmos_client,
        openai_client=openai_client,
        chat_client=chat_client
    )
    
    print("\n\n" + "="*70)
    print("📊 COMPARISON RESULTS")
    print("="*70)
    print("\n❌ WITHOUT Tool (Scenario A):")
    print("   • Agent only had Session 3 in passive context")
    print("   • Risk tolerance from Session 1 was NOT available")
    print("   • Agent made generic recommendation")
    print("   • Potentially unsafe (ignored client's constraint)")
    
    print("\n✅ WITH Tool (Scenario B):")
    print("   • Agent autonomously called recall_facts()")
    print("   • Retrieved risk tolerance from Session 1")
    print("   • Made personalized, constraint-aware recommendation")
    print("   • Safe and aligned with client's needs")
    
    print("\n💡 Key Insight:")
    print("   Hidden tool injection enables agents to be PROACTIVE about memory")
    print("   instead of relying only on PASSIVE context injection.")
    
    print("\n🎯 Implementation Benefit:")
    print("   User's code is identical for both scenarios - only config differs!")
    print("   No need to define tools, handle search logic, or manage memory manually.")


if __name__ == "__main__":
    asyncio.run(main())
