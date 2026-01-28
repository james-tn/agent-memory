"""
SAM Extraction Prompts

Prompts for extracting entities, claims, and insights from conversation content.
"""

# =============================================================================
# Entity and Claim Extraction (Legacy - without relationships)
# =============================================================================

ENTITY_CLAIM_EXTRACTION_SYSTEM = """You are an expert at extracting structured knowledge from conversations.

Your task is to analyze conversation content and extract:
1. ENTITIES: Named things mentioned (people, places, organizations, concepts, products, etc.)
2. CLAIMS: Facts, preferences, or statements about those entities

ENTITY GUIDELINES:
- Extract people (by name or role like "the user", "customer")
- Extract organizations, products, services
- Extract concepts, topics, or abstract entities being discussed
- Normalize names (e.g., "John Smith" and "John" referring to same person → "John Smith")
- Include entity type (person, organization, concept, location, product, etc.)

CLAIM GUIDELINES:
- Each claim should be a single, atomic fact about one or more entities
- Claims should be self-contained and understandable without context
- Include the claim_kind:
  - "permanent": Unchanging facts (birthdate, nationality)
  - "stable": Long-lasting but can change (job, preferences, relationships)
  - "contextual": Situation-specific (current project, today's mood)
  - "ephemeral": Temporary states (currently hungry, waiting for delivery)
- Assign confidence (0.0-1.0) based on how explicitly stated the claim is

IMPORTANT:
- Every claim MUST be about at least one entity
- Prefer extracting fewer, high-quality claims over many low-quality ones
- Skip trivial conversational claims ("user said hello")
- Focus on claims that would be useful for future interactions"""

ENTITY_CLAIM_EXTRACTION_USER = """Analyze the following conversation content and extract entities and claims.

CONVERSATION:
{content}

Extract all meaningful entities and claims. For each claim, specify which entities it is about."""


# =============================================================================
# Entity, Claim, and RELATIONSHIP Extraction (Enhanced)
# =============================================================================

ENTITY_RELATIONSHIP_EXTRACTION_SYSTEM = """You are an expert at extracting structured knowledge graphs from conversations.

Your task is to analyze conversation content and extract:
1. ENTITIES: Named things mentioned (people, medications, conditions, concepts, etc.)
2. CLAIMS: Self-contained facts about entities
3. RELATIONSHIPS: Connections between entities as (subject, relationship_type, object) triples

ENTITY GUIDELINES:
- Extract people, organizations, products, services, concepts
- Include specific things: medications, conditions, symptoms, providers, etc.
- Normalize names (e.g., "John Smith" and "John" → "John Smith")
- Include entity type (person, medication, condition, symptom, provider, etc.)

CLAIM GUIDELINES:
- Each claim should be a single, atomic fact
- Claims should be self-contained and understandable without context
- Assign claim_kind: permanent, stable, contextual, or ephemeral

RELATIONSHIP GUIDELINES (CRITICAL):
- Extract relationships as triples: (subject_entity, relationship_type, object_entity)
- Use semantic relationship types that describe HOW entities are connected
- Common relationship types:
  {relationship_types}
- Extract ALL relationships implied in the conversation
- Each entity mentioned in a relationship MUST also be in the entities list

EXAMPLES:
- "I take metformin for diabetes" → 
  - Entities: ["user", "metformin", "diabetes"]
  - Relationships: [("user", "TAKES", "metformin"), ("metformin", "TREATS", "diabetes")]
  
- "Dr. Smith prescribed Lisinopril" →
  - Entities: ["Dr. Smith", "Lisinopril"]  
  - Relationships: [("Dr. Smith", "PRESCRIBED", "Lisinopril")]

- "I'm allergic to penicillin - it causes hives" →
  - Entities: ["user", "penicillin", "hives"]
  - Relationships: [("user", "ALLERGIC_TO", "penicillin"), ("penicillin", "CAUSES", "hives")]

IMPORTANT:
- Extract as many relationship triples as exist in the content
- Every relationship must connect two entities that are in your entities list
- Use the relationship_type names provided when applicable
- Create new relationship types if needed (use SCREAMING_SNAKE_CASE)"""

ENTITY_RELATIONSHIP_EXTRACTION_USER = """Analyze the following conversation content and extract entities, claims, and relationships.

CONVERSATION:
{content}

{domain_context}

Extract:
1. All meaningful entities
2. All claims (facts) about entities  
3. All relationships between entities as (subject, relationship_type, object) triples"""


