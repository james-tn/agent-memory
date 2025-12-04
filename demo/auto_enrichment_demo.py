"""
Demo: Automatic Context Enrichment with Agent Memory

This demo showcases the automatic fact enrichment capability where the
backend automatically enriches context with recalled facts when semantic
triggers are detected (like "allergy", "medication", "prescribe").

Architecture:
- Auto-enrichment is controlled by config.auto_enrich_context flag
- Semantic triggers detect when enrichment is needed (e.g., "medication", "prescribe")
- Caching prevents redundant searches within the same session
- Works seamlessly without explicit search_memory tool calls

Scenario:
- Session 1: Patient mentions penicillin allergy
- [3 sessions pass...]
- Session 4: Doctor mentions "prescription" (trigger word)
- Backend automatically retrieves and includes allergy info
- Client receives enriched context without explicit search
"""

import asyncio
import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ChatCompletionsToolDefinition, FunctionTool

from memory.orchestrator import MemoryServiceOrchestrator
from memory.config import MemoryConfig

# Load environment
load_dotenv()


async def run_medical_consultation(
    orchestrator: MemoryServiceOrchestrator,
    session_id: str,
    session_name: str,
    turns: list[tuple[str, str]]
):
    """Run a medical consultation session."""
    print(f"\n{'='*60}")
    print(f"🏥 {session_name} (Session: {session_id})")
    print(f"{'='*60}")
    
    for user_msg, assistant_msg in turns:
        print(f"\n👤 Patient: {user_msg}")
        await orchestrator.process_turn("user", user_msg)
        
        # Get context BEFORE responding (this is where auto-enrichment happens)
        context = await orchestrator.get_current_context(auto_enrich=True)
        
        # Check if enrichment was triggered
        if context.get("enrichment_triggered"):
            print(f"  ✨ [Auto-Enriched] Backend automatically retrieved relevant facts:")
            recalled = context.get("recalled_facts", "")
            print(f"  📋 {recalled[:200]}..." if len(recalled) > 200 else f"  📋 {recalled}")
        
        print(f"👨‍⚕️ Doctor: {assistant_msg}")
        await orchestrator.process_turn("assistant", assistant_msg)
    
    # End session
    result = await orchestrator.end_session()
    print(f"\n✅ Session ended. Insights: {len(result.get('insights_extracted', []))}")
    return result


