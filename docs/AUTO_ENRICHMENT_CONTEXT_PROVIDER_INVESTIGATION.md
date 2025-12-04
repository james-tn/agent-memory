# Auto-Enrichment via Context Provider Investigation

## Executive Summary

**Goal:** Implement automatic context enrichment as a **hidden/implicit tool** in the Agent Framework's `ContextProvider`, so that any agent using `CosmosMemoryProvider` can have their context automatically enriched without:
1. The user explicitly defining a `search_memory` tool
2. The agent needing to call a tool
3. The user seeing the tool in the agent's tool list

**Key Finding:** ✅ **This is FEASIBLE** via the Agent Framework's `ContextProvider.invoking()` method, which can return a `Context` object containing tools that are injected transparently.

---

## Architecture Overview

### Current Auto-Enrichment (Orchestrator-Level)

**Location:** `memory/orchestrator.py`

**How it works:**
```python
# 1. Config enables auto-enrichment
config = MemoryConfig(auto_enrich_context=True, enrichment_trigger_keywords=[...])

# 2. On get_current_context(), semantic triggers are detected
context = await orchestrator.get_current_context(auto_enrich=True)

# 3. Backend automatically retrieves relevant facts
if _should_enrich_context():
    recalled_facts = await _enrich_with_recalled_facts()
    context["recalled_facts"] = recalled_facts
```

**Limitation:** This requires **explicit calls** to `get_current_context(auto_enrich=True)`. It doesn't work transparently for Agent Framework agents.

---

### Proposed Architecture: Context Provider-Level Auto-Enrichment

**Location:** `memory/cosmos_memory_provider_embedded.py`

**How it works:**

```python
class CosmosMemoryProvider(ContextProvider):
    """
    Implements transparent auto-enrichment via implicit tool injection.
    """
    
    async def invoking(
        self, 
        messages: ChatMessage | MutableSequence[ChatMessage], 
        **kwargs: Any
    ) -> Context:
        """
        Called BEFORE AI invocation.
        
        Key Innovation:
        ---------------
        1. Analyze recent messages for semantic triggers
        2. If triggers detected, perform fact retrieval BEFORE agent runs
        3. Inject retrieved facts as messages (existing approach)
        4. Optionally: Inject a hidden search_memory tool for fallback
        """
        
        # Build base context (existing approach)
        context = self._build_base_context()  # longterm insights, summaries, etc.
        
        # NEW: Auto-enrichment logic
        if self.config.auto_enrich_context:
            recent_messages = self._get_recent_messages(messages)
            
            if self._should_enrich_context(recent_messages):
                # Perform retrieval BEFORE agent invocation
                recalled_facts = await self._enrich_with_recalled_facts()
                
                if recalled_facts:
                    # Add as context message
                    enrichment_message = ChatMessage(
                        role=Role.USER,
                        text=f"## Auto-Retrieved Relevant Facts\n{recalled_facts}"
                    )
                    context.messages.append(enrichment_message)
        
        # Optional: Inject hidden search tool for agent-initiated searches
        if self.config.inject_search_tool:
            context.tools = [self._create_search_tool()]
        
        return context
```

---

## Agent Framework Integration Points

### 1. `ContextProvider` Base Class

**File:** `agent_framework/_agents.py`

**Key Methods:**

```python
class ContextProvider(ABC):
    @abstractmethod
    async def invoking(
        self, 
        messages: ChatMessage | MutableSequence[ChatMessage], 
        **kwargs: Any
    ) -> Context:
        """
        Called BEFORE model invocation.
        
        Returns:
            Context object with:
            - instructions: str | None
            - messages: Sequence[ChatMessage]  ← Can inject enriched context here
            - tools: Sequence[ToolProtocol]    ← Can inject hidden tools here
        """
        pass
    
    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called AFTER model invocation.
        Used to store conversation turns.
        """
        pass
```

### 2. `Context` Class

**File:** `agent_framework/_agents.py`

**Structure:**

```python
class Context:
    def __init__(
        self,
        instructions: str | None = None,
        messages: Sequence[ChatMessage] | None = None,
        tools: Sequence[ToolProtocol] | None = None,  # ← KEY: Tools can be injected!
    ):
        self.instructions = instructions
        self.messages = messages or []
        self.tools = tools or []
```

**Key Insight:** The `tools` parameter allows us to **dynamically inject tools** per invocation without the user defining them.

---

## Implementation Options

### Option 1: Pure Message Injection (Simplest, Recommended for Phase 1)

**Approach:** Detect triggers and inject recalled facts as messages BEFORE agent runs.

