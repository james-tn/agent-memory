"""
Advanced Interactive Demo - Integrated with Real Memory Service

This version actually runs the memory service and shows real-time updates with hybrid search.
"""

import streamlit as st
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.orchestrator import MemoryServiceOrchestrator
from memory.config import MemoryConfig
from memory.cosmos_utils import CosmosUtils
from demo.setup_cosmosdb import get_cosmos_client, get_openai_client
from azure.cosmos import ContainerProxy

# Page config
st.set_page_config(
    page_title="Agent Memory Service - Live Demo",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Modern gradient header */
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    
    /* Chat messages */
    .chat-user {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
        padding: 1.2rem;
        border-radius: 15px;
        margin: 0.8rem 0;
        border-left: 5px solid #2196f3;
        box-shadow: 0 2px 8px rgba(33,150,243,0.2);
        animation: slideIn 0.3s ease-out;
    }
    
    .chat-assistant {
        background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%);
        padding: 1.2rem;
        border-radius: 15px;
        margin: 0.8rem 0;
        border-left: 5px solid #9c27b0;
        box-shadow: 0 2px 8px rgba(156,39,176,0.2);
        animation: slideIn 0.3s ease-out;
    }
    
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 12px rgba(102,126,234,0.3);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0.5rem 0;
    }
    
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    
    /* Memory state cards */
    .memory-card {
        background: white;
        border: 2px solid #e0e0e0;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        transition: all 0.3s ease;
    }
    
    .memory-card:hover {
        border-color: #667eea;
        box-shadow: 0 4px 12px rgba(102,126,234,0.2);
    }
    
    /* Insight cards */
    .insight-card {
        background: linear-gradient(135deg, #fff5e1 0%, #ffe4b5 100%);
        border-left: 4px solid #ffa726;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 6px rgba(255,167,38,0.2);
    }
    
    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0.25rem;
    }
    
    .status-active {
        background-color: #4caf50;
        color: white;
    }
    
    .status-processing {
        background-color: #ff9800;
        color: white;
    }
    
    .status-completed {
        background-color: #2196f3;
        color: white;
    }
    
    /* Progress bar */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: #f8f9fa;
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Code blocks */
    .memory-state-code {
        background-color: #f5f5f5;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        overflow-x: auto;
    }
