"""
Unified Lifecycle, Frame, and Weakref Diagnostic Harness.

This module implements the Capstone Systems Challenge for Day 01, integrating
deterministic reference-count destruction, allocation provenance logging via
frame introspection, circular reference detection, and non-retaining weak caching.
"""

from __future__ import annotations

import gc
import inspect
import sys
import weakref
from typing import Any, Callable, Optional


class TrackedResource:
    """
    A monitored resource that logs allocation provenance via frame introspection
    and executes a deterministic deallocation callback upon reclamation.
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

        # Systems Nuance: Inspect caller frame without creating persistent frame cycles.
        # Holding a frame reference in local scope creates a reference cycle between
        # the frame and its f_locals, preventing deterministic deallocation.
        # We extract metadata immediately and delete the frame reference in a finally block.
        frame = sys._getframe(1)
        try:
            self.allocated_at = f"{frame.f_code.co_name}:{frame.f_lineno}"
        finally:
            del frame

    def __del__(self) -> None:
        if self.on_dealloc is not None:
            try:
                self.on_dealloc(self.name, self.address)
            except Exception:
                pass

    def __repr__(self) -> str:
        return f"TrackedResource({self.name!r}, addr={hex(self.address)}, origin={self.allocated_at})"


class SystemLifecycleHarness:
    """Diagnostic harness testing reference counting, cycles, and weakref caching."""

    def __init__(self) -> None:
        self.dealloc_events: list[str] = []
        self.registry: weakref.WeakValueDictionary[str, TrackedResource] = (
            weakref.WeakValueDictionary()
        )

    def _record_dealloc(self, name: str, addr: int) -> None:
        self.dealloc_events.append(name)

    def allocate(self, name: str) -> TrackedResource:
        """Allocate a tracked resource and register it in the non-retaining cache."""
        resource = TrackedResource(name, on_dealloc=self._record_dealloc)
        self.registry[name] = resource
        return resource

    def execute_lifecycle_suite(self) -> dict[str, Any]:
        """Execute full integration verification of Day 01 memory mechanics."""
        gc.collect()

        # Step 1: Immediate refcount destruction
        res1: Optional[TrackedResource] = self.allocate("Resource_Alpha")
        registered_initially = "Resource_Alpha" in self.registry
        del res1
        immediate_success = "Resource_Alpha" in self.dealloc_events

        # Step 2: Cyclic reference retention
        res_a: Optional[TrackedResource] = self.allocate("Node_A")
        res_b: Optional[TrackedResource] = self.allocate("Node_B")
        res_a.partner = res_b
        res_b.partner = res_a

        del res_a
        del res_b

        cycle_delayed = (
            "Node_A" not in self.dealloc_events and "Node_B" not in self.dealloc_events
        )

        # Step 3: Forcing GC collection of cycles
        reclaimed_cycles = gc.collect()
        cycle_collected = (
            "Node_A" in self.dealloc_events and "Node_B" in self.dealloc_events
        )

        return {
            "registered_initially": registered_initially,
            "immediate_refcount_success": immediate_success,
            "cycle_delayed_properly": cycle_delayed,
            "cycle_collected_by_gc": cycle_collected,
            "reclaimed_cycle_objects": reclaimed_cycles,
            "weakref_registry_empty": len(self.registry) == 0,
        }


def run_demo() -> None:
    """Command-line runnable capstone harness demonstration."""
    print("=== Day 01 Capstone Verification Results ===")
    harness = SystemLifecycleHarness()
    results = harness.execute_lifecycle_suite()
    for metric, status in results.items():
        print(f"  {metric:<30}: {status}")


if __name__ == "__main__":
    run_demo()