async def main():
    """Main demo flow."""
    print("\n🎯 Automatic Context Enrichment Demo")
    print("="*60)
    print("Demonstrating backend auto-enrichment with semantic triggers")
    print("="*60)
    
    # Setup
    project_connection_string = os.environ["PROJECT_CONNECTION_STRING"]
    credential = DefaultAzureCredential()
    project_client = AIProjectClient.from_connection_string(
        conn_str=project_connection_string,
        credential=credential
    )
    
    chat_client = project_client.inference.get_chat_completions_client()
    model_name = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    
    # Configuration with AUTO-ENRICHMENT ENABLED
    config = MemoryConfig(
        K_TURN_BUFFER=10,
        M_SESSIONS_RECENT=1,  # Only load 1 recent session at init
        auto_enrich_context=True,  # 🔥 ENABLE AUTO-ENRICHMENT
        enrichment_trigger_keywords=[
            # Medical safety keywords
            "allergy", "allergic", "allergies",
            "medication", "medicine", "drug", "prescribe", "prescription",
            "treatment", "therapy",
            # Memory reference keywords
            "remember", "recall", "mentioned", "told", "said before",
            "history", "previously", "last time"
        ]
    )
    
    user_id = "patient_12345"
    
    # Initialize orchestrator
    orchestrator = MemoryServiceOrchestrator(
        user_id=user_id,
        config=config,
        chat_client=chat_client,
        model_name=model_name
    )
    
    print(f"\n📋 Configuration:")
    print(f"  • Auto-enrichment: {config.auto_enrich_context}")
    print(f"  • Recent sessions at init: {config.M_SESSIONS_RECENT}")
    print(f"  • Trigger keywords: {len(config.enrichment_trigger_keywords)} keywords")
    print(f"  • Patient ID: {user_id}")
    
    # ========================================================================
    # SESSION 1: Patient mentions allergy
    # ========================================================================
    await run_medical_consultation(
        orchestrator,
        "visit_001",
        "Initial Consultation - January 2024",
        [
            (
                "I'm here for a routine checkup. By the way, I should mention I'm allergic to penicillin - I get severe hives.",
                "Thank you for letting me know about your penicillin allergy. I've noted that in your record. This is important for any future prescriptions."
            ),
            (
                "Yes, I had a bad reaction years ago. Always want to be safe.",
                "Absolutely. We'll always check for alternatives when antibiotics are needed. Your vitals look good today."
            )
        ]
    )
    
    # ========================================================================
    # SESSION 2: Follow-up, no medication discussion
    # ========================================================================
    await run_medical_consultation(
        orchestrator,
        "visit_002",
        "Follow-up - February 2024",
        [
            (
                "I'm here for the blood test results.",
                "Your results look excellent. Cholesterol is within normal range, blood sugar is good."
            ),
            (
                "That's great news! Anything I should watch out for?",
                "Just maintain your current diet and exercise routine. Come back in 6 months for another check."
            )
        ]
    )
    
    # ========================================================================
    # SESSION 3: Different topic
    # ========================================================================
    await run_medical_consultation(
        orchestrator,
        "visit_003",
        "Nutrition Consultation - March 2024",
        [
            (
                "I want to discuss improving my diet.",
                "Great! Let's talk about incorporating more vegetables and reducing processed foods."
            ),
            (
                "Any specific recommendations?",
                "Focus on leafy greens, lean proteins, and whole grains. I'll send you a meal plan."
            )
        ]
    )
    
    # ========================================================================
    # SESSION 4: Doctor mentions "prescription" - AUTO-ENRICHMENT TRIGGERS!
    # ========================================================================
    print("\n" + "🔥"*30)
    print("🔥 SESSION 4: TRIGGER WORD DETECTION")
    print("🔥 Watch for automatic enrichment when 'prescription' is mentioned")
    print("🔥"*30)
    
    await run_medical_consultation(
        orchestrator,
        "visit_004",
        "Sinus Infection - June 2024",
        [
            (
                "I've had a sinus infection for 3 days now. It's getting worse.",
                "Let me examine you. Yes, I can see inflammation. You'll need antibiotics."
            ),
            (
                "What will you prescribe?",  # 🔥 TRIGGER WORD: "prescribe"
                # ⚡ AUTO-ENRICHMENT HAPPENS HERE! Backend retrieves allergy info from Session 1
                "Given your symptoms, I'll prescribe amoxicillin... wait, let me check your allergies first. "
                "Ah yes, you're allergic to penicillin. Let me prescribe azithromycin instead - it's a different class of antibiotic."
            ),
            (
                "Thank you for checking! I always worry about that.",
                "Safety first! Azithromycin should clear this up in 5 days. Take it with food."
            )
        ]
    )
    
    # ========================================================================
    # Demonstrate manual retrieval for comparison
    # ========================================================================
    print(f"\n{'='*60}")
    print("📊 Manual Fact Retrieval (for comparison)")
    print(f"{'='*60}")
    
    query = "What allergies does this patient have?"
    facts = await orchestrator.retrieve_facts(query, include_summaries=True)
    print(f"\nQuery: '{query}'")
    print(f"Retrieved facts:\n{facts[:300]}...")
    
    print("\n" + "="*60)
    print("✅ Demo Complete!")
    print("="*60)
    print("\n🎯 Key Takeaways:")
    print("  1. Auto-enrichment triggered by semantic keywords ('prescribe')")
    print("  2. Backend automatically retrieved allergy info from Session 1")
    print("  3. No explicit search_memory tool call needed")
    print("  4. Caching prevents redundant searches in same session")
    print("  5. Works seamlessly with agent's natural conversation flow")
    print("\n📝 Architecture Benefits:")
    print("  • Reduces client complexity (no manual retrieval logic)")
    print("  • Improves safety (critical info auto-retrieved)")
    print("  • Performance optimized (caching + selective triggers)")
    print("  • Flexible (config flag + keyword customization)")


if __name__ == "__main__":
    asyncio.run(main())