**Pros:**
- ✅ No new tools needed
- ✅ Works with existing infrastructure
- ✅ Transparent to user
- ✅ No tool calling overhead

**Cons:**
- ❌ Always retrieves, even if agent doesn't need it
- ❌ Cannot adapt mid-conversation (retrieval happens BEFORE agent thinks)

**Implementation:**

```python
async def invoking(self, messages, **kwargs) -> Context:
    # Build base context
    context = self._build_base_context()
    
    # Auto-enrichment
    if self.config.auto_enrich_context:
        recent_messages = [messages] if isinstance(messages, ChatMessage) else list(messages)[-3:]
        
        if self._should_enrich(recent_messages):
            facts = await self._orchestrator.retrieve_facts(
                query=self._build_retrieval_query(recent_messages),
                include_summaries=True,
                include_insights=True
            )
            
            if facts:
                context.messages.append(ChatMessage(
                    role=Role.USER,
                    text=f"## Automatically Retrieved Relevant Context\n{facts}"
                ))
    
    return context
```

---

### Option 2: Hidden Tool Injection (More Flexible, Recommended for Phase 2)

**Approach:** Inject a `search_memory` tool that the agent can use, but **don't show it to the user**.

**Pros:**
- ✅ Agent decides when to search (intelligent)
- ✅ No wasted retrievals
- ✅ Mid-conversation adaptation
- ✅ User doesn't need to define the tool

**Cons:**
- ❌ More complex implementation
- ❌ Agent must recognize when to search (but GPT-4 is good at this)
- ❌ Requires tool calling support

**Implementation:**

```python
async def invoking(self, messages, **kwargs) -> Context:
    # Build base context
    context = self._build_base_context()
    
    # Inject hidden search tool if enabled
    if self.config.inject_search_tool:
        @ai_function
        async def search_memory(query: str) -> str:
            """
            Search long-term memory for relevant past information.
            Use this when you need information from previous conversations
            that isn't in the current context.
            
            Args:
                query: Natural language search query
            
            Returns:
                Relevant facts from past conversations
            """
            return await self._memory.search(
                query,
                include_summaries=True,
                include_insights=True
            )
        
        # Inject as hidden tool
        context.tools = [search_memory]
    
    return context
```

**User Experience:**

```python
# User code (no tools defined!)
agent = ChatAgent(
    chat_client=client,
    instructions="You are a medical assistant",
    context_providers=[memory_provider]  # ← Hidden tool injected automatically
)

# Agent automatically has search_memory available, uses it when needed
result = await agent.run("What medications was I prescribed last month?")
# Behind the scenes: Agent calls search_memory("medications prescribed") automatically
```

---

### Option 3: Hybrid (Best of Both Worlds)

**Approach:** Combine both strategies:
1. **Proactive injection** for predictable triggers (Phase 1)
2. **Hidden tool** for unpredictable needs (Phase 2)

**Pros:**
- ✅ Fast for common patterns (no tool call needed)
- ✅ Flexible for edge cases (agent can search)
- ✅ Best user experience

**Cons:**
- ❌ Most complex to implement
- ❌ Requires careful tuning of trigger thresholds

**Implementation:**

```python
async def invoking(self, messages, **kwargs) -> Context:
    context = self._build_base_context()
    
    # Strategy 1: Proactive enrichment for high-confidence triggers
    if self.config.auto_enrich_context:
        recent_messages = self._get_recent_messages(messages)
        confidence = self._calculate_enrichment_confidence(recent_messages)
        
        if confidence >= self.config.auto_enrich_threshold:  # e.g., 0.8
            facts = await self._retrieve_facts(recent_messages)
            if facts:
                context.messages.append(ChatMessage(
                    role=Role.USER,
                    text=f"## Auto-Retrieved Context\n{facts}"
                ))
    
    # Strategy 2: Hidden tool for agent-initiated searches
    if self.config.inject_search_tool:
        context.tools = [self._create_search_tool()]
    
    return context
```

---

## Configuration Design

### `CosmosMemoryProviderConfig` Extensions

```python
@dataclass
class CosmosMemoryProviderConfig:
    """Configuration for CosmosMemoryProvider with auto-enrichment."""
    
    # Existing fields
    memory_config: MemoryConfig
    include_longterm_insights: bool = True
    include_recent_sessions: bool = True
    # ...
    
    # NEW: Auto-enrichment settings
    auto_enrich_context: bool = False
    """Enable automatic context enrichment based on semantic triggers."""
    
    enrichment_trigger_keywords: list[str] = field(default_factory=lambda: [
        "allergy", "medication", "prescribe", "treatment",
        "remember", "recall", "history", "previously"
    ])
    """Keywords that trigger automatic fact retrieval."""
    
    auto_enrich_threshold: float = 0.7
    """Confidence threshold for automatic enrichment (0.0 - 1.0)."""
    
    inject_search_tool: bool = False
    """Inject hidden search_memory tool for agent-initiated searches."""
    
    search_tool_name: str = "search_memory"
    """Name of the injected search tool."""
    
    search_tool_description: str = (
        "Search long-term memory for relevant past information. "
        "Use when you need context from previous conversations."
    )
    """Description for the injected search tool."""
```