</style>
""", unsafe_allow_html=True)

# Demo scenarios with realistic financial advisor conversations
SCENARIOS = {
    "🌟 Scenario 1: New Client - First Session": {
        "description": "First-time client discussing retirement planning. Watch the system build initial understanding and extract insights.",
        "user_id": "demo_user_1",
        "session_id": "session_first_meeting",
        "conversation": [
            ("What is a Roth IRA?", "A Roth IRA is a retirement account where you contribute after-tax money, but all growth and withdrawals in retirement are tax-free. It's excellent for long-term wealth building, especially if you expect to be in a higher tax bracket later."),
            ("What are the contribution limits for 2024?", "For 2024, the Roth IRA contribution limit is $7,000 if you're under 50, or $8,000 if you're 50 or older. However, there are income limits that phase out your eligibility."),
            ("Can I withdraw money early without penalties?", "Yes! You can withdraw your contributions anytime tax-free and penalty-free since you already paid taxes on them. However, earnings can only be withdrawn tax-free after age 59½ and after the account has been open for 5 years."),
            ("How much should I contribute?", "I recommend contributing as much as you can afford, up to the $7,000 limit. Even if you can only start with $100-200/month, that's great! The key is consistency and starting early to maximize compound growth."),
            ("What if my income is too high?", "If your income exceeds the Roth IRA limits ($161,000 for single filers in 2024), you can use a 'backdoor Roth IRA' strategy - contribute to a traditional IRA and then convert it to a Roth. It's a common workaround for high earners."),
        ]
    },
    
    "🔄 Scenario 2: Returning Client with Context": {
        "description": "Client returns after first session. Memory system loads previous context automatically.",
        "user_id": "demo_user_1",
        "session_id": "session_second_meeting",
        "conversation": [
            ("Hi, I'm back! I want to follow up on our Roth IRA discussion.", "Welcome back! Last time we discussed Roth IRA basics - the $7,000 contribution limit, tax-free growth, and withdrawal rules. You were interested in starting contributions. Have you had a chance to think about how much you'd like to contribute?"),
            ("Yes, I think I can do $500 per month. Is that good?", "That's excellent! $500/month equals $6,000/year, which is 86% of the maximum $7,000 limit. Over 30 years at a conservative 7% return, that could grow to over $600,000 - all tax-free! When would you like to start?"),
            ("I'll start next month. Should I invest in stocks or bonds?", "Great question! For a Roth IRA with a long time horizon, I typically recommend a diversified approach: perhaps 80% stocks (mix of US and international) and 20% bonds for stability. Many people use low-cost index funds or target-date funds. What's your risk tolerance?"),
            ("I'm comfortable with moderate risk.", "Perfect! For moderate risk, I'd suggest a balanced portfolio: 70% stocks, 30% bonds. Consider a three-fund portfolio: US total market index (50%), international stocks (20%), and bond index (30%). This gives you global diversification with manageable risk."),
        ]
    },
    
    "🔍 Scenario 3: Memory Retrieval Test": {
        "description": "Client asks about previous discussions - demonstrates memory retrieval across sessions.",
        "user_id": "demo_user_1",
        "session_id": "session_third_meeting",
        "conversation": [
            ("What was the contribution amount we agreed on?", "Based on our previous discussion, you decided to contribute $500 per month to your Roth IRA, which totals $6,000 per year - nearly the maximum limit of $7,000. You were planning to start next month."),
            ("And what was my risk profile again?", "You indicated you're comfortable with moderate risk. We discussed a balanced portfolio allocation: 70% stocks (50% US total market, 20% international) and 30% bonds. This provides good growth potential while managing volatility."),
            ("Did we talk about backdoor Roth conversions?", "Yes! We mentioned that if your income exceeds $161,000 (single filer limit), you can use a backdoor Roth IRA strategy - contribute to a traditional IRA first, then convert it to a Roth. This is a legal workaround for high earners."),
        ]
    },
    
    "📈 Scenario 4: Extended Session (10+ turns)": {
        "description": "Long conversation demonstrating automatic buffer pruning and summarization.",
        "user_id": "demo_user_2",
        "session_id": "session_extended",
        "conversation": [
            ("I need help planning my retirement. I'm 45 years old.", "Great! At 45, you have about 20 years until typical retirement age. Let's start by understanding your current situation. Do you have any existing retirement accounts?"),
            ("Yes, I have a 401k through work with about $180,000.", "That's a solid foundation! How much are you currently contributing, and does your employer offer matching?"),
            ("I contribute 8% and my employer matches 4%. My salary is $120,000.", "Excellent! You're putting in $9,600/year with $4,800 employer match - that's $14,400 annually. At this rate with 7% returns, you'll have around $850K by 65. Have you thought about additional savings like an IRA?"),
            ("Not really. Should I?", "Absolutely! Even with your 401k, adding an IRA gives you more investment options and potential tax diversification. With your income, you might be better with a Roth IRA for tax-free growth. Can you afford an additional $500-700/month?"),
            ("Probably $500/month. How much would that add to my retirement?", "Great! $500/month ($6,000/year) over 20 years at 7% return adds approximately $260,000 to your retirement nest egg. Combined with your 401k, you'd be looking at $1.1M+ by age 65."),
            ("That sounds good! What about Social Security?", "Good question! At your income level, you can expect around $2,500-3,000/month from Social Security (in today's dollars) if you retire at 67. However, many planners recommend not relying solely on SS due to potential future changes."),
            ("So total retirement income would be?", "Let's calculate: With $1.1M saved, using the 4% withdrawal rule, you'd have $44,000/year from savings plus $30,000-36,000 from Social Security = $74,000-80,000 annual retirement income. That's about 62-67% of your current income."),
            ("Is that enough?", "Many financial planners recommend 70-80% of pre-retirement income. You're close! To reach 80% ($96,000/year), you'd need about $1.5M saved. That means increasing total contributions from $1,200/month to around $1,700/month. Is that feasible?"),
            ("That's tight. What if I work until 67?", "Working 2 extra years helps significantly! It gives investments more time to grow, delays withdrawals, and increases Social Security benefits by about 16%. You'd likely exceed your 80% target without increasing contributions."),
            ("That's a relief! What about healthcare before Medicare?", "Critical planning point! Healthcare from 65 to 67 (before Medicare) can cost $1,000-1,500/month. Budget $30,000-36,000 for this gap. Consider building this into your emergency fund or HSA if you have one."),
            ("I do have an HSA with $15,000.", "Perfect! HSAs are amazing retirement tools - triple tax advantage! Max it out each year ($4,150 for family in 2024). Leave funds invested for medical expenses in retirement. That $15,000 could grow to $35,000+ by retirement."),
            ("This is so helpful! One more question - what about inflation?", "Excellent thinking! We've been using today's dollars. True inflation-adjusted returns are closer to 4-5%, not 7%. But we've also been conservative on SS estimates and not accounting for raises. The plan should hold up well with modest inflation (~2-3% annually)."),
        ]
    }
}


@st.cache_resource
def initialize_memory_service(user_id: str, session_id: str):
    """Initialize the memory service (cached to avoid re-initialization)"""
    try:
        # Get clients
        cosmos_client = get_cosmos_client()
        chat_client = get_openai_client()
        
        # Get database and containers
        db = cosmos_client.get_database_client("cosmosvector")
        interactions_container = db.get_container_client("interactions")
        insights_container = db.get_container_client("insights")
        summaries_container = db.get_container_client("session_summaries")
        
        # Create config and cosmos utilities
        config = MemoryConfig()
        cosmos_utils = CosmosUtils(
            embedding_client=chat_client
        )
        
        # Create orchestrator
        orchestrator = MemoryServiceOrchestrator(
            user_id=user_id,
            session_id=session_id,
            config=config,
            cosmos_utils=cosmos_utils,
            interactions_container=interactions_container,
            summaries_container=summaries_container,
            insights_container=insights_container,
            chat_client=chat_client
        )
        
        return orchestrator
    except Exception as e:
        print(e)
        st.error(f"Failed to initialize memory service: {str(e)}")
        st.exception(e)  # Show full traceback for debugging
        return None


# Initialize session state
if 'demo_state' not in st.session_state:
    st.session_state.demo_state = {
        'current_scenario': None,
        'conversation_history': [],
        'turn_index': 0,
        'is_playing': False,
        'orchestrator': None,
        'memory_stats': {
            'turn_buffer_size': 0,
            'cumulative_summary': "",
            'session_summary': "",
            'key_topics': [],
            'insights_extracted': [],
            'insights_count': 0,
            'total_turns': 0,
            'session_ended': False
        },
        'speed': 1.0,
        'show_details': False
    }


def render_header():
    """Render main header"""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown('<h1 class="main-header">🧠 Agent Memory Service - Live Demo</h1>', unsafe_allow_html=True)
        st.caption("**Real-time visualization** of conversation memory, context compression, and insight extraction")
    
    with col2:
        if st.session_state.demo_state['orchestrator']:
            st.markdown('<span class="status-badge status-active">🟢 Connected</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge">⚪ Not Connected</span>', unsafe_allow_html=True)
    
    st.divider()


def render_sidebar():
    """Render sidebar with controls"""
    with st.sidebar:
        st.markdown("## 📋 Demo Scenarios")
        
        for scenario_name, scenario_data in SCENARIOS.items():
            if st.button(scenario_name, key=f"scenario_{scenario_name}", use_container_width=True):
                # Reset and load new scenario
                st.session_state.demo_state.update({
                    'current_scenario': scenario_name,
                    'conversation_history': [],
                    'turn_index': 0,
                    'is_playing': False,
                    'orchestrator': initialize_memory_service(
                        scenario_data['user_id'],
                        scenario_data['session_id']
                    ),
                    'memory_stats': {
                        'turn_buffer_size': 0,
                        'cumulative_summary': "",
                        'session_summary': "",
                        'key_topics': [],
                        'insights_extracted': [],
                        'insights_count': 0,
                        'total_turns': 0,
                        'session_ended': False
                    }
                })
                st.rerun()
        
        # Show controls only if scenario is selected
        if st.session_state.demo_state['current_scenario']:
            st.divider()
            st.markdown("## ⚙️ Playback Controls")
            
            col1, col2 = st.columns(2)
            with col1:
                play_icon = "⏸️ Pause" if st.session_state.demo_state['is_playing'] else "▶️ Play"
                if st.button(play_icon, use_container_width=True, key="play_pause"):
                    st.session_state.demo_state['is_playing'] = not st.session_state.demo_state['is_playing']
                    st.rerun()
            
            with col2:
                if st.button("⏭️ Next", use_container_width=True, key="next_turn"):
                    asyncio.run(advance_turn())
                    st.rerun()
            
            if st.button("🔄 Reset Scenario", use_container_width=True, key="reset"):
                st.session_state.demo_state['conversation_history'] = []
                st.session_state.demo_state['turn_index'] = 0
                st.session_state.demo_state['is_playing'] = False
                st.rerun()
            
            st.markdown("**Playback Speed:**")
            speed = st.select_slider(
                "speed",
                options=[0.5, 1.0, 1.5, 2.0, 3.0],
                value=1.0,
                label_visibility="collapsed"
            )
            st.session_state.demo_state['speed'] = speed
            
            st.divider()
            
            # Progress
            scenario = SCENARIOS[st.session_state.demo_state['current_scenario']]
            total = len(scenario['conversation'])
            current = st.session_state.demo_state['turn_index']
            
            st.markdown("## 📊 Progress")
            st.progress(current / total if total > 0 else 0)
            st.caption(f"**Turn {current} of {total}**")
            
            if current >= total:
                st.success("✅ Scenario Complete!")
            
            st.divider()
            
            # Current scenario info
            st.markdown("## 📖 About This Scenario")
            st.markdown(f"**{st.session_state.demo_state['current_scenario']}**")
            st.caption(scenario['description'])


async def advance_turn():
    """Advance to next conversation turn"""
    if not st.session_state.demo_state['current_scenario']:
        return
    
    scenario = SCENARIOS[st.session_state.demo_state['current_scenario']]
    turn_index = st.session_state.demo_state['turn_index']
    orchestrator = st.session_state.demo_state['orchestrator']
    
    if turn_index >= len(scenario['conversation']):
        st.session_state.demo_state['is_playing'] = False
        return
    
    user_msg, assistant_msg = scenario['conversation'][turn_index]
    
    # Add to conversation history
    st.session_state.demo_state['conversation_history'].append({
        'role': 'user',
        'content': user_msg,
        'timestamp': datetime.now().strftime("%H:%M:%S")
    })
    
    st.session_state.demo_state['conversation_history'].append({
        'role': 'assistant',
        'content': assistant_msg,
        'timestamp': datetime.now().strftime("%H:%M:%S")
    })
    
    # Process through memory service
    if orchestrator:
        try:
            result = await orchestrator.process_turn(user_msg, assistant_msg)
            
            # Update stats
            stats = st.session_state.demo_state['memory_stats']
            stats['turn_buffer_size'] = result.get('active_turns_count', 0)
            stats['total_turns'] += 1
            
            # Check if summarization occurred
            if result.get('summarization_triggered'):
                stats['cumulative_summary'] = "Summary created"
        
        except Exception as e:
            print(e)
            st.error(f"Error processing turn: {str(e)}")
    
    # Increment turn
    st.session_state.demo_state['turn_index'] += 1
    
    # End session if complete
    if st.session_state.demo_state['turn_index'] >= len(scenario['conversation']):
        await end_session()


async def end_session():
    """End the session and trigger reflection"""
    orchestrator = st.session_state.demo_state['orchestrator']
    
    if orchestrator and not st.session_state.demo_state['memory_stats']['session_ended']:
        try:
            result = await orchestrator.end_session(trigger_reflection=True)
            
            # Update stats with actual results
            stats = st.session_state.demo_state['memory_stats']
            stats['session_ended'] = True
            stats['session_summary'] = result.get('session_summary', '')
            stats['key_topics'] = result.get('key_topics', [])
            stats['insights_extracted'] = result.get('insights_extracted', [])
            stats['insights_count'] = len(result.get('insights_extracted', []))
            
        except Exception as e:
            print(e)
            st.error(f"Error ending session: {str(e)}")
            st.exception(e)


def render_chat():
    """Render chat interface"""
    st.markdown("### 💬 Live Conversation")
    
    if not st.session_state.demo_state['current_scenario']:
        st.info("👈 **Select a scenario** from the sidebar to begin the demo")
        return
    
    # Chat container
    for msg in st.session_state.demo_state['conversation_history']:
        if msg['role'] == 'user':
            st.markdown(f"""
            <div class="chat-user">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <strong>👤 User</strong>
                    <span style="color: #666; font-size: 0.85em;">{msg['timestamp']}</span>
                </div>
                <div>{msg['content']}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-assistant">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <strong>🤖 AI Financial Advisor</strong>
                    <span style="color: #666; font-size: 0.85em;">{msg['timestamp']}</span>
                </div>
                <div>{msg['content']}</div>
            </div>
            """, unsafe_allow_html=True)


def render_memory_visualization():
    """Render memory state visualization"""
    st.markdown("### 🧠 Memory System State")
    
    if not st.session_state.demo_state['current_scenario']:
        st.info("Memory visualization will appear here once a scenario is started")
        return
    
    stats = st.session_state.demo_state['memory_stats']
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="Turn Buffer",
            value=f"{stats['turn_buffer_size']}/10",
            help="Current conversation turns in active buffer"
        )
    
    with col2:
        st.metric(
            label="Total Turns",
            value=stats['total_turns'],
            help="Total conversation exchanges processed"
        )
    
    with col3:
        st.metric(
            label="Insights",
            value=stats['insights_count'],
            help="Number of insights extracted"
        )
    
    # Memory components
    with st.expander("📝 Turn Buffer (Working Memory)", expanded=True):
        if stats['turn_buffer_size'] > 0:
            st.caption(f"**{stats['turn_buffer_size']}** active turns in buffer")
            st.caption("Displays the most recent conversation turns kept in working memory")
            
            # Show recent turns
            recent_turns = st.session_state.demo_state['conversation_history'][-min(10, len(st.session_state.demo_state['conversation_history'])):]
            for turn in recent_turns:
                icon = "👤" if turn['role'] == 'user' else "🤖"
                st.markdown(f"**{icon}:** {turn['content'][:100]}...")
        else:
            st.caption("Buffer is empty - add conversation turns to see them here")
    
    with st.expander("📋 Cumulative Summary", expanded=bool(stats.get('cumulative_summary') or stats.get('session_summary'))):
        if stats.get('session_summary'):
            st.markdown("**Session Summary:**")
            st.info(stats['session_summary'])
            if stats.get('key_topics'):
                st.markdown("**Key Topics:** " + ", ".join(f"`{topic}`" for topic in stats['key_topics']))
        elif stats.get('cumulative_summary'):
            st.info(stats['cumulative_summary'])
            st.caption("✨ Summary is automatically generated after 10 conversation turns")
        else:
            st.caption("Summary will be generated after 10 turns (buffer full)")
    
    with st.expander("💡 Extracted Insights", expanded=stats['session_ended']):
        if stats.get('insights_extracted') and len(stats['insights_extracted']) > 0:
            st.success(f"✅ **{stats['insights_count']} insights** extracted from this session!")
            st.caption("Insights include: goals, knowledge level, preferences, behavior patterns")
            
            # Display each insight
            for idx, insight in enumerate(stats['insights_extracted'], 1):
                with st.container():
                    st.markdown(f"**Insight #{idx}**")
                    
                    # Display insight details
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"📝 {insight.get('insight_text', 'N/A')}")
                    with col2:
                        category = insight.get('category', 'N/A')
                        importance = insight.get('importance', 'N/A')
                        st.markdown(f"**Category:** `{category}`")
                        st.markdown(f"**Importance:** `{importance}`")
                    
                    if 'confidence' in insight and insight['confidence'] is not None:
                        st.progress(float(insight['confidence']), text=f"Confidence: {insight['confidence']:.0%}")
                    
                    st.divider()
        elif stats['insights_count'] > 0:
            st.success(f"✅ **{stats['insights_count']} insights** extracted from this session!")
            st.caption("Insights include: goals, knowledge level, preferences, behavior patterns")
        elif stats['session_ended']:
            st.warning("Session ended but no insights were extracted (trivial session)")
        else:
            st.caption("Insights will be extracted when the session completes")


def main():
    """Main application"""
    render_header()
    render_sidebar()
    
    # Main content - two columns
    col1, col2 = st.columns([3, 2])
    
    with col1:
        render_chat()
    
    with col2:
        render_memory_visualization()
    
    # Auto-advance if playing
    if st.session_state.demo_state['is_playing']:
        scenario = SCENARIOS.get(st.session_state.demo_state['current_scenario'])
        if scenario and st.session_state.demo_state['turn_index'] < len(scenario['conversation']):
            import time
            time.sleep(2.0 / st.session_state.demo_state['speed'])
            asyncio.run(advance_turn())
            st.rerun()


if __name__ == "__main__":
    main()
