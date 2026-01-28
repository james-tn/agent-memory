"""
Generic Domain Configuration

Universal schema that works across any domain.
This is the default/fallback when no specific domain is configured.
"""

from sam.domains.base import (
    DomainConfig, EntityTypeConfig, RelationshipTypeConfig, 
    MultiHopPattern, register_domain
)


@register_domain("generic")
class GenericDomain(DomainConfig):
    """Generic universal domain - works for any application."""
    
    def __init__(self):
        super().__init__(
            domain_id="generic",
            display_name="Generic Assistant",
            description="Universal personal assistant that remembers conversations across any topic.",
            
            entity_types=[
                EntityTypeConfig(
                    name="PERSON",
                    description="A person mentioned in conversation",
                    examples=["Alice Chen", "Dr. Smith", "my mom"],
                    extraction_hints=["Look for names, pronouns resolved to names, family relations"]
                ),
                EntityTypeConfig(
                    name="ORGANIZATION",
                    description="A company, institution, or group",
                    examples=["TechCorp", "Stanford University", "the AV team"],
                    extraction_hints=["Companies, teams, departments, institutions"]
                ),
                EntityTypeConfig(
                    name="LOCATION",
                    description="A place or geographic location",
                    examples=["San Francisco", "the office", "Yosemite"],
                    extraction_hints=["Cities, countries, landmarks, buildings"]
                ),
                EntityTypeConfig(
                    name="PROJECT",
                    description="A work project or initiative",
                    examples=["the AV project", "CVPR paper", "Q1 goals"],
                    extraction_hints=["Named projects, papers, initiatives"]
                ),
                EntityTypeConfig(
                    name="TECHNOLOGY",
                    description="A technology, tool, or technical concept",
                    examples=["PointPillars", "PyTorch", "LiDAR"],
                    extraction_hints=["Frameworks, architectures, tools, concepts"]
                ),
                EntityTypeConfig(
                    name="EVENT",
                    description="A specific event or occurrence",
                    examples=["CVPR 2026", "the interview", "vacation"],
                    extraction_hints=["Conferences, meetings, milestones, trips"]
                ),
            ],
            
            relationship_types=[
                RelationshipTypeConfig(
                    name="WORKS_AT",
                    description="Employment relationship",
                    source_types=["PERSON"],
                    target_types=["ORGANIZATION"],
                    examples=["Alice works at TechCorp"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="WORKS_ON",
                    description="Person works on a project/technology",
                    source_types=["PERSON"],
                    target_types=["PROJECT", "TECHNOLOGY"],
                    examples=["Marcus works on PointPillars"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="TEAM_MEMBER",
                    description="Person is a member of a team/organization",
                    source_types=["PERSON"],
                    target_types=["ORGANIZATION", "PROJECT"],
                    examples=["Priya is on the AV team"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="MENTORS",
                    description="Mentorship relationship",
                    source_types=["PERSON"],
                    target_types=["PERSON"],
                    examples=["Alice mentors Priya"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="FAMILY_OF",
                    description="Family relationship",
                    source_types=["PERSON"],
                    target_types=["PERSON"],
                    examples=["Alice's dad", "her mother"],
                    is_symmetric=False,
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="LOCATED_IN",
                    description="Location relationship",
                    source_types=["PERSON", "ORGANIZATION", "EVENT"],
                    target_types=["LOCATION"],
                    examples=["Alice is in San Francisco"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="PARTICIPATED_IN",
                    description="Participation in an event",
                    source_types=["PERSON"],
                    target_types=["EVENT"],
                    examples=["Alice presented at CVPR"],
                    supports_multi_hop=True
                ),
                RelationshipTypeConfig(
                    name="PREFERS",
                    description="Preference or like",
                    source_types=["PERSON"],
                    target_types=["TECHNOLOGY", "ORGANIZATION"],
                    examples=["Alice prefers Ethiopian coffee"],
                    supports_multi_hop=False
                ),
            ],
            
            multi_hop_patterns=[
                MultiHopPattern(
                    pattern=r"the person who",
                    description="Indirect person reference",
                    expected_hops=2,
                    example_query="What does the person who went to Yosemite prefer?",
                    traversal_hint="query -> event/action -> person -> preference"
                ),
                MultiHopPattern(
                    pattern=r"'s (father|mother|dad|mom|parent)",
                    description="Family chain",
                    expected_hops=2,
                    example_query="Where does Alice's father work?",
                    traversal_hint="person -> family -> person -> workplace"
                ),
                MultiHopPattern(
                    pattern=r"team that|project that",
                    description="Team/project indirect reference",
                    expected_hops=2,
                    example_query="What technology does the team that Alice leads use?",
                    traversal_hint="query -> team -> technology"
                ),
            ],
            
            extraction_system_prompt="""
Focus on extracting:
1. People and their relationships (work, family, social)
2. Projects and who works on them
3. Preferences and opinions
4. Events and participation
""",
            
            default_activation_decay=0.7,
            default_max_depth=3,
            default_activation_threshold=0.05
        )
