"""
Base domain configuration classes.

Domains define:
1. Entity types specific to the domain
2. Relationship types (edge types) for graph traversal
3. Extraction prompts optimized for the domain
4. Multi-hop query patterns
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Type
from enum import Enum


@dataclass
class EntityTypeConfig:
    """Configuration for a domain-specific entity type."""
    name: str
    description: str
    examples: List[str]
    extraction_hints: List[str] = field(default_factory=list)


@dataclass
class RelationshipTypeConfig:
    """Configuration for a domain-specific relationship type."""
    name: str
    description: str
    source_types: List[str]  # Valid source entity types
    target_types: List[str]  # Valid target entity types
    examples: List[str]
    is_symmetric: bool = False
    supports_multi_hop: bool = True  # Whether this edge type is useful for multi-hop


@dataclass
class MultiHopPattern:
    """Pattern for detecting multi-hop queries in this domain."""
    pattern: str  # Regex pattern
    description: str
    expected_hops: int
    example_query: str
    traversal_hint: str  # e.g., "patient -> medication -> contraindication"


@dataclass
class DomainConfig:
    """
    Complete configuration for a domain-specific ontology.
    
    This controls:
    - What entity types are extracted
    - What relationship types are created
    - How multi-hop queries are detected
    - Extraction prompt customization
    """
    domain_id: str
    display_name: str
    description: str
    
    # Ontology
    entity_types: List[EntityTypeConfig]
    relationship_types: List[RelationshipTypeConfig]
    
    # Multi-hop patterns
    multi_hop_patterns: List[MultiHopPattern] = field(default_factory=list)
    
    # Extraction customization
    extraction_system_prompt: str = ""
    extraction_examples: List[Dict[str, Any]] = field(default_factory=list)
    
    # Retrieval customization
    default_activation_decay: float = 0.7
    default_max_depth: int = 3
    default_activation_threshold: float = 0.05
    
    def get_entity_type_names(self) -> List[str]:
        """Get list of entity type names."""
        return [et.name for et in self.entity_types]
    
    def get_relationship_type_names(self) -> List[str]:
        """Get list of relationship type names."""
        return [rt.name for rt in self.relationship_types]
    
    def get_multi_hop_relationship_types(self) -> List[str]:
        """Get relationship types that support multi-hop traversal."""
        return [rt.name for rt in self.relationship_types if rt.supports_multi_hop]
    
    def build_extraction_prompt(self) -> str:
        """Build domain-specific extraction prompt."""
        entity_section = "## Entity Types\n"
        for et in self.entity_types:
            entity_section += f"- **{et.name}**: {et.description}\n"
            entity_section += f"  Examples: {', '.join(et.examples)}\n"
        
        relationship_section = "## Relationship Types\n"
        for rt in self.relationship_types:
            entity_section += f"- **{rt.name}**: {rt.description}\n"
            entity_section += f"  From: {rt.source_types} → To: {rt.target_types}\n"
            entity_section += f"  Examples: {', '.join(rt.examples)}\n"
        
        return f"""You are extracting information for a {self.display_name} application.

{self.description}

{entity_section}

{relationship_section}

{self.extraction_system_prompt}
"""


# Domain registry
_DOMAIN_REGISTRY: Dict[str, Type["DomainConfig"]] = {}


def register_domain(domain_id: str):
    """Decorator to register a domain configuration."""
    def decorator(cls):
        _DOMAIN_REGISTRY[domain_id] = cls
        return cls
    return decorator


def get_domain_config(domain_id: str) -> DomainConfig:
    """Get domain configuration by ID."""
    if domain_id not in _DOMAIN_REGISTRY:
        raise ValueError(f"Unknown domain: {domain_id}. Available: {list(_DOMAIN_REGISTRY.keys())}")
    return _DOMAIN_REGISTRY[domain_id]()


def list_domains() -> List[str]:
    """List available domain IDs."""
    return list(_DOMAIN_REGISTRY.keys())
