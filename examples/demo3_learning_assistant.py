"""
Demo 3: Learning Assistant with Progress Tracking
=================================================

This demo showcases:
- Learning style adaptation
- Progress tracking across sessions
- Difficulty adjustment based on performance
- Personalized examples based on interests
- Long-term educational goals

Scenario:
- Session 1: Initial assessment, discover learning style and struggles
- Session 2: Adapted teaching approach based on profile
- Session 3: Progress check and difficulty adjustment
"""

import asyncio
import uuid
import os
import random
from azure.identity import AzureCliCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from memory.cosmos_memory_provider import CosmosMemoryProvider


# Mock problem database
MATH_PROBLEMS = {
    "easy": [
        {"question": "If you have 5 apples and buy 3 more, how many do you have?", "answer": "8"},
        {"question": "2 + 3 = ?", "answer": "5"},
    ],
    "medium": [
        {"question": "A basketball player scored 15 points in the first half and 12 in the second. What's the total?", "answer": "27"},
        {"question": "If a soccer team scored 3 goals per game for 5 games, how many total goals?", "answer": "15"},
    ],
    "hard": [
        {"question": "A train travels 60 miles in 2 hours. At this rate, how far will it travel in 5 hours?", "answer": "150"},
        {"question": "If 3x + 5 = 20, what is x?", "answer": "5"},
    ]
}


def get_practice_problem(difficulty: str, topic: str = "general") -> str:
    """Tool: Get a practice problem at specified difficulty."""
    difficulty = difficulty.lower()
    if difficulty not in MATH_PROBLEMS:
        return "Invalid difficulty level. Choose: easy, medium, or hard."
    
    problem = random.choice(MATH_PROBLEMS[difficulty])
    return f"Problem: {problem['question']}\n(This is a {difficulty} level {topic} problem)"


def check_answer(student_answer: str, correct_answer: str) -> str:
    """Tool: Check if student's answer is correct."""
    student_answer = student_answer.strip().lower()
    correct_answer = correct_answer.strip().lower()
    
    if student_answer == correct_answer:
        return "✓ Correct! Great job!"
    else:
        return f"Not quite. The correct answer is {correct_answer}. Let's work through it together."


def get_learning_resources(topic: str, difficulty: str) -> str:
    """Tool: Get recommended learning resources."""
    resources = {
        "addition": {
            "easy": "Khan Academy: Basic Addition, Math Games for Kids",
            "medium": "Practice worksheets: Multi-digit addition",
            "hard": "Word problems compilation, Advanced addition strategies"
        },
        "algebra": {
            "easy": "Introduction to Variables, Visual Algebra",
            "medium": "Solving Linear Equations, Algebra Practice",
            "hard": "Advanced Equations, Quadratic Functions"
        }
    }
    
    topic_resources = resources.get(topic.lower(), {})
    return topic_resources.get(difficulty.lower(), "General math resources available")


