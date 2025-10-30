"""
Interactive Memory Service Demo with Streamlit

A modern UI that visualizes the Agent Memory Service in action with:
- Live chat between simulated user and AI assistant
- Real-time memory state visualization
- Multiple demo scenarios
- Interactive controls
"""

import streamlit as st
import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any
import json

# Setup page config
st.set_page_config(
    page_title="Agent Memory Service Demo",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern UI
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    .chat-user {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #2196f3;
    }
    .chat-assistant {
        background-color: #f3e5f5;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #9c27b0;
    }
    .memory-state {
        background-color: #f5f5f5;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
    }
    .insight-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .scenario-button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        cursor: pointer;
        margin: 0.5rem;
    }
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
</style>
""", unsafe_allow_html=True)

# Demo scenarios
SCENARIOS = {
    "Scenario 1: Financial Planning - First Session": {
        "description": "New client discussing retirement planning. Watch as the system builds initial understanding.",
        "conversation": [
            ("user", "Hi, I'm interested in planning for retirement. I'm 35 years old."),
            ("assistant", "Welcome! Let me help you with retirement planning. At 35, you have excellent time to build a solid retirement strategy. What's your target retirement age?"),
            ("user", "I'd like to retire at 65. I have a 401k through work but not sure if I'm contributing enough."),
            ("assistant", "Great! A 30-year timeline gives us plenty of flexibility. Currently, how much are you contributing to your 401k, and does your employer offer matching?"),
            ("user", "I contribute 5% and my employer matches 3%. My salary is $95,000."),
            ("assistant", "That's a good start! You're putting in $4,750/year with $2,850 employer match. To maximize growth, I recommend increasing to at least 10-15% if possible. Let's discuss your risk tolerance."),
            ("user", "I'm moderately comfortable with risk. I don't want to be too aggressive but want good growth."),
            ("assistant", "Perfect. A moderate risk profile typically means 60-70% stocks, 30-40% bonds. This balances growth potential with stability. Have you thought about Roth IRA contributions as well?"),
            ("user", "Not really. What's the benefit?"),
            ("assistant", "Roth IRA offers tax-free growth and withdrawals in retirement. For 2024, you can contribute up to $7,000. Combined with your 401k, you'd have excellent tax diversification."),
        ],
        "expected_insights": ["demographics", "financial_goals", "risk_profile", "current_situation"]
    },
    
    "Scenario 2: Follow-up Session with Context": {
        "description": "Returning client - watch how memory loads previous session context and builds on it.",
        "conversation": [
            ("user", "Hi! I'm back. I've been thinking about what we discussed."),
            ("assistant", "Welcome back! Last time we talked about your retirement planning - you're 35, targeting retirement at 65, with moderate risk tolerance. You have a 401k with 5% contribution and were interested in learning about Roth IRAs. What questions do you have?"),
            ("user", "I want to increase my 401k contribution to 10%. How should I adjust my portfolio?"),
            ("assistant", "Excellent decision! Increasing from 5% to 10% means $9,500/year plus employer match - that's $12,350 annually. For your moderate risk profile, I recommend a target-date fund for 2055 or a balanced portfolio: 65% US stocks, 15% international stocks, 20% bonds."),
            ("user", "What about the Roth IRA? Can I afford both?"),
            ("assistant", "Let's calculate: 10% 401k is $792/month. Adding $583/month for Roth IRA ($7,000/year) totals $1,375/month. That's about 17% of gross income - very solid! If that fits your budget, you'd be setting yourself up excellently for retirement."),
            ("user", "That seems doable. Can you help me understand the tax implications?"),
            ("assistant", "Absolutely! 401k contributions reduce your taxable income now (saving ~$2,090 in taxes at 22% bracket). Roth IRA is after-tax, so no immediate deduction, but all growth and withdrawals are tax-free in retirement. This gives you tax diversification - very strategic!"),
        ],
        "expected_insights": ["learning_progress", "preferences", "behavior_patterns"]
    },
    
    "Scenario 3: Complex Query with Memory Retrieval": {
        "description": "Client asks about previous discussions - demonstrates CFR agent retrieving past context.",
        "conversation": [
            ("user", "What was my target contribution amount we discussed before?"),
            ("assistant", "[Retrieving from memory...] Based on our previous sessions, we discussed increasing your 401k from 5% to 10% of your $95,000 salary, which is $9,500 annually. We also talked about adding a Roth IRA contribution of $7,000/year, totaling around $16,500 in retirement savings annually."),
            ("user", "Right! And what was my risk profile again?"),
            ("assistant", "[Searching memory...] You indicated a moderate risk tolerance. You wanted good growth but not overly aggressive investments. We recommended a portfolio mix of approximately 65% US stocks, 15% international stocks, and 20% bonds, or alternatively a 2055 target-date fund."),
            ("user", "Perfect. Now I'm wondering about my emergency fund. Did we cover that?"),
            ("assistant", "I don't see that we've discussed emergency funds yet in our previous sessions. This is actually crucial to address! Before maximizing retirement contributions, you should have 3-6 months of expenses in an accessible savings account. Would you like to discuss that now?"),
        ],
        "expected_insights": ["preferences", "concern"]
    },
    
    "Scenario 4: Long Session with Context Compression": {
        "description": "Extended conversation demonstrating automatic summarization after 10 turns.",
        "conversation": [
            ("user", "I want to talk about estate planning today."),
            ("assistant", "Great topic! Estate planning ensures your assets go where you want them. At 35, key components include: will, beneficiary designations, power of attorney, and healthcare directive. Have you started any of these?"),
            ("user", "I have a will from 5 years ago but haven't updated it."),
            ("assistant", "Important to review! Major life changes like marriage, kids, job changes, or asset growth should trigger updates. What's changed in the last 5 years for you?"),
            ("user", "I got married 2 years ago, and we just bought a house."),
            ("assistant", "Congratulations! Those are significant changes requiring will updates: ensure spouse is primary beneficiary, decide on property inheritance, update life insurance beneficiaries. Do you have life insurance?"),
            ("user", "Yes, through my employer - $200,000."),
            ("assistant", "Good start, but employer coverage may be insufficient. Rule of thumb: 10-12x annual salary. At $95k, that's ~$1M. Consider supplemental term life insurance - it's very affordable at your age."),
            ("user", "How much would that cost?"),
            ("assistant", "For a healthy 35-year-old, $750k-$1M 20-year term policy typically runs $40-70/month. That's less than $1,000/year for substantial protection. Your spouse would have funds to cover mortgage, living expenses, and retirement savings if something happened."),
            ("user", "That's reasonable. What about the house title - should we do anything special?"),
            ("assistant", "Great question! For married couples, common options: joint tenancy (automatic transfer to spouse) or tenancy by entirety (similar but more protection from creditors). Check how your deed is currently titled and consult a local estate attorney."),
            ("user", "We have it as joint tenancy. What about retirement accounts - can my spouse access them?"),
            ("assistant", "401k and IRA beneficiary designations override your will! CRITICAL: verify your spouse is listed as primary beneficiary on ALL retirement accounts. This ensures tax-advantaged transfer. Check this ASAP - it's a common oversight."),
            ("user", "I'll check that tomorrow. Should we set up a trust?"),
            ("assistant", "[SUMMARIZATION TRIGGERED] At 35 with moderate assets, a simple will usually suffices. Trusts become important when: estate >$13M (federal tax threshold), minor children (guardianship control), special needs dependents, or complex family situations. We can revisit as your wealth grows."),
            ("user", "That makes sense. What about health care directives?"),
            ("assistant", "Critical but often overlooked! Healthcare directive (living will) specifies medical wishes if incapacitated. Healthcare power of attorney designates decision-maker. These prevent family conflicts during medical crises. Most attorneys include them with basic estate planning packages (~$500-1,500 total)."),
        ],
        "expected_insights": ["current_situation", "concern", "preferences", "behavior_patterns"]
    }
}


# Initialize session state
if 'demo_state' not in st.session_state:
    st.session_state.demo_state = {
        'current_scenario': None,
        'conversation_history': [],
        'turn_index': 0,
        'is_playing': False,
        'session_id': None,
        'memory_stats': {
            'turn_buffer': [],
            'cumulative_summary': "",
            'insights': [],
            'session_summaries': [],
            'active_turns_count': 0,
            'total_interactions': 0
        },
        'reflection_results': None,
        'speed': 1.0
    }


def render_header():
    """Render the main header"""
    st.markdown('<h1 class="main-header">🧠 Agent Memory Service - Live Demo</h1>', unsafe_allow_html=True)
    st.markdown("**Watch the memory system in action:** See how conversations are stored, summarized, and insights are extracted in real-time!")
    st.divider()


def render_scenario_selector():
    """Render scenario selection sidebar"""
    with st.sidebar:
        st.markdown("### 📋 Demo Scenarios")
        
        for scenario_name, scenario_data in SCENARIOS.items():
            if st.button(scenario_name, key=f"btn_{scenario_name}", use_container_width=True):
                st.session_state.demo_state['current_scenario'] = scenario_name
                st.session_state.demo_state['conversation_history'] = []
                st.session_state.demo_state['turn_index'] = 0
                st.session_state.demo_state['is_playing'] = False
                st.session_state.demo_state['session_id'] = f"demo_{int(time.time())}"
                st.rerun()
        
        st.divider()
        
        # Playback controls
        if st.session_state.demo_state['current_scenario']:
            st.markdown("### ⚙️ Playback Controls")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("▶️ Play" if not st.session_state.demo_state['is_playing'] else "⏸️ Pause", use_container_width=True):
                    st.session_state.demo_state['is_playing'] = not st.session_state.demo_state['is_playing']
                    st.rerun()
            
            with col2:
                if st.button("⏭️ Next Turn", use_container_width=True):
                    advance_conversation()
                    st.rerun()
            
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.demo_state['conversation_history'] = []
                st.session_state.demo_state['turn_index'] = 0
                st.session_state.demo_state['is_playing'] = False
                st.rerun()
            
            st.markdown("**Speed:**")
            speed = st.slider("", 0.5, 3.0, 1.0, 0.5, label_visibility="collapsed")
            st.session_state.demo_state['speed'] = speed
            
            st.divider()
            
            # Current scenario info
            st.markdown("### 📖 Current Scenario")
            st.markdown(f"**{st.session_state.demo_state['current_scenario']}**")
            scenario_data = SCENARIOS[st.session_state.demo_state['current_scenario']]
            st.caption(scenario_data['description'])
            
            st.divider()
            
            # Progress
            st.markdown("### 📊 Progress")
            total_turns = len(scenario_data['conversation'])
            current_turn = st.session_state.demo_state['turn_index']
            st.progress(current_turn / total_turns if total_turns > 0 else 0)
            st.caption(f"Turn {current_turn} / {total_turns}")


def advance_conversation():
    """Advance to the next conversation turn"""
    if not st.session_state.demo_state['current_scenario']:
        return
    
    scenario = SCENARIOS[st.session_state.demo_state['current_scenario']]
    turn_index = st.session_state.demo_state['turn_index']
    
    if turn_index < len(scenario['conversation']):
        role, content = scenario['conversation'][turn_index]
        
        # Add to conversation history
        st.session_state.demo_state['conversation_history'].append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        })
        
        # Update memory stats (simulate memory operations)
        update_memory_stats(role, content, turn_index)
        
        # Increment turn index
        st.session_state.demo_state['turn_index'] += 1
        
        # Check if we should trigger reflection (end of scenario)
        if st.session_state.demo_state['turn_index'] >= len(scenario['conversation']):
            trigger_reflection()
            st.session_state.demo_state['is_playing'] = False


def update_memory_stats(role: str, content: str, turn_index: int):
    """Simulate memory system updates"""
    stats = st.session_state.demo_state['memory_stats']
    
    # Add to turn buffer
    stats['turn_buffer'].append({
        'role': role,
        'content': content,
        'turn_number': turn_index + 1
    })
    stats['active_turns_count'] = len(stats['turn_buffer'])
    stats['total_interactions'] += 1
    
    # Simulate pruning/summarization after 10 turns
    if len(stats['turn_buffer']) >= 10:
        # Create summary of buffer
        summary = f"Turns {turn_index-9} to {turn_index+1}: Discussed retirement planning details including contribution amounts, risk tolerance, and tax implications."
        stats['cumulative_summary'] = summary
        
        # Clear buffer (keep last 5)
        stats['turn_buffer'] = stats['turn_buffer'][-5:]
        stats['active_turns_count'] = len(stats['turn_buffer'])


def trigger_reflection():
    """Simulate reflection process"""
    scenario = SCENARIOS[st.session_state.demo_state['current_scenario']]
    
    # Simulate insight extraction
    insights = []
    for category in scenario['expected_insights']:
        insights.append({
            'category': category,
            'confidence': 0.85 + (hash(category) % 15) / 100,
            'text': f"Extracted {category} insight from conversation"
        })
    
    st.session_state.demo_state['memory_stats']['insights'] = insights
    st.session_state.demo_state['reflection_results'] = {
        'insights_extracted': len(insights),
        'categories': scenario['expected_insights']
    }


def render_chat_interface():
    """Render the chat conversation"""
    st.markdown("### 💬 Live Conversation")
    
    if not st.session_state.demo_state['current_scenario']:
        st.info("👈 Select a scenario from the sidebar to begin")
        return
    
    chat_container = st.container()
    
    with chat_container:
        for msg in st.session_state.demo_state['conversation_history']:
            if msg['role'] == 'user':
                st.markdown(f"""
                <div class="chat-user">
                    <strong>👤 User</strong> <span style="color: #666; font-size: 0.85em;">{msg['timestamp']}</span><br>
                    {msg['content']}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-assistant">
                    <strong>🤖 AI Assistant</strong> <span style="color: #666; font-size: 0.85em;">{msg['timestamp']}</span><br>
                    {msg['content']}
                </div>
                """, unsafe_allow_html=True)


def render_memory_state():
    """Render memory state visualization"""
    st.markdown("### 🧠 Memory System State")
    
    if not st.session_state.demo_state['current_scenario']:
        st.info("Start a scenario to see memory state")
        return
    
    stats = st.session_state.demo_state['memory_stats']
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Active Turns", stats['active_turns_count'], help="Current turns in buffer")
    
    with col2:
        st.metric("Total Interactions", stats['total_interactions'], help="Total conversation turns")
    
    with col3:
        st.metric("Insights Extracted", len(stats['insights']), help="Number of insights from reflection")
    
    with col4:
        has_summary = "Yes" if stats['cumulative_summary'] else "No"
        st.metric("Cumulative Summary", has_summary, help="Whether conversation has been summarized")
    
    # Turn buffer visualization
    with st.expander("📝 Turn Buffer (Active Memory)", expanded=True):
        if stats['turn_buffer']:
            st.caption(f"Current buffer size: {len(stats['turn_buffer'])} / 10 turns")
            for turn in stats['turn_buffer'][-5:]:  # Show last 5
                role_icon = "👤" if turn['role'] == 'user' else "🤖"
                st.markdown(f"""
                <div class="memory-state">
                    <strong>{role_icon} Turn {turn['turn_number']}:</strong><br>
                    {turn['content'][:100]}{'...' if len(turn['content']) > 100 else ''}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Buffer is empty")
    
    # Cumulative summary
    with st.expander("📋 Cumulative Summary", expanded=bool(stats['cumulative_summary'])):
        if stats['cumulative_summary']:
            st.markdown(f"""
            <div class="memory-state">
                {stats['cumulative_summary']}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.caption("No summary yet (triggered after 10 turns)")
    
    # Insights
    with st.expander("💡 Extracted Insights", expanded=bool(stats['insights'])):
        if stats['insights']:
            for insight in stats['insights']:
                st.markdown(f"""
                <div class="insight-card">
                    <strong>📌 {insight['category'].replace('_', ' ').title()}</strong><br>
                    <span style="color: #666;">Confidence: {insight['confidence']:.2%}</span><br>
                    {insight['text']}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No insights extracted yet (triggered at session end)")


def main():
    """Main application"""
    render_header()
    render_scenario_selector()
    
    # Main content layout
    col1, col2 = st.columns([3, 2])
    
    with col1:
        render_chat_interface()
    
    with col2:
        render_memory_state()
    
    # Auto-advance if playing
    if st.session_state.demo_state['is_playing']:
        scenario = SCENARIOS.get(st.session_state.demo_state['current_scenario'])
        if scenario and st.session_state.demo_state['turn_index'] < len(scenario['conversation']):
            time.sleep(2.0 / st.session_state.demo_state['speed'])
            advance_conversation()
            st.rerun()


if __name__ == "__main__":
    main()
