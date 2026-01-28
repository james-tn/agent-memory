# Automatic Context Enrichment

## Overview

The Automatic Context Enrichment feature enables the backend to automatically enrich conversation context with relevant recalled facts when semantic triggers are detected. This eliminates the need for explicit `search_memory` tool calls in predictable scenarios while maintaining performance through intelligent caching.

## Architecture

### Components

1. **Configuration** (`memory/config.py`)
   - `auto_enrich_context`: Boolean flag to enable/disable auto-enrichment
   - `enrichment_trigger_keywords`: List of semantic keywords that trigger enrichment

2. **Orchestrator** (`memory/orchestrator.py`)
   - `_should_enrich_context()`: Detects semantic triggers in recent conversation
   - `_enrich_with_recalled_facts()`: Performs retrieval with caching
   - `get_current_context()`: Returns enriched context when appropriate

3. **Caching Mechanism**
   - `_enrichment_cache`: Stores retrieved facts per session
   - `_last_enrichment_turn_count`: Tracks when last enrichment occurred
   - Prevents redundant searches (minimum 3 turns between enrichments)

## How It Works

### 1. Trigger Detection

The system scans the last 3 conversation turns for trigger keywords:

**Medical Safety Keywords:**
- `allergy`, `allergic`, `allergies`
- `medication`, `medicine`, `drug`, `prescribe`, `prescription`
- `treatment`, `therapy`

**Memory Reference Keywords:**
- `remember`, `recall`, `mentioned`, `told`, `said before`
- `history`, `previously`, `last time`

### 2. Automatic Enrichment Flow

```python
# When get_current_context() is called:
context = await orchestrator.get_current_context(auto_enrich=True)

# If triggers detected:
# 1. Check cache (avoid redundant searches)
# 2. If not cached, perform fact retrieval
# 3. Cache results for this session
# 4. Add recalled_facts to context
# 5. Set enrichment_triggered flag

# Context structure:
{
    "active_turns": [...],
    "cumulative_summary": "...",
    "buffer_status": {...},
    "recalled_facts": "...",        # Added when enriched
    "enrichment_triggered": True    # Indicates enrichment occurred
}
```

### 3. Caching Strategy

- **Per-session cache**: Retrieved facts stored for current session
- **Minimum spacing**: 3 turns between enrichments (prevents spam)
- **Cache invalidation**: Cleared on session end
- **Performance**: Avoids redundant LLM calls within session

## Configuration

### Enable Auto-Enrichment

```python
from memory.config import MemoryConfig

config = MemoryConfig(
    auto_enrich_context=True,  # Enable feature
    enrichment_trigger_keywords=[
        # Customize keywords for your domain
        "allergy", "medication", "prescribe",
        "remember", "history", "previously"
    ]
)
```

### Override Per-Request

```python
# Force enrichment regardless of config
context = await orchestrator.get_current_context(auto_enrich=True)

# Disable enrichment for this call
context = await orchestrator.get_current_context(auto_enrich=False)

# Use config default
context = await orchestrator.get_current_context()  # Uses config.auto_enrich_context
```

## Use Cases

### 1. Medical Safety (Primary Use Case)

**Scenario**: Doctor prescribing medication needs allergy information

```python
# Session 1: Patient mentions allergy
User: "I'm allergic to penicillin"
Assistant: "Noted. We'll avoid penicillin-based medications"

# Session 4 (3 months later): Trigger word detected
User: "What will you prescribe for my infection?"
# 🔥 Backend automatically retrieves allergy info from Session 1
# 📋 Context enriched with: "Patient allergic to penicillin (severe hives)"
Assistant: "I'll prescribe azithromycin instead - it's safe for you"
```

**Benefits**:
- Critical safety information automatically available
- Reduces risk of prescribing errors
- No explicit search needed by client

### 2. Customer Service Context

**Scenario**: Support agent needs customer history

```python
config = MemoryConfig(
    auto_enrich_context=True,
    enrichment_trigger_keywords=[
        "previous", "history", "last time", "before",
        "issue", "problem", "complaint"
    ]
)

# Session 3: Customer mentions previous issue
User: "I had a similar problem last month"
# 🔥 Auto-enrichment retrieves Session 1 details
# 📋 Context includes: "Previous issue: router connectivity"
Assistant: "I see you had router connectivity issues. Is this related?"
```

### 3. Financial Advisory

**Scenario**: Advisor needs client's risk tolerance and goals

```python
config = MemoryConfig(
    auto_enrich_context=True,
    enrichment_trigger_keywords=[
        "investment", "portfolio", "risk", "strategy",
        "goals", "retirement", "savings"
    ]
)

# Session 1: Client establishes risk tolerance
User: "I'm conservative - I can't afford to lose money"
# Session 3: Investment discussion
User: "What investments do you recommend?"
# 🔥 Auto-enrichment retrieves risk tolerance from Session 1
Assistant: "Given your conservative profile, I recommend bonds and dividend stocks"
```