### `MemoryConfig` Extensions

```python
@dataclass
class MemoryConfig:
    # Existing fields
    buffer_size: int = 10
    # ...
    
    # NEW: Auto-enrichment settings (used by orchestrator)
    auto_enrich_enabled: bool = False
    """Enable auto-enrichment at orchestrator level (internal)."""
    
    enrichment_cache_ttl: int = 5
    """Number of turns before re-enriching (prevents spam)."""
```

---

## Comparison with Azure AI Search Context Provider

### Azure AI Search Pattern

**File:** `agent_framework_azure_ai_search/_search_provider.py`

```python
class AzureAISearchContextProvider(ContextProvider):
    async def invoking(self, messages, **kwargs) -> Context:
        # 1. Extract user query from messages
        query = self._extract_query(messages)
        
        # 2. Perform search BEFORE agent invocation
        if self.mode == "semantic":
            results = await self._semantic_search(query)
        else:
            results = await self._agentic_search(messages)
        
        # 3. Inject results as context messages
        context_messages = [ChatMessage(role=Role.USER, text=self.context_prompt)]
        context_messages.extend([
            ChatMessage(role=Role.USER, text=part) 
            for part in results
        ])
        
        return Context(messages=context_messages)
```

**Key Insight:** Azure AI Search does **proactive retrieval** in `invoking()` and injects results as messages. We can use the same pattern!

---

## Implementation Roadmap

### Phase 1: Message-Based Auto-Enrichment (Week 1)

**Goal:** Implement Option 1 (pure message injection)

**Tasks:**
1. ✅ Move trigger detection logic from `orchestrator.py` to `cosmos_memory_provider_embedded.py`
2. ✅ Implement `_should_enrich_context()` in provider
3. ✅ Implement `_enrich_with_recalled_facts()` in provider (delegates to orchestrator)
4. ✅ Update `invoking()` to inject enriched messages
5. ✅ Add configuration options to `CosmosMemoryProviderConfig`
6. ✅ Create demo showing automatic enrichment
7. ✅ Update documentation

**Acceptance Criteria:**
- Agent receives enriched context automatically when triggers detected
- No explicit `search_memory` tool needed by user
- Works transparently with existing Agent Framework patterns

---

### Phase 2: Hidden Tool Injection (Week 2-3)

**Goal:** Implement Option 2 (hidden search tool)

**Tasks:**
1. Create `_create_search_tool()` method in provider
2. Implement tool injection via `Context(tools=[...])`
3. Add `inject_search_tool` configuration flag
4. Test that injected tool is available to agent but not visible to user
5. Create demo showing agent autonomously using hidden tool
6. Performance benchmarking (message injection vs. tool calling)

**Acceptance Criteria:**
- Agent can call hidden `search_memory` tool
- User doesn't see tool in their code
- Agent intelligently decides when to search

---

### Phase 3: Hybrid Approach (Week 4)

**Goal:** Implement Option 3 (proactive + fallback)

**Tasks:**
1. Implement confidence scoring for trigger detection
2. Add `auto_enrich_threshold` configuration
3. Combine message injection (high confidence) with tool injection (low confidence)
4. Create comprehensive benchmarks comparing all three approaches
5. Document best practices for each strategy

**Acceptance Criteria:**
- System uses appropriate strategy based on confidence
- Performance optimized (minimal unnecessary retrievals)
- User can configure strategy per use case

---

## Key Design Decisions

### Decision 1: Where to Implement Auto-Enrichment?

**Options:**
- ❌ **Orchestrator-level** (current): Requires explicit calls, not transparent
- ✅ **Context Provider-level** (proposed): Transparent, framework-integrated

**Rationale:** Context provider's `invoking()` method is **designed** for this use case. It's called automatically before every agent invocation, making it the perfect place for transparent enrichment.

---

### Decision 2: Message Injection vs. Tool Injection?

**Options:**
- **Phase 1**: Message injection (predictable triggers)
- **Phase 2**: Tool injection (unpredictable needs)
- **Phase 3**: Hybrid (both)

