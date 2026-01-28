# 🧠 Spreading Activation: Deep Dive

## The Cognitive Science Foundation

Spreading Activation is a theory of how human memory works, first proposed by **Allan Collins and Elizabeth Loftus in 1975**. It explains why thinking about one thing naturally brings related things to mind.

---

## 🌊 The Core Insight: Memory as a Network

```
Traditional View (Filing Cabinet):          Reality (Neural Network):
─────────────────────────────────           ─────────────────────────

┌─────────────────────────────┐            Every memory is connected
│ Memory #1: "Emma"           │            to many other memories
├─────────────────────────────┤            through associations.
│ Memory #2: "College"        │
├─────────────────────────────┤                    ┌─────────┐
│ Memory #3: "529 Plan"       │                    │  Emma   │
├─────────────────────────────┤                   ╱    │     ╲
│ Memory #4: "Tax Benefits"   │            ┌─────┐    │      ┌─────┐
└─────────────────────────────┘            │Age 8│    │      │Smile│
                                           └─────┘    │      └─────┘
Retrieval: Search each one                       ┌────┴────┐
separately for relevance                         │ College │
                                                 │  Goal   │
                                                ╱    │     ╲
                                         ┌─────┐    │      ┌──────┐
                                         │ 529 │────┴──────│Stress│
                                         │Plan │           └──────┘
                                         └──┬──┘
                                            │
                                       ┌────┴────┐
                                       │   Tax   │
                                       │Benefits │
                                       └─────────┘
```

---

## ⚡ How Activation Spreads

When you think of something, that memory node becomes **activated**. This activation then **spreads** to connected nodes, like ripples in a pond:

```
Time T=0: Query "Emma"
─────────────────────────────────────────────────────────────────────────

                                    🔥 ACTIVATED
                                   ╔═══════════╗
                                   ║   Emma    ║  activation = 1.0
                                   ║  (query)  ║
                                   ╚═════╤═════╝
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
         ┌─────────┐              ┌─────────────┐              ┌─────────┐
         │  Age 8  │              │   College   │              │ Daughter│
         │         │              │    Goal     │              │         │
         └─────────┘              └─────────────┘              └─────────┘
           (dormant)                (dormant)                   (dormant)


Time T=1: Activation spreads (decay = 0.7)
─────────────────────────────────────────────────────────────────────────

                                   ╔═══════════╗
                                   ║   Emma    ║  activation = 1.0
                                   ╚═════╤═════╝
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │ × 0.7                    │ × 0.7                    │ × 0.7
              ▼                          ▼                          ▼
         ╔═════════╗              ╔═════════════╗              ╔═════════╗
         ║  Age 8  ║  0.7         ║   College   ║  0.7         ║Daughter ║  0.7
         ╚═════════╝              ║    Goal     ║              ╚═════════╝
                                  ╚══════╤══════╝
                                         │
                          ┌──────────────┼──────────────┐
                          ▼              ▼              ▼
                     ┌─────────┐   ┌─────────┐   ┌─────────┐
                     │Savings  │   │ 529 Plan│   │ Stress  │
                     └─────────┘   └─────────┘   └─────────┘
                       (dormant)    (dormant)     (dormant)


Time T=2: Second hop (decay = 0.7 × 0.7 = 0.49)
─────────────────────────────────────────────────────────────────────────

                                   ╔═══════════╗
                                   ║   Emma    ║  1.0
                                   ╚═════╤═════╝
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              ▼                          ▼                          ▼
         ╔═════════╗              ╔═════════════╗              ╔═════════╗
         ║  Age 8  ║  0.7         ║   College   ║  0.7         ║Daughter ║  0.7
         ╚════╤════╝              ║    Goal     ║              ╚═════════╝
              │                   ╚══════╤══════╝
              ▼                          │
         ┌─────────┐       ┌─────────────┼─────────────┐
         │10 years │       ▼             ▼             ▼
         │ horizon │  ╔═════════╗  ╔═════════╗   ╔═════════╗
         └─────────┘  ║Savings  ║  ║ 529 Plan║   ║ Stress  ║
           0.49       ║  0.49   ║  ║   0.49  ║   ║  0.49   ║
                      ╚═════════╝  ╚════╤════╝   ╚═════════╝
                                        │
                                        ▼
                                  ┌───────────┐
                                  │    Tax    │
                                  │ Benefits  │
                                  └───────────┘
                                     0.34 (0.49 × 0.7)


Final Activation Map:
─────────────────────────────────────────────────────────────────────────

Node                    Activation    Hops from Query
────────────────────    ──────────    ───────────────
Emma                    1.00          0 (anchor)
College Goal            0.70          1
Age 8                   0.70          1
Daughter                0.70          1
529 Plan                0.49          2
Savings                 0.49          2
Stress                  0.49          2
10 year horizon         0.49          2
Tax Benefits            0.34          3
```

