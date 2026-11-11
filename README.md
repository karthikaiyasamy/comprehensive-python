# Comprehensive Python

A Fast-Track, Systems-Oriented Guide for Professional Engineers.

---

## Overview

Comprehensive Python is a multi-day training curriculum designed for software engineers coming from languages such as C, C++, Java, C#, or Go. 

Rather than teaching generic programming syntax (what is a loop or if-statement), this course focuses on the internal mechanics of CPython, the runtime execution model, memory layout, reference semantics, and idiomatic production patterns.

By the end of this curriculum, you will understand:
1. How CPython compiles, interprets, and executes code at the bytecode and memory level.
2. How memory allocation, reference counting, and garbage collection work under the hood.
3. How to write idiomatic, high-throughput Python using generators, decorators, and modern object models (`dataclass`, `__slots__`).
4. How to leverage static typing (`mypy`), defensive error patterns, and PEP 8 standards.
5. How to handle concurrency (threading, multiprocessing, `asyncio`) and the Global Interpreter Lock (GIL).
6. How to write production-grade test suites with `pytest` and profile runtime bottlenecks.

---

## Curriculum Structure (13 Days)

### Part 1: The Core Mental Model and Memory Mechanics
* **Day 01:** [Execution Model and Memory Architecture](Day_01_Execution_Model_and_Memory.md)
  * CPython architecture, bytecode compilation, execution stack.
  * Variables as names (pointers), object identity (`id()`), reference counting.
  * The `is` vs `==` distinction, small integer and string interning, cyclic garbage collection.
* **Day 02:** [Types, Mutability, and Memory Layout](Day_02_Types_Mutability_and_Memory_Layout.md)
  * Everything is an object: `PyObject` internal struct in C.
  * Primitive equivalents: `int` (arbitrary precision), `float` (IEEE 754), `bool`, `str` (Unicode representations).
  * Mutability vs immutability, in-place modifications, shallow vs deep copying (`copy` module).
* **Day 03:** [Collections, Hash Maps, and Computational Complexity](Day_03_Collections_and_Data_Structures.md)
  * Lists as dynamic contiguous arrays over-allocation strategy.
  * Tuples vs Lists, memory footprints.
  * Dictionaries and Sets: Compact hash tables, hash collisions, open addressing, Big-O lookup mechanics.

### Part 2: Idiomatic Control Flow and Functional Mechanics
* **Day 04:** [Control Flow, Scopes, and Comprehensions](Day_04_Control_Flow_Comprehensions_and_Scopes.md)
  * Structural pattern matching (`match/case`) with guards and destructuring.
  * Variable scope resolution: The LEGB rule (Local, Enclosing, Global, Built-in).
  * List, Dict, and Set comprehensions: Bytecode efficiency and avoiding side effects.
* **Day 05:** [Functions, Closures, and Decorators](Day_05_Functions_Closures_and_Decorators.md)
  * First-class functions, frame objects, stack frames.
  * Argument passing: Pass-by-object-reference, default argument traps (mutable defaults).
  * Closures and cell objects (`__closure__`).
  * Function decorators from scratch, parameterized decorators, preserving metadata (`functools.wraps`).
* **Day 06:** [Iterators, Generators, and Stream Processing](Day_06_Iterators_Generators_and_Data_Streaming.md)
  * The Iteration Protocol: `__iter__` and `__next__`.
  * Generators and the `yield` keyword: Pausing and resuming frame execution.
  * Memory-efficient streaming of gigabyte-scale datasets.
  * Generator expressions, chaining pipelines with `itertools`.

### Part 3: Object-Oriented Design and Modern Standards
* **Day 07:** [Object-Oriented Programming and Dunder Protocols](Day_07_OOP_Dunder_Methods_and_Protocols.md)
  * Class creation, instance initialization (`__init__` vs `__new__`).
  * Dunder methods: String representation (`__repr__` vs `__str__`), arithmetic, comparison, and hashing.
  * The descriptor protocol and properties (`@property`).
  * Multiple inheritance and Method Resolution Order (MRO / C3 Linearization).
