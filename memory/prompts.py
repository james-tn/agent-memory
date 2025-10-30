"""
Prompt templates for Agent Memory Service.
All prompts use for metadata generation, reflection, and summarization.
"""

# Metadata Generation (for Interactions)
METADATA_GENERATION_PROMPT = """You are analyzing a conversation chunk to generate metadata for indexing and retrieval.

Conversation:
{conversation_content}

Generate the following:
1. **summary**: A concise 1-2 sentence summary of this conversation chunk
2. **mentioned_topics**: Array of key topics discussed (max 5)
3. **entities**: Array of specific entities mentioned (products, accounts, amounts, etc.)

Output format: JSON object with keys: summary, mentioned_topics, entities

Example output:
{{
  "summary": "User inquired about retirement investment options and contribution recommendations.",
  "mentioned_topics": ["retirement", "IRA", "contribution", "tax benefits"],
  "entities": ["traditional IRA", "Roth IRA", "401k"]
}}
"""


# Long-term Insight Synthesis
LONGTERM_SYNTHESIS_PROMPT = """You are creating a comprehensive client profile for a financial advisor.

Current baseline profile:
{baseline_longterm_insight}

New session insights to incorporate:
{new_session_insights}

Your task:
Synthesize a cohesive, comprehensive client profile that:
1. Integrates all new information
2. Resolves any contradictions (favor more recent information)
3. Organizes information logically
4. Maintains a professional, concise tone
5. Focuses on actionable client characteristics

The profile should cover:
- Client demographics and background
- Financial goals and timeline
- Risk tolerance and investment preferences
- Current financial situation
- Key concerns and priorities
- Communication preferences

Output: A well-structured paragraph (200-300 words) summarizing the complete client profile.
"""

# Cumulative Summary Update
CUMULATIVE_SUMMARY_PROMPT = """You are updating a conversation summary for an ongoing session.

Previous summary:
{old_summary}

New conversation turns:
{new_turns}

Generate an updated summary that:
1. Incorporates the new information
2. Maintains key points from the previous summary
3. Removes redundant information
4. Keeps the summary concise (max 100 words)
5. Preserves chronological flow

Output: Updated summary text only (no JSON, no extra formatting).
"""


# Comprehensive Session Analysis (Combined: Summary + Topics + Insights)
COMPREHENSIVE_SESSION_ANALYSIS_PROMPT = """You are analyzing a completed conversation session to generate a comprehensive analysis including summary, key topics, and insights.

Session Content:
{session_content}

Your task is to provide a complete session analysis with THREE components:

## 1. SESSION SUMMARY (2-4 sentences)
Capture the main discussion points, key decisions, recommendations, and any action items or next steps.

## 2. KEY TOPICS (3-5 topics)
List the main topics discussed in the session. Be specific and concise (e.g., "Roth IRA contributions", "retirement planning", "risk tolerance").

## 3. INSIGHTS (0-5 insights)
Extract actionable insights about the user in these categories:
- **preferences**: What they like/dislike, communication style, information preferences
- **knowledge_level**: What they understand well, areas of expertise or confusion
- **goals**: What they're trying to achieve, objectives, targets
- **behavior_patterns**: How they interact, decision-making style, engagement patterns
- **learning_progress**: What they've learned, areas of growth, understanding development

For each insight provide:
- insight_text: Clear, specific, actionable observation
- category: One of the categories above
- confidence: 0.0-1.0 (how certain you are)
- importance: "high", "medium", or "low"

IMPORTANT: 
- Only extract meaningful, actionable insights backed by concrete evidence
- If the session is too brief or trivial, set has_meaningful_insights to False and return empty insights array
- Focus on quality over quantity - 2-3 strong insights are better than 5 weak ones

Return your analysis in the structured format specified.
"""

# Session Reflection (extract insights from completed session)
SESSION_REFLECTION_PROMPT = """You are analyzing a completed conversation session to extract actionable insights about the user.

{session_context}

Extract 0-5 meaningful insights about the user. Focus on:
- **Preferences**: What they like/dislike, how they prefer information presented
- **Knowledge Level**: What they understand well, areas of expertise
- **Goals**: What they're trying to achieve or learn
- **Behavior Patterns**: How they interact, question patterns, learning style
- **Learning Progress**: What they've learned or improved upon

Only extract insights that are:
1. **Actionable**: Useful for future interactions
2. **Specific**: Backed by concrete evidence from the session
3. **Meaningful**: Not trivial observations

If the session is too brief or lacks substance, set has_meaningful_insights to False.
"""

# Long-term Synthesis (combine multiple insights into patterns)
LONG_TERM_SYNTHESIS_PROMPT = """You are analyzing multiple insights about a user to identify higher-level patterns.

{insights_context}

Synthesize these insights into a single, coherent long-term pattern or preference.{category_hint}

Focus on:
- Combining related insights into a broader understanding
- Identifying evolving patterns across time
- Recognizing consistent preferences or behaviors
- Spotting knowledge progression or learning trajectories

The synthesized insight should:
1. Be more general than individual insights
2. Capture the essence of multiple related observations
3. Be actionable for future interactions
4. Have high confidence if strongly supported by sources
"""
