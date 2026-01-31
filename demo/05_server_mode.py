"""
Demo: Financial Advisor with Remote Memory Service.

This demo shows how to use the Memory Service API (server mode).
The memory server handles all background processing (reflection, synthesis).

Prerequisites:
1. Start the memory server:
   uv run uvicorn server.main:app --port 8000

2. Run this demo:
   uv run python demo/04_financial_advisor_remote.py
"""

import asyncio
import os
import sys
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from openai import AzureOpenAI

from client import MemoryServiceClient, SessionContext

load_dotenv()


# =============================================================================
# Configuration
# =============================================================================

MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000")
USER_ID = f"demo-user-{datetime.now().strftime('%H%M%S')}"

SYSTEM_PROMPT = """You are a helpful financial advisor assistant. You provide 
personalized financial guidance based on the user's situation and goals.

Be conversational, ask clarifying questions, and remember details the user shares.
When making recommendations, explain your reasoning clearly.

{memory_context}
"""


# =============================================================================
# Simple Agent (uses Azure OpenAI directly)
# =============================================================================

class SimpleFinancialAdvisor:
    """Simple agent that uses memory context from the remote service."""
    
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
        # Reset or update system message
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
# Interactive Demo
# =============================================================================

async def run_interactive_demo():
    """Run interactive demo with remote memory service."""
    
    print("=" * 70)
    print("💰 Financial Advisor Demo (Remote Memory Service)")
    print("=" * 70)
    print(f"Memory Service: {MEMORY_SERVICE_URL}")
    print(f"User ID: {USER_ID}")
    print("=" * 70)
    print()
    print("Commands:")
    print("  /context  - Show current memory context")
    print("  /search   - Search memory for a topic")
    print("  /insights - Show long-term insights")
    print("  /quit     - End session and exit")
    print()
    
    # Initialize agent
    agent = SimpleFinancialAdvisor()
    
    # Connect to memory service
    async with MemoryServiceClient(MEMORY_SERVICE_URL, USER_ID) as memory:
        # Health check
        try:
            health = await memory.health_check()
            print(f"✓ Memory service: {health['status']} ({health['active_sessions']} active sessions)")
        except Exception as e:
            print(f"❌ Memory service unavailable: {e}")
            print("   Start with: uv run uvicorn server.main:app --port 8000")
            return
        
        # Start session
        print("\nStarting session...")
        ctx = await memory.start_session()
        print(f"✓ Session: {ctx.session_id[:8]}...")
        
        # Set initial context
        agent.set_context(ctx.context)
        
        if ctx.context:
            print(f"✓ Loaded memory context ({len(ctx.context)} chars)")
        
        print("\n" + "-" * 70)
        print("Chat with your financial advisor (type /quit to end)")
        print("-" * 70 + "\n")
        
        turn_count = 0
        
        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    cmd = user_input.lower()
                    
                    if cmd == "/quit":
                        print("\nEnding session...")
                        break
                    
                    elif cmd == "/context":
                        ctx = await memory.get_context()
                        print(f"\n--- Memory Context ({ctx.turn_count} turns) ---")
                        print(ctx.context[:1000] if ctx.context else "(empty)")
                        print("---\n")
                        continue
                    
                    elif cmd.startswith("/search"):
                        query = cmd.replace("/search", "").strip() or "retirement savings"
                        print(f"\nSearching for: {query}")
                        results = await memory.search(query, top_k=3)
                        print(f"Results:\n{results}\n")
                        continue
                    
                    elif cmd == "/insights":
                        insights = await memory.get_insights(limit=5)
                        print(f"\n--- Long-term Insights ({len(insights)}) ---")
                        for i, insight in enumerate(insights, 1):
                            print(f"{i}. {insight}")
                        print("---\n")
                        continue
                    
                    else:
                        print("Unknown command. Try /context, /search, /insights, or /quit")
                        continue
                
                # Get agent response
                response = agent.chat(user_input)
                print(f"\nAdvisor: {response}\n")
                
                # Store turn in memory
                result = await memory.store_turn(user_input, response)
                turn_count = result.turn_count
                
                if result.pruning_triggered:
                    print("  [Memory pruned - older turns summarized]")
                    # Get updated context after pruning
                    ctx = await memory.get_context()
                    agent.set_context(ctx.context)
                
            except KeyboardInterrupt:
                print("\n\nInterrupted. Ending session...")
                break
            except Exception as e:
                print(f"\nError: {e}\n")
        
        # End session
        print("\nProcessing session (extracting insights)...")
        end_result = await memory.end_session(trigger_reflection=True)
        
        print(f"\n{'=' * 70}")
        print("Session Summary")
        print("=" * 70)
        print(f"Turns: {turn_count}")
        print(f"Insights extracted: {end_result.insights_count}")
        print(f"Long-term synthesis: {'Yes' if end_result.synthesis_triggered else 'No'}")
        if end_result.summary:
            print(f"\nSummary:\n{end_result.summary[:500]}...")
        print("=" * 70)