---

## 🔬 The Mathematical Model

### Basic Spreading Activation Equation

$$A_j(t+1) = \sum_{i} w_{ij} \cdot A_i(t) \cdot d$$

Where:
- $A_j(t+1)$ = Activation of node $j$ at time $t+1$
- $A_i(t)$ = Activation of node $i$ at time $t$
- $w_{ij}$ = Weight of edge from $i$ to $j$
- $d$ = Decay factor (typically 0.7-0.9)

### With Threshold Pruning

$$A_j(t+1) = \begin{cases} 
\sum_{i} w_{ij} \cdot A_i(t) \cdot d & \text{if } A_i(t) \cdot d > \theta \\
0 & \text{otherwise}
\end{cases}$$

Where $\theta$ is the threshold (typically 0.1)

### Edge Type Weighting

Different relationships have different strengths:

$$A_j(t+1) = \sum_{i} w_{ij} \cdot \tau_{type(i,j)} \cdot A_i(t) \cdot d$$

Where $\tau$ is the type-specific weight:

| Edge Type | Weight ($\tau$) | Rationale |
|-----------|-----------------|-----------|
| `IS_A` | 0.95 | Strong semantic connection |
| `PART_OF` | 0.90 | Strong structural relationship |
| `HAS_PROPERTY` | 0.85 | Direct attribute |
| `RELATED_TO` | 0.75 | General association |
| `CAUSED_BY` | 0.70 | Causal but indirect |
| `MENTIONED_WITH` | 0.50 | Co-occurrence only |
| `HAPPENED_BEFORE` | 0.40 | Temporal, weaker semantic link |

---

## 🎯 Why This Works for Memory Retrieval

### 1. **Contextual Relevance**

Traditional vector search: "What's similar to the query?"
Spreading activation: "What's connected to what's similar?"

```
Query: "What investment advice did you give about my daughter?"

Vector Search Only:                    With Spreading Activation:
──────────────────                     ──────────────────────────

Top 3 matches:                         Start: "daughter" → Emma (1.0)
1. "daughter Emma mentioned"           
2. "family financial goals"            Spread to:
3. "children's education"              • College Goal (0.7)
                                       • Age 8 (0.7)
Missing: 529 plan connection!          
                                       Spread further:
                                       • 529 Plan (0.49) ← FOUND!
                                       • Tax Benefits (0.34) ← BONUS!
```

### 2. **Associative Memory**

Humans don't search all memories; they **follow associations**:

```
Human Thinking:                        Spreading Activation:
──────────────                         ─────────────────────

"My friend John..."                    John (1.0)
    ↓                                       ↓
"...works at Microsoft..."             Microsoft (0.7)
    ↓                                       ↓
"...which is in Seattle..."            Seattle (0.49)
    ↓                                       ↓
"...where we had that great            Restaurant (0.34)
 dinner at that restaurant..."              ↓
    ↓                                  Spinasse (0.24)
"...Spinasse! That's it!"

The brain doesn't search "all restaurants I know"
It FOLLOWS THE CHAIN of associations!
```

### 3. **Explaining Connections**

Spreading activation gives you a **reasoning chain**:

