"""
Demo 2: Shopping Assistant with Preference Learning
===================================================

This demo showcases:
- Learning user preferences over time
- Personalized product recommendations
- Purchase history tracking
- Style and budget awareness
- Cross-session preference retention

Scenario:
- Session 1: User browses items, agent learns style preferences
- Session 2: (New thread) User gets recommendations matching preferences
- Session 3: (New thread) Agent suggests complementary items based on history
"""

import asyncio
import uuid
import os
from azure.identity import AzureCliCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from memory.cosmos_memory_provider import CosmosMemoryProvider


# Mock product database
PRODUCTS = {
    "sneakers_nike_blue": {"name": "Nike Air Max", "color": "Blue", "price": 120, "category": "Sneakers", "brand": "Nike"},
    "sneakers_adidas_black": {"name": "Adidas Ultraboost", "color": "Black", "price": 180, "category": "Sneakers", "brand": "Adidas"},
    "sneakers_nb_white": {"name": "New Balance 574", "color": "White", "price": 85, "category": "Sneakers", "brand": "New Balance"},
    "jacket_north_face": {"name": "North Face Jacket", "color": "Black", "price": 200, "category": "Outerwear", "brand": "North Face"},
    "jacket_patagonia": {"name": "Patagonia Fleece", "color": "Navy", "price": 150, "category": "Outerwear", "brand": "Patagonia"},
    "tshirt_nike": {"name": "Nike Performance Tee", "color": "Blue", "price": 35, "category": "Shirts", "brand": "Nike"},
    "tshirt_under_armour": {"name": "Under Armour Tech Tee", "color": "Black", "price": 30, "category": "Shirts", "brand": "Under Armour"},
    "socks_nike_pack": {"name": "Nike Crew Socks 6-Pack", "color": "White", "price": 18, "category": "Accessories", "brand": "Nike"},
    "hat_nike_cap": {"name": "Nike Dri-FIT Cap", "color": "Blue", "price": 25, "category": "Accessories", "brand": "Nike"},
}


def search_products(category: str = None, max_price: int = None, brand: str = None, color: str = None) -> str:
    """Tool: Search for products with filters."""
    results = []
    for product_id, product in PRODUCTS.items():
        if category and product["category"] != category:
            continue
        if max_price and product["price"] > max_price:
            continue
        if brand and product["brand"] != brand:
            continue
        if color and product["color"] != color:
            continue
        results.append(f"{product['name']} (${product['price']}) - {product['color']}")
    
    if not results:
        return "No products found matching your criteria."
    return "Found products:\n" + "\n".join(f"- {r}" for r in results)


def get_product_details(product_name: str) -> str:
    """Tool: Get detailed information about a product."""
    for product in PRODUCTS.values():
        if product["name"].lower() in product_name.lower():
            return (
                f"{product['name']}\n"
                f"Brand: {product['brand']}\n"
                f"Category: {product['category']}\n"
                f"Color: {product['color']}\n"
                f"Price: ${product['price']}"
            )
    return "Product not found."


def add_to_wishlist(product_name: str) -> str:
    """Tool: Add a product to user's wishlist."""
    return f"✓ Added '{product_name}' to your wishlist!"


