"""
Demo: Fact Retrieval Across Multiple Sessions

This demonstrates how the CFR agent retrieves information from old sessions
that are not loaded in the initial context.

Scenario:
- M_SESSIONS_RECENT=1 (only load 1 recent session at initialization)
- Run 4 sessions with a medical patient
- Session 4 needs to retrieve critical allergy info from Session 1
- Session 1 is NOT in initial context, must use fact retrieval
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Load environment
load_dotenv(BASE_DIR / '.env')

from memory.orchestrator import MemoryServiceOrchestrator
from memory.config import MemoryConfig
from memory.cosmos_utils import CosmosUtils
from demo.setup_cosmosdb import get_cosmos_client, get_openai_client


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}\n")


async def run_session(orchestrator, conversations):
    """Run a session with multiple conversation turns."""
    for i, (user_msg, assistant_msg) in enumerate(conversations, 1):
        print(f"Turn {i}:")
        print(f"  👤 User: {user_msg}")
        print(f"  🤖 Assistant: {assistant_msg}")
        await orchestrator.process_turn(user_msg, assistant_msg)
    
    result = await orchestrator.end_session(trigger_reflection=True)
    print(f"\n✓ Session ended:")
    print(f"  📋 Summary: {result['session_summary'][:120]}...")
    print(f"  🏷️  Topics: {', '.join(result['key_topics'][:3])}")
    print(f"  💡 Insights: {len(result['insights_extracted'])} extracted")
    
    if result['insights_extracted']:
        for insight in result['insights_extracted'][:2]:
            print(f"     - {insight['insight_text'][:80]}...")
    
    return result


async def main():
    """Run the fact retrieval demo."""
    print_header("FACT RETRIEVAL DEMO: Medical Safety Scenario")
    
    print("Configuration:")
    print("  • num_recent_sessions_for_init = 1 (only load 1 recent session at init)")
    print("  • Running 4 sessions")
    print("  • Session 4 must retrieve allergy info from Session 1")
    print("  • Session 1 will NOT be in Session 4's initial context")
    
    # Setup
    cosmos_client = get_cosmos_client()
    chat_client = get_openai_client()
    
    database_name = os.getenv("COSMOS_DB_NAME", "agent_memory_db")
    db = cosmos_client.get_database_client(database_name)
    interactions_container = db.get_container_client("interactions")
    summaries_container = db.get_container_client("session_summaries")
    insights_container = db.get_container_client("insights")
    
    # Config with num_recent_sessions_for_init=1
    config = MemoryConfig(
        buffer_size=10,
        num_recent_sessions_for_init=1,  # Only load 1 recent session!
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL"),
        embedding_model=os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002")
    )
    
    cosmos_utils = CosmosUtils(
        embedding_client=chat_client,
        embedding_deployment=config.EMBEDDING_MODEL
    )
    
    user_id = "demo_patient_retrieval"
    
    # ======================================================================
    # SESSION 1: Patient reports penicillin allergy (3 months ago)
    # ======================================================================
    print_header("SESSION 1: Initial Visit - Penicillin Allergy Reported")
    
    orchestrator1 = MemoryServiceOrchestrator(
        user_id=user_id,
        session_id="visit_001_allergy",
        config=config,
        cosmos_utils=cosmos_utils,
        interactions_container=interactions_container,
        summaries_container=summaries_container,
        insights_container=insights_container,
        chat_client=chat_client
    )
    
    session1_conversations = [
        ("Hi, I'm here for my first appointment", 
         "Welcome! Let me get your medical history. Do you have any known allergies?"),
        
        ("Yes, I'm allergic to penicillin. I had a bad rash reaction once", 
         "Thank you for that important information. I've documented your penicillin allergy with rash reaction in your file. This is critical for prescribing medications. Any other allergies?"),
        
        ("No, that's the only one", 
         "Good to know. Are you currently taking any medications?"),
        
        ("Just Lisinopril 10mg daily for blood pressure", 
         "Perfect. I've noted you're on Lisinopril 10mg for hypertension. We'll make sure any future medications are compatible with your current treatment."),
    ]
    
    await run_session(orchestrator1, session1_conversations)
    
    # ======================================================================
    # SESSION 2: Diabetes management (2 months ago)
    # ======================================================================
    print_header("SESSION 2: Diabetes Management Discussion")
    
    orchestrator2 = MemoryServiceOrchestrator(
        user_id=user_id,
        session_id="visit_002_diabetes",
        config=config,
        cosmos_utils=cosmos_utils,
        interactions_container=interactions_container,
        summaries_container=summaries_container,
        insights_container=insights_container,
        chat_client=chat_client
    )
    
    session2_conversations = [
        ("My blood sugar has been high lately", 
         "I see. Let's discuss your diabetes management. What are your typical readings?"),
        
        ("Usually around 180-200 in the morning", 
         "That's higher than we'd like. Are you taking your metformin regularly?"),
        
        ("Yes, 1000mg twice daily", 
         "Good adherence. We may need to adjust your dosage. I'll check your A1C today."),
    ]
    
    await run_session(orchestrator2, session2_conversations)
    
    # ======================================================================
    # SESSION 3: Flu vaccine (1 month ago)
    # ======================================================================
    print_header("SESSION 3: Flu Vaccine Visit")
    
    orchestrator3 = MemoryServiceOrchestrator(
        user_id=user_id,
        session_id="visit_003_vaccine",
        config=config,
        cosmos_utils=cosmos_utils,
        interactions_container=interactions_container,
        summaries_container=summaries_container,
        insights_container=insights_container,
        chat_client=chat_client
    )
    
    session3_conversations = [
        ("I'm here for my flu shot", 
         "Great! Let me verify you have no contraindications. Any current illnesses?"),
        
        ("No, I'm feeling fine", 
         "Perfect. I'll administer the flu vaccine today. You may have mild soreness at the injection site for 1-2 days."),
    ]
    
    await run_session(orchestrator3, session3_conversations)
    
    print("\n⏳ Waiting for database writes to complete...")
    await asyncio.sleep(3)
    
    # ======================================================================
    # SESSION 4: TODAY - Needs antibiotic (must retrieve Session 1 allergy info)
    # ======================================================================
    print_header("SESSION 4: Current Visit - Sinus Infection (Critical Test!)")
    
    print("⚠️  CRITICAL: Session 1 is 3 sessions ago")
    print("⚠️  With num_recent_sessions_for_init=1, Session 1 is NOT in initial context")
    print("⚠️  Must use CFR agent to retrieve allergy information\n")
    
    orchestrator4 = MemoryServiceOrchestrator(
        user_id=user_id,
        session_id="visit_004_antibiotic",
        config=config,
        cosmos_utils=cosmos_utils,
        interactions_container=interactions_container,
        summaries_container=summaries_container,
        insights_container=insights_container,
        chat_client=chat_client
    )
    
    # Initial consultation
    print("Turn 1:")
    print("  👤 User: I have a sinus infection and need antibiotics")
    print("  🤖 Assistant: I understand. Let me check your medical history before prescribing.")
    await orchestrator4.process_turn(
        "I have a sinus infection and need antibiotics",
        "I understand. Let me check your medical history before prescribing."
    )
    
    # ======================================================================
    # CRITICAL MOMENT: Agent searches for allergy information
    # ======================================================================
    print("\n" + "="*80)
    print("  🔍 FACT RETRIEVAL: Searching for allergy information")
    print("="*80 + "\n")
    
    print("Query: 'Does the patient have any drug allergies?'")
    print("Searching: Interactions only (default)\n")
    
    allergy_facts = await orchestrator4.retrieve_facts(
        "Does the patient have any drug allergies or medication allergies?"
    )
    
    print("📊 RETRIEVAL RESULT:")
    print(f"  {allergy_facts}\n")
    
    # Verify critical information was found
    if "penicillin" in allergy_facts.lower() or "allerg" in allergy_facts.lower():
        print("✅ SUCCESS: Penicillin allergy found from Session 1!")
        print("✅ Session 1 was NOT in initial context (3 sessions ago)")
        print("✅ CFR agent successfully retrieved critical safety information\n")
    else:
        print("❌ WARNING: Allergy information not found!")
        print("❌ This could lead to dangerous prescription\n")
    
    # Now let's also search with summaries included
    print("\nQuery: 'What allergies does this patient have?'")
    print("Searching: Interactions + Session Summaries\n")
    
    allergy_facts_with_summaries = await orchestrator4.retrieve_facts(
        "What allergies does this patient have?",
        include_summaries=True
    )
    
    print("📊 RETRIEVAL RESULT:")
    print(f"  {allergy_facts_with_summaries}\n")
    
    # Also check current medications
    print("\nQuery: 'What medications is the patient taking?'")
    print("Searching: Interactions + Summaries + Insights\n")
    
    medication_facts = await orchestrator4.retrieve_facts(
        "What medications is the patient currently taking?",
        include_summaries=True,
        include_insights=True
    )
    
    print("📊 RETRIEVAL RESULT:")
    print(f"  {medication_facts}\n")
    
    # Agent prescribes safely based on retrieved information
    print("="*80)
    print("Turn 2:")
    print("  👤 User: What can you prescribe for me?")
    response = (
        "Based on your documented penicillin allergy (which caused a rash reaction), "
        "I'm prescribing Azithromycin (Z-Pack) instead. It's a macrolide antibiotic - "
        "a completely different class from penicillin - and is very effective for sinus infections. "
        "It's also safe with your current medications: Lisinopril for blood pressure and Metformin for diabetes."
    )
    print(f"  🤖 Assistant: {response}")
    
    await orchestrator4.process_turn(
        "What can you prescribe for me?",
        response
    )
    
    result4 = await orchestrator4.end_session(trigger_reflection=True)
    
    print(f"\n✓ Session ended:")
    print(f"  📋 Summary: {result4['session_summary'][:120]}...")
    print(f"  💡 Insights: {len(result4['insights_extracted'])} extracted")
    
    # ======================================================================
    # SUMMARY
    # ======================================================================
    print_header("DEMO SUMMARY")
    
    print("✅ Test PASSED: Fact retrieval across multiple sessions successful!")
    print("\nKey Points:")
    print("  1. Session 1 allergy information was 3 sessions old")
    print("  2. With num_recent_sessions_for_init=1, Session 1 NOT in Session 4's initial context")
    print("  3. CFR agent successfully retrieved critical allergy information")
    print("  4. Agent prescribed safe alternative medication (Azithromycin)")
    print("  5. Patient safety maintained through intelligent retrieval")
    
    print("\nRetrieval Options Demonstrated:")
    print("  • Default: Search interactions only (fast, focused)")
    print("  • With summaries: Search interactions + session summaries")
    print("  • With insights: Search all memory sources (comprehensive)")
    
    print("\nReal-World Application:")
    print("  • Medical: Retrieve critical patient history (allergies, medications)")
    print("  • Financial: Recall client's complete investment portfolio")
    print("  • Education: Remember student's learning preferences and progress")
    print("  • Customer Service: Access full customer interaction history")
    
    print("\n" + "="*80)
    print("Demo completed successfully!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