```
Query: "Why did you recommend 529?"

Path Found (via activation):
─────────────────────────────

Emma (1.0)
    │
    │ [HAS_GOAL]
    ▼
College Savings (0.7)
    │
    │ [SOLUTION_FOR]
    ▼
529 Plan (0.49)
    │
    │ [HAS_BENEFIT]
    ▼
Tax Advantages (0.34)

Synthesized Answer:
"I recommended the 529 Plan because it's a solution for Emma's 
college savings goal, and it provides tax advantages that align 
with your financial objectives."
```

---

## 🔧 Implementation Deep Dive

### Algorithm Variants

#### 1. **Simple BFS Spreading** (What we use)

```python
def spread_activation_bfs(
    graph: KnowledgeGraph,
    anchors: List[str],
    decay: float = 0.7,
    threshold: float = 0.1,
    max_hops: int = 3
) -> Dict[str, float]:
    """
    Breadth-first spreading activation.
    
    Pros: Simple, predictable, easy to control depth
    Cons: All edges at same hop get same treatment
    """
    activations = {nid: 1.0 for nid in anchors}
    frontier = [(nid, 1.0, 0) for nid in anchors]
    
    while frontier:
        node_id, activation, depth = frontier.pop(0)
        
        if depth >= max_hops:
            continue
        
        for neighbor_id, edge_type, edge_weight in graph.get_neighbors(node_id):
            new_activation = activation * decay * edge_weight
            
            if new_activation > threshold:
                if neighbor_id not in activations or activations[neighbor_id] < new_activation:
                    activations[neighbor_id] = new_activation
                    frontier.append((neighbor_id, new_activation, depth + 1))
    
    return activations
```

#### 2. **Priority Queue Spreading** (Best-first)

```python
import heapq

def spread_activation_priority(
    graph: KnowledgeGraph,
    anchors: List[str],
    decay: float = 0.7,
    threshold: float = 0.1,
    max_nodes: int = 100
) -> Dict[str, float]:
    """
    Priority-based spreading activation.
    
    Pros: Always expands highest-activation node first
    Cons: Can skip nearby low-activation but important nodes
    """
    activations = {nid: 1.0 for nid in anchors}
    
    # Max-heap (negate for Python's min-heap)
    frontier = [(-1.0, nid) for nid in anchors]
    heapq.heapify(frontier)
    
    visited = set()
    
    while frontier and len(visited) < max_nodes:
        neg_activation, node_id = heapq.heappop(frontier)
        activation = -neg_activation
        
        if node_id in visited:
            continue
        visited.add(node_id)
        
        for neighbor_id, edge_type, edge_weight in graph.get_neighbors(node_id):
            new_activation = activation * decay * edge_weight
            
            if new_activation > threshold and neighbor_id not in visited:
                if neighbor_id not in activations or activations[neighbor_id] < new_activation:
                    activations[neighbor_id] = new_activation
                    heapq.heappush(frontier, (-new_activation, neighbor_id))
    
    return activations
```

#### 3. **Synchronous Spreading** (Neural network style)

```python
def spread_activation_sync(
    graph: KnowledgeGraph,
    anchors: List[str],
    decay: float = 0.7,
    threshold: float = 0.1,
    iterations: int = 3
) -> Dict[str, float]:
    """
    Synchronous spreading (all nodes update simultaneously).
    
    Pros: More like actual neural networks, handles cycles better
    Cons: Slower, more complex
    """
    # Initialize activations
    activations = {nid: 0.0 for nid in graph.nodes}
    for nid in anchors:
        activations[nid] = 1.0
    
    for _ in range(iterations):
        new_activations = activations.copy()
        
        for node_id in graph.nodes:
            if activations[node_id] > threshold:
                # Spread to neighbors
                for neighbor_id, edge_type, edge_weight in graph.get_neighbors(node_id):
                    contribution = activations[node_id] * decay * edge_weight
                    # Accumulate (don't replace)
                    new_activations[neighbor_id] = max(
                        new_activations[neighbor_id],
                        contribution
                    )
        
        activations = new_activations
    
    return {nid: act for nid, act in activations.items() if act > 0}
```

#### 4. **Bidirectional Spreading** (Meet in the middle)

