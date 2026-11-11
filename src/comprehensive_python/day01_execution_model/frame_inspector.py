"""
Frame Object and Execution Stack Introspection.

This module provides utilities to inspect active CPython PyFrameObject instances,
enabling call stack traversal, scope inspection, and execution frame analysis.
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from types import FrameType
from typing import Any, Optional


@dataclass(frozen=True)
class FrameInfo:
    """Snapshot of a CPython execution frame."""

    depth: int
    function_name: str
    filename: str
    line_number: int
    local_keys: tuple[str, ...]


def inspect_call_stack(max_depth: int = 20) -> list[FrameInfo]:
    """
    Traverse the active CPython call stack using f_back pointers.

    Starting from the immediate caller's frame, steps backward until reaching
    the top-level module frame or the specified max_depth limit.
    """
    frames: list[FrameInfo] = []
    
    # Retrieve current frame (sys._getframe is a C-level introspection intrinsic)
    current_frame: Optional[FrameType] = sys._getframe(1)
    depth = 0

    while current_frame is not None and depth < max_depth:
        code = current_frame.f_code
        frames.append(
            FrameInfo(
                depth=depth,
                function_name=code.co_name,
                filename=code.co_filename.split("/")[-1],
                line_number=current_frame.f_lineno,
                local_keys=tuple(sorted(current_frame.f_locals.keys())),
            )
        )
        current_frame = current_frame.f_back
        depth += 1

    return frames


def get_caller_context() -> dict[str, Any]:
    """
    Inspect the calling scope to extract caller name and active local bindings.
    """
    caller_frame = sys._getframe(1)
    return {
        "caller_function": caller_frame.f_code.co_name,
        "caller_locals": dict(caller_frame.f_locals),
        "caller_line": caller_frame.f_lineno,
    }


def run_demo() -> None:
    """Command-line runnable call stack traversal demonstration."""
    print("=== CPython Call Stack Traversal ===")

    def innermost_worker(value: int) -> list[FrameInfo]:
        intermediate = value * 10  # noqa: F841
        return inspect_call_stack()

    def middle_layer(param: str) -> list[FrameInfo]:
        token = f"proc_{param}"  # noqa: F841
        return innermost_worker(42)

    def outer_entry() -> list[FrameInfo]:
        context_flag = True  # noqa: F841
        return middle_layer("telemetry")

    stack = outer_entry()
    print(f"Captured {len(stack)} stack frames:")
    for frame in stack:
        print(
            f"  Level {frame.depth:02d}: {frame.function_name:<20} "
            f"in {frame.filename}:{frame.line_number} "
            f"(locals: {', '.join(frame.local_keys)})"
        )


if __name__ == "__main__":
    run_demo()

