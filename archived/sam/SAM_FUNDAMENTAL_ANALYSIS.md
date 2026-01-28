# SAM Algorithm: Fundamental Analysis & Redesign

## Executive Summary

After deep analysis of the Spreading Activation Memory (SAM) algorithm, I've identified several fundamental issues that explain why SAM underperforms compared to simple vector search on multi-hop queries. This document outlines the root causes, what principles still hold, and a proposed redesign.

## 1. The Actual Graph Structure

From analyzing the healthcare test database:

```
Entities: 138
Claims: 424
Edges: 2,233

Edge Type Distribution:
- ABOUT: 951 (claims pointing to entities)
- MENTIONS: 580 (claims mentioning entities)  
- PRODUCED: 424 (episodes producing claims)
- RELATED_TO: 90 (generic entity relationships)
- CAUSES: 22 (causal relationships)
- TREATS: 17
- TAKES: 16 (patient takes medication)
- SIDE_EFFECT_OF: 4 (rare but critical!)
```

**Key Insight #1**: The graph is dominated by STRUCTURAL edges (ABOUT, MENTIONS, PRODUCED = 88%) with only 12% being SEMANTIC edges (TAKES, TREATS, CAUSES, etc.). The semantic edges we want to prioritize are rare.

**Key Insight #2**: The semantic edges ARE there and ARE correct:
```
Hydrochlorothiazide --CAUSES--> muscle cramps (weight=0.85)
leg cramps --SIDE_EFFECT_OF--> HCTZ
```

So the answer to "What causes Michael's muscle cramps?" is in the graph as a direct 3-hop path:
```
Michael --TAKES--> Hydrochlorothiazide --CAUSES--> muscle cramps
```

## 2. Why Vector Search Wins

Vector search directly embeds the query "What could be causing Michael's muscle cramps?" and finds claims with similar embeddings:

```
TOP 10 Vector Results:
1. "Michael experiences leg cramps"
2. "Michael experienced leg cramps"
3. "Eating bananas and taking potassium supplement reduced Michael's leg cramps"
4. "Michael experienced leg cramps after starting HCTZ"
5. "Low potassium can cause muscle cramps"
```

These claims have high cosine similarity because:
- They literally contain "cramps", "Michael", "leg"
- The embedding captures the semantic query about muscle issues

**Vector's advantage**: It jumps directly to the ANSWER (claims) without needing to traverse a graph.

## 3. Why SAM Loses

### Problem A: The Hub Amplification Problem

Michael has 247 connections. When we anchor Michael at 0.9 activation:

```
Michael (0.9) 
  ├── TAKES → Metformin (0.9 × 0.7 × 1.8 = 1.13)
  │              └── claims about Metformin...
  ├── TAKES → Lisinopril (0.9 × 0.7 × 1.8 = 1.13)
  │              └── claims about Lisinopril...
  ├── TAKES → HCTZ (0.9 × 0.7 × 1.8 = 1.13)
  │              └── claims about HCTZ & cramps...
  ├── TAKES → 6 more medications...
  └── 230+ other edges (ABOUT, MENTIONS, etc.)
```

Even with degree penalty, Michael spreads activation to ALL 247 neighbors. The claims about cramps compete with claims about A1C, blood pressure, allergies, etc.

### Problem B: Multiplicative Boost Compounding

The current formula has multiple multiplicative boosts:
```python
new_activation = (
    current_activation 
    × decay (0.7)
    × edge_weight (~1.0)
    × edge_type_boost (up to 2.0)
    × degree_penalty (0.1-1.0)
    × goal_boost (up to 1.3)
    × dead_end_penalty (0.3-1.0)
    × claim_boost (2.0)
)
```

When these compound favorably:
- Path: Michael → Metformin → Metformin claims
- Calculation: 0.9 × 0.7 × 1.8 × 0.65 × 1.3 × 1.0 × 2.0 = **1.9**

When they compound unfavorably:
- Path: muscle cramps → cramp claims  
- Calculation: 0.9 × 0.7 × 1.0 × 1.0 × 0.85 × 1.0 × 2.0 = **1.1**

The medication path BEATS the symptom path despite the symptom being more relevant!

### Problem C: Query Focus vs. Context Confusion