```python
def spread_activation_bidirectional(
    graph: KnowledgeGraph,
    source_anchors: List[str],
    target_anchors: List[str],
    decay: float = 0.7,
    threshold: float = 0.1,
    max_hops: int = 2
) -> Tuple[Dict[str, float], List[str]]:
    """
    Spread from both ends and find intersection.
    
    Useful for: Finding connections between two concepts
    """
    # Spread from sources
    source_activations = spread_activation_bfs(
        graph, source_anchors, decay, threshold, max_hops
    )
    
    # Spread from targets
    target_activations = spread_activation_bfs(
        graph, target_anchors, decay, threshold, max_hops
    )
    
    # Find intersection
    intersection = set(source_activations.keys()) & set(target_activations.keys())
    
    # Combined activation (multiply source and target activations)
    combined = {
        nid: source_activations[nid] * target_activations[nid]
        for nid in intersection
    }
    
    return combined, list(intersection)
```

---

## 📊 Tuning Parameters

### Decay Factor ($d$)

```
High decay (0.9):                      Low decay (0.5):
────────────────                       ────────────────

Activation spreads far                 Activation stays local
                                       
    1.0 → 0.9 → 0.81 → 0.73               1.0 → 0.5 → 0.25 → 0.125
    
Use when:                              Use when:
• Sparse graphs                        • Dense graphs
• Need distant connections             • Precision over recall
• Exploratory retrieval                • Focused retrieval
```

### Threshold ($\theta$)

```
High threshold (0.3):                  Low threshold (0.05):
─────────────────────                  ──────────────────────

Only strong connections                Many weak connections included
Less noise, might miss relevant        More recall, more noise

    ●━━━━●     ●                          ●━━━━●━━━━●━━━━●
    │         (pruned)                    │    │    │
    ●                                     ●━━━━●━━━━●
                                          │    │    │
                                          ●━━━━●━━━━●
```

### Edge Type Weights

```python
# Conservative (trust explicit relationships)
CONSERVATIVE_WEIGHTS = {
    "IS_A": 0.95,
    "PART_OF": 0.90,
    "HAS_PROPERTY": 0.85,
    "RELATED_TO": 0.60,
    "MENTIONED_WITH": 0.30,
}

# Aggressive (explore more connections)
AGGRESSIVE_WEIGHTS = {
    "IS_A": 0.95,
    "PART_OF": 0.90,
    "HAS_PROPERTY": 0.85,
    "RELATED_TO": 0.80,
    "MENTIONED_WITH": 0.60,
}

# Domain-specific (e.g., for financial advisor)
FINANCIAL_WEIGHTS = {
    "HAS_GOAL": 0.95,      # Goals are central
    "SOLUTION_FOR": 0.90,  # Solutions matter
    "HAS_RISK": 0.85,      # Risk is important
    "RELATED_TO": 0.60,
    "MENTIONED_WITH": 0.40,
}
```

---

## 🔄 Integration with Vector Search

Spreading activation works best when combined with vector search:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HYBRID RETRIEVAL PIPELINE                                │
└─────────────────────────────────────────────────────────────────────────────┘

Step 1: Vector Search (Find semantic anchors)
───────────────────────────────────────────────

Query: "college savings for my daughter"
                    │
                    ▼
            ┌───────────────┐
            │ Vector Search │
            │ (pgvector)    │
            └───────┬───────┘
                    │
     ┌──────────────┼──────────────┐
     ▼              ▼              ▼
  "Emma"      "College Goal"    "Savings"
  (sim: 0.9)   (sim: 0.85)     (sim: 0.7)


Step 2: Spreading Activation (Expand context)
─────────────────────────────────────────────

Anchors: [Emma, College Goal, Savings]
                    │
                    ▼
         ┌──────────────────────┐
         │ Spreading Activation │
         │ (decay=0.7, hops=3)  │
         └──────────┬───────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
 ┌──────┐       ┌───────┐       ┌──────────┐
 │529   │       │Age 8  │       │Risk Tol. │
 │Plan  │  ◄─── │       │  ───► │(moderate)│
 │0.49  │       │0.7    │       │0.49      │
 └──┬───┘       └───────┘       └──────────┘
    │
    ▼
 ┌──────────┐
 │Tax       │
 │Benefits  │
 │0.34      │
 └──────────┘


