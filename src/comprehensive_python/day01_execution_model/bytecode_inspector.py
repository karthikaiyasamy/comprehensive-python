"""
Bytecode Inspection and VM Stack Analysis.

This module provides programmatic introspection of CPython bytecode instructions,
allowing engineers to analyze opcode sequences, stack depth, and VM dispatch efficiency.
"""

from __future__ import annotations

import dis
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class InstructionSummary:
    """Structured representation of a disassembled bytecode instruction."""

    opname: str
    opcode: int
    argval: Any
    argrepr: str
    starts_line: int | None
    is_jump_target: bool


def inspect_bytecode(target: Callable[..., Any]) -> list[InstructionSummary]:
    """
    Decompile a Python function or code object into a structured list of instructions.

    Uses the standard library `dis` module to extract opcodes and operands
    evaluated by ceval.c in the CPython runtime.
    """
    instructions: list[InstructionSummary] = []
    for instr in dis.get_instructions(target):
        instructions.append(
            InstructionSummary(
                opname=instr.opname,
                opcode=instr.opcode,
                argval=instr.argval,
                argrepr=instr.argrepr,
                starts_line=instr.starts_line,
                is_jump_target=instr.is_jump_target,
            )
        )
    return instructions


def compare_construction_bytecode() -> dict[str, list[str]]:
    """
    Compare the bytecode instructions generated for different list construction patterns:
    1. Imperative loop with list.append()
    2. List comprehension
    3. Direct list literal
    """
    def via_loop(items: list[int]) -> list[int]:
        out = []
        for x in items:
            out.append(x * 2)
        return out

    def via_comprehension(items: list[int]) -> list[int]:
        return [x * 2 for x in items]

    def via_literal() -> list[int]:
        return [1, 2, 3, 4]

    return {
        "via_loop": [i.opname for i in inspect_bytecode(via_loop)],
        "via_comprehension": [i.opname for i in inspect_bytecode(via_comprehension)],
        "via_literal": [i.opname for i in inspect_bytecode(via_literal)],
    }


def run_demo() -> None:
    """Command-line runnable bytecode inspection demonstration."""
    print("=== Bytecode VM Stack Analysis ===")

    def sample_calculation(x: int, y: int) -> int:
        return (x + y) * 2

    instructions = inspect_bytecode(sample_calculation)
    print(f"Disassembling sample_calculation (Total opcodes: {len(instructions)}):")
    for idx, instr in enumerate(instructions):
        print(f"  [{idx:02d}] {instr.opname:<20} arg={instr.argrepr:<10}")

    print("\nComparing List Construction Paradigms:")
    comparison = compare_construction_bytecode()
    for method, opcodes in comparison.items():
        print(f"  {method:<18}: {len(opcodes)} instructions -> {' -> '.join(opcodes[:6])}...")


if __name__ == "__main__":
    run_demo()

