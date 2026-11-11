"""
Safe State Snapshotting and Object Header Diagnostics.

This module provides tools for safe deep snapshotting of state dictionaries,
preventing mutation leakage across thread or task boundaries, and inspecting
CPython object header overheads.
"""

from __future__ import annotations

import copy
import sys
from typing import Any, Optional


class ConfigNode:
    """Represents a stateful configuration node within an execution graph."""

    def __init__(self, key: str, value: Any, parent: Optional[ConfigNode] = None) -> None:
        self.key = key
        self.value = value
        self.parent = parent

    def __repr__(self) -> str:
        return f"ConfigNode({self.key!r}={self.value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ConfigNode):
            return False
        return self.key == other.key and self.value == other.value


def snapshot_state(state: dict[str, Any]) -> dict[str, Any]:
    """
    Create an isolated, deep copy of a state dictionary.

    Ensures that modifications to nested containers, lists, or custom class instances
    in the source state do not leak into downstream processing pipelines.

    Raises:
        TypeError: If state is not an instance of dict.
    """
    if not isinstance(state, dict):
        raise TypeError(f"Expected dict, got {type(state).__name__}")

    # copy.deepcopy handles full graph traversal with memoization of visited IDs,
    # preventing infinite recursion on cyclic structures while isolating object pointers.
    return copy.deepcopy(state)


def inspect_object_header(obj: Any) -> dict[str, Any]:
    """
    Inspect CPython object metadata and memory footprint.

    Returns:
        Dictionary containing memory address, type name, sys.getsizeof allocation,
        and current reference count.
    """
    return {
        "address": hex(id(obj)),
        "type": type(obj).__name__,
        "size_bytes": sys.getsizeof(obj),
        "ref_count": sys.getrefcount(obj) - 1,
    }


def demonstrate_shallow_vs_deep() -> dict[str, bool]:
    """
    Demonstrate mutation leakage in shallow copies compared to complete isolation
    in deep copies.
    """
    original: dict[str, Any] = {
        "scalar": 100,
        "nested_list": [1, 2, 3],
        "node": ConfigNode("alpha", "10.0.0.1"),
    }

    shallow = original.copy()
    deep = snapshot_state(original)

    # Mutate nested elements in original
    original["nested_list"].append(999)
    original["node"].value = "MUTATED"

    # In shallow copy, nested mutable objects are shared pointers
    shallow_leaked_list = shallow["nested_list"] == [1, 2, 3, 999]
    shallow_leaked_node = shallow["node"].value == "MUTATED"

    # In deep copy, nested objects were independently replicated
    deep_isolated_list = deep["nested_list"] == [1, 2, 3]
    deep_isolated_node = deep["node"].value == "10.0.0.1"

    return {
        "shallow_leaked_list": shallow_leaked_list,
        "shallow_leaked_node": shallow_leaked_node,
        "deep_isolated_list": deep_isolated_list,
        "deep_isolated_node": deep_isolated_node,
    }


def run_demo() -> None:
    """Command-line runnable demonstration of memory layout and snapshot safety."""
    print("=== State Snapshotting and Object Header Diagnostics ===")

    sample_dict = {"status": "ACTIVE", "workers": [1, 2, 3]}
    header = inspect_object_header(sample_dict)
    print("Object header inspection for dictionary:")
    for k, v in header.items():
        print(f"  {k:<12}: {v}")

    print("\nEvaluating Shallow vs Deep Snapshot isolation:")
    results = demonstrate_shallow_vs_deep()
    for check, passed in results.items():
        print(f"  {check:<25}: {passed}")


if __name__ == "__main__":
    run_demo()
