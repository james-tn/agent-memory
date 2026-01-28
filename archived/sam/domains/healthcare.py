"""
Healthcare Domain Configuration

Specialized ontology for healthcare/medical assistant applications.
Focuses on patient health, medications, conditions, and care relationships.

Key advantages for SAM:
- ALLERGIC_TO relationships prevent dangerous recommendations
- PRESCRIBED → CONTRAINDICATED chains catch drug interactions
- TREATS relationships enable "what helps my condition?" queries
- Temporal relationships track symptom progression
"""

from sam.domains.base import (
    DomainConfig, EntityTypeConfig, RelationshipTypeConfig, 
    MultiHopPattern, register_domain
)


@register_domain("healthcare")
class HealthcareDomain(DomainConfig):
    """Healthcare assistant domain with medical ontology."""
    
    def __init__(self):
        super().__init__(
            domain_id="healthcare",
            display_name="Healthcare Assistant",
            description="""Personal health assistant that remembers medical history, 
medications, conditions, and preferences. Helps track health over time and 
provides personalized guidance while respecting medical relationships.""",
            
            entity_types=[
                EntityTypeConfig(
                    name="PATIENT",
                    description="The user/patient being assisted",
                    examples=["the patient", "I", "user"],
                    extraction_hints=["Usually refers to the person talking about their health"]
                ),
                EntityTypeConfig(
                    name="MEDICATION",
                    description="A drug, supplement, or medication",
                    examples=["Lisinopril", "Vitamin D", "ibuprofen", "my blood pressure medication"],
                    extraction_hints=["Brand names, generic names, drug classes, supplements"]
                ),
                EntityTypeConfig(
                    name="CONDITION",
                    description="A medical condition, disease, or diagnosis",
                    examples=["hypertension", "Type 2 diabetes", "seasonal allergies", "my back pain"],
                    extraction_hints=["Diagnoses, symptoms that became conditions, chronic issues"]
                ),
                EntityTypeConfig(
                    name="SYMPTOM",
                    description="A symptom or health complaint",
                    examples=["headache", "fatigue", "swelling in my ankles", "difficulty sleeping"],
                    extraction_hints=["Physical complaints, changes noticed, side effects"]
                ),
                EntityTypeConfig(
                    name="ALLERGEN",
                    description="Something the patient is allergic to",
                    examples=["penicillin", "shellfish", "pollen", "latex"],
                    extraction_hints=["Drugs, foods, environmental triggers"]
                ),
                EntityTypeConfig(
                    name="PROVIDER",
                    description="A healthcare provider",
                    examples=["Dr. Smith", "my cardiologist", "the ER doctor", "my therapist"],
                    extraction_hints=["Doctors, specialists, nurses, therapists"]
                ),
                EntityTypeConfig(
                    name="PROCEDURE",
                    description="A medical procedure or test",
                    examples=["blood test", "MRI", "colonoscopy", "physical therapy session"],
                    extraction_hints=["Tests, surgeries, treatments, therapy sessions"]
                ),
                EntityTypeConfig(
                    name="MEASUREMENT",
                    description="A health measurement or vital sign",
                    examples=["blood pressure 130/85", "A1C of 6.5", "weight 180 lbs"],
                    extraction_hints=["Vitals, lab values, measurements with numbers"]
                ),
                EntityTypeConfig(
                    name="LIFESTYLE",
                    description="Lifestyle factors affecting health",
                    examples=["exercise routine", "diet", "sleep schedule", "stress level"],
                    extraction_hints=["Habits, routines, behaviors affecting health"]
                ),
            ],
            
            relationship_types=[
                # Critical safety relationships
                RelationshipTypeConfig(
                    name="ALLERGIC_TO",
                    description="Patient has allergy to substance (CRITICAL - always retrieve)",
                    source_types=["PATIENT"],
                    target_types=["ALLERGEN", "MEDICATION"],
                    examples=["I'm allergic to penicillin", "shellfish gives me hives"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="CONTRAINDICATED_WITH",
                    description="Medication should not be used with another medication/condition",
                    source_types=["MEDICATION"],
                    target_types=["MEDICATION", "CONDITION"],
                    examples=["Don't take ibuprofen with blood thinners"],
                    supports_multi_hop=True
                ),
                
                # Treatment relationships
                RelationshipTypeConfig(
                    name="PRESCRIBED",
                    description="Patient is prescribed a medication",
                    source_types=["PATIENT", "PROVIDER"],
                    target_types=["MEDICATION"],
                    examples=["Dr. Smith prescribed Lisinopril", "I take metformin"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="TREATS",
                    description="Medication or procedure treats a condition",
                    source_types=["MEDICATION", "PROCEDURE"],
                    target_types=["CONDITION", "SYMPTOM"],
                    examples=["Lisinopril treats hypertension", "physical therapy for back pain"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="DIAGNOSED_WITH",
                    description="Patient has been diagnosed with a condition",
                    source_types=["PATIENT"],
                    target_types=["CONDITION"],
                    examples=["I was diagnosed with Type 2 diabetes"],
                    supports_multi_hop=True
                ),
                
                # Symptom relationships
                RelationshipTypeConfig(
                    name="EXPERIENCES",
                    description="Patient experiences a symptom",
                    source_types=["PATIENT"],
                    target_types=["SYMPTOM"],
                    examples=["I've been having headaches", "experiencing fatigue"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="SYMPTOM_OF",
                    description="Symptom is associated with a condition",
                    source_types=["SYMPTOM"],
                    target_types=["CONDITION"],
                    examples=["Fatigue is a symptom of diabetes"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="SIDE_EFFECT_OF",
                    description="Symptom is a side effect of medication",
                    source_types=["SYMPTOM"],
                    target_types=["MEDICATION"],
                    examples=["The dizziness might be from my new medication"],
                    supports_multi_hop=True
                ),
                
                # Care relationships
                RelationshipTypeConfig(
                    name="TREATED_BY",
                    description="Patient is treated by a provider",
                    source_types=["PATIENT"],
                    target_types=["PROVIDER"],
                    examples=["I see Dr. Smith for my heart", "my therapist"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="SPECIALIST_FOR",
                    description="Provider specializes in a condition type",
                    source_types=["PROVIDER"],
                    target_types=["CONDITION"],
                    examples=["Dr. Smith is my cardiologist"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="ORDERED",
                    description="Provider ordered a procedure/test",
                    source_types=["PROVIDER"],
                    target_types=["PROCEDURE"],
                    examples=["Dr. Smith ordered blood work"],
                    supports_multi_hop=True
                ),
                
                # Measurement relationships
                RelationshipTypeConfig(
                    name="MEASURED",
                    description="A measurement was recorded",
                    source_types=["PATIENT", "PROCEDURE"],
                    target_types=["MEASUREMENT"],
                    examples=["My blood pressure was 130/85"],
                    supports_multi_hop=False
                ),
                RelationshipTypeConfig(
                    name="INDICATES",
                    description="Measurement indicates a condition status",
                    source_types=["MEASUREMENT"],
                    target_types=["CONDITION"],
                    examples=["A1C of 6.5 indicates good diabetes control"],
                    supports_multi_hop=True
                ),
                
                # Lifestyle relationships
                RelationshipTypeConfig(
                    name="AFFECTS",
                    description="Lifestyle factor affects a condition",
                    source_types=["LIFESTYLE"],
                    target_types=["CONDITION", "SYMPTOM"],
                    examples=["Exercise helps my blood pressure", "stress triggers headaches"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="FOLLOWS",
                    description="Patient follows a lifestyle regimen",
                    source_types=["PATIENT"],
                    target_types=["LIFESTYLE"],
                    examples=["I exercise 3 times a week", "I'm on a low-sodium diet"],
                    supports_multi_hop=False
                ),
            ],
            
            multi_hop_patterns=[
                MultiHopPattern(
                    pattern=r"interact with|safe with|take with",
                    description="Drug interaction query",
                    expected_hops=2,
                    example_query="Can I take ibuprofen with my blood pressure medication?",
                    traversal_hint="medication1 -> CONTRAINDICATED_WITH -> medication2"
                ),
                MultiHopPattern(
                    pattern=r"allerg|avoid|can't take",
                    description="Allergy-based contraindication",
                    expected_hops=2,
                    example_query="What pain relievers can I take given my allergies?",
                    traversal_hint="patient -> ALLERGIC_TO -> allergen -> similar medications"
                ),
                MultiHopPattern(
                    pattern=r"side effect|causing|from my medication",
                    description="Side effect investigation",
                    expected_hops=2,
                    example_query="Could my dizziness be from my new medication?",
                    traversal_hint="symptom -> SIDE_EFFECT_OF -> medication -> PRESCRIBED"
                ),
                MultiHopPattern(
                    pattern=r"treat|help with|for my",
                    description="Treatment lookup",
                    expected_hops=2,
                    example_query="What medications treat my condition?",
                    traversal_hint="condition -> TREATS (reverse) -> medication"
                ),
                MultiHopPattern(
                    pattern=r"specialist|doctor for|who treats",
                    description="Provider lookup for condition",
                    expected_hops=2,
                    example_query="Who should I see about my heart condition?",
                    traversal_hint="condition -> SPECIALIST_FOR (reverse) -> provider"
                ),
                MultiHopPattern(
                    pattern=r"what's causing|why do I have|related to",
                    description="Symptom-condition investigation",
                    expected_hops=3,
                    example_query="What's causing my fatigue - is it the medication or the condition?",
                    traversal_hint="symptom -> SYMPTOM_OF/SIDE_EFFECT_OF -> condition/medication"
                ),
            ],
            
            extraction_system_prompt="""
You are extracting health information. Pay special attention to:

1. **ALLERGIES** - Always extract allergy information, this is safety-critical
2. **MEDICATIONS** - Current and past medications, including OTC and supplements
3. **CONDITIONS** - Diagnosed conditions and suspected conditions
4. **SYMPTOMS** - Any symptoms mentioned, especially new ones or changes
5. **RELATIONSHIPS** - Who treats the patient, what treats what

When uncertain if something is a condition vs symptom, prefer SYMPTOM.
Always link medications to what they treat when mentioned.
Always link symptoms to potential causes (medication side effects OR conditions).
""",
            
            extraction_examples=[
                {
                    "input": "I've been taking Lisinopril for my blood pressure, but I've been getting dizzy lately. I'm also allergic to penicillin.",
                    "entities": [
                        {"name": "Lisinopril", "type": "MEDICATION"},
                        {"name": "hypertension", "type": "CONDITION"},
                        {"name": "dizziness", "type": "SYMPTOM"},
                        {"name": "penicillin", "type": "ALLERGEN"},
                    ],
                    "relationships": [
                        {"source": "patient", "type": "PRESCRIBED", "target": "Lisinopril"},
                        {"source": "Lisinopril", "type": "TREATS", "target": "hypertension"},
                        {"source": "patient", "type": "EXPERIENCES", "target": "dizziness"},
                        {"source": "dizziness", "type": "SIDE_EFFECT_OF", "target": "Lisinopril"},
                        {"source": "patient", "type": "ALLERGIC_TO", "target": "penicillin"},
                    ]
                }
            ],
            
            # Tuned for healthcare: more exploration, lower threshold for safety
            default_activation_decay=0.75,  # Spread further for safety
            default_max_depth=4,  # Allow deeper chains (allergy -> drug class -> alternatives)
            default_activation_threshold=0.03  # Lower threshold - don't miss allergies
        )