async def main() -> None:
    print("=" * 80)
    print("Demo 3: Learning Assistant with Adaptive Teaching")
    print("=" * 80)
    print()
    
    # Setup
    user_id = "student_demo_user"
    memory_service_url = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000")
    
    print(f"Student ID: {user_id}")
    print(f"Memory Service: {memory_service_url}")
    print()
    
    # =========================================================================
    # SESSION 1: Initial Assessment - Discover Learning Profile
    # =========================================================================
    print("─" * 80)
    print("SESSION 1: First Tutoring Session - Assessment & Learning Style")
    print("─" * 80)
    print()
    
    memory_provider = CosmosMemoryProvider(
        service_url=memory_service_url,
        user_id=user_id,
        auto_manage_session=False
    )
    
    await memory_provider._start_session()
    
    # Create the agent
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions=(
            "You are a patient and encouraging math tutor. "
            "Adapt your teaching style to each student's needs, interests, and learning pace. "
            "Pay attention to: learning struggles, preferred examples (sports, music, etc.), "
            "confidence level, and progress over time. "
            "Always remember important details about each student to personalize future sessions. "
            "Use encouraging language and celebrate improvements."
        ),
        tools=[get_practice_problem, check_answer, get_learning_resources],
        context_providers=[memory_provider],
    )
    
    thread = agent.get_new_thread()
    
    # Question 1: Initial struggle
    query = "Hi, I'm really struggling with word problems in math. They're so confusing!"
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:200]}...")
    print()
    
    # Question 2: Reveal interest
    query = "I love basketball! I play every day after school."
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:200]}...")
    print()
    
    # Question 3: Learning style preference
    query = "I understand things better when someone shows me with pictures or real examples, not just numbers."
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:200]}...")
    print()
    
    # Question 4: Try a problem
    query = "Okay, can you give me an easy problem to start?"
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:200]}...")
    print()
    
    # Answer (simulated)
    query = "Is it 8?"
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:150]}...")
    print()
    
    await asyncio.sleep(1.0)
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 1 complete - Agent should have learned:")
    print("   - Struggles with: Word problems")
    print("   - Interest: Basketball")
    print("   - Learning style: Visual/concrete examples")
    print("   - Current level: Easy problems")
    print("   - Confidence: Building")
    print()
    
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 2: Adaptive Teaching - Personalized Examples
    # =========================================================================
    print("─" * 80)
    print("SESSION 2: Second Session (3 days later) - Adapted Teaching")
    print("─" * 80)
    print()
    
    memory_provider = CosmosMemoryProvider(
        service_url=memory_service_url,
        user_id=user_id,
        auto_manage_session=False
    )
    
    await memory_provider._start_session()
    
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions=(
            "You are a patient and encouraging math tutor. "
            "Adapt your teaching style to each student's needs, interests, and learning pace. "
            "Pay attention to: learning struggles, preferred examples (sports, music, etc.), "
            "confidence level, and progress over time. "
            "Always remember important details about each student to personalize future sessions. "
            "Use encouraging language and celebrate improvements."
        ),
        tools=[get_practice_problem, check_answer, get_learning_resources],
        context_providers=[memory_provider],
    )
    
    thread = agent.get_new_thread()
    
    # Question 1: Return for practice
    query = "Hi! I want to practice more word problems."
    print(f"📚 Student: {query}")
    print("   [NOTE: New thread - should use basketball examples]")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:250]}...")
    print()
    
    # Question 2: Request medium difficulty
    query = "That was easier than I thought! Can you give me a medium level problem?"
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:200]}...")
    print()
    
    # Answer (simulated)
    query = "I think it's 27 points total."
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:150]}...")
    print()
    
    await asyncio.sleep(1.0)
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 2 complete - Testing if agent:")
    print("   - Used basketball-themed examples")
    print("   - Recognized improved confidence")
    print("   - Adjusted difficulty appropriately")
    print("   - Provided visual/concrete explanations")
    print()
    
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 3: Progress Check - Difficulty Progression
    # =========================================================================
    print("─" * 80)
    print("SESSION 3: Progress Review (1 week later) - Advancing Skills")
    print("─" * 80)
    print()
    
    memory_provider = CosmosMemoryProvider(
        service_url=memory_service_url,
        user_id=user_id,
        auto_manage_session=False
    )
    
    await memory_provider._start_session()
    
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions=(
            "You are a patient and encouraging math tutor. "
            "Adapt your teaching style to each student's needs, interests, and learning pace. "
            "Pay attention to: learning struggles, preferred examples (sports, music, etc.), "
            "confidence level, and progress over time. "
            "Always remember important details about each student to personalize future sessions. "
            "Use encouraging language and celebrate improvements."
        ),
        tools=[get_practice_problem, check_answer, get_learning_resources],
        context_providers=[memory_provider],
    )
    
    thread = agent.get_new_thread()
    
    # Question: Progress check
    query = "I've been practicing a lot! I feel more confident with word problems now."
    print(f"📚 Student: {query}")
    print("   [NOTE: Another new thread - testing progress tracking]")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:250]}...")
    print()
    
    # Challenge request
    query = "Can you challenge me with a harder problem? Maybe something about algebra?"
    print(f"📚 Student: {query}")
    result = await agent.run(query, thread=thread)
    print(f"👨‍🏫 Tutor: {result.text[:200]}...")
    print()
    
    await asyncio.sleep(1.0)
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 3 complete - Testing if agent:")
    print("   - Tracked progress from Session 1 to now")
    print("   - Celebrated improvement")
    print("   - Appropriately increased difficulty")
    print("   - Maintained personalization (basketball examples)")
    print()
    
    print("🎉 Demo Complete!")
    print()
    print("Key Capabilities Demonstrated:")
    print("✓ Learning style adaptation (visual/concrete examples)")
    print("✓ Interest-based personalization (basketball)")
    print("✓ Progress tracking across sessions")
    print("✓ Difficulty adjustment based on performance")
    print("✓ Encouraging, personalized teaching approach")


if __name__ == "__main__":
    asyncio.run(main())
