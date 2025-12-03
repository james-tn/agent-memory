"""
Demo 1: Financial Advisor with CosmosDB Memory
==============================================

This demo showcases:
- Long-term user insights (risk tolerance, financial goals)
- Session summaries (previous consultation topics)
- Cumulative context (building knowledge across conversations)
- Personalized recommendations based on history
- Multi-session continuity
- New thread with memory retention

Scenario:
- Session 1: User discusses retirement planning, reveals risk profile
- Session 2: (New thread) User asks about investments - agent remembers profile
- Session 3: (New thread) Tax strategies - agent recalls all previous context
"""

import asyncio
import uuid
import os
from azure.identity import AzureCliCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from memory.cosmos_memory_provider_embedded import CosmosMemoryProvider
from memory.provider_config import CosmosMemoryProviderConfig
from memory.config import MemoryConfig
from demo.setup_cosmosdb import get_cosmos_client, get_openai_client
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
print("AZURE_COSMOS_DATABASE_NAME: ",os.getenv("AZURE_COSMOS_DATABASE_NAME"))
def get_401k_contribution_limit(year: int) -> str:
    """Tool: Get 401k contribution limits for a given year."""
    limits = {
        2024: "$23,000 (under 50), $30,500 (50+)",
        2025: "$23,500 (under 50), $31,000 (50+)"
    }
    return limits.get(year, "Information not available for this year")


def get_roth_ira_limit(year: int) -> str:
    """Tool: Get Roth IRA contribution limits."""
    limits = {
        2024: "$7,000 (under 50), $8,000 (50+)",
        2025: "$7,000 (under 50), $8,000 (50+)"
    }
    return limits.get(year, "Information not available for this year")


def calculate_retirement_needs(current_age: int, retirement_age: int, annual_expenses: int) -> str:
    """Tool: Calculate estimated retirement savings needed."""
    years_in_retirement = 90 - retirement_age  # Assume living to 90
    total_needed = annual_expenses * years_in_retirement
    return f"Estimated retirement savings needed: ${total_needed:,} (assuming annual expenses of ${annual_expenses:,} for {years_in_retirement} years)"


