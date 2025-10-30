"""
Demo 4: Medical Assistant with Explicit Memory Search

This demo showcases the search_memory() tool for on-demand memory retrieval.
Unlike automatic context injection, search_memory() allows the agent to 
explicitly search for specific information when needed.

Scenario:
- Session 1: Initial patient visit - record medical history, medications, allergies
- Session 2: Follow-up visit - explicitly search for past medications
- Session 3: New symptom - search for drug interactions with known allergies

The agent proactively uses search_memory() to retrieve relevant patient history
before making recommendations or answering questions.
"""

import asyncio
import os
from azure.identity import AzureCliCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from memory.cosmos_memory_provider import CosmosMemoryProvider


# Mock medical database
DRUG_DATABASE = {
    "ibuprofen": {
        "name": "Ibuprofen",
        "type": "NSAID pain reliever",
        "dosage": "200-400mg every 4-6 hours",
        "interactions": ["penicillin_allergy"]
    },
    "acetaminophen": {
        "name": "Acetaminophen",
        "type": "Pain reliever/fever reducer",
        "dosage": "500-1000mg every 4-6 hours",
        "interactions": []
    },
    "lisinopril": {
        "name": "Lisinopril",
        "type": "ACE inhibitor for blood pressure",
        "dosage": "10mg daily",
        "interactions": ["sulfa_allergy"]
    },
    "amoxicillin": {
        "name": "Amoxicillin",
        "type": "Antibiotic (penicillin)",
        "dosage": "500mg three times daily",
        "interactions": ["penicillin_allergy"]
    }
}


def check_drug_interactions(drug_name: str, allergy: str) -> str:
    """
    Check if a drug has interactions with a known allergy.
    
    Args:
        drug_name: Name of the drug to check
        allergy: Known allergy (e.g., "penicillin_allergy")
    
    Returns:
        Interaction warning or safe confirmation
    """
    drug = DRUG_DATABASE.get(drug_name.lower())
    if not drug:
        return f"Drug '{drug_name}' not found in database."
    
    if allergy in drug["interactions"]:
        return f"⚠️ WARNING: {drug['name']} interacts with {allergy.replace('_', ' ')}. DO NOT PRESCRIBE."
    else:
        return f"✓ {drug['name']} is safe for patient with {allergy.replace('_', ' ')}."


def get_drug_info(drug_name: str) -> str:
    """
    Get information about a specific drug.
    
    Args:
        drug_name: Name of the drug
    
    Returns:
        Drug information including type, dosage, and interactions
    """
    drug = DRUG_DATABASE.get(drug_name.lower())
    if not drug:
        return f"Drug '{drug_name}' not found in database."
    
    info = f"**{drug['name']}**\n"
    info += f"Type: {drug['type']}\n"
    info += f"Dosage: {drug['dosage']}\n"
    info += f"Interactions: {', '.join(drug['interactions']) if drug['interactions'] else 'None'}"
    
    return info


def record_vitals(blood_pressure: str, temperature: str, heart_rate: str) -> str:
    """
    Record patient vital signs.
    
    Args:
        blood_pressure: Blood pressure reading (e.g., "120/80")
        temperature: Temperature in Fahrenheit (e.g., "98.6")
        heart_rate: Heart rate in BPM (e.g., "72")
    
    Returns:
        Confirmation message
    """
    return f"✓ Vitals recorded:\n- BP: {blood_pressure}\n- Temp: {temperature}°F\n- HR: {heart_rate} bpm"