# =============================================================================
# Scripted Demo (for testing)
# =============================================================================

async def run_scripted_demo():
    """Run scripted demo for testing."""
    
    print("=" * 70)
    print("💰 Financial Advisor Demo (Scripted Test)")
    print("=" * 70)
    print(f"Memory Service: {MEMORY_SERVICE_URL}")
    print(f"User ID: {USER_ID}")
    print("=" * 70)
    
    # Test conversation
    conversation = [
        "Hi! I'm looking for advice on saving for retirement. I'm 35 years old.",
        "Yes, I have a 401k through my employer. They match up to 6%.",
        "I'm currently contributing 8%, so I'm getting the full match. Should I contribute more?",
        "What about a Roth IRA? Is that something I should consider at my age?",
        "That makes sense. What's the contribution limit for a Roth IRA?",
    ]
    
    agent = SimpleFinancialAdvisor()
    
    async with MemoryServiceClient(MEMORY_SERVICE_URL, USER_ID) as memory:
        # Health check
        try:
            health = await memory.health_check()
            print(f"\n✓ Memory service: {health['status']}")
        except Exception as e:
            print(f"\n❌ Memory service unavailable: {e}")
            return False
        
        # Start session
        ctx = await memory.start_session()
        print(f"✓ Session started: {ctx.session_id[:8]}...")
        agent.set_context(ctx.context)
        
        # Run conversation
        print("\n" + "-" * 70)
        for i, user_msg in enumerate(conversation, 1):
            print(f"\n[Turn {i}]")
            print(f"User: {user_msg}")
            
            response = agent.chat(user_msg)
            print(f"Advisor: {response[:200]}...")
            
            result = await memory.store_turn(user_msg, response)
            print(f"  → Stored (turn {result.turn_count})")
        
        # Get final context
        print("\n" + "-" * 70)
        ctx = await memory.get_context()
        print(f"\nFinal context ({ctx.turn_count} turns):")
        print(ctx.context[:500] + "..." if len(ctx.context) > 500 else ctx.context)
        
        # Search test
        print("\n" + "-" * 70)
        print("\nSearching memory for 'Roth IRA'...")
        results = await memory.search("Roth IRA contribution", top_k=2)
        print(f"Results: {results[:300]}...")
        
        # End session
        print("\n" + "-" * 70)
        print("\nEnding session...")
        end_result = await memory.end_session()
        
        print(f"\n{'=' * 70}")
        print("✅ Demo Complete!")
        print("=" * 70)
        print(f"Insights extracted: {end_result.insights_count}")
        if end_result.summary:
            print(f"Summary: {end_result.summary[:300]}...")
        
        return True


# =============================================================================
# Main
# =============================================================================

async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Financial Advisor Demo")
    parser.add_argument(
        "--scripted", "-s",
        action="store_true",
        help="Run scripted demo instead of interactive"
    )
    args = parser.parse_args()
    
    if args.scripted:
        success = await run_scripted_demo()
        sys.exit(0 if success else 1)
    else:
        await run_interactive_demo()


if __name__ == "__main__":
    asyncio.run(main())
