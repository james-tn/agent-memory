"""
SAM Domain-Specific Configurations

Provides domain-specific ontologies, entity types, and relationship types
to improve extraction and retrieval quality for targeted use cases.

Available domains:
- generic: Default universal schema (works for any domain)
- healthcare: Patient health records, medications, conditions
- (future) shopping: Product recommendations, purchase history
- (future) legal: Case management, precedents, parties
"""

from sam.domains.base import DomainConfig, get_domain_config, list_domains
from sam.domains.generic import GenericDomain
from sam.domains.healthcare import HealthcareDomain

__all__ = [
    "DomainConfig",
    "get_domain_config", 
    "list_domains",
    "GenericDomain",
    "HealthcareDomain",
]