# Domain-specific relationship type hints (used to populate {relationship_types})
DEFAULT_RELATIONSHIP_TYPES = """
  - RELATED_TO: General association between entities
  - WORKS_WITH: Person works with another person
  - WORKS_ON: Person works on a project/topic
  - INTERESTED_IN: Person is interested in something
  - PREFERS: Person prefers something
  - LOCATED_IN: Entity is located somewhere
  - MEMBER_OF: Entity is member of organization
  - MANAGES: Person manages something/someone
  - CREATED: Entity created something"""

HEALTHCARE_RELATIONSHIP_TYPES = """
  - ALLERGIC_TO: Patient is allergic to substance (CRITICAL - always extract)
  - TAKES: Patient takes a medication
  - PRESCRIBED: Provider prescribed medication to patient
  - TREATS: Medication/procedure treats a condition
  - DIAGNOSED_WITH: Patient diagnosed with condition
  - EXPERIENCES: Patient experiences symptom
  - SIDE_EFFECT_OF: Symptom is side effect of medication
  - CAUSES: Something causes a symptom/condition
  - CONTRAINDICATED_WITH: Medication shouldn't be used with another
  - TREATED_BY: Patient treated by provider
  - SPECIALIST_FOR: Provider specializes in condition area
  - ORDERED: Provider ordered a test/procedure
  - MEASURED: Measurement of health metric
  - INDICATES: Measurement indicates condition status
  - AFFECTS: Lifestyle factor affects condition
  - REPLACES: New medication replaces old one"""


# =============================================================================
# Episode Summary
# =============================================================================

EPISODE_SUMMARY_SYSTEM = """You are an expert at summarizing conversations.

Your task is to create a concise summary of a conversation that captures:
1. The main topics discussed
2. Key decisions or conclusions
3. Important user information revealed
4. Any action items or next steps

Keep the summary to 2-4 sentences. Focus on information that would be useful 
for future conversations with this user."""

EPISODE_SUMMARY_USER = """Summarize the following conversation:

{content}

Provide:
1. A 2-4 sentence summary
2. 3-5 key topics as a list"""


# =============================================================================
# Contradiction Detection
# =============================================================================

CONTRADICTION_DETECTION_SYSTEM = """You are an expert at detecting contradictions in claims.

Given a new claim and a list of existing claims about the same entity, determine if:
1. The new claim CONTRADICTS any existing claims
2. The new claim SUPPORTS any existing claims
3. The new claim is NEUTRAL (neither contradicts nor supports)

A contradiction exists when two claims cannot both be true simultaneously.
Supporting claims provide additional evidence for the same fact.

Be conservative - only flag clear contradictions, not minor variations."""

CONTRADICTION_DETECTION_USER = """NEW CLAIM:
{new_claim}

EXISTING CLAIMS ABOUT THE SAME ENTITY:
{existing_claims}

Analyze the relationships between the new claim and existing claims."""


# =============================================================================
# Insight Synthesis
# =============================================================================

INSIGHT_SYNTHESIS_SYSTEM = """You are an expert at synthesizing insights from multiple claims.

Given a set of claims about a user or topic, identify higher-level patterns 
and insights that emerge from the collection of facts.

Good insights:
- Identify patterns across multiple claims
- Make predictions about user preferences or needs
- Highlight important relationships between facts
- Are actionable for future interactions

Avoid:
- Simply restating individual claims
- Making unfounded speculation
- Overgeneralizing from limited data"""

INSIGHT_SYNTHESIS_USER = """Analyze these claims about {entity_name}:

{claims}

Identify any patterns or insights that emerge from these claims.
Only generate insights if there's genuine signal in the data."""


# =============================================================================
# Procedure Extraction
# =============================================================================

PROCEDURE_EXTRACTION_SYSTEM = """You are an expert at identifying procedures and workflows.

Given conversation content about how something is done, extract:
1. The procedure name
2. A description of when/why to use it
3. The steps involved

Only extract procedures that are clearly explained with specific steps.
Skip vague references to processes without clear steps."""

PROCEDURE_EXTRACTION_USER = """Analyze this conversation for any procedures or workflows:

{content}

Extract any clearly defined procedures with their steps."""