The query "What could be causing Michael's muscle cramps?" has:
- **Context entity**: Michael (who is the patient)
- **Focus entity**: muscle cramps (what we're asking about)

But SAM treats them equally (both anchored at 0.9). Michael should be a CONTEXT anchor (providing filtering), not a SPREADING anchor.

### Problem D: Edge Type Boosts Are Wrong Direction

TAKES boost (1.8x) helps spreading from Michael → medications. But what we WANT is:
- CAUSES boost going FROM medication/condition → symptom
- SIDE_EFFECT_OF boost going FROM symptom → medication

The directionality of semantic edges matters for answering causal questions.

## 4. What Still Holds True

### Principle 1: Graph Structure Has Value
The path `Michael → TAKES → HCTZ → CAUSES → muscle cramps` IS the right answer. Pure vector search can't explicitly represent or traverse this path.

### Principle 2: Semantic Edges Are More Valuable
TAKES, CAUSES, SIDE_EFFECT_OF edges encode domain knowledge that pure similarity doesn't capture.

### Principle 3: Activation Decay Makes Sense
Information further from the query focus should generally be less relevant.

### Principle 4: Claims Are The Answers
Entities are concepts; claims are facts. The final retrieval should be claims, not entities.

## 5. Proposed Algorithm Redesign

### 5.1 Separate Context Anchors from Focus Anchors

```python
@dataclass
class QueryDecomposition:
    context_entities: List[str]  # e.g., ["Michael"] - who/what provides context
    focus_entities: List[str]    # e.g., ["muscle cramps"] - what we're asking about
    query_intent: str            # e.g., "CAUSE" - what relationship we're seeking
```

Different anchor types get different treatment:
- **Context anchors**: Lower initial activation (0.5), heavy degree penalty
- **Focus anchors**: Higher initial activation (1.0), standard penalty

### 5.2 Intent-Directed Edge Following

Instead of uniform edge type boosts, use query intent to choose which edges to follow:

```python
INTENT_EDGE_PREFERENCES = {
    "CAUSE": [EdgeType.CAUSES, EdgeType.SIDE_EFFECT_OF, EdgeType.RESULTS_IN],
    "TREATMENT": [EdgeType.TREATS, EdgeType.PRESCRIBED, EdgeType.MANAGES],
    "MEDICATION": [EdgeType.TAKES, EdgeType.PRESCRIBED],
}

def should_follow_edge(edge_type, query_intent):
    preferred = INTENT_EDGE_PREFERENCES.get(query_intent, [])
    if edge_type in preferred:
        return 1.0  # Full weight
    elif edge_type in SEMANTIC_EDGES:
        return 0.5  # Reduced weight
    else:
        return 0.2  # Low weight for structural edges
```

### 5.3 Claim-Centric Final Retrieval

Instead of mixing entities and claims in the result, use a two-phase approach:

**Phase 1: Entity Spreading**
Spread activation only through entities, following semantic edges.

**Phase 2: Claim Collection**
For each activated entity, collect claims ABOUT that entity, weighted by entity activation:
```python
claim_score = entity_activation × claim_relevance_to_query
```

### 5.4 Simpler Activation Formula

Remove compounding boosts. Use ONE adjustment factor per hop:

```python
new_activation = current_activation × decay × edge_factor

where edge_factor = edge_weight × intent_match × (1 / sqrt(degree))
```

No multiplicative goal boost, claim boost, dead-end penalty. These are post-processing filters.

### 5.5 Sublinear Accumulation

When a node is reached by multiple paths, use sublinear accumulation instead of MAX:

```python
# Current (MAX):
activation = max(old_activation, new_activation)

# Proposed (sublinear):
activation = sqrt(old_activation² + new_activation²)
```

This rewards being reached by multiple paths without runaway amplification.

## 6. Immediate Fixes (Before Full Redesign)

### Fix 1: Reduce Context Entity Spreading

```python
def anchor_activation_for(entity_name, query):
    if is_context_entity(entity_name, query):  # e.g., patient name
        return 0.5  # Lower starting point
    else:
        return 0.9  # Normal focus entity
```

### Fix 2: Remove Edge Type Boost Entirely

Set all edge_type_boost to 1.0. Let edge weights alone determine importance.

### Fix 3: Filter to Claims Only in Results

```python
# After spreading
activated = [n for n in activated if n.node_type == NodeType.CLAIM]
```

### Fix 4: Goal-Directed as Filter, Not Boost

```python
# Instead of multiplying goal_boost during spreading:
# Post-filter by goal relevance
activated = [n for n in activated if goal_relevance(n, goal) > 0.3]
```

## 7. Evaluation Framework

To avoid overfitting to one scenario, we need a proper evaluation:

### Test Query Categories:
1. **Single-hop**: "What medications does Michael take?"
   - Expected: Direct claims about Michael's medications
   
2. **Multi-hop causal**: "What could be causing Michael's muscle cramps?"
   - Expected: Claims linking medication → side effect
   
3. **Multi-hop treatment**: "How is Michael's blood pressure being treated?"
   - Expected: Claims about Lisinopril, dosage changes
   
4. **Temporal reasoning**: "What changed after switching to Losartan?"
   - Expected: Claims with temporal context

### Metrics:
- **Precision@10**: Are the top 10 results relevant?
- **Recall@10**: Are the key facts in top 10?
- **Path Validity**: Does the algorithm follow the RIGHT paths?

## 8. Conclusion

The fundamental issue isn't any single parameter. It's that:

1. **The algorithm conflates context and focus** - treating patient entity same as symptom entity
2. **Multiplicative boosts compound unpredictably** - creating amplification instead of decay
3. **Edge following is undirected** - doesn't consider query intent
4. **Results mix node types** - entities crowd out claims

The solution requires rethinking the algorithm structure, not just tuning parameters.

---

## Appendix: Graph Structure Analysis Output

```
Michael's medications (via TAKES edges):
- Metformin
- Lisinopril  
- baby aspirin
- Vitamin D
- ibuprofen
- potassium supplement
- Losartan
- Hydrochlorothiazide
- HCTZ

Edges TO 'muscle cramps' entity:
- Hydrochlorothiazide 12.5mg --CAUSES--> muscle cramps (w=0.95)
- Hydrochlorothiazide --CAUSES--> muscle cramps (w=0.85)
- potassium --RELATED_TO--> muscle cramps (w=0.5)

The CORRECT 3-hop path exists:
Michael --TAKES--> Hydrochlorothiazide --CAUSES--> muscle cramps

But it competes with 247 other paths from Michael.
```
