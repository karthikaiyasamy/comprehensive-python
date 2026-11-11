"""
Unit tests for Day 02: Types, Mutability, and Memory Layout.
"""

from __future__ import annotations

import unittest

from comprehensive_python.day02_types_mutability import (
    ConfigNode,
    inspect_object_header,
    snapshot_state,
)


class TestDay02Snapshot(unittest.TestCase):
    """Test cases for state isolation, deep snapshots, and object headers."""

    def test_snapshot_type_validation(self) -> None:
        """Verify TypeError is raised when input is not a dict."""
        with self.assertRaises(TypeError):
            # Pass a list instead of dict
            snapshot_state([1, 2, 3])  # type: ignore[arg-type]

    def test_snapshot_deep_isolation(self) -> None:
        """Verify nested structures and custom objects are isolated from source mutation."""
        initial_state = {
            "version": 1,
            "hosts": ["node-01", "node-02"],
            "config": ConfigNode("cluster", "primary"),
        }

        snapshot = snapshot_state(initial_state)

        # Mutate initial state
        initial_state["version"] = 2
        initial_state["hosts"].append("node-03")
        initial_state["config"].value = "corrupted"

        # Verify snapshot retained original values
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["hosts"], ["node-01", "node-02"])
        self.assertEqual(snapshot["config"].value, "primary")

    def test_circular_reference_handled(self) -> None:
        """Verify that deepcopy resolves circular object graphs without recursion errors."""
        node_a = ConfigNode("A", 100)
        node_b = ConfigNode("B", 200)
        node_a.parent = node_b
        node_b.parent = node_a

        state = {"root": node_a}
        snapshot = snapshot_state(state)

        self.assertIsNot(snapshot["root"], node_a)
        self.assertEqual(snapshot["root"].key, "A")
        self.assertEqual(snapshot["root"].parent.key, "B")

    def test_inspect_object_header(self) -> None:
        """Verify object header metadata reporting."""
        target = [1, 2, 3]
        header = inspect_object_header(target)

        self.assertEqual(header["type"], "list")
        self.assertGreater(header["size_bytes"], 0)
        self.assertTrue(header["address"].startswith("0x"))


if __name__ == "__main__":
    unittest.main()

