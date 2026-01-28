"""
SAM Extractor

Extracts entities, claims, relationships, and insights from Episode content using LLM.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sam.llm_client import LLMClient
from sam.embeddings import EmbeddingsService
from sam.stores.base import MemoryStore
from sam.models.graph import (
    Episode, Entity, Claim, Insight, Edge,
    EntityCreate, ClaimCreate, InsightCreate, EdgeCreate,
    NodeType, EdgeType, ClaimKind
)
from sam.extraction_models import (
    EntityClaimExtractionResult,
    EntityRelationshipExtractionResult,
    ExtractedEntity,
    ExtractedClaim,
    ExtractedRelationship,
    EpisodeSummaryResult,
    ContradictionDetectionResult,
    InsightSynthesisResult
)
from sam.prompts import (
    ENTITY_CLAIM_EXTRACTION_SYSTEM,
    ENTITY_CLAIM_EXTRACTION_USER,
    ENTITY_RELATIONSHIP_EXTRACTION_SYSTEM,
    ENTITY_RELATIONSHIP_EXTRACTION_USER,
    DEFAULT_RELATIONSHIP_TYPES,
    HEALTHCARE_RELATIONSHIP_TYPES,
    EPISODE_SUMMARY_SYSTEM,
    EPISODE_SUMMARY_USER,
    CONTRADICTION_DETECTION_SYSTEM,
    CONTRADICTION_DETECTION_USER,
    INSIGHT_SYNTHESIS_SYSTEM,
    INSIGHT_SYNTHESIS_USER
)


# Relationship type to EdgeType mapping
RELATIONSHIP_TO_EDGE_TYPE = {
    # Generic
    "RELATED_TO": EdgeType.RELATED_TO,
    "WORKS_WITH": EdgeType.WORKS_WITH,
    "WORKS_ON": EdgeType.WORKS_ON,
    "MANAGES": EdgeType.MANAGES,
    "MEMBER_OF": EdgeType.MEMBER_OF,
    "CREATED": EdgeType.CREATED,
    "PREFERS": EdgeType.PREFERS,
    "INTERESTED_IN": EdgeType.INTERESTED_IN,
    "DISLIKES": EdgeType.DISLIKES,
    "LOCATED_IN": EdgeType.LOCATED_IN,
    "LIVES_IN": EdgeType.LIVES_IN,
    
    # Healthcare
    "ALLERGIC_TO": EdgeType.ALLERGIC_TO,
    "TAKES": EdgeType.TAKES,
    "PRESCRIBED": EdgeType.PRESCRIBED,
    "TREATS": EdgeType.TREATS,
    "DIAGNOSED_WITH": EdgeType.DIAGNOSED_WITH,
    "EXPERIENCES": EdgeType.EXPERIENCES,
    "SIDE_EFFECT_OF": EdgeType.SIDE_EFFECT_OF,
    "CAUSES": EdgeType.CAUSES,
    "CONTRAINDICATED_WITH": EdgeType.CONTRAINDICATED_WITH,
    "TREATED_BY": EdgeType.TREATED_BY,
    "SPECIALIST_FOR": EdgeType.SPECIALIST_FOR,
    "ORDERED": EdgeType.ORDERED,
    "MEASURED": EdgeType.MEASURED,
    "INDICATES": EdgeType.INDICATES,
    "AFFECTS": EdgeType.AFFECTS,
    "REPLACES": EdgeType.REPLACES,
}


# Edge weights by relationship type (for SAM activation spreading)
RELATIONSHIP_WEIGHTS = {
    # Critical safety relationships (highest weight)
    "ALLERGIC_TO": 1.0,
    "CONTRAINDICATED_WITH": 1.0,
    
    # Strong medical relationships
    "TAKES": 0.9,
    "PRESCRIBED": 0.9,
    "TREATS": 0.9,
    "DIAGNOSED_WITH": 0.9,
    "SIDE_EFFECT_OF": 0.85,
    "CAUSES": 0.85,
    
    # Moderate medical relationships
    "EXPERIENCES": 0.7,
    "TREATED_BY": 0.7,
    "SPECIALIST_FOR": 0.7,
    "ORDERED": 0.7,
    "INDICATES": 0.7,
    "AFFECTS": 0.7,
    "REPLACES": 0.8,
    "MEASURED": 0.6,
    
    # Generic relationships
    "WORKS_WITH": 0.6,
    "WORKS_ON": 0.6,
    "MANAGES": 0.7,
    "MEMBER_OF": 0.5,
    "CREATED": 0.6,
    "PREFERS": 0.5,
    "INTERESTED_IN": 0.5,
    "DISLIKES": 0.5,
    "LOCATED_IN": 0.4,
    "LIVES_IN": 0.5,
    
    # Fallback
    "RELATED_TO": 0.3,
}


class Extractor:
    """
    Extracts structured knowledge from Episode content.
    
    Capabilities:
    - Entity extraction
    - Claim extraction (with ABOUT edges to entities)
    - Relationship extraction (Entity → Entity edges with semantic types)
    - Episode summarization
    - Contradiction detection
    - Insight synthesis
    """
    
    def __init__(
        self,
        store: MemoryStore,
        llm_client: LLMClient,
        embeddings: Optional[EmbeddingsService] = None,
        generate_embeddings: bool = True,
        domain: Optional[str] = None
    ):
        """
        Initialize extractor.
        
        Args:
            store: MemoryStore for persisting extracted nodes
            llm_client: LLM client for extraction
            embeddings: Embeddings service (created from llm_client if not provided)
            generate_embeddings: Whether to generate embeddings for new nodes
            domain: Domain name for domain-specific extraction (e.g., "healthcare")
        """
        self.store = store
        self.llm_client = llm_client
        self.embeddings = embeddings or EmbeddingsService(llm_client)
        self.generate_embeddings = generate_embeddings
        self.domain = domain
        
        # Load domain config if specified
        self.domain_config = None
        if domain:
            try:
                from sam.domains import get_domain_config
                self.domain_config = get_domain_config(domain)
            except Exception as e:
                print(f"  ⚠ Could not load domain config '{domain}': {e}")
    
    async def extract_from_episode(
        self,
        episode: Episode,
        detect_contradictions: bool = True,
        generate_summary: bool = True,
        extract_relationships: bool = True
    ) -> Dict[str, Any]:
        """
        Extract entities, claims, and relationships from an Episode.
        
        This is the main extraction entry point.
        
        Args:
            episode: Episode to extract from
            detect_contradictions: Whether to check for contradictions
            generate_summary: Whether to generate Episode summary
            extract_relationships: Whether to extract entity-to-entity relationships
            
        Returns:
            Dict with extraction results:
            - entities: List of created/updated Entity objects
            - claims: List of created Claim objects
            - edges: List of created Edge objects
            - contradictions: List of contradiction info (if detected)
            - summary: Episode summary (if generated)
        """
        print(f"[Extractor] Processing Episode {episode.id[:8]}...")
        
        results = {
            "entities": [],
            "claims": [],
            "edges": [],
            "relationships": [],  # New: entity-to-entity edges
            "contradictions": [],
            "summary": None,
            "key_topics": []
        }
        
        # Skip if Episode has no content
        if not episode.raw_content or not episode.raw_content.strip():
            print(f"  ⚠ Episode has no content, skipping")
            return results
        
        # 1. Extract entities, claims, and optionally relationships using LLM
        if extract_relationships:
            extraction = await self._extract_entities_claims_relationships(episode.raw_content)
            relationships = extraction.relationships if hasattr(extraction, 'relationships') else []
        else:
            extraction = await self._extract_entities_and_claims(episode.raw_content)
            relationships = []
        
        if not extraction.entities and not extraction.claims:
            print(f"  ⚠ No entities or claims extracted")
            return results
        
        rel_count = len(relationships) if relationships else 0
        print(f"  📦 Extracted {len(extraction.entities)} entities, {len(extraction.claims)} claims, {rel_count} relationships")
        
        # 2. Create/get entities in store
        entity_map = {}  # name -> Entity
        for extracted_entity in extraction.entities:
            entity = await self._create_or_get_entity(
                extracted_entity,
                episode.tenant_id
            )
            entity_map[extracted_entity.name.lower()] = entity
            results["entities"].append(entity)
            
            # Create or strengthen MENTIONS edge (co-occurrence strengthening)
            if hasattr(self.store, 'get_or_create_edge'):
                mentions_edge, _ = await self.store.get_or_create_edge(
                    EdgeCreate(
                        tenant_id=episode.tenant_id,
                        source_id=episode.id,
                        target_id=entity.id,
                        edge_type=EdgeType.MENTIONS
                    ),
                    strengthen_on_exist=True,
                    strengthen_amount=0.1
                )
            else:
                mentions_edge = await self.store.create_edge(EdgeCreate(
                    tenant_id=episode.tenant_id,
                    source_id=episode.id,
                    target_id=entity.id,
                    edge_type=EdgeType.MENTIONS
                ))
            results["edges"].append(mentions_edge)
        
        # 3. Create claims with ABOUT edges
        for extracted_claim in extraction.claims:
            # Find entities this claim is about
            entity_ids = []
            entity_names_found = []
            for entity_name in extracted_claim.entity_names:
                entity = entity_map.get(entity_name.lower())
                if entity:
                    entity_ids.append(entity.id)
                    entity_names_found.append(entity.name)
            
            if not entity_ids:
                print(f"    ⚠ Skipping claim - no matching entities: {extracted_claim.content[:50]}...")
                continue
            
            # Check for contradictions before creating
            contradictions = []
            if detect_contradictions:
                for entity_id in entity_ids:
                    existing_claims = await self.store.get_claims_for_entity(
                        entity_id, episode.tenant_id
                    )
                    if existing_claims:
                        contradiction_result = await self._detect_contradictions(
                            extracted_claim.content,
                            [c.content for c in existing_claims]
                        )
                        if contradiction_result.has_contradiction:
                            for rel in contradiction_result.relationships:
                                if rel.relationship == "CONTRADICTS":
                                    contradictions.append({
                                        "new_claim": extracted_claim.content,
                                        "existing_claim": existing_claims[rel.existing_claim_index].content,
                                        "explanation": rel.explanation
                                    })
            
            results["contradictions"].extend(contradictions)
            
            # Create the claim
            claim = await self._create_claim(
                extracted_claim,
                entity_ids,
                episode,
                entity_names_found
            )
            results["claims"].append(claim)
            
            # Create PRODUCED edge from Episode to Claim
            produced_edge = await self.store.create_edge(EdgeCreate(
                tenant_id=episode.tenant_id,
                source_id=episode.id,
                target_id=claim.id,
                edge_type=EdgeType.PRODUCED
            ))
            results["edges"].append(produced_edge)
        
        # 4. Create entity-to-entity relationship edges (NEW - key for multi-hop SAM)
        if extract_relationships and relationships:
            for rel in relationships:
                rel_edge = await self._create_relationship_edge(
                    rel, entity_map, episode.tenant_id
                )
                if rel_edge:
                    results["relationships"].append(rel_edge)
                    results["edges"].append(rel_edge)
            
            if results["relationships"]:
                print(f"  🔗 Created {len(results['relationships'])} entity-to-entity relationship edges")
        
        # 5. Generate Episode summary
        if generate_summary:
            summary_result = await self._generate_summary(episode.raw_content)
            results["summary"] = summary_result.summary
            results["key_topics"] = summary_result.key_topics
            
            # Update Episode with summary
            await self.store.close_episode(
                episode_id=episode.id,
                tenant_id=episode.tenant_id,
                summary=summary_result.summary,
                key_topics=summary_result.key_topics
            )
        
        rel_count = len(results.get('relationships', []))
        print(f"  ✓ Extraction complete: {len(results['entities'])} entities, "
              f"{len(results['claims'])} claims, {rel_count} relationships, "
              f"{len(results['contradictions'])} contradictions")
        
        return results
    
    async def _extract_entities_and_claims(
        self,
        content: str
    ) -> EntityClaimExtractionResult:
        """Extract entities and claims from content using LLM (legacy method)."""
        messages = [
            {"role": "system", "content": ENTITY_CLAIM_EXTRACTION_SYSTEM},
            {"role": "user", "content": ENTITY_CLAIM_EXTRACTION_USER.format(content=content)}
        ]
        
        try:
            result = self.llm_client.chat_completion_structured(
                messages=messages,
                response_format=EntityClaimExtractionResult,
                model=self.llm_client.processing_model
            )
            return result
        except Exception as e:
            print(f"  ⚠ Extraction failed: {e}")
            return EntityClaimExtractionResult()
    
    async def _extract_entities_claims_relationships(
        self,
        content: str
    ) -> EntityRelationshipExtractionResult:
        """Extract entities, claims, AND relationships from content using LLM.
        
        This is the enhanced extraction method that produces entity-to-entity
        relationship triples for multi-hop SAM traversal.
        """
        # Determine relationship types based on domain
        if self.domain == "healthcare":
            relationship_types = HEALTHCARE_RELATIONSHIP_TYPES
            domain_context = "This is a HEALTHCARE conversation. Pay special attention to medications, conditions, allergies, and provider relationships."
        else:
            relationship_types = DEFAULT_RELATIONSHIP_TYPES
            domain_context = ""
        
        system_prompt = ENTITY_RELATIONSHIP_EXTRACTION_SYSTEM.format(
            relationship_types=relationship_types
        )
        user_prompt = ENTITY_RELATIONSHIP_EXTRACTION_USER.format(
            content=content,
            domain_context=domain_context
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            result = self.llm_client.chat_completion_structured(
                messages=messages,
                response_format=EntityRelationshipExtractionResult,
                model=self.llm_client.processing_model
            )
            return result
        except Exception as e:
            print(f"  ⚠ Relationship extraction failed: {e}")
            # Fall back to legacy extraction
            legacy = await self._extract_entities_and_claims(content)
            return EntityRelationshipExtractionResult(
                entities=legacy.entities,
                claims=legacy.claims,
                relationships=[]
            )
    
    async def _create_relationship_edge(
        self,
        rel: ExtractedRelationship,
        entity_map: Dict[str, Entity],
        tenant_id: str
    ) -> Optional[Edge]:
        """Create an entity-to-entity relationship edge.
        
        Args:
            rel: The extracted relationship triple
            entity_map: Map of entity name (lowercase) -> Entity object
            tenant_id: Tenant ID
            
        Returns:
            Created Edge or None if entities not found
        """
        # Find source entity
        source_entity = entity_map.get(rel.subject_name.lower())
        if not source_entity:
            # Try fuzzy match
            for name, entity in entity_map.items():
                if rel.subject_name.lower() in name or name in rel.subject_name.lower():
                    source_entity = entity
                    break
        
        # Find target entity
        target_entity = entity_map.get(rel.object_name.lower())
        if not target_entity:
            # Try fuzzy match
            for name, entity in entity_map.items():
                if rel.object_name.lower() in name or name in rel.object_name.lower():
                    target_entity = entity
                    break
        
        if not source_entity or not target_entity:
            print(f"    ⚠ Skipping relationship - entities not found: "
                  f"{rel.subject_name} --{rel.relationship_type}--> {rel.object_name}")
            return None
        
        # Map relationship type to EdgeType
        rel_type_upper = rel.relationship_type.upper().replace(" ", "_")
        edge_type = RELATIONSHIP_TO_EDGE_TYPE.get(rel_type_upper, EdgeType.RELATED_TO)
        
        # Get weight for this relationship type
        weight = RELATIONSHIP_WEIGHTS.get(rel_type_upper, 0.5)
        
        # Create the edge
        try:
            if hasattr(self.store, 'get_or_create_edge'):
                edge, created = await self.store.get_or_create_edge(
                    EdgeCreate(
                        tenant_id=tenant_id,
                        source_id=source_entity.id,
                        target_id=target_entity.id,
                        edge_type=edge_type,
                        weight=weight,
                        metadata={
                            "relationship_type": rel.relationship_type,
                            "confidence": rel.confidence,
                            "evidence": rel.evidence
                        }
                    ),
                    strengthen_on_exist=True,
                    strengthen_amount=0.1
                )
            else:
                edge = await self.store.create_edge(EdgeCreate(
                    tenant_id=tenant_id,
                    source_id=source_entity.id,
                    target_id=target_entity.id,
                    edge_type=edge_type,
                    weight=weight,
                    metadata={
                        "relationship_type": rel.relationship_type,
                        "confidence": rel.confidence,
                        "evidence": rel.evidence
                    }
                ))
            
            return edge
        except Exception as e:
            print(f"    ⚠ Failed to create relationship edge: {e}")
            return None
    
    async def _create_or_get_entity(
        self,
        extracted: ExtractedEntity,
        tenant_id: str
    ) -> Entity:
        """Create or get existing entity, updating if needed."""
        # Try to find existing entity
        existing = await self.store.find_entity_by_name(
            extracted.name, tenant_id
        )
        
        if existing:
            # Increment mention count
            entity = await self.store.increment_entity_mention(
                existing.id, tenant_id
            )
            
            # TODO: Merge aliases if new ones provided
            
            return entity
        
        # Create new entity
        embedding = None
        if self.generate_embeddings:
            embedding = self.embeddings.embed_entity(
                extracted.name,
                extracted.entity_type,
                extracted.aliases
            )
        
        entity = await self.store.create_entity(EntityCreate(
            tenant_id=tenant_id,
            name=extracted.name,
            entity_type=extracted.entity_type,
            aliases=extracted.aliases,
            embedding=embedding
        ))
        
        return entity
    
    async def _create_claim(
        self,
        extracted: ExtractedClaim,
        entity_ids: List[str],
        episode: Episode,
        entity_names: List[str]
    ) -> Claim:
        """Create a new claim."""
        # Map claim_kind string to enum
        claim_kind_map = {
            "permanent": ClaimKind.PERMANENT,
            "stable": ClaimKind.STABLE,
            "contextual": ClaimKind.CONTEXTUAL,
            "ephemeral": ClaimKind.EPHEMERAL
        }
        claim_kind = claim_kind_map.get(extracted.claim_kind, ClaimKind.STABLE)
        
        # Generate embedding
        embedding = None
        if self.generate_embeddings:
            embedding = self.embeddings.embed_claim(
                extracted.content,
                entity_names
            )
        
        claim = await self.store.create_claim(ClaimCreate(
            tenant_id=episode.tenant_id,
            content=extracted.content,
            claim_kind=claim_kind,
            confidence=extracted.confidence,
            source_episode_id=episode.id,
            entity_ids=entity_ids,
            embedding=embedding
        ))
        
        return claim
    
    async def _detect_contradictions(
        self,
        new_claim: str,
        existing_claims: List[str]
    ) -> ContradictionDetectionResult:
        """Detect contradictions between new claim and existing claims."""
        if not existing_claims:
            return ContradictionDetectionResult()
        
        existing_formatted = "\n".join([
            f"{i}. {claim}" for i, claim in enumerate(existing_claims)
        ])
        
        messages = [
            {"role": "system", "content": CONTRADICTION_DETECTION_SYSTEM},
            {"role": "user", "content": CONTRADICTION_DETECTION_USER.format(
                new_claim=new_claim,
                existing_claims=existing_formatted
            )}
        ]
        
        try:
            result = self.llm_client.chat_completion_structured(
                messages=messages,
                response_format=ContradictionDetectionResult,
                model=self.llm_client.processing_model
            )
            return result
        except Exception as e:
            print(f"  ⚠ Contradiction detection failed: {e}")
            return ContradictionDetectionResult()
    
    async def _generate_summary(
        self,
        content: str
    ) -> EpisodeSummaryResult:
        """Generate Episode summary."""
        messages = [
            {"role": "system", "content": EPISODE_SUMMARY_SYSTEM},
            {"role": "user", "content": EPISODE_SUMMARY_USER.format(content=content)}
        ]
        
        try:
            result = self.llm_client.chat_completion_structured(
                messages=messages,
                response_format=EpisodeSummaryResult,
                model=self.llm_client.processing_model
            )
            return result
        except Exception as e:
            print(f"  ⚠ Summary generation failed: {e}")
            return EpisodeSummaryResult(
                summary="Summary generation failed",
                key_topics=["unknown"]
            )
    
    async def synthesize_insights(
        self,
        entity: Entity,
        min_claims: int = 3
    ) -> List[Insight]:
        """
        Synthesize insights from claims about an entity.
        
        Args:
            entity: Entity to synthesize insights for
            min_claims: Minimum claims required to attempt synthesis
            
        Returns:
            List of created Insight objects
        """
        # Get claims about this entity
        claims = await self.store.get_claims_for_entity(
            entity.id, entity.tenant_id
        )
        
        if len(claims) < min_claims:
            print(f"  ⚠ Not enough claims ({len(claims)}) for insight synthesis")
            return []
        
        # Format claims for LLM
        claims_formatted = "\n".join([
            f"{i}. {claim.content} (confidence: {claim.confidence:.2f})"
            for i, claim in enumerate(claims)
        ])
        
        messages = [
            {"role": "system", "content": INSIGHT_SYNTHESIS_SYSTEM},
            {"role": "user", "content": INSIGHT_SYNTHESIS_USER.format(
                entity_name=entity.name,
                claims=claims_formatted
            )}
        ]
        
        try:
            result = self.llm_client.chat_completion_structured(
                messages=messages,
                response_format=InsightSynthesisResult,
                model=self.llm_client.reasoning_model  # Use reasoning model for synthesis
            )
        except Exception as e:
            print(f"  ⚠ Insight synthesis failed: {e}")
            return []
        
        if not result.has_meaningful_insights:
            return []
        
        # Create insights
        created_insights = []
        for synthesized in result.insights:
            # Get source claim IDs
            source_claim_ids = [
                claims[i].id for i in synthesized.source_claim_indices
                if i < len(claims)
            ]
            
            # Generate embedding
            embedding = None
            if self.generate_embeddings:
                embedding = self.embeddings.embed_text(synthesized.content)
            
            insight = await self.store.create_insight(InsightCreate(
                tenant_id=entity.tenant_id,
                content=synthesized.content,
                confidence=synthesized.confidence,
                source_claim_ids=source_claim_ids,
                embedding=embedding
            ))
            created_insights.append(insight)
            
            # Create DERIVED_FROM edges from Insight to source Claims
            for claim_id in source_claim_ids:
                await self.store.create_edge(EdgeCreate(
                    tenant_id=entity.tenant_id,
                    source_id=insight.id,
                    target_id=claim_id,
                    edge_type=EdgeType.DERIVED_FROM
                ))
        
        print(f"  💡 Synthesized {len(created_insights)} insights for {entity.name}")
        return created_insights