Step 3: Re-rank by Combined Score
─────────────────────────────────

Final Score = (vector_sim × 0.4) + (activation × 0.4) + (recency × 0.2)

Node              Vector Sim   Activation   Recency   Final Score
──────────────    ──────────   ──────────   ───────   ───────────
Emma              0.90         1.00         0.8       0.92
College Goal      0.85         1.00         0.7       0.88
529 Plan          0.60         0.49         0.6       0.56
Age 8             0.40         0.70         0.5       0.54
Tax Benefits      0.30         0.34         0.4       0.34
```

---

## 🧪 Advanced Techniques

### 1. **Attention-Weighted Spreading**

Use the query to weight different edge types dynamically:

```python
def attention_weighted_spread(
    query: str,
    graph: KnowledgeGraph,
    anchors: List[str],
    llm: ChatClient
) -> Dict[str, float]:
    """Use LLM to determine edge type importance for this query."""
    
    # Ask LLM which relationship types are most relevant
    prompt = f"""
    For the query: "{query}"
    
    Rank these relationship types by relevance (1-10):
    - IS_A (category membership)
    - HAS_PROPERTY (attributes)
    - RELATED_TO (general association)
    - CAUSED_BY (causal relationships)
    - PART_OF (component relationships)
    - HAS_GOAL (objectives)
    
    Return as JSON: {{"IS_A": 8, "HAS_PROPERTY": 9, ...}}
    """
    
    weights = llm.get_json_response(prompt)
    normalized_weights = {k: v/10 for k, v in weights.items()}
    
    return spread_activation_bfs(
        graph, anchors,
        edge_weights=normalized_weights
    )
```

### 2. **Inhibitory Spreading**

Some nodes should reduce activation of others (contradictions):

```python
def spread_with_inhibition(
    graph: KnowledgeGraph,
    anchors: List[str],
    inhibitory_edges: Set[str] = {"CONTRADICTS", "CONTRASTS_WITH"}
) -> Dict[str, float]:
    """Negative activation for contradictory relationships."""
    
    activations = {}
    
    for node_id, activation, depth in spread(...):
        for neighbor_id, edge_type, weight in graph.get_neighbors(node_id):
            if edge_type in inhibitory_edges:
                # Negative contribution
                new_activation = -activation * decay * weight
            else:
                new_activation = activation * decay * weight
            
            # Accumulate (can go negative)
            activations[neighbor_id] = activations.get(neighbor_id, 0) + new_activation
    
    # Filter out negative activations
    return {nid: act for nid, act in activations.items() if act > 0}
```

### 3. **Temporal Decay**

Recent memories should have higher baseline activation:

```python
from datetime import datetime, timedelta

def temporal_spreading(
    graph: KnowledgeGraph,
    anchors: List[str],
    temporal_half_life: timedelta = timedelta(days=30)
) -> Dict[str, float]:
    """Apply temporal decay to node activation."""
    
    now = datetime.utcnow()
    
    def temporal_boost(node: GraphNode) -> float:
        age = now - node.last_accessed
        # Exponential decay with half-life
        return 0.5 ** (age / temporal_half_life)
    
    # Standard spreading
    base_activations = spread_activation_bfs(graph, anchors)
    
    # Apply temporal boost
    return {
        nid: act * temporal_boost(graph.get_node(nid))
        for nid, act in base_activations.items()
    }
```

---

## 📚 References

1. **Collins, A. M., & Loftus, E. F. (1975)**. A spreading-activation theory of semantic processing. *Psychological Review*, 82(6), 407-428.

2. **Anderson, J. R. (1983)**. A spreading activation theory of memory. *Journal of Verbal Learning and Verbal Behavior*, 22(3), 261-295.

3. **Crestani, F. (1997)**. Application of spreading activation techniques in information retrieval. *Artificial Intelligence Review*, 11(6), 453-482.

4. **Microsoft GraphRAG (2024)**. From Local to Global: A Graph RAG Approach to Query-Focused Summarization. *arXiv preprint*.

5. **MemGPT (2023)**. Towards LLMs as Operating Systems. Managing memory for extended context.
