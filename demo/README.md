# 🧠 Agent Memory Service - Interactive Demo

A beautiful, modern web interface that demonstrates the Agent Memory Service in action with real-time visualizations of conversation memory, context compression, and insight extraction.

![Demo Screenshot](https://img.shields.io/badge/Status-Live-success)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-red)

---

## 🎯 What This Demo Shows

### Real-Time Memory Visualization
- **Live Chat Interface**: Watch a simulated conversation between user and AI assistant
- **Turn Buffer**: See active conversation turns in working memory
- **Context Compression**: Observe automatic summarization after 10 turns
- **Insight Extraction**: View extracted insights at session end

### 4 Pre-Built Scenarios

#### 🌟 Scenario 1: New Client - First Session
- First-time interaction
- System builds initial understanding
- Demonstrates insight extraction from scratch

#### 🔄 Scenario 2: Returning Client with Context  
- Shows session initialization with previous context
- Memory loads past session summaries
- Demonstrates context continuity

#### 🔍 Scenario 3: Memory Retrieval Test
- Client asks about previous discussions
- Demonstrates CFR (Contextual Fact Retrieval) agent
- Shows semantic search across past conversations

#### 📈 Scenario 4: Extended Session (10+ turns)
- Long conversation (12+ turns)
- Triggers automatic buffer pruning
- Demonstrates cumulative summarization

---

## 🚀 Quick Start

### Option 1: Simple Launch (Windows)
```bash
# Just double-click this file:
demo/run_demo.bat
```

The demo will automatically open in your browser at `http://localhost:8501`

### Option 2: Manual Launch
```bash
# From project root
cd c:\testing\agent_memory

# Install demo dependencies (if not already installed)
pip install streamlit plotly pandas

# Run the demo
uv run streamlit run demo/interactive_demo_live.py
```

---

## 🎮 How to Use the Demo

### Step 1: Select a Scenario
Click any scenario button in the left sidebar to load it.

### Step 2: Control Playback
- **▶️ Play**: Auto-advance through conversation (adjustable speed)
- **⏸️ Pause**: Pause auto-playback
- **⏭️ Next**: Manually advance to next turn
- **🔄 Reset**: Restart the scenario

### Step 3: Watch the Magic
As the conversation progresses, observe:

1. **Chat Interface (Left)**:
   - User messages (blue)
   - AI Assistant responses (purple)
   - Timestamps

2. **Memory State (Right)**:
   - **Turn Buffer**: Active conversation turns (0-10)
   - **Cumulative Summary**: Generated after 10 turns
   - **Extracted Insights**: Shown at session end

---

## 📊 Understanding the Visualizations

### Turn Buffer (Working Memory)
```
Capacity: 10 turns
Behavior: 
  - Fills up as conversation progresses
  - At 10 turns: triggers summarization
  - Keeps last 5 turns + summary
```

### Cumulative Summary
```
Generated: After every 10 turns
Purpose: Compress older conversation context
Result: Saves tokens while preserving information
```

### Extracted Insights
```
Triggered: At session end
Categories:
  - Demographics
  - Financial Goals
  - Risk Profile
  - Current Situation
  - Concerns
  - Preferences
```

---

## 🎨 UI Features

### Modern Design Elements
- ✨ Gradient headers and cards
- 🎭 Smooth animations for messages
- 📱 Responsive layout
- 🌈 Color-coded message types
- 📊 Real-time metrics

### Interactive Controls
- Speed slider (0.5x - 3.0x)
- Play/Pause toggle
- Step-through mode
- Scenario reset
- Progress indicator

---

## 🔧 Technical Details

### Technology Stack
```
Frontend: Streamlit 1.31+
Backend: Agent Memory Service (Python 3.12+)
Database: Azure CosmosDB with vector search
LLM: Azure OpenAI (gpt-5-nano, gpt-5-nanoo-mini)
Embeddings: text-embedding-ada-002
```

### Memory Architecture Demonstrated
```
┌─────────────────────────────────────────┐
│  1. Current Memory Keeper               │
│     - Turn buffer (k=10)                │
│     - Active turns (n=5)                │
│     - Cumulative summarization          │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  2. CFR Agent (Contextual Retrieval)    │
│     - Semantic search                   │
│     - Tool-based mini-agent             │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  3. Reflection Process                  │
│     - Session insights                  │
│     - Category classification           │
└─────────────────────────────────────────┘
```

---

## 📖 Scenario Details

### Scenario 1: New Client Session
**Turns**: 5 exchanges  
**Topics**: Roth IRA basics, contribution limits, withdrawals  
**Expected Insights**:
- Demographics (age, income level)
- Financial goals (retirement planning)
- Knowledge level (learning about Roth IRAs)
- Preferences (tax-advantaged accounts)

### Scenario 2: Returning Client
**Turns**: 4 exchanges  
**Topics**: Follow-up on Roth IRA, portfolio allocation  
**Demonstrates**:
- Context loading from previous session
- Personalized responses based on history
- Progressive learning tracking

### Scenario 3: Memory Retrieval
**Turns**: 3 exchanges  
**Topics**: Querying past discussions  
**Demonstrates**:
- CFR agent searching past interactions
- Accurate recall of previous details
- Semantic understanding of queries

### Scenario 4: Extended Session
**Turns**: 12 exchanges  
**Topics**: Comprehensive retirement planning  
**Demonstrates**:
- Automatic buffer pruning at turn 10
- Cumulative summary generation
- Multiple insight categories

---

## 🐛 Troubleshooting

### Demo Won't Start
```bash
# Check Streamlit is installed
pip list | grep streamlit

# Install if missing
pip install streamlit

# Try running directly
streamlit run demo/interactive_demo_live.py
```

### Connection Issues
```bash
# Verify CosmosDB connection
# Check .env file has correct credentials:
COSMOS_ENDPOINT=...
COSMOS_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
```

### Memory Service Errors
```bash
# Make sure you're in the right directory
cd c:\testing\agent_memory

# Check all dependencies are installed
uv sync

# Run tests to verify service is working
uv run python -m tests.test_orchestrator
```

---

## 🎓 Learning Objectives

After using this demo, you should understand:

1. **How conversation memory works**
   - Turn-by-turn buffering
   - Automatic summarization
   - Context window management

2. **Memory retrieval strategies**
   - Semantic search
   - Hybrid search (vector + full-text)
   - Agent-based retrieval

3. **Insight extraction**
   - Session-level insights
   - Category classification
   - Confidence scoring

4. **Real-world applications**
   - Personalized AI assistants
   - Context-aware chatbots
   - Long-term user modeling

---

## 📝 Customization

### Add Your Own Scenario
Edit `demo/interactive_demo_live.py`:

```python
SCENARIOS = {
    "Your Custom Scenario": {
        "description": "Your description",
        "user_id": "custom_user",
        "session_id": "custom_session",
        "conversation": [
            ("User message", "Assistant response"),
            # ... more turns
        ]
    }
}
```

### Adjust Memory Parameters
Edit `memory/config.py`:

```python
class MemoryConfig:
    K_TURN_BUFFER = 10  # Buffer size before pruning
    N_ACTIVE_TURNS = 5  # Recent turns to keep
    # ... other params
```

---

## 🌟 Next Steps

After exploring the demo:

1. **Try the test suite**: `uv run python -m tests.test_orchestrator`
2. **Read the docs**: See `agent_memory_design.md`
3. **Integrate with your agent**: See `demo/setup_demo_data.py`
4. **Deploy to production**: Configure Azure resources

---

## 📚 Additional Resources

- **Design Document**: `agent_memory_design.md`
- **Implementation Guide**: `agent_memory_implementation_design.md`
- **API Documentation**: `memory/README.md`
- **Test Suite**: `tests/`

---

## 💡 Tips for Best Demo Experience

1. **Start with Scenario 1**: Understand the basics first
2. **Use Step Mode**: Click "Next" to carefully observe each change
3. **Watch the Metrics**: See how buffer size changes
4. **Compare Scenarios**: Run 1, then 2 to see context loading
5. **Try Different Speeds**: 0.5x for learning, 3.0x for overview

---

## ❓ FAQ

**Q: Is this using real AI or simulated?**  
A: The conversation is pre-scripted, but the memory operations (storage, retrieval, summarization, insights) are REAL - using actual Azure CosmosDB and OpenAI services.

**Q: Can I modify the conversations?**  
A: Yes! Edit the `SCENARIOS` dictionary in the demo file.

**Q: How do I see the actual database entries?**  
A: Use Azure Portal to view your CosmosDB containers, or check the test output logs.

**Q: Can I integrate this with a real agent?**  
A: Absolutely! See the `MemoryServiceOrchestrator` API docs for integration patterns.

---

## 🤝 Contributing

Want to improve the demo? Great!

1. Add new scenarios
2. Enhance visualizations
3. Add new metrics
4. Improve UI/UX

---

## 📄 License

This demo is part of the Agent Memory Service project.

---

**Built with ❤️ using Streamlit, Azure CosmosDB, and Azure OpenAI**