async def run_demo():
    """Run the medical assistant demo."""
    
    # Initialize memory provider
    memory = CosmosMemoryProvider(
        service_url=os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000"),
        user_id="patient_john_doe",
        auto_manage_session=False  # Client manually manages session
    )
    
    # Start session explicitly
    await memory._start_session()
    
    # Create agent with memory and tools
    # search_memory is passed as a tool directly from memory provider
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions="""You are Dr. AI, a medical assistant helping with patient care.

IMPORTANT - Memory Search Strategy:
1. At the START of each conversation, proactively use search_memory() to retrieve:
   - Past medications the patient is taking
   - Known allergies and sensitivities
   - Chronic conditions and medical history
   - Previous symptoms and treatments

2. Before prescribing ANY medication:
   - Search memory for "allergies" and "current medications"
   - Use check_drug_interactions() to verify safety
   - Never prescribe without checking interactions

3. When patient mentions symptoms:
   - Search memory for "past symptoms" or similar conditions
   - Search for "previous treatments" to see what worked before

4. For follow-up visits:
   - Search memory for information from the initial visit
   - Look for progress on previous treatments
   - Check for any changes in patient status

Remember: search_memory() is a tool you can use to explicitly search patient history.
Use it proactively to provide safe, personalized care.""",
        tools=[
            check_drug_interactions,
            get_drug_info,
            record_vitals,
            memory.search_memory  # Add search_memory as a tool!
        ],
        context_providers=[memory]
    )
    
    print("=" * 70)
    print("Demo 4: Medical Assistant with Explicit Memory Search")
    print("=" * 70)
    print("\nThis demo showcases the search_memory() tool for on-demand retrieval.")
    print("Watch how the agent proactively searches patient history before making")
    print("medical recommendations.\n")
    
    # ============================================================================
    # SESSION 1: Initial Patient Visit
    # ============================================================================
    print("\n" + "=" * 70)
    print("SESSION 1: Initial Patient Visit - Recording Medical History")
    print("=" * 70)
    
    # Create thread for this session
    thread = agent.get_new_thread()
    
    # Initial consultation
    user_input = """Hello Dr. AI, I'm here for my annual checkup. 
    
My vitals today are:
- Blood pressure: 138/85
- Temperature: 98.4°F
- Heart rate: 78 bpm

I've been taking Lisinopril 10mg daily for my blood pressure.

I have a severe allergy to penicillin - I get hives and difficulty breathing.

Also, I've been experiencing occasional headaches, maybe 2-3 times per week."""
    
    print(f"\n👤 Patient: {user_input}\n")
    
    result = await agent.run(user_input, thread=thread)
    print(f"🏥 Dr. AI: {result.text}\n")
    
    # Wait for async callbacks to complete
    await asyncio.sleep(1.0)
    
    # End session - triggers summarization on server
    await memory.end_session()
    await memory.close()
    
    # Wait before next session
    input("\n[Press Enter to continue to Session 2...]")
    
    # ============================================================================
    # SESSION 2: Follow-up Visit - Agent Searches for Past Medications
    # ============================================================================
    print("\n" + "=" * 70)
    print("SESSION 2: Follow-up Visit - Two Weeks Later")
    print("=" * 70)
    print("\nNote: Agent should use search_memory() to retrieve past medications")
    print("and allergies before making recommendations.\n")
    
    # Create NEW memory provider for new session
    memory = CosmosMemoryProvider(
        service_url=os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000"),
        user_id="patient_john_doe",  # Same user
        auto_manage_session=False
    )
    
    # Start new session
    await memory._start_session()
    
    # Create new agent with new memory provider (includes search_memory tool)
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions="""You are Dr. AI, a medical assistant helping with patient care.

IMPORTANT - Memory Search Strategy:
1. At the START of each conversation, proactively use search_memory() to retrieve:
   - Past medications the patient is taking
   - Known allergies and sensitivities
   - Chronic conditions and medical history
   - Previous symptoms and treatments

2. Before prescribing ANY medication:
   - Search memory for "allergies" and "current medications"
   - Use check_drug_interactions() to verify safety
   - Never prescribe without checking interactions

3. When patient mentions symptoms:
   - Search memory for "past symptoms" or similar conditions
   - Search for "previous treatments" to see what worked before

4. For follow-up visits:
   - Search memory for information from the initial visit
   - Look for progress on previous treatments
   - Check for any changes in patient status

Remember: search_memory() is a tool you can use to explicitly search patient history.
Use it proactively to provide safe, personalized care.""",
        tools=[
            check_drug_interactions,
            get_drug_info,
            record_vitals,
            memory.search_memory
        ],
        context_providers=[memory]
    )
    
    # New thread
    thread = agent.get_new_thread()
    
    user_input = """Hi Dr. AI, I'm back for my follow-up. 

My headaches have gotten worse - now happening daily. They're really affecting 
my work. Can you recommend something for pain relief?"""
    
    print(f"\n👤 Patient: {user_input}\n")
    print("   [NOTE: Agent should search memory for allergies before recommending medication]\n")
    
    result = await agent.run(user_input, thread=thread)
    print(f"🏥 Dr. AI: {result.text}\n")
    
    # Wait for async callbacks
    await asyncio.sleep(1.0)
    
    await memory.end_session()
    await memory.close()
    
    # Wait before next session
    input("\n[Press Enter to continue to Session 3...]")
    
    # ============================================================================
    # SESSION 3: New Symptom - Search for Allergy Interactions
    # ============================================================================
    print("\n" + "=" * 70)
    print("SESSION 3: Urgent Visit - One Month Later")
    print("=" * 70)
    print("\nNote: Agent should search for known allergies before prescribing")
    print("antibiotics to prevent dangerous interactions.\n")
    
    # Create NEW memory provider for new session
    memory = CosmosMemoryProvider(
        service_url=os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000"),
        user_id="patient_john_doe",  # Same user
        auto_manage_session=False
    )
    
    # Start new session
    await memory._start_session()
    
    # Create new agent with new memory provider (includes search_memory tool)
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions="""You are Dr. AI, a medical assistant helping with patient care.

IMPORTANT - Memory Search Strategy:
1. At the START of each conversation, proactively use search_memory() to retrieve:
   - Past medications the patient is taking
   - Known allergies and sensitivities
   - Chronic conditions and medical history
   - Previous symptoms and treatments

2. Before prescribing ANY medication:
   - Search memory for "allergies" and "current medications"
   - Use check_drug_interactions() to verify safety
   - Never prescribe without checking interactions

3. When patient mentions symptoms:
   - Search memory for "past symptoms" or similar conditions
   - Search for "previous treatments" to see what worked before

4. For follow-up visits:
   - Search memory for information from the initial visit
   - Look for progress on previous treatments
   - Check for any changes in patient status

Remember: search_memory() is a tool you can use to explicitly search patient history.
Use it proactively to provide safe, personalized care.""",
        tools=[
            check_drug_interactions,
            get_drug_info,
            record_vitals,
            memory.search_memory
        ],
        context_providers=[memory]
    )
    
    # New thread
    thread = agent.get_new_thread()
    
    user_input = """Dr. AI, I have a terrible sinus infection. Lots of pressure, 
thick green discharge, and fever. I think I need antibiotics. 

My friend said Amoxicillin worked great for her sinus infection. Can you 
prescribe that for me?"""
    
    print(f"\n👤 Patient: {user_input}\n")
    print("   [NOTE: Agent should search for penicillin allergy - Amoxicillin is dangerous!]\n")
    
    result = await agent.run(user_input, thread=thread)
    print(f"🏥 Dr. AI: {result.text}\n")
    
    # Wait for async callbacks
    await asyncio.sleep(1.0)
    
    await memory.end_session()
    await memory.close()
    
    # ============================================================================
    # DEMO SUMMARY
    # ============================================================================
    print("\n" + "=" * 70)
    print("DEMO COMPLETE: Key Observations")
    print("=" * 70)
    print("""
1. **Automatic Context Injection**:
   - At each session start, relevant memory is automatically provided
   - Enables basic continuity (greeting returning patient, etc.)

2. **Explicit Memory Search**:
   - Agent uses search_memory() tool to actively retrieve specific information
   - Searches for "allergies" before prescribing medications
   - Looks up "past medications" when making recommendations
   - Retrieves "previous symptoms" to provide context-aware care

3. **Hybrid Strategy Benefits**:
   - Automatic: Provides general context and continuity
   - On-demand: Enables precise retrieval for critical decisions
   - Together: Creates proactive, safe, personalized care

4. **When to Use search_memory()**:
   - Before making important decisions (prescriptions, procedures)
   - When patient mentions something from past visits
   - To verify information before taking action
   - When specific historical details are needed

This demonstrates how search_memory() enhances agent capabilities beyond
passive context injection, enabling proactive information retrieval.
""")


if __name__ == "__main__":
    print("\n🏥 Starting Medical Assistant Demo...")
    print("📋 Ensure the memory service is running: python run_server.py\n")
    
    asyncio.run(run_demo())