**Rationale:** Start simple (messages) for immediate value, then add flexibility (tools) for complex scenarios.

---

### Decision 3: Tool Visibility

**User's Concern:** "user do not have to define the search explicitly but we do that behind the scene"

**Solution:** Tools injected via `Context(tools=[...])` are **automatically available** to the agent but **not defined in user code**:

```python
# User code - NO tool definition needed
agent = ChatAgent(
    chat_client=client,
    context_providers=[memory_provider]  # ← Tool injected here transparently
)

# Agent automatically has access to search_memory
# User never sees it in their code
```

**Verification needed:** Does Agent Framework show injected tools in `agent.tools` or keep them hidden?

---

## Risk Assessment

### Risk 1: Tool Visibility Leaking to User

**Risk:** Injected tools might appear in `agent.tools` property, confusing users.

**Mitigation:** 
- Test visibility behavior
- If visible, document as "auto-injected tools"
- Provide config flag to disable injection

**Likelihood:** Low (Context is per-invocation, not stored)

---

### Risk 2: Performance Overhead

**Risk:** Auto-enrichment on every turn could slow down agent.

**Mitigation:**
- Caching (existing mechanism)
- Confidence thresholding
- Config flag to disable
- Benchmark different strategies

**Likelihood:** Medium (requires tuning)

---

### Risk 3: Redundant Retrievals

**Risk:** Both message injection AND agent tool calling could cause duplicate searches.

**Mitigation:**
- Cache results per turn
- Use confidence thresholds (high → inject, low → tool)
- Track whether enrichment already occurred

**Likelihood:** Low (caching prevents this)

---

## Open Questions for User Approval

### Question 1: Implementation Phasing

**Q:** Should we implement all three phases, or just Phase 1 (message injection) first?

**Recommendation:** Start with Phase 1 for quick wins, then evaluate if Phase 2/3 are needed.

---

### Question 2: Configuration Defaults

**Q:** Should auto-enrichment be **enabled by default** or **opt-in**?

**Options:**
- **Opt-in** (safer): `auto_enrich_context=False` by default
- **Opt-out** (bolder): `auto_enrich_context=True` by default

**Recommendation:** **Opt-in** for Phase 1, **opt-out** once stable in Phase 3.

---

### Question 3: Tool Naming

**Q:** What should the hidden tool be called?

**Options:**
- `search_memory` (descriptive)
- `recall_facts` (action-oriented)
- `retrieve_context` (neutral)
- `_internal_search_memory` (signals it's internal)

**Recommendation:** `search_memory` (matches existing demos, clear purpose)

---

### Question 4: Trigger Keyword Customization

**Q:** Should users be able to customize trigger keywords per domain?

**Recommendation:** Yes, via `enrichment_trigger_keywords` config. Provide domain-specific defaults:
- Medical: `["allergy", "medication", "prescribe", "diagnosis"]`
- Financial: `["investment", "portfolio", "risk", "retirement"]`
- General: `["remember", "recall", "previously", "history"]`

---

## Next Steps

### Before Implementation

1. **User Approval**: Get confirmation on:
   - Phase 1 approach (message injection)
   - Configuration design
   - Tool naming conventions

2. **Validation Tests**:
   - Test `Context(tools=[...])` behavior
   - Verify tool visibility to user
   - Benchmark enrichment overhead

### After Approval

1. **Revert Auto-Enrichment Changes**: 
   - Remove changes to `orchestrator.py`, `config.py`, `memory/config.py`
   - Keep only orchestrator's retrieval infrastructure

2. **Implement Phase 1**:
   - Add enrichment logic to `CosmosMemoryProvider.invoking()`
   - Update `CosmosMemoryProviderConfig`
   - Create demo

3. **Documentation**:
   - Update README with auto-enrichment section
   - Create architecture diagram
   - Write best practices guide

---

## Conclusion

**Feasibility:** ✅ **HIGHLY FEASIBLE**

The Agent Framework's `ContextProvider` pattern is **designed exactly** for this use case. The `invoking()` method gives us a transparent injection point for both messages and tools, enabling automatic context enrichment without user-visible tool definitions.

**Recommended Approach:**
1. **Phase 1** (Immediate): Message injection for predictable triggers
2. **Phase 2** (Future): Hidden tool injection for agent autonomy
3. **Phase 3** (Advanced): Hybrid strategy with confidence scoring

**Key Innovation:** Moving auto-enrichment from **orchestrator-level** (requires explicit calls) to **context provider-level** (transparent, framework-integrated) makes it truly automatic and seamless for Agent Framework users.

**Awaiting Approval To Proceed** 🚦
