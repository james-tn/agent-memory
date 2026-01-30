"""
Demo: Financial Advisor with Direct/Embedded Memory.

This demo shows how to use AgentMemory directly (embedded mode).
Compare with 04_financial_advisor_remote.py for server mode.

Usage:
    uv run python demo/05_financial_advisor_direct.py
"""

import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from openai import AzureOpenAI

from memory import AgentMemory, AgentMemoryConfig
from memory.db import DatabaseType

load_dotenv()


# =============================================================================
# Configuration
# =============================================================================

USER_ID = f"demo-user-{datetime.now().strftime('%H%M%S')}"

SYSTEM_PROMPT = """You are a helpful financial advisor assistant. You provide 
personalized financial guidance based on the user's situation and goals.

Be conversational, ask clarifying questions, and remember details the user shares.
When making recommendations, explain your reasoning clearly.

{memory_context}
"""


# =============================================================================
# Simple Agent
# =============================================================================

class SimpleFinancialAdvisor:
    """Simple agent that uses memory context."""
    
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        )
        self.model = os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
        self.messages = []
    
    def set_context(self, memory_context: str):
        """Set memory context in system prompt."""
        system_msg = SYSTEM_PROMPT.format(
            memory_context=f"\n--- MEMORY CONTEXT ---\n{memory_context}\n---" 
            if memory_context else ""
        )
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = system_msg
        else:
            self.messages.insert(0, {"role": "system", "content": system_msg})
    
    def chat(self, user_message: str) -> str:
        """Send message and get response."""
        self.messages.append({"role": "user", "content": user_message})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            max_completion_tokens=500
        )
        
        assistant_message = response.choices[0].message.content
        self.messages.append({"role": "assistant", "content": assistant_message})
        
        return assistant_message


# =============================================================================
# Scripted Demo
# =============================================================================

async def run_scripted_demo():
    """Run scripted demo for comparison with remote mode."""
    
    print("=" * 70)
    print("💰 Financial Advisor Demo (Direct/Embedded Mode)")
    print("=" * 70)
    print(f"User ID: {USER_ID}")
    print(f"Database: CosmosDB")
    print("=" * 70)
    
    # Test conversation (same as remote demo)
    conversation = [
        "Hi! I'm looking for advice on saving for retirement. I'm 35 years old.",
        "Yes, I have a 401k through my employer. They match up to 6%.",
        "I'm currently contributing 8%, so I'm getting the full match. Should I contribute more?",
        "What about a Roth IRA? Is that something I should consider at my age?",
        "That makes sense. What's the contribution limit for a Roth IRA?",
    ]
    
    # Initialize OpenAI client
    openai_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Create AgentMemory directly (embedded mode)
    config = AgentMemoryConfig(
        auto_manage_sessions=False,
        include_longterm_insights=True,
        include_recent_sessions=True,
        include_cumulative_summary=True,
    )
    
    memory = AgentMemory(
        user_id=USER_ID,
        openai_client=openai_client,
        db_type=DatabaseType.COSMOSDB,
        config=config,
    )
    
    agent = SimpleFinancialAdvisor()
    
    try:
        # Start session
        print("\nStarting session...")
        await memory.start_session()
        print(f"✓ Session started: {memory.session_id[:8]}...")
        
        # Get initial context
        context = memory.get_context()
        agent.set_context(context)
        
        # Run conversation
        print("\n" + "-" * 70)
        for i, user_msg in enumerate(conversation, 1):
            print(f"\n[Turn {i}]")
            print(f"User: {user_msg}")
            
            response = agent.chat(user_msg)
            print(f"Advisor: {response[:200]}...")
            
            result = await memory.add_turn(user_msg, response)
            turn_count = result.get("turn_count", 0)
            print(f"  → Stored (turn {turn_count})")
        
        # Get final context
        print("\n" + "-" * 70)
        context = memory.get_context()
        print(f"\nFinal context:")
        print(context[:500] + "..." if len(context) > 500 else context)
        
        # Search test
        print("\n" + "-" * 70)
        print("\nSearching memory for 'Roth IRA'...")
        results = await memory.search("Roth IRA contribution", top_k=2)
        print(f"Results: {results[:300]}...")
        
        # End session
        print("\n" + "-" * 70)
        print("\nEnding session...")
        end_result = await memory.end_session(trigger_reflection=True)
        
        print(f"\n{'=' * 70}")
        print("✅ Demo Complete!")
        print("=" * 70)
        print(f"Insights extracted: {len(end_result.get('insights', []))}")
        if end_result.get("summary"):
            print(f"Summary: {end_result['summary'][:300]}...")
        
        return True
        
    finally:
        await memory.close()


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    asyncio.run(run_scripted_demo())
