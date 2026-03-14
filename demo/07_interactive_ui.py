"""
Interactive Memory Demo - Streamlit + Remote Memory Service
============================================================

A rich, interactive demo that showcases all memory features with a web UI.
Uses the Memory Service API (server mode) for production-grade multi-client support.

Features:
- Real-time chat interface with memory visualization
- Pre-built demo scenarios (Financial, Shopping, Learning, Medical)
- Auto-play mode with adjustable speed
- Memory search with semantic similarity
- Live insight extraction and session summary display
- Memory tier visualization (active turns → summaries → insights)

Prerequisites:
1. Start the memory server:
   uv run uvicorn server.main:app --port 8000

2. Run this demo:
   streamlit run demo/07_interactive_ui.py

Requirements:
- Memory service running on localhost:8000
- Azure OpenAI deployment (for agent responses)
- streamlit package (pip install streamlit)
"""

import asyncio
import html
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import time
import streamlit as st
import httpx

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

from openai import AzureOpenAI


# ============================================================================
# Configuration
# ============================================================================

MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Agent Memory Demo - Live",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    
    .chat-user {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
        padding: 1.2rem;
        border-radius: 15px;
        margin: 0.8rem 0;
        border-left: 5px solid #2196f3;
        box-shadow: 0 2px 8px rgba(33,150,243,0.2);
    }
    
    .chat-assistant {
        background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%);
        padding: 1.2rem;
        border-radius: 15px;
        margin: 0.8rem 0;
        border-left: 5px solid #9c27b0;
        box-shadow: 0 2px 8px rgba(156,39,176,0.2);
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        text-align: center;
    }
    
    .insight-card {
        background: linear-gradient(135deg, #fff5e1 0%, #ffe4b5 100%);
        border-left: 4px solid #ffa726;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .status-active { background-color: #4caf50; color: white; }
    .status-inactive { background-color: #9e9e9e; color: white; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Demo Scenarios
# ============================================================================

SCENARIOS = {
    "💰 Financial Advisor - Session 1": {
        "description": "First-time client discussing retirement planning. Watch the system build initial understanding.",
        "user_id": "client_sarah",
        "agent_type": "Financial Advisor",
        "conversation": [
            ("What is a Roth IRA?", "A Roth IRA is a retirement account where you contribute after-tax money, but all growth and withdrawals in retirement are tax-free. It's excellent for long-term wealth building."),
            ("What are the contribution limits for 2024?", "For 2024, the Roth IRA contribution limit is $7,000 if you're under 50, or $8,000 if you're 50 or older. There are income limits too."),
            ("I'm 35 and earn $95,000 per year", "At 35 with $95k salary, you're well within income limits and have 30 years until retirement. You can contribute the full $7,000 annually."),
            ("I'm generally conservative with investments", "For conservative investors, I'd recommend 60% stocks and 40% bonds. This provides growth potential while managing risk."),
            ("I'll start with $500/month", "$500/month equals $6,000/year - that's 86% of the maximum. Excellent disciplined approach!"),
        ]
    },
    "💰 Financial Advisor - Session 2": {
        "description": "Client returns. Watch memory recall age (35), income ($95k), risk tolerance (conservative)!",
        "user_id": "client_sarah",
        "agent_type": "Financial Advisor",
        "conversation": [
            ("Hi, I'm back! I set up the $500/month transfers", "Wonderful! I remember you're 35 with a conservative risk profile. How are you feeling about your investment strategy?"),
            ("I got a raise! Now making $110k", "Congratulations! With $110k, you could increase to $583/month to hit the $7,000 max. Even an extra $83/month compounds significantly!"),
            ("My company offers a 401k match too", "Always capture free money - max out your employer 401k match first, then your Roth IRA. What's the match percentage?"),
            ("They match 50% up to 6% of salary", "On $110k, contributing 6% gets you a $3,300 match. Combined with your Roth IRA, you're saving $17,100/year for retirement!"),
        ]
    },
    "🛍️ Shopping Assistant - Session 1": {
        "description": "Customer browses running shoes. System learns preferences: Nike, blue, $100-120 budget, size 10.",
        "user_id": "customer_mike",
        "agent_type": "Shopping Assistant",
        "conversation": [
            ("I'm looking for running shoes", "Great! What's your budget range, and do you have any brand preferences?"),
            ("I usually like Nike, budget around $100-120", "Nike makes great shoes in that range. What's your shoe size, and any color preferences?"),
            ("Size 10, and I really like blue", "I have several Nike options in size 10 with blue colorways. Road running, trail, or general training?"),
            ("Mostly road running, 20 miles per week", "For 20 miles/week, I'd recommend the Nike Pegasus 40 in blue ($120) - great cushioning and durability."),
            ("The Pegasus sounds good!", "The Nike Pegasus 40 in blue, size 10 is in stock! It has React foam cushioning and lasts 400-500 miles."),
        ]
    },
    "🛍️ Shopping Assistant - Session 2": {
        "description": "Customer returns. Agent remembers: Nike preference, blue color, size 10, bought Pegasus!",
        "user_id": "customer_mike",
        "agent_type": "Shopping Assistant",
        "conversation": [
            ("Hi! Loved the Pegasus. Looking for running shorts now", "Welcome back! Glad you're enjoying the Nike Pegasus 40. For shorts, what length - 5, 7, or 9-inch?"),
            ("7-inch, and blue to match the shoes", "The Nike Dri-FIT Stride 7-inch shorts in blue for $50 would match your Pegasus perfectly!"),
            ("What about a running shirt?", "The Nike Dri-FIT Miler in blue ($35) would complete your set. Total $85 for shorts and shirt."),
            ("Add both! You really remember my preferences!", "I remember you love Nike, prefer blue, and budget around $100-120. Great running kit!"),
        ]
    },
    "🎓 Learning Assistant - Session 1": {
        "description": "Student struggles with algebra. System learns: visual learner, loves basketball, struggles with word problems.",
        "user_id": "student_alex",
        "agent_type": "Math Tutor",
        "conversation": [
            ("I don't understand how to solve 2x + 5 = 13", "Let's solve step by step. We want x alone. First, what do we do to remove the 5?"),
            ("Subtract 5?", "Exactly! 2x + 5 - 5 = 13 - 5, so 2x = 8. Now what do we do to get x alone?"),
            ("Divide by 2?", "Perfect! 2x ÷ 2 = 8 ÷ 2, so x = 4. Check: 2(4) + 5 = 13 ✓. Do you find step-by-step easier?"),
            ("Yes! I'm more of a visual learner. Word problems are hardest", "I'll use more visual examples. What topics interest you? Sports, gaming, music?"),
            ("I love basketball! Play point guard", "Let's use basketball examples! If you score 2 points per free throw and make 5, plus 13 other points..."),
        ]
    },
    "🏥 Medical Assistant - Session 1 (Critical!)": {
        "description": "⚕️ Patient reports penicillin allergy. System stores critical safety information!",
        "user_id": "patient_emma",
        "agent_type": "Medical Assistant",
        "conversation": [
            ("I'm here for a checkup", "Welcome! Do you have any known allergies, especially to medications?"),
            ("Yes, I'm allergic to penicillin. Got a rash last time", "That's very important! Noting: PENICILLIN ALLERGY with rash reaction. Any other allergies?"),
            ("No, just penicillin", "Got it. What brings you in today?"),
            ("I have high blood pressure. Doctor wants to start medication", "Based on your blood pressure and penicillin allergy, Lisinopril 10mg daily is a good option - not related to penicillin."),
            ("Yes please!", "Prescription sent for Lisinopril 10mg. Remember: NEVER take penicillin or related antibiotics!"),
        ]
    },
    "🏥 Medical Assistant - Session 2 (LIFESAVING!)": {
        "description": "⚕️ Patient requests Amoxicillin. Agent finds penicillin allergy, PREVENTS DANGEROUS PRESCRIPTION! 🚨",
        "user_id": "patient_emma",
        "agent_type": "Medical Assistant",
        "conversation": [
            ("Hi! I have a sinus infection and need antibiotics", "I'm sorry you're not feeling well! Let me check your medical history..."),
            ("Can I just get Amoxicillin?", "⚠️ WAIT! You have a documented PENICILLIN ALLERGY! Amoxicillin IS penicillin-based - it could cause a serious reaction!"),
            ("Oh my god, I completely forgot!", "I'm glad I caught this! For your sinus infection, I can prescribe Azithromycin instead - completely different class, safe for you."),
            ("Thank you for catching that!", "You're welcome! Always mention your penicillin allergy. You're also on Lisinopril 10mg. Feel better soon!"),
        ]
    },
}


# ============================================================================
# Helper Functions
# ============================================================================

def get_openai_client():
    """Create Azure OpenAI client for agent responses."""
    return AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )


def check_server_health():
    """Check if memory service is healthy."""
    try:
        response = httpx.get(f"{MEMORY_SERVICE_URL}/health", timeout=5.0)
        return response.status_code == 200, response.json()
    except Exception as e:
        return False, {"error": str(e)}


# ============================================================================
# Synchronous Memory Service Client (for Streamlit)
# ============================================================================

class SyncMemoryClient:
    """Synchronous HTTP client for Memory Service - works well with Streamlit."""
    
    def __init__(self, service_url: str, user_id: str, timeout: float = 60.0):
        self.service_url = service_url.rstrip("/")
        self.user_id = user_id
        self.session_id = None
        self.timeout = timeout
    
    def start_session(self):
        """Start a new session."""
        response = httpx.post(
            f"{self.service_url}/sessions/start",
            json={"user_id": self.user_id, "session_id": self.session_id},
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        self.session_id = data["session_id"]
        return data
    
    def store_turn(self, user_message: str, assistant_message: str):
        """Store a conversation turn."""
        response = httpx.post(
            f"{self.service_url}/sessions/turn",
            json={
                "user_id": self.user_id,
                "session_id": self.session_id,
                "user_message": user_message,
                "assistant_message": assistant_message
            },
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def get_context(self):
        """Get current context."""
        response = httpx.get(
            f"{self.service_url}/sessions/context",
            params={"user_id": self.user_id, "session_id": self.session_id},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def end_session(self, trigger_reflection: bool = True):
        """End the session."""
        response = httpx.post(
            f"{self.service_url}/sessions/end",
            json={
                "user_id": self.user_id,
                "session_id": self.session_id,
                "trigger_reflection": trigger_reflection
            },
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def search(self, query: str, top_k: int = 5):
        """Search memory."""
        response = httpx.post(
            f"{self.service_url}/search",
            json={
                "user_id": self.user_id,
                "query": query,
                "top_k": top_k
            },
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json().get("results", "")
    
    def get_insights(self, limit: int = 10):
        """Get user insights."""
        response = httpx.get(
            f"{self.service_url}/users/{self.user_id}/insights",
            params={"limit": limit},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json().get("insights", [])


# ============================================================================
# Session State
# ============================================================================

def init_session_state():
    """Initialize Streamlit session state."""
    defaults = {
        "current_scenario": None,
        "conversation_history": [],
        "turn_index": 0,
        "is_playing": False,
        "memory_client": None,
        "session_active": False,
        "memory_context": "",
        "insights": [],
        "session_summary": "",
        "key_topics": [],
        "turn_count": 0,
        "speed": 1.0,
        "server_healthy": False,
        "insights_count": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ============================================================================
# Memory Service Actions (Synchronous)
# ============================================================================

def start_scenario(scenario_name: str):
    """Start a new scenario with the memory service."""
    scenario = SCENARIOS[scenario_name]
    
    client = SyncMemoryClient(
        service_url=MEMORY_SERVICE_URL,
        user_id=scenario["user_id"],
        timeout=60.0
    )
    
    data = client.start_session()
    
    st.session_state.current_scenario = scenario_name
    st.session_state.memory_client = client
    st.session_state.session_active = True
    st.session_state.memory_context = data.get("context", "")
    st.session_state.conversation_history = []
    st.session_state.turn_index = 0
    st.session_state.is_playing = False
    st.session_state.insights = []
    st.session_state.session_summary = ""
    st.session_state.key_topics = []
    st.session_state.turn_count = 0
    st.session_state.insights_count = 0


def advance_turn():
    """Advance to the next conversation turn."""
    if not st.session_state.current_scenario:
        return
    
    scenario = SCENARIOS[st.session_state.current_scenario]
    turn_index = st.session_state.turn_index
    
    if turn_index >= len(scenario["conversation"]):
        st.session_state.is_playing = False
        return
    
    user_msg, assistant_msg = scenario["conversation"][turn_index]
    client = st.session_state.memory_client
    
    # Add to conversation history
    st.session_state.conversation_history.append({
        "role": "user",
        "content": user_msg,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })
    st.session_state.conversation_history.append({
        "role": "assistant",
        "content": assistant_msg,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })
    
    # Store in memory service
    if client:
        try:
            result = client.store_turn(user_msg, assistant_msg)
            st.session_state.turn_count = result.get("turn_count", 0)
            
            # Update context
            ctx = client.get_context()
            st.session_state.memory_context = ctx.get("context", "")
        except Exception as e:
            st.error(f"Error storing turn: {e}")
    
    st.session_state.turn_index += 1
    
    # End session if complete
    if st.session_state.turn_index >= len(scenario["conversation"]):
        end_scenario()


def end_scenario():
    """End the current scenario and get insights."""
    client = st.session_state.memory_client
    
    if client and st.session_state.session_active:
        try:
            result = client.end_session(trigger_reflection=True)
            
            # Debug: show what we got
            print(f"[DEBUG] end_session result: {result}")
            
            st.session_state.session_summary = result.get("summary", "")
            st.session_state.insights_count = result.get("insights_count", 0)
            
            # Get insights from the insights endpoint
            try:
                scenario = SCENARIOS[st.session_state.current_scenario]
                temp_client = SyncMemoryClient(MEMORY_SERVICE_URL, scenario["user_id"])
                insights = temp_client.get_insights(limit=10)
                st.session_state.insights = insights
                print(f"[DEBUG] Got {len(insights)} insights")
            except Exception as e:
                print(f"[DEBUG] Error getting insights: {e}")
        except Exception as e:
            st.error(f"Error ending session: {e}")
            print(f"[DEBUG] Error ending session: {e}")
        
        st.session_state.session_active = False
        st.session_state.is_playing = False


def search_memory(query: str) -> str:
    """Search memory for relevant information."""
    if not st.session_state.current_scenario:
        return "No active scenario"
    
    scenario = SCENARIOS[st.session_state.current_scenario]
    
    try:
        client = SyncMemoryClient(MEMORY_SERVICE_URL, scenario["user_id"])
        return client.search(query, top_k=3)
    except Exception as e:
        return f"Search error: {e}"


# ============================================================================
# UI Components
# ============================================================================

def render_header():
    """Render the main header."""
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown('<h1 class="main-header">🧠 Agent Memory Service - Live Demo</h1>', unsafe_allow_html=True)
        st.caption("Real-time visualization of conversation memory, context compression, and insight extraction")
    
    with col2:
        healthy, health_data = check_server_health()
        if healthy:
            st.markdown(f'<span class="status-badge status-active">🟢 Server Online ({health_data.get("active_sessions", 0)} sessions)</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-inactive">🔴 Server Offline</span>', unsafe_allow_html=True)
            st.error("Start server: `uv run uvicorn server.main:app --port 8000`")
    
    st.divider()


def render_sidebar():
    """Render sidebar with scenario selection and controls."""
    with st.sidebar:
        st.markdown("## 📋 Demo Scenarios")
        
        # Scenario buttons
        for scenario_name in SCENARIOS.keys():
            if st.button(scenario_name, key=f"btn_{scenario_name}", use_container_width=True):
                start_scenario(scenario_name)
                st.rerun()
        
        # Controls if scenario is selected
        if st.session_state.current_scenario:
            st.divider()
            st.markdown("## ⚙️ Playback Controls")
            
            col1, col2 = st.columns(2)
            with col1:
                play_label = "⏸️ Pause" if st.session_state.is_playing else "▶️ Play"
                if st.button(play_label, use_container_width=True):
                    st.session_state.is_playing = not st.session_state.is_playing
                    st.rerun()
            
            with col2:
                if st.button("⏭️ Next", use_container_width=True):
                    advance_turn()
                    st.rerun()
            
            if st.button("🔄 Reset", use_container_width=True):
                start_scenario(st.session_state.current_scenario)
                st.rerun()
            
            # Speed control
            speed = st.select_slider("Speed", options=[0.5, 1.0, 1.5, 2.0, 3.0], value=1.0)
            st.session_state.speed = speed
            
            st.divider()
            
            # Progress
            scenario = SCENARIOS[st.session_state.current_scenario]
            total = len(scenario["conversation"])
            current = st.session_state.turn_index
            
            st.markdown("## 📊 Progress")
            st.progress(current / total if total > 0 else 0)
            st.caption(f"Turn {current} of {total}")
            
            if current >= total:
                st.success("✅ Scenario Complete!")
            
            st.divider()
            
            # Scenario info
            st.markdown("## 📖 About")
            st.caption(scenario["description"])
            
            st.divider()
            
            # Memory search
            st.markdown("## 🔍 Memory Search")
            query = st.text_input("Search query", placeholder="e.g., retirement savings")
            if st.button("Search", use_container_width=True) and query:
                result = search_memory(query)
                st.write("**Results:**")
                st.write(result[:500] + "..." if len(result) > 500 else result)


def render_chat():
    """Render the chat interface."""
    st.markdown("### 💬 Live Conversation")
    
    if not st.session_state.current_scenario:
        st.info("👈 **Select a scenario** from the sidebar to begin")
        return
    
    scenario = SCENARIOS[st.session_state.current_scenario]
    agent_type = scenario.get("agent_type", "AI Assistant")
    
    agent_icons = {
        "Financial Advisor": "💼",
        "Shopping Assistant": "🛒",
        "Math Tutor": "📐",
        "Medical Assistant": "⚕️",
        "AI Assistant": "🤖"
    }
    agent_icon = agent_icons.get(agent_type, "🤖")
    
    # Chat messages
    for msg in st.session_state.conversation_history:
        safe_timestamp = html.escape(msg["timestamp"])
        safe_content = html.escape(msg["content"]).replace("\n", "<br>")
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="chat-user">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <strong>👤 User</strong>
                    <span style="color: #666; font-size: 0.85em;">{safe_timestamp}</span>
                </div>
                <div>{safe_content}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            safe_agent_type = html.escape(agent_type)
            st.markdown(f"""
            <div class="chat-assistant">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <strong>{agent_icon} {safe_agent_type}</strong>
                    <span style="color: #666; font-size: 0.85em;">{safe_timestamp}</span>
                </div>
                <div>{safe_content}</div>
            </div>
            """, unsafe_allow_html=True)


def clean_context_for_display(raw_context: str) -> str:
    """Clean context by removing session_initialization XML wrapper tags."""
    if not raw_context:
        return ""
    
    # Remove <session_initialization>...</session_initialization> wrapper but KEEP the content
    # This regex captures content between the tags and replaces with just the content
    cleaned = re.sub(
        r'<session_initialization>\s*([\s\S]*?)\s*</session_initialization>\s*',
        r'\1',
        raw_context,
        flags=re.MULTILINE
    )
    
    return cleaned.strip()


def render_memory_panel():
    """Render memory state visualization."""
    st.markdown("### 🧠 Memory System State")
    
    if not st.session_state.current_scenario:
        st.info("Memory visualization will appear once a scenario is started")
        return
    
    # Clean context once
    context = clean_context_for_display(st.session_state.memory_context)
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Turns Processed", st.session_state.turn_index)
    
    with col2:
        st.metric("Context Length", f"{len(context):,} chars")
    
    with col3:
        st.metric("Insights", st.session_state.insights_count)
    
    # Memory components
    with st.expander("📝 Current Context", expanded=True):
        if context:
            st.markdown(context)
        else:
            st.caption("Context will appear as conversation progresses")
    
    with st.expander("📋 Session Summary", expanded=bool(st.session_state.session_summary)):
        if st.session_state.session_summary:
            st.info(st.session_state.session_summary)
        else:
            st.caption("Summary will be generated when session ends")
    
    with st.expander("💡 Extracted Insights", expanded=bool(st.session_state.insights)):
        if st.session_state.insights:
            st.success(f"✅ **{len(st.session_state.insights)} insights** extracted!")
            st.caption("Insights include: goals, knowledge level, preferences, behavior patterns")
            
            for idx, insight in enumerate(st.session_state.insights, 1):
                with st.container():
                    st.markdown(f"**Insight #{idx}**")
                    
                    # Handle both dict and string formats
                    if isinstance(insight, dict):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            insight_text = insight.get('insight_text', str(insight))
                            st.markdown(f"📝 {insight_text}")
                        with col2:
                            category = insight.get('category', insight.get('insight_type', 'general'))
                            st.markdown(f"**Category:** `{category}`")
                            if 'importance' in insight:
                                st.markdown(f"**Importance:** `{insight['importance']}`")
                        
                        # Show confidence if available
                        if 'confidence' in insight and insight['confidence'] is not None:
                            try:
                                conf = float(insight['confidence'])
                                st.progress(conf, text=f"Confidence: {conf:.0%}")
                            except (ValueError, TypeError):
                                pass
                    else:
                        st.markdown(f"📝 {insight}")
                    
                    st.divider()
        else:
            st.caption("Insights will be extracted when session completes")


# ============================================================================
# Main App
# ============================================================================

def main():
    """Main Streamlit application."""
    init_session_state()
    
    render_header()
    render_sidebar()
    
    # Main content - two columns
    col_chat, col_memory = st.columns([3, 2])
    
    with col_chat:
        render_chat()
    
    with col_memory:
        render_memory_panel()
    
    # Auto-advance if playing
    if st.session_state.is_playing and st.session_state.current_scenario:
        scenario = SCENARIOS[st.session_state.current_scenario]
        if st.session_state.turn_index < len(scenario["conversation"]):
            import time
            time.sleep(2.0 / st.session_state.speed)
            advance_turn()
            st.rerun()


if __name__ == "__main__":
    main()
