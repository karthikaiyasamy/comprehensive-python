"""
Day 02: Types, Mutability, and Memory Layout.

Modules:
- snapshot: Deep copy isolation and safe state snapshotting for concurrent pipelines.
"""

from .snapshot import ConfigNode, inspect_object_header, snapshot_state

__all__ = ["ConfigNode", "inspect_object_header", "snapshot_state"]