## Comparison with Other Approaches

### 1. Passive Injection (Session Init)

**Approach**: Load recent sessions at initialization

```python
config = MemoryConfig(M_SESSIONS_RECENT=2)  # Load 2 recent sessions
```

**Pros:**
- Simple, no runtime logic
- All recent context available upfront

**Cons:**
- Fixed cost regardless of need
- May miss older critical info
- Context bloat for irrelevant sessions

**Use When**: Most info is in recent 1-2 sessions

---

### 2. Active Search (Tool Calling)

**Approach**: Agent uses `search_memory` tool

```python
@ai_function
async def search_memory(query: str) -> str:
    """Search memory for relevant facts"""
    return await orchestrator.retrieve_facts(query)
```

**Pros:**
- Agent decides when to search
- Flexible query formulation
- Transparent to user

**Cons:**
- Agent must recognize need
- Requires tool-calling capability
- Extra LLM inference for decision

**Use When**: Agent has autonomy, unpredictable needs

---

### 3. Automatic Enrichment (This Feature)

**Approach**: Backend detects triggers and enriches

```python
config = MemoryConfig(
    auto_enrich_context=True,
    enrichment_trigger_keywords=["prescribe", "allergy"]
)
```

**Pros:**
- No agent decision needed
- Predictable performance (caching)
- Domain-specific optimization
- Client-agnostic

**Cons:**
- Requires trigger keyword tuning
- May retrieve unnecessarily
- Less flexible than tool calling

**Use When**: Predictable patterns, safety-critical domains

---

### Hybrid Approach (Recommended)

Combine all three for optimal results:

```python
config = MemoryConfig(
    M_SESSIONS_RECENT=1,           # Load most recent session
    auto_enrich_context=True,      # Enable automatic enrichment
    enrichment_trigger_keywords=[...] # Domain keywords
)

# Agent also has search_memory tool for unpredictable needs
@ai_function
async def search_memory(query: str) -> str:
    """Explicitly search memory when needed"""
    return await orchestrator.retrieve_facts(query)
```

**Result**: Fast recent context + automatic safety net + agent autonomy

## Performance Considerations

### Caching Strategy

```python
# First trigger in session
Turn 5: User mentions "prescribe"
→ Perform retrieval (LLM call)
→ Cache result
→ Return enriched context

# Subsequent triggers (within 3 turns)
Turn 6: User mentions "medication"
→ Use cached result (no LLM call)
→ Return enriched context

# Later triggers (after 3+ turns)
Turn 10: User mentions "allergy"
→ Check turn distance: 10 - 5 = 5 turns ✓
→ Perform new retrieval (LLM call)
→ Update cache
→ Return enriched context
```

**Benefits**:
- Reduces redundant LLM calls
- Maintains fresh context (3-turn window)
- Balances performance and accuracy

### Cost Analysis

**Scenario**: 4-session medical consultation

- **Without auto-enrichment**: 
  - Session 4 requires explicit search: 1 retrieval call
  - Total: 1 retrieval

- **With auto-enrichment**:
  - Session 4 first trigger: 1 retrieval call (cached)
  - Session 4 subsequent triggers: 0 calls (cache hit)
  - Total: 1 retrieval (same cost, automatic)

**Cost Impact**: Minimal (caching prevents overhead)

## Testing

Run the demo to see auto-enrichment in action:

```bash
cd c:\testing\agent_memory
python demo/auto_enrichment_demo.py
```

### Expected Output

```
🏥 Session 4: Sinus Infection - June 2024
==============================

👤 Patient: What will you prescribe?
  ✨ [Auto-Enriched] Backend automatically retrieved relevant facts:
  📋 Patient is allergic to penicillin (severe hives reaction). Mentioned in initial consultation...

👨‍⚕️ Doctor: Given your symptoms, I'll prescribe amoxicillin... wait, let me check your allergies first.
Ah yes, you're allergic to penicillin. Let me prescribe azithromycin instead.
```

## API Usage

### Python Client

```python
from memory.orchestrator import MemoryServiceOrchestrator
from memory.config import MemoryConfig

# Enable auto-enrichment
config = MemoryConfig(auto_enrich_context=True)
orchestrator = MemoryServiceOrchestrator(user_id="user123", config=config)

# Process conversation
await orchestrator.process_turn("user", "What medications do you recommend?")

# Get enriched context
context = await orchestrator.get_current_context(auto_enrich=True)

# Check if enrichment occurred
if context.get("enrichment_triggered"):
    print("Context enriched with:", context["recalled_facts"])
```

