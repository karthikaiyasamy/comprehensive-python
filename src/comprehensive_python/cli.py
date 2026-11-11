"""
Comprehensive Python Command-Line Interface.

Allows running systems demonstrations, lab benchmarks, and verification
routines across the 13-day curriculum.
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from comprehensive_python.day01_execution_model import (
    bytecode_inspector,
    frame_inspector,
    lifecycle_harness,
    memory_tracker,
    reference_traps,
    weakref_cache,
)
from comprehensive_python.day02_types_mutability import snapshot


def run_day01() -> None:
    """Execute all Day 01 demonstrations."""
    print("=" * 60)
    print("DAY 01: EXECUTION MODEL AND MEMORY ARCHITECTURE")
    print("=" * 60)
    memory_tracker.run_demo()
    print("-" * 60)
    bytecode_inspector.run_demo()
    print("-" * 60)
    frame_inspector.run_demo()
    print("-" * 60)
    weakref_cache.run_demo()
    print("-" * 60)
    reference_traps.run_demo()
    print("-" * 60)
    lifecycle_harness.run_demo()


def run_day02() -> None:
    """Execute Day 02 demonstrations."""
    print("=" * 60)
    print("DAY 02: TYPES, MUTABILITY, AND MEMORY LAYOUT")
    print("=" * 60)
    snapshot.run_demo()


DISPATCH_TABLE: dict[int, tuple[str, Callable[[], None]]] = {
    1: ("Execution Model and Memory Architecture", run_day01),
    2: ("Types, Mutability, and Memory Layout", run_day02),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python-lab",
        description="Comprehensive Python: Systems-Oriented Practice Runner.",
    )
    parser.add_argument(
        "--day",
        "-d",
        type=int,
        choices=range(1, 14),
        help="Specify the curriculum day to run (1 to 13).",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Run demonstrations across all available modules.",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all implemented curriculum lab modules.",
    )

    args = parser.parse_args()

    if args.list:
        print("Available Curriculum Lab Modules:")
        for day, (title, _) in sorted(DISPATCH_TABLE.items()):
            print(f"  Day {day:02d}: {title}")
        return 0

    if args.day:
        if args.day in DISPATCH_TABLE:
            _, runner = DISPATCH_TABLE[args.day]
            runner()
            return 0
        else:
            print(f"Lab implementations for Day {args.day:02d} are pending.")
            return 1

    if args.all:
        for day, (_, runner) in sorted(DISPATCH_TABLE.items()):
            runner()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