async def main() -> None:
    print("=" * 80)
    print("Demo 1: Financial Advisor with Multi-Tier Memory")
    print("=" * 80)
    print()
    
    # Setup
    user_id = f"client_{uuid.uuid4().hex[:8]}"
    cosmos_client = get_cosmos_client()
    openai_client = get_openai_client()
    
    # Configure core memory behavior
    memory_config = MemoryConfig(
        database_name=os.getenv("AZURE_COSMOS_DATABASE_NAME", "agent_memory_db"),
        buffer_size=20,
        active_turns=10,
        trigger_reflection_on_end=True,  # Generate insights at session end
        min_confidence=0.7,  # Insight confidence threshold
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL")
    )
    
    # Configure Agent Framework integration
    provider_config = CosmosMemoryProviderConfig(
        memory_config=memory_config,
        inject_instructions=True,
        inject_messages=True,
        auto_manage_session=True  # Session starts automatically on first agent.run()
    )
    
    # Create memory provider
    memory_provider = CosmosMemoryProvider(
        user_id=user_id,
        memory_config=memory_config,
        cosmos_client=cosmos_client,
        openai_client=openai_client,
        config=provider_config
    )
    
    print(f"Client ID: {user_id}")
    print()
    
    # =========================================================================
    # SESSION 1: Initial Consultation - Build User Profile
    # =========================================================================
    print("─" * 80)
    print("SESSION 1: Initial Retirement Planning Consultation")
    print("─" * 80)
    print()
    
    # Create the agent with CosmosDB memory provider
    # Provider MUST be attached to agent, not thread - agent passes it to threads automatically
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions=(
            "You are a knowledgeable financial advisor specializing in retirement planning. "
            "You provide personalized advice based on each client's unique situation, risk tolerance, "
            "and financial goals. Always remember important details about your clients for future sessions. "
            "Be professional, empathetic, and clear in your explanations."
        ),
        tools=[get_401k_contribution_limit, get_roth_ira_limit, calculate_retirement_needs],
        context_providers=memory_provider,  # Provider attached here
    )
    
    # Create thread - it will automatically get the agent's context provider
    thread = agent.get_new_thread()
    
    # Note: Session starts automatically on first agent.run() (auto_manage_session=True)
    # You still must call end_session_explicit() when done
    
    try:
        # Question 1: Introduce yourself
        query = "Hi, I'm 35 years old and want to start planning for retirement. I currently have $50,000 in savings."
        print(f"👤 Client: {query}")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:200]}...")
        print()
        
        # Question 2: Reveal risk tolerance
        query = "I'm generally conservative with money - I don't like taking big risks. I've never invested in stocks before."
        print(f"👤 Client: {query}")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:200]}...")
        print()
        
        # Question 3: Discuss goals
        query = "I'd like to retire at 65 and maintain my current lifestyle which costs about $60,000 per year."
        print(f"👤 Client: {query}")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:200]}...")
        print()
        
        # Question 4: Current retirement accounts
        query = "I have a 401k through work but I'm only contributing 3%. My employer matches up to 5%."
        print(f"👤 Client: {query}")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:200]}...")
        print()
    finally:
        # End session and trigger reflection
        await memory_provider.end_session_explicit()
    
    print("✅ Session 1 complete - Agent should have learned:")
    print("   - Age: 35, wants to retire at 65")
    print("   - Conservative risk tolerance")
    print("   - Current savings: $50k")
    print("   - Goal: $60k/year in retirement")
    print("   - Underutilizing 401k match")
    print()
    
    # Small delay to simulate time between sessions
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 2: Follow-up - Investment Advice (NEW THREAD)
    # =========================================================================
    print("─" * 80)
    print("SESSION 2: Investment Strategy Discussion (2 weeks later)")
    print("─" * 80)
    print()
    
    # Create new thread (simulating a new conversation)
    # Agent's context provider is automatically attached
    thread = agent.get_new_thread()
    
    # Note: Session starts automatically on first agent.run() (auto_manage_session=True)
    
    try:
        # Question 1: Ask about investments WITHOUT repeating profile
        query = "I've been thinking about your advice. What specific investments would you recommend for me?"
        print(f"👤 Client: {query}")
        print("   [NOTE: New thread - testing if agent remembers conservative risk tolerance]")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:250]}...")
        print()
        
        # Question 2: Ask about Roth IRA
        query = "Should I open a Roth IRA? What's the contribution limit for 2025?"
        print(f"👤 Client: {query}")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:200]}...")
        print()
    finally:
        await memory_provider.end_session_explicit()
    
    print("✅ Session 2 complete - Testing if agent:")
    print("   - Remembered conservative risk profile")
    print("   - Tailored recommendations accordingly")
    print("   - Didn't ask for information already known")
    print()
    
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 3: Tax Strategy (NEW THREAD AGAIN)
    # =========================================================================
    print("─" * 80)
    print("SESSION 3: Tax-Advantaged Strategy (1 month later)")
    print("─" * 80)
    print()
    
    # Create yet another new thread
    # Agent's context provider is automatically attached
    thread = agent.get_new_thread()
    
    # Note: Session starts automatically on first agent.run() (auto_manage_session=True)
    
    try:
        # Question: Tax strategy
        query = "I got a raise! I now make $85,000. How should I adjust my retirement strategy?"
        print(f"👤 Client: {query}")
        print("   [NOTE: Another new thread - testing cumulative memory]")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:250]}...")
        print()
        
        # Follow-up
        query = "What's the maximum I can contribute to my 401k this year?"
        print(f"👤 Client: {query}")
        result = await agent.run(query, thread=thread)
        print(f"💼 Advisor: {result.text[:150]}...")
        print()
    finally:
        await memory_provider.end_session_explicit()
    
    print("✅ Session 3 complete - Testing if agent:")
    print("   - Still remembers client profile from Session 1")
    print("   - Recalls previous advice from Session 2")
    print("   - Provides contextually appropriate recommendations")
    print()
    
    # =========================================================================
    # FINAL STATUS CHECK
    # =========================================================================
    print("=" * 80)
    print("MEMORY SYSTEM STATUS")
    print("=" * 80)
    status = memory_provider.get_status()
    print(f"User ID: {status['user_id']}")
    print(f"Session Active: {status['session_active']}")
    print(f"Configuration:")
    print(f"  - Long-term insights: {status['config']['include_longterm_insights']}")
    print(f"  - Recent sessions: {status['config']['include_recent_sessions']}")
    print(f"  - Cumulative summary: {status['config']['include_cumulative_summary']}")
    print()
    
    print("🎉 Demo Complete!")
    print()
    print("Key Capabilities Demonstrated:")
    print("✓ Long-term user profile retention (age, goals, risk tolerance)")
    print("✓ Session summaries (what was discussed in each meeting)")
    print("✓ Context continuity across new threads")
    print("✓ Personalized recommendations without re-asking questions")
    print("✓ Multi-tier memory: active turns → session summary → long-term insights")


if __name__ == "__main__":
    asyncio.run(main())
