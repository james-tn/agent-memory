"""
Custom test runner for CosmosMemoryProvider integration tests.
Uses real CosmosDB and Azure OpenAI from .env
"""
import asyncio
import sys
from tests.test_cosmos_memory_provider import (
    cosmos_client,
    openai_client,
    provider_config,
    TestCosmosMemoryProviderInit,
    TestCosmosMemoryProviderThreadLifecycle,
    TestCosmosMemoryProviderContextInjection,
    TestCosmosMemoryProviderTurnStorage,
    TestCosmosMemoryProviderContextManager,
    TestCosmosMemoryProviderUtilities,
)


def run_test(test_func, *args):
    """Run a test function and return success status."""
    try:
        if asyncio.iscoroutinefunction(test_func):
            asyncio.run(test_func(*args))
        else:
            test_func(*args)
        return True
    except Exception as e:
        print(f" ✗ FAILED")
        print(f"  Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("=" * 70)
    print("Running CosmosMemoryProvider Integration Tests")
    print("Using REAL CosmosDB and Azure OpenAI from .env")
    print("=" * 70)
    print()
    
    # Get fixtures
    cosmos = cosmos_client()
    openai = openai_client()
    config = provider_config()
    
    passed = 0
    failed = 0
    
    # Test Init
    print("Testing Initialization...")
    test_init = TestCosmosMemoryProviderInit()
    
    print("  test_init_with_cosmos_client... ", end="", flush=True)
    if run_test(test_init.test_init_with_cosmos_client, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    print("  test_init_validates_user_id... ", end="", flush=True)
    if run_test(test_init.test_init_validates_user_id, cosmos, openai):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    print("  test_init_with_custom_memory_config... ", end="", flush=True)
    if run_test(test_init.test_init_with_custom_memory_config, cosmos, openai):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    # Test Thread Lifecycle
    print("\nTesting Thread Lifecycle...")
    test_lifecycle = TestCosmosMemoryProviderThreadLifecycle()
    
    print("  test_thread_created_with_auto_session... ", end="", flush=True)
    if run_test(test_lifecycle.test_thread_created_with_auto_session, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    print("  test_thread_created_no_auto_manage... ", end="", flush=True)
    if run_test(test_lifecycle.test_thread_created_no_auto_manage, cosmos, openai):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    # Test Context Injection
    print("\nTesting Context Injection...")
    test_context = TestCosmosMemoryProviderContextInjection()
    
    print("  test_invoking_without_session_returns_empty... ", end="", flush=True)
    if run_test(test_context.test_invoking_without_session_returns_empty, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    print("  test_invoking_with_session_provides_context... ", end="", flush=True)
    if run_test(test_context.test_invoking_with_session_provides_context, cosmos, openai):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    # Test Turn Storage
    print("\nTesting Turn Storage...")
    test_storage = TestCosmosMemoryProviderTurnStorage()
    
    print("  test_invoked_stores_conversation_turn... ", end="", flush=True)
    if run_test(test_storage.test_invoked_stores_conversation_turn, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    print("  test_invoked_without_session_does_nothing... ", end="", flush=True)
    if run_test(test_storage.test_invoked_without_session_does_nothing, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    # Test Context Manager
    print("\nTesting Context Manager...")
    test_cm = TestCosmosMemoryProviderContextManager()
    
    print("  test_context_manager_ends_session_on_exit... ", end="", flush=True)
    if run_test(test_cm.test_context_manager_ends_session_on_exit, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    # Test Utilities
    print("\nTesting Utility Methods...")
    test_utils = TestCosmosMemoryProviderUtilities()
    
    print("  test_end_session_explicit... ", end="", flush=True)
    if run_test(test_utils.test_end_session_explicit, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    print("  test_get_status... ", end="", flush=True)
    if run_test(test_utils.test_get_status, cosmos, openai, config):
        print("✓ PASSED")
        passed += 1
    else:
        failed += 1
    
    # Summary
    print()
    print("=" * 70)
    if failed == 0:
        print(f"All {passed} integration tests completed successfully! ✓")
    else:
        print(f"{passed} tests passed, {failed} tests failed")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