### REST API (Future)

```python
# GET /memory/context?auto_enrich=true
response = requests.get(
    f"{BASE_URL}/memory/context",
    params={
        "user_id": "user123",
        "session_id": "session456",
        "auto_enrich": "true"
    }
)

context = response.json()
if context.get("enrichment_triggered"):
    print("Auto-enriched with:", context["recalled_facts"])
```

## Best Practices

### 1. Keyword Selection

**Domain-specific**:
```python
# Medical domain
keywords = ["allergy", "medication", "prescribe", "treatment", "diagnosis"]

# Financial domain
keywords = ["investment", "risk", "portfolio", "retirement", "goals"]

# Customer service
keywords = ["issue", "problem", "previous", "history", "complaint"]
```

**Balance specificity vs. coverage**:
- Too specific: May miss enrichment opportunities
- Too broad: Unnecessary retrievals, higher cost

### 2. Caching Configuration

```python
# Adjust turn threshold based on conversation pace
# Fast-paced (chat support): Shorter window
_last_enrichment_turn_count + 2  # Every 2 turns

# Slower-paced (medical consult): Longer window
_last_enrichment_turn_count + 5  # Every 5 turns
```

### 3. Monitoring

```python
# Log enrichment events
if context.get("enrichment_triggered"):
    logger.info(f"Auto-enrichment at turn {turn_count}, retrieved {len(facts)} chars")
    
# Track cache hit rate
cache_hits = enrichments_from_cache / total_enrichments
logger.info(f"Cache hit rate: {cache_hits:.2%}")
```

### 4. Fallback Strategy

```python
# If auto-enrichment fails, have fallback
try:
    context = await orchestrator.get_current_context(auto_enrich=True)
except Exception as e:
    logger.warning(f"Auto-enrichment failed: {e}")
    # Fall back to basic context
    context = await orchestrator.get_current_context(auto_enrich=False)
```

## Troubleshooting

### Enrichment Not Triggering

**Check trigger keywords**:
```python
# Debug: Print keywords being checked
print(f"Trigger keywords: {config.enrichment_trigger_keywords}")
print(f"Recent turns: {[turn.content for turn in recent_turns]}")
```

**Verify configuration**:
```python
assert config.auto_enrich_context == True
assert len(config.enrichment_trigger_keywords) > 0
```

### Excessive Retrievals

**Increase caching threshold**:
```python
# In orchestrator._should_enrich_context()
turn_threshold = 5  # Increase from 3 to 5 turns
```

**Narrow trigger keywords**:
```python
# Remove broad keywords like "the", "is", "can"
keywords = ["allergy", "medication"]  # Keep specific only
```

### Cache Not Working

**Verify turn counting**:
```python
# Debug: Print turn counts
print(f"Current turn: {turn_count}")
print(f"Last enrichment: {self._last_enrichment_turn_count}")
print(f"Distance: {turn_count - self._last_enrichment_turn_count}")
```

## Future Enhancements

### 1. Adaptive Triggers

Learn keywords from user patterns:
```python
# Track which keywords lead to useful enrichments
enrichment_effectiveness = {
    "prescribe": 0.95,  # 95% of enrichments useful
    "remember": 0.60,   # 60% useful
}
# Auto-adjust keyword set
```

### 2. Multi-level Caching

```python
# L1: Turn-level cache (current)
# L2: Topic-level cache (e.g., "allergies")
# L3: Session-level cache (persist across sessions)
```

### 3. Confidence Scoring

```python
context = await orchestrator.get_current_context(auto_enrich=True)
# Add confidence score
context["enrichment_confidence"] = 0.87  # How relevant are recalled facts?
```

### 4. User Feedback Loop

```python
# Track whether enriched facts were used
await orchestrator.record_enrichment_feedback(
    enrichment_id="enrich_123",
    was_useful=True
)
# Adjust future enrichment strategy
```

## Summary

**Automatic Context Enrichment** provides intelligent, domain-optimized memory retrieval without requiring explicit tool calls. It balances performance (caching), safety (medical use cases), and simplicity (client-agnostic).

**Key Benefits**:
- ✅ Automatic retrieval of critical information
- ✅ Reduced client complexity
- ✅ Performance-optimized with caching
- ✅ Flexible configuration
- ✅ Safety-focused for medical/financial domains

**When to Use**:
- Predictable information needs (medical allergies, financial risk profiles)
- Safety-critical domains
- Simple client implementations
- Domain-specific keyword patterns

**When to Avoid**:
- Highly unpredictable information needs
- Cost-sensitive applications (prefer explicit searches)
- Clients with sophisticated agent logic (use tool calling instead)

For most applications, a **hybrid approach** combining passive injection, auto-enrichment, and tool calling provides the best results.
