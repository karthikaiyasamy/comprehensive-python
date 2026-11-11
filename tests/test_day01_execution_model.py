"""
Unit and integration tests for Day 01: Execution Model and Memory Architecture.
"""

from __future__ import annotations

import gc
import sys
import unittest

from comprehensive_python.day01_execution_model import (
    ExpiringWeakCache,
    ObjectLifecycleTracker,
    SystemLifecycleHarness,
    TrackedResource,
    demonstrate_multiplied_list_trap,
    demonstrate_mutable_default_trap,
    inspect_bytecode,
    inspect_call_stack,
    inspect_function_defaults,
)


class TestObjectLifecycleTracker(unittest.TestCase):
    """Test cases for reference counting, cyclic memory, and interning."""

    def setUp(self) -> None:
        gc.collect()

    def tearDown(self) -> None:
        gc.collect()

    def test_immediate_refcount_deallocation(self) -> None:
        """Verify that single-owner objects are deterministically deallocated upon del."""
        deallocated: list[str] = []

        def on_dealloc(name: str, address: int) -> None:
            deallocated.append(name)

        resource = TrackedResource("Alpha_Buffer", on_dealloc=on_dealloc)
        self.assertEqual(len(deallocated), 0)

        # Deleting the only reference should trigger immediate reclamation without gc.collect()
        del resource
        self.assertIn("Alpha_Buffer", deallocated)

    def test_cyclic_reference_retention_and_gc(self) -> None:
        """Verify that circular references prevent immediate deallocation until GC runs."""
        deallocated: list[str] = []

        def on_dealloc(name: str, address: int) -> None:
            deallocated.append(name)

        node_a = TrackedResource("NodeA", on_dealloc=on_dealloc)
        node_b = TrackedResource("NodeB", on_dealloc=on_dealloc)

        # Establish circular reference
        node_a.partner = node_b
        node_b.partner = node_a

        # Delete external names
        del node_a
        del node_b

        # Cycle prevents immediate reclamation
        self.assertEqual(len(deallocated), 0)

        # Force cyclic garbage collector to detect and break cycle
        collected = gc.collect()
        self.assertGreater(collected, 0)
        self.assertIn("NodeA", deallocated)
        self.assertIn("NodeB", deallocated)

    def test_small_integer_interning_range(self) -> None:
        """Verify CPython small integer cache bounds [-5, 256]."""
        # Test inside cached range
        for n in (-5, 0, 1, 42, 256):
            self.assertTrue(
                ObjectLifecycleTracker.test_integer_interning(n),
                f"Integer {n} should be interned",
            )

        # Test outside cached range (dynamically constructed)
        for n in (-10, -6, 257, 1000):
            self.assertFalse(
                ObjectLifecycleTracker.test_integer_interning(n),
                f"Integer {n} should not be interned",
            )

        low, high = ObjectLifecycleTracker.find_interning_range(-10, 300)
        self.assertEqual(low, -5)
        self.assertEqual(high, 256)


class TestBytecodeInspector(unittest.TestCase):
    """Test cases for bytecode disassembly and stack operation inspection."""

    def test_inspect_bytecode_extraction(self) -> None:
        """Verify that bytecode opcodes are properly extracted into structured objects."""
        def adder(a: int, b: int) -> int:
            return a + b

        instructions = inspect_bytecode(adder)
        self.assertGreater(len(instructions), 0)

        opnames = [instr.opname for instr in instructions]
        self.assertIn("RETURN_VALUE", opnames)


class TestFrameInspector(unittest.TestCase):
    """Test cases for CPython frame traversal and execution context."""

    def test_call_stack_traversal(self) -> None:
        """Verify that call stack inspection accurately walks parent frames."""
        def level_three() -> list[str]:
            frames = inspect_call_stack(max_depth=5)
            return [f.function_name for f in frames]

        def level_two() -> list[str]:
            return level_three()

        def level_one() -> list[str]:
            return level_two()

        names = level_one()
        self.assertGreaterEqual(len(names), 3)
        self.assertEqual(names[0], "level_three")
        self.assertEqual(names[1], "level_two")
        self.assertEqual(names[2], "level_one")


