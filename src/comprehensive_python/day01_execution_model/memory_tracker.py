"""
Memory Tracking and Object Lifecycle Utilities.

This module provides tools for inspecting CPython reference counting,
cyclic references, and generational garbage collector mechanics.
"""

from __future__ import annotations

import gc
import sys
from typing import Any, Callable, Optional


class TrackedResource:
    """
    A monitored resource that logs its allocation and deallocation.

    Allows callers to register an optional deallocation callback to deterministically
    verify when CPython reclaims the underlying heap object.
    """

    def __init__(
        self,
        name: str,
        on_dealloc: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self.name = name
        self.on_dealloc = on_dealloc
        self.address = id(self)
        self.partner: Optional[TrackedResource] = None

    def __del__(self) -> None:
        if self.on_dealloc is not None:
            try:
                self.on_dealloc(self.name, self.address)
            except Exception:
                pass

    def __repr__(self) -> str:
        return f"TrackedResource(name={self.name!r}, address={hex(self.address)})"


class ObjectLifecycleTracker:
    """
    Manages and observes object allocation, reference counts, and GC reclamation.
    """

    @staticmethod
    def get_real_ref_count(target: Any) -> int:
        """
        Return the reference count of the target object using sys.getrefcount.

        Systems Nuance (CPython execution stack):
        In traditional CPython bytecode evaluation, passing an object into a function
        adds a temporary reference on the evaluation stack. In modern CPython (3.14+),
        vectorcall and fast-locals stack frame optimizations allow direct borrowed
        references when passing local variables to C-level builtins without inflating
        the refcount.

        When called inside a local function frame, sys.getrefcount(target) precisely
        reflects active strong references (e.g. 1 for an unaliased local variable,
        incrementing by 1 for each alias or container inclusion).
        """
        return sys.getrefcount(target)

    @staticmethod
    def test_integer_interning(value: int) -> bool:
        """
        Check if two dynamically computed integers share the exact memory identity.

        We construct integers dynamically via string parsing to prevent CPython's
        peephole optimizer or AST constant folder from fusing them into identical constants
        at compile time.
        """
        val_a = int(str(value))
        val_b = int(str(value))
        return val_a is val_b

    @staticmethod
    def find_interning_range(start: int = -10, end: int = 300) -> tuple[int, int]:
        """
        Scan a range of integers to detect the lower and upper bounds of CPython's
        pre-allocated small integer cache (typically -5 to 256).
        """
        interned: list[int] = []
        for n in range(start, end + 1):
            if ObjectLifecycleTracker.test_integer_interning(n):
                interned.append(n)
        if not interned:
            return (0, 0)
        return (min(interned), max(interned))

    @staticmethod
    def demonstrate_cyclic_reference() -> dict[str, Any]:
        """
        Create an isolated cyclic reference graph and demonstrate how CPython
        handles reference count vs cyclic garbage collection.

        Returns a dictionary of execution metrics.
        """
        deallocated_names: list[str] = []

        def record_dealloc(name: str, address: int) -> None:
            deallocated_names.append(name)

        # Step 1: Create cyclic pair
        node_a: Optional[TrackedResource] = TrackedResource("node_a", record_dealloc)
        node_b: Optional[TrackedResource] = TrackedResource("node_b", record_dealloc)

        node_a.partner = node_b
        node_b.partner = node_a

        # Both nodes have at least 2 references (local variable + partner reference)
        ref_count_a_initial = ObjectLifecycleTracker.get_real_ref_count(node_a)
        ref_count_b_initial = ObjectLifecycleTracker.get_real_ref_count(node_b)

        # Step 2: Delete external name bindings
        del node_a
        del node_b

        # At this point, the cycle prevents reference count from reaching 0.
        dealloc_before_gc = list(deallocated_names)

        # Step 3: Force cyclic garbage collection
        collected_unreachable = gc.collect()
        dealloc_after_gc = list(deallocated_names)

        return {
            "ref_count_a_initial": ref_count_a_initial,
            "ref_count_b_initial": ref_count_b_initial,
            "deallocated_before_gc": dealloc_before_gc,
            "deallocated_after_gc": dealloc_after_gc,
            "gc_collected_count": collected_unreachable,
        }


def run_demo() -> None:
    """Command-line runnable demonstration of memory mechanics."""
    print("=== CPython Memory and Lifecycle Diagnostics ===")
    
    # 1. Immediate Reference Counting Deallocation
    dealloc_log: list[str] = []
    res = TrackedResource("Buffer_01", lambda name, addr: dealloc_log.append(name))
    print(f"Allocated resource: {res}")
    print(f"Reference count: {ObjectLifecycleTracker.get_real_ref_count(res)}")
    print("Deleting reference...")
    del res
    print(f"Deallocation observed immediately: {'Buffer_01' in dealloc_log}")

    # 2. Integer Interning Range Check
    low, high = ObjectLifecycleTracker.find_interning_range()
    print(f"Detected small integer intern cache: [{low}, {high}]")

    # 3. Cyclic Garbage Collection
    print("Demonstrating cyclic reference collection...")
    metrics = ObjectLifecycleTracker.demonstrate_cyclic_reference()
    print(f"Deallocations before gc.collect(): {metrics['deallocated_before_gc']}")
    print(f"Deallocations after gc.collect(): {metrics['deallocated_after_gc']}")
    print(f"Total unreachable objects cleared: {metrics['gc_collected_count']}")


if __name__ == "__main__":
    run_demo()
