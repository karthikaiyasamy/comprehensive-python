"""
Reference Pitfalls and Shared Mutable State Diagnostics.

This module provides diagnostic utilities to demonstrate and prevent the two most
frequent reference pitfalls encountered when transitioning to CPython:
1. Multiplying containers containing mutable elements ([[0] * 3] * 3).
2. Mutable default arguments stored in PyFunctionObject.__defaults__.
"""

from __future__ import annotations

from typing import Any, Callable, Optional


def demonstrate_multiplied_list_trap() -> dict[str, Any]:
    """
    Demonstrate how list multiplication creates shallow reference duplicates.

    When executing `[[0] * 3] * 3`, Python allocates ONE inner list [0, 0, 0]
    and populates the outer list with three pointers to that identical memory address.
    """
    trapped_matrix = [[0] * 3] * 3
    addresses = [id(row) for row in trapped_matrix]

    # Mutating row 0 mutates all rows because they point to the same PyListObject
    trapped_matrix[0][0] = 99
    all_rows_affected = all(row[0] == 99 for row in trapped_matrix)

    # Safe idiom: Independent list comprehension allocations
    safe_matrix = [[0] * 3 for _ in range(3)]
    safe_matrix[0][0] = 99
    only_first_row_affected = safe_matrix[0][0] == 99 and safe_matrix[1][0] == 0

    return {
        "shared_inner_addresses": addresses[0] == addresses[1] == addresses[2],
        "all_rows_affected_in_trap": all_rows_affected,
        "only_first_row_affected_in_safe": only_first_row_affected,
        "trapped_matrix": trapped_matrix,
        "safe_matrix": safe_matrix,
    }


def demonstrate_mutable_default_trap() -> tuple[Callable[..., list[Any]], Callable[..., list[Any]]]:
    """
    Demonstrate that default parameter expressions are evaluated once at function definition time,
    storing mutable objects in the PyFunctionObject's __defaults__ tuple on the heap.
    """

    def buggy_accumulator(item: Any, target: list[Any] = []) -> list[Any]:
        target.append(item)
        return target

    def safe_accumulator(item: Any, target: Optional[list[Any]] = None) -> list[Any]:
        if target is None:
            target = []
        target.append(item)
        return target

    return buggy_accumulator, safe_accumulator


def inspect_function_defaults(func: Callable[..., Any]) -> tuple[Any, ...]:
    """
    Directly inspect the __defaults__ attribute of a PyFunctionObject heap struct.
    """
    return func.__defaults__ or ()


def run_demo() -> None:
    """Command-line runnable demonstration of reference traps."""
    print("=== Reference Pitfalls and Shared Mutable State ===")

    # 1. Multiplied List Diagnostic
    results = demonstrate_multiplied_list_trap()
    print("Trap 1: Container Multiplication ([[0] * 3] * 3)")
    print(f"  All rows share identical pointer: {results['shared_inner_addresses']}")
    print(f"  Mutating matrix[0][0] affected all rows: {results['all_rows_affected_in_trap']}")
    print(f"  Comprehension matrix protected: {results['only_first_row_affected_in_safe']}")

    # 2. Mutable Default Argument Diagnostic
    print("\nTrap 2: Mutable Default Argument (func.__defaults__)")
    buggy_func, safe_func = demonstrate_mutable_default_trap()

    print(f"  Initial __defaults__: {inspect_function_defaults(buggy_func)}")
    buggy_func("event_1")
    print(f"  After 1st invocation: {inspect_function_defaults(buggy_func)}")
    buggy_func("event_2")
    print(f"  After 2nd invocation: {inspect_function_defaults(buggy_func)}")

    safe_1 = safe_func("event_1")
    safe_2 = safe_func("event_2")
    print(f"  Safe accumulator calls isolated: {safe_1 == ['event_1']} and {safe_2 == ['event_2']}")


if __name__ == "__main__":
    run_demo()

