"""
Day 01: Execution Model and Memory Architecture.

Modules:
- memory_tracker: Reference counting and cyclic garbage collection tracking.
- bytecode_inspector: Bytecode disassembly and stack evaluation analysis.
- frame_inspector: Call stack navigation and frame object inspection.
- weakref_cache: Weak reference lifetime management and non-retaining caches.
- reference_traps: Mutable default arguments and shared mutable state traps.
"""

from .bytecode_inspector import inspect_bytecode
from .frame_inspector import inspect_call_stack
from .memory_tracker import ObjectLifecycleTracker, TrackedResource
from .reference_traps import (
    demonstrate_multiplied_list_trap,
    demonstrate_mutable_default_trap,
    inspect_function_defaults,
)
from .weakref_cache import ExpiringWeakCache

__all__ = [
    "ObjectLifecycleTracker",
    "TrackedResource",
    "inspect_bytecode",
    "inspect_call_stack",
    "ExpiringWeakCache",
    "demonstrate_multiplied_list_trap",
    "demonstrate_mutable_default_trap",
    "inspect_function_defaults",
]