async def main() -> None:
    print("=" * 80)
    print("Demo 2: Shopping Assistant with Preference Learning")
    print("=" * 80)
    print()
    
    # Setup
    user_id = "shopper_demo_user"
    memory_service_url = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000")
    
    print(f"Shopper ID: {user_id}")
    print(f"Memory Service: {memory_service_url}")
    print()
    
    # =========================================================================
    # SESSION 1: Initial Browsing - Learning Preferences
    # =========================================================================
    print("─" * 80)
    print("SESSION 1: First Visit - Browse & Discover Preferences")
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
            "You are a helpful shopping assistant at a sportswear store. "
            "Help customers find products they'll love by learning their preferences. "
            "Pay attention to: preferred brands, favorite colors, budget constraints, and style. "
            "Remember these preferences for future visits to provide personalized recommendations. "
            "Be friendly, helpful, and attentive to detail."
        ),
        tools=[search_products, get_product_details, add_to_wishlist],
        context_providers=[memory_provider],
    )
    
    thread = agent.get_new_thread()
    
    # Question 1: Initial interest
    query = "Hi! I'm looking for some new sneakers."
    print(f"🛍️  Customer: {query}")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:200]}...")
    print()
    
    # Question 2: Reveal brand preference
    query = "I really like Nike products. Can you show me Nike sneakers?"
    print(f"🛍️  Customer: {query}")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:200]}...")
    print()
    
    # Question 3: Color and budget
    query = "I prefer blue colors and my budget is around $100-120. What do you have?"
    print(f"🛍️  Customer: {query}")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:200]}...")
    print()
    
    # Question 4: Add to wishlist
    query = "The Nike Air Max looks good! Add it to my wishlist. I'll think about it."
    print(f"🛍️  Customer: {query}")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:150]}...")
    print()
    
    await asyncio.sleep(1.0)
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 1 complete - Agent should have learned:")
    print("   - Preferred brand: Nike")
    print("   - Favorite color: Blue")
    print("   - Budget: $100-120")
    print("   - Interested in: Sneakers")
    print("   - Wishlist: Nike Air Max")
    print()
    
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 2: Return Visit - Personalized Recommendations
    # =========================================================================
    print("─" * 80)
    print("SESSION 2: Return Visit (1 week later) - Testing Personalization")
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
            "You are a helpful shopping assistant at a sportswear store. "
            "Help customers find products they'll love by learning their preferences. "
            "Pay attention to: preferred brands, favorite colors, budget constraints, and style. "
            "Remember these preferences for future visits to provide personalized recommendations. "
            "Be friendly, helpful, and attentive to detail."
        ),
        tools=[search_products, get_product_details, add_to_wishlist],
        context_providers=[memory_provider],
    )
    
    thread = agent.get_new_thread()
    
    # Question 1: Return visit
    query = "Hi! I'm back. What do you recommend for me today?"
    print(f"🛍️  Customer: {query}")
    print("   [NOTE: New thread - should remember Nike, blue, $100-120 budget]")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:250]}...")
    print()
    
    # Question 2: Ask about accessories
    query = "I also need some accessories to go with my sneakers. What would match?"
    print(f"🛍️  Customer: {query}")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:200]}...")
    print()
    
    # Question 3: Purchase decision
    query = "Great! I'll take the Nike Air Max from my wishlist and the Nike cap."
    print(f"🛍️  Customer: {query}")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:150]}...")
    print()
    
    await asyncio.sleep(1.0)
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 2 complete - Testing if agent:")
    print("   - Provided personalized recommendations")
    print("   - Remembered wishlist items")
    print("   - Suggested matching accessories in preferred color")
    print()
    
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 3: Follow-up Purchase - Complementary Items
    # =========================================================================
    print("─" * 80)
    print("SESSION 3: Follow-up Visit (2 weeks later) - Complementary Items")
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
            "You are a helpful shopping assistant at a sportswear store. "
            "Help customers find products they'll love by learning their preferences. "
            "Pay attention to: preferred brands, favorite colors, budget constraints, and style. "
            "Remember these preferences for future visits to provide personalized recommendations. "
            "Be friendly, helpful, and attentive to detail."
        ),
        tools=[search_products, get_product_details, add_to_wishlist],
        context_providers=[memory_provider],
    )
    
    thread = agent.get_new_thread()
    
    # Question: Complementary purchase
    query = "I loved my recent purchases! What else would go well with my Nike sneakers and cap?"
    print(f"🛍️  Customer: {query}")
    print("   [NOTE: Yet another new thread - testing purchase history recall]")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:250]}...")
    print()
    
    # Follow-up
    query = "Show me Nike shirts that would match."
    print(f"🛍️  Customer: {query}")
    result = await agent.run(query, thread=thread)
    print(f"🤖 Assistant: {result.text[:150]}...")
    print()
    
    await asyncio.sleep(1.0)
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 3 complete - Testing if agent:")
    print("   - Recalled previous purchases")
    print("   - Suggested complementary items")
    print("   - Maintained brand and color preferences")
    print()
    
    print("🎉 Demo Complete!")
    print()
    print("Key Capabilities Demonstrated:")
    print("✓ Preference learning (brand, color, budget)")
    print("✓ Wishlist and purchase history tracking")
    print("✓ Personalized product recommendations")
    print("✓ Complementary item suggestions")
    print("✓ Cross-session preference retention")


if __name__ == "__main__":
    asyncio.run(main())