class CacheablePayload:
    """User-defined class that supports weak references via __weakref__."""

    def __init__(self, name: str, data: list[int]) -> None:
        self.name = name
        self.data = data


class TestWeakrefCache(unittest.TestCase):
    """Test cases for non-retaining weak reference caches."""

    def setUp(self) -> None:
        gc.collect()

    def tearDown(self) -> None:
        gc.collect()

    def test_builtin_types_reject_weakref(self) -> None:
        """
        Demonstrate that CPython built-in container types (list, dict) do not have
        tp_weaklistoffset allocated in their C struct, raising TypeError on weakref.
        """
        cache: ExpiringWeakCache[list[int]] = ExpiringWeakCache()
        with self.assertRaises(TypeError):
            cache.set("raw_list", [1, 2, 3])

    def test_weak_cache_retains_live_object(self) -> None:
        """Verify cache returns object while a strong reference is maintained."""
        cache: ExpiringWeakCache[CacheablePayload] = ExpiringWeakCache()
        live_item = CacheablePayload("item1", [10, 20, 30])

        cache.set("items", live_item)
        self.assertTrue(cache.contains("items"))
        self.assertIs(cache.get("items"), live_item)
        self.assertEqual(len(cache), 1)

    def test_weak_cache_auto_eviction_on_drop(self) -> None:
        """Verify cache entry evaporates when the strong reference is deleted."""
        cache: ExpiringWeakCache[CacheablePayload] = ExpiringWeakCache()
        finalized_keys: list[str] = []

        item_ref = CacheablePayload("payload_obj", [100, 200, 300])
        cache.set("payload", item_ref, on_finalize=lambda k: finalized_keys.append(k))

        self.assertIn("payload", cache.live_keys())

        # Drop the only strong reference
        del item_ref
        gc.collect()

        self.assertNotIn("payload", cache.live_keys())
        self.assertIsNone(cache.get("payload"))
        self.assertIn("payload", finalized_keys)


class TestReferenceTraps(unittest.TestCase):
    """Test cases for mutable default arguments and container multiplication traps."""

    def test_multiplied_list_shares_pointers(self) -> None:
        """Verify that [[0]*3]*3 shares the exact same inner list across all rows."""
        trap_results = demonstrate_multiplied_list_trap()
        self.assertTrue(trap_results["shared_inner_addresses"])
        self.assertTrue(trap_results["all_rows_affected_in_trap"])
        self.assertTrue(trap_results["only_first_row_affected_in_safe"])

    def test_mutable_default_persists_in_defaults_tuple(self) -> None:
        """Verify that mutable default arguments persist across function invocations."""
        buggy_func, safe_func = demonstrate_mutable_default_trap()

        # Buggy accumulator retains state in __defaults__
        call1 = buggy_func("itemA")
        self.assertEqual(call1, ["itemA"])
        call2 = buggy_func("itemB")
        self.assertEqual(call2, ["itemA", "itemB"])

        defaults = inspect_function_defaults(buggy_func)
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0], ["itemA", "itemB"])

        # Safe accumulator initializes new list per call
        safe1 = safe_func("itemA")
        self.assertEqual(safe1, ["itemA"])
        safe2 = safe_func("itemB")
        self.assertEqual(safe2, ["itemB"])


class TestDay01CapstoneHarness(unittest.TestCase):
    """Test cases for the Capstone SystemLifecycleHarness."""

    def test_lifecycle_suite_execution(self) -> None:
        """Verify that the capstone lifecycle integration suite passes all criteria."""
        harness = SystemLifecycleHarness()
        metrics = harness.execute_lifecycle_suite()

        self.assertTrue(metrics["registered_initially"])
        self.assertTrue(metrics["immediate_refcount_success"])
        self.assertTrue(metrics["cycle_delayed_properly"])
        self.assertTrue(metrics["cycle_collected_by_gc"])
        self.assertGreater(metrics["reclaimed_cycle_objects"], 0)
        self.assertTrue(metrics["weakref_registry_empty"])


if __name__ == "__main__":
    unittest.main()
