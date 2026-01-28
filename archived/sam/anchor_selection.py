"""
SAM Anchor Selection Module

Improved anchor selection using:
1. Named entity recognition patterns
2. Query parsing for entity mentions
3. Relationship extraction
4. Multi-hop query planning
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class QueryPlan:
    """Structured representation of a query for multi-hop retrieval."""
    original_query: str
    extracted_entities: List[str]
    extracted_relationships: List[str]
    inferred_entity_types: List[str]
    requires_multi_hop: bool
    estimated_hops: int
    search_terms: List[str]
    anchor_boost_terms: List[str]  # Terms to boost in anchor search


# Named entity patterns - expanded for better coverage
ENTITY_PATTERNS = [
    # Person names: Capitalized word followed by 1-2 more capitalized words
    # Use non-greedy matching and explicit word boundaries
    (r'(?<![A-Za-z])([A-Z][a-z]+)\s+([A-Z][a-z]+)(?:\s+([A-Z][a-z]+))?(?![A-Za-z])', 'PERSON'),
    (r'\b(Dr\.|Mr\.|Ms\.|Mrs\.|Prof\.)\s*([A-Z][a-z]+)(?:\s+([A-Z][a-z]+))?', 'PERSON'),
    
    # Single proper names (common first names) - for healthcare scenarios
    # This pattern matches capitalized words that are likely person names
    (r"\b([A-Z][a-z]+)'s\b", 'PERSON'),  # "Michael's" -> Michael
    
    # Organizations
    (r'\b([A-Z][a-zA-Z]*(?:Corp|Inc|LLC|Ltd|Co|Company|Team|Division|Group))\b', 'ORG'),
    (r'\b(TechCorp|Raytheon|NVIDIA|Google|Microsoft|Amazon|Apple)\b', 'ORG'),
    
    # Locations - explicit list
    (r'\b(San Francisco|Boston|Seattle|Bay Area|Yosemite|Stowe|Lands End)\b', 'LOCATION'),
    
    # Technical terms
    (r'\b(PointPillars|EfficientNetV2|BEVFusion|TransFusion|FPN|DETR|ViT)\b', 'TECH'),
    (r'\b(LiDAR|RADAR|camera|sensor|GPU|Orin)\b', 'TECH'),
    (r'\b(PyTorch|TensorFlow|CUDA|SLURM|nuScenes|Waymo|CARLA)\b', 'TECH'),
    
    # Conferences/Publications
    (r'\b(CVPR|ICCV|NeurIPS|ICML|ECCV|AAAI)(?:\s*\d{4})?\b', 'CONFERENCE'),
    
    # Roles
    (r'\b(senior\s+)?(?:ML|software|data)\s+engineer\b', 'ROLE'),
    (r'\b(?:Principal|Staff|Senior|Junior)\s+Engineer\b', 'ROLE'),
    (r'\b(team lead|mentor|mentee|manager)\b', 'ROLE'),
    
    # Healthcare-specific patterns
    (r'\b(penicillin|amoxicillin|azithromycin|metformin|lisinopril|ibuprofen|aspirin)\b', 'MEDICATION'),
    (r'\b(diabetes|hypertension|allergy|allergies|blood pressure|heart disease)\b', 'CONDITION'),
]

# Relationship patterns for multi-hop detection
RELATIONSHIP_PATTERNS = [
    # Possessive/belonging patterns
    (r"(\w+)'s\s+(\w+)", 'POSSESSIVE'),  # "Alice's team", "Alice's dad"
    (r"the\s+(\w+)\s+of\s+the\s+(\w+)", 'OF_RELATION'),
    
    # Role relationships
    (r"(\w+)\s+(?:who|that)\s+(?:is|was)\s+(?:a|an|the)\s+(\w+)", 'ROLE_OF'),
    (r"the\s+person\s+(?:who|that)\s+(\w+)", 'PERSON_WHO'),
    
    # Multi-hop indicators
    (r"the\s+(?:father|mother|parent|dad|mom)\s+of", 'FAMILY_HOP'),
    (r"(?:work|works|worked)\s+(?:at|for|with)", 'WORK_HOP'),
    (r"(?:mentor|mentors|mentored)\s+(\w+)", 'MENTOR_HOP'),
    (r"(?:team|project)\s+(?:led|leads)\s+by", 'LEAD_HOP'),
]

# Multi-hop query indicators
MULTI_HOP_INDICATORS = [
    # Indirect references
    r"the person who",
    r"the one who",
    r"someone who",
    r"the team that",
    r"the project that",
    
    # Family/relationship chains
    r"father of",
    r"mother of",
    r"parent of",
    r"'s (?:father|mother|dad|mom|parent)",
    r"'s (?:team|project|work|company)",
    
    # Property chains
    r"the (?:\w+) of the (?:\w+) who",
    r"what (?:does|did) the (?:\w+) of",
    
    # Indirect questions
    r"what (?:company|project|team|work) does .+ do",
    r"where does .+ work",
    r"who (?:works|worked) (?:with|for|at)",
]


def extract_entities(text: str) -> List[Tuple[str, str]]:
    """
    Extract named entities from text.
    
    Returns:
        List of (entity_name, entity_type) tuples
    """
    entities = []
    
    for pattern, entity_type in ENTITY_PATTERNS:
        matches = re.finditer(pattern, text)
        for match in matches:
            # Handle grouped patterns (for PERSON names with multiple groups)
            groups = match.groups()
            if groups and any(groups):
                # Join non-None groups with space
                entity = ' '.join(g for g in groups if g)
            else:
                entity = match.group(0)
            
            entity = entity.strip()
            # Clean up entity
            entity = re.sub(r'^(Dr\.|Mr\.|Ms\.|Mrs\.|Prof\.)\s*', '', entity)
            if len(entity) > 1:  # Skip single chars
                entities.append((entity, entity_type))
    
    # Also extract single capitalized words that might be names
    # Common question words and articles to exclude
    stop_words = {
        'what', 'who', 'when', 'where', 'why', 'how', 'which',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'can', 'could', 'should', 'would', 'will', 'may', 'might',
        'do', 'does', 'did', 'has', 'have', 'had', 'to', 'for',
        'in', 'on', 'at', 'by', 'with', 'from', 'about', 'of',
        'if', 'then', 'and', 'or', 'but', 'because', 'that', 'this'
    }
    
    # Find single capitalized words not at start of sentence
    words = text.split()
    for i, word in enumerate(words):
        # Clean punctuation
        clean_word = re.sub(r'[^\w]', '', word)
        if not clean_word:
            continue
            
        # Skip if it's a known stop word
        if clean_word.lower() in stop_words:
            continue
            
        # Check if it's a capitalized word (not at sentence start or after '?')
        if clean_word[0].isupper() and clean_word[1:].islower() and len(clean_word) > 2:
            # If not the first word, or first word after common question starters
            if i > 0 or (i == 0 and not any(text.lower().startswith(q) for q in ['what', 'who', 'where', 'when', 'why', 'how', 'which', 'is', 'are', 'can', 'could', 'should', 'would'])):
                # Likely a proper noun/name
                entities.append((clean_word, 'PROPER_NOUN'))
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for ent, etype in entities:
        key = ent.lower()
        if key not in seen:
            seen.add(key)
            unique.append((ent, etype))
    
    return unique


def detect_multi_hop(query: str) -> Tuple[bool, int]:
    """
    Detect if query requires multi-hop reasoning.
    
    Returns:
        Tuple of (requires_multi_hop, estimated_hops)
    """
    query_lower = query.lower()
    hop_score = 0
    
    for pattern in MULTI_HOP_INDICATORS:
        if re.search(pattern, query_lower):
            hop_score += 1
    
    # Count relationship chains
    possessives = len(re.findall(r"'s\s+\w+", query_lower))
    hop_score += possessives
    
    # Count "of the" chains
    of_chains = len(re.findall(r"of the", query_lower))
    hop_score += of_chains
    
    # Indirect references add hops
    indirect = len(re.findall(r"the (?:person|one|team) (?:who|that)", query_lower))
    hop_score += indirect
    
    if hop_score >= 3:
        return True, 3
    elif hop_score >= 1:
        return True, 2
    else:
        return False, 1


def extract_search_terms(query: str) -> List[str]:
    """
    Extract important search terms from query.
    
    Focuses on nouns, names, and technical terms.
    """
    # Remove common question words
    stop_words = {
        'what', 'who', 'where', 'when', 'why', 'how', 'which',
        'is', 'are', 'was', 'were', 'the', 'a', 'an', 'and', 'or',
        'of', 'to', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'does', 'did', 'do', 'has', 'have', 'had', 'that', 'this',
        'it', 'its', 'they', 'them', 'their', 'be', 'been', 'being'
    }
    
    # Tokenize
    words = re.findall(r'\b\w+\b', query.lower())
    
    # Filter stop words and short words
    terms = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Boost capitalized words from original
    capitalized = re.findall(r'\b[A-Z][a-zA-Z]+\b', query)
    for cap in capitalized:
        if cap.lower() not in stop_words:
            terms.insert(0, cap.lower())
    
    # Deduplicate
    seen = set()
    unique = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    
    return unique


def analyze_query(query: str) -> QueryPlan:
    """
    Analyze a query to create a retrieval plan.
    
    This is the main entry point for improved anchor selection.
    
    Args:
        query: Natural language query
        
    Returns:
        QueryPlan with extraction and planning info
    """
    # Extract entities
    entities = extract_entities(query)
    entity_names = [name for name, _ in entities]
    entity_types = list(set(etype for _, etype in entities))
    
    # Detect multi-hop requirements
    requires_multi_hop, estimated_hops = detect_multi_hop(query)
    
    # Extract search terms
    search_terms = extract_search_terms(query)
    
    # Extract relationships
    relationships = []
    for pattern, rel_type in RELATIONSHIP_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            relationships.append(rel_type)
    
    # Compute anchor boost terms
    # Prioritize: entities > capitalized > other terms
    anchor_boost = entity_names.copy()
    
    # Add capitalized words not in entities
    capitalized = re.findall(r'\b[A-Z][a-zA-Z]+\b', query)
    for cap in capitalized:
        if cap not in anchor_boost:
            anchor_boost.append(cap)
    
    # Add remaining search terms
    for term in search_terms:
        if term not in [a.lower() for a in anchor_boost]:
            anchor_boost.append(term)
    
    return QueryPlan(
        original_query=query,
        extracted_entities=entity_names,
        extracted_relationships=relationships,
        inferred_entity_types=entity_types,
        requires_multi_hop=requires_multi_hop,
        estimated_hops=estimated_hops,
        search_terms=search_terms,
        anchor_boost_terms=anchor_boost[:10]  # Top 10
    )


def get_optimized_search_query(query_plan: QueryPlan) -> str:
    """
    Create an optimized search query from the plan.
    
    Focuses on entity names and key terms for better anchor matching.
    """
    terms = []
    
    # Add entities first
    terms.extend(query_plan.extracted_entities)
    
    # Add boost terms
    for term in query_plan.anchor_boost_terms:
        if term not in terms:
            terms.append(term)
    
    return " ".join(terms)


def suggest_activation_params(query_plan: QueryPlan) -> Dict[str, Any]:
    """
    Suggest activation parameters based on query analysis.
    
    Multi-hop queries need:
    - Higher max_depth
    - Lower activation threshold
    - More anchors
    """
    params = {
        "max_depth": 3,
        "activation_threshold": 0.05,
        "anchor_top_k": 10,
        "activation_decay": 0.7,
    }
    
    if query_plan.requires_multi_hop:
        hops = query_plan.estimated_hops
        
        # Increase depth for multi-hop
        params["max_depth"] = max(3, hops + 1)
        
        # Lower threshold to allow more exploration
        params["activation_threshold"] = 0.03
        
        # More anchors for broader search
        params["anchor_top_k"] = 15
        
        # Slightly less decay for deeper traversal
        params["activation_decay"] = 0.75
    
    return params