* **Day 08:** [Dataclasses, Slots, and Modern Object Design](Day_08_Dataclasses_Slots_and_Modern_Classes.md)
  * Standard boilerplate reduction with `@dataclass`.
  * Memory optimization using `__slots__` (eliminating `__dict__`).
  * Immutability with frozen dataclasses.
  * Structural subtyping with `typing.Protocol` (Duck typing with static checks).
* **Day 09:** [Static Typing, Mypy, and Defensive Code Architecture](Day_09_Type_Hints_Mypy_and_Defensive_Patterns.md)
  * Python Type System: Gradual typing, `mypy`, strict mode.
  * Generics (`TypeVar`, `Generic`), Unions, Optionals, Literals.
  * Exception hierarchies: Built-in exceptions, custom domain exceptions, exception chaining (`from e`).
  * Clean architecture and PEP 8 style standards.

### Part 4: Systems, Concurrency, and Production Tooling
* **Day 10:** [File I/O, Context Managers, and High-Throughput Parsing](Day_10_File_IO_Context_Managers_and_Parsing.md)
  * The Context Management Protocol: `__enter__` and `__exit__`.
  * Implementing custom context managers with `@contextlib.contextmanager`.
  * Binary vs text streams, buffering, memory-mapped files (`mmap`).
  * High-speed CSV, JSON, and structured log parsing.
* **Day 11:** [Concurrency, The GIL, Threading, and Asyncio](Day_11_Concurrency_GIL_Threading_and_Asyncio.md)
  * The Global Interpreter Lock (GIL): Why it exists, when it drops, impact on CPU-bound vs I/O-bound tasks.
  * Threading vs Multiprocessing: `concurrent.futures.ThreadPoolExecutor` vs `ProcessPoolExecutor`.
  * Shared memory and inter-process communication (IPC).
  * Asynchronous programming (`asyncio`): Event loops, coroutines, tasks, non-blocking I/O.
* **Day 12:** [Production Testing with Pytest, Profiling, and Packaging](Day_12_Testing_with_Pytest_Profiling_and_Packaging.md)
  * Automated testing with `pytest`: Fixtures, parametrization, test discovery.
  * Mocking external dependencies (`unittest.mock`).
  * Performance profiling: `cProfile`, line profiler, memory profiler.
  * Modern packaging and environment management (`pyproject.toml`, virtual environments).
* **Day 13:** [High-Throughput Pipelines, Memory Discipline & Production Robustness](Day_13_High_Throughput_Pipelines_and_Production_Robustness.md)
  * Memory discipline: Resident Set Size (RSS), virtual memory, and Linux OOM Killer (exit code 137) mechanics.
  * C-level overhead awareness: `PyObject` internal anatomy, object allocation taxes, instance `__dict__` vs `__slots__`.
  * Deduplication with `sys.intern()` and zero-copy buffer slicing with `memoryview`.
  * Production robustness: Atomic file replacements (`os.replace`), POSIX signal handling (`SIGTERM`/`SIGINT`), and structured logging.
  * Deterministic testing of gigabyte-scale stream parsers using in-memory `pytest` fixtures (`io.StringIO`/`io.BytesIO`).

---

## Pedagogical Design

Every day follows a consistent, structured blueprint:
1. **The Systems Mental Model:** How the concept behaves in CPython and memory.
2. **ASCII Architecture Diagram:** Visual layout of pointers, stack frames, heap objects, or execution flow.
3. **Language Comparison (C++ / Java vs Python):** Contrast with traditional compiled languages.
4. **Runnable Production Code:** Self-contained, realistic code demonstrating the concept.
5. **Common Traps and Pitfalls:** Subtle bugs that catch experienced engineers coming from other languages.
6. **Hands-On Exercise:** A practical engineering challenge with a complete reference solution.

