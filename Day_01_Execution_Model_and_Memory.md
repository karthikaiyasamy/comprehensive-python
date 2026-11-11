# Day 01: Execution Model and Memory Architecture

---

## 1. The Systems Mental Model: How Python Runs Code

Engineers coming from C++ or Java often ask: *Is Python compiled or interpreted?*

The precise answer is: **Python is compiled to bytecode, which is then interpreted by a stack-based virtual machine (CPython).**

```text
 [Source Code: app.py]
          │
          ▼  Compilation Phase (AST Parsing & Symbol Table)
 [Bytecode: app.cpython-314.pyc] (Platform-independent bytecode instructions)
          │
          ▼  Execution Phase (Virtual Machine)
 [CPython VM: ceval.c] (C loop executing opcodes against evaluation stack)
          │
          ▼  System Interaction
 [Host CPU & OS Kernel] (RAM, Registers, System Calls)
```

### The Compilation Step
When you run `python app.py`:
1. **Lexing & Parsing:** Python parses the source code into an Abstract Syntax Tree (AST).
2. **Bytecode Generation:** The compiler translates the AST into a sequence of bytecode instructions (`PyCodeObject`).
3. **Caching:** If imported as a module, CPython serializes this bytecode into the `__pycache__/` directory with a `.pyc` extension, tagged with the Python version and timestamp.

### The Virtual Machine Evaluation Loop
CPython is implemented in C. At its heart lies `Python/ceval.c`, an evaluation loop (historically a massive `switch` statement, now heavily optimized with computed gotos and adaptive specialization in modern Python 3.11+).

The CPython VM is a **stack machine** (similar to the JVM). It does not use CPU registers directly for intermediate arithmetic; it pushes and pops object pointers onto a thread-local value stack.

---

## 2. Bytecode Disassembly and the VM Evaluation Stack

To inspect the instructions executed by the CPython virtual machine, use the standard library `dis` (disassembler) module.

```python
import dis

def calculate(a: int, b: int) -> int:
    result = a + b * 2
    return result

dis.dis(calculate)
```

### Output Analysis (CPython Bytecode)
```text
  4           0 RESUME                   0

  5           2 LOAD_FAST                0 (a)
              4 LOAD_FAST                1 (b)
              6 LOAD_CONST               1 (2)
              8 BINARY_OP                5 (*)
             12 BINARY_OP                0 (+)
             16 STORE_FAST               2 (result)

  6          18 LOAD_FAST                2 (result)
             20 RETURN_VALUE
```

### Execution Flow on the Stack
1. `LOAD_FAST 0 (a)`: Pushes a pointer to object `a` onto the evaluation stack.
2. `LOAD_FAST 1 (b)`: Pushes a pointer to object `b` onto the evaluation stack.
3. `LOAD_CONST 1 (2)`: Pushes a pointer to the integer constant `2` onto the stack.
4. `BINARY_OP 5 (*)`: Pops `2` and `b`, invokes the C-level multiplication slot (`nb_multiply`), pushes the result pointer.
5. `BINARY_OP 0 (+)`: Pops the product and `a`, invokes addition (`nb_add`), pushes the sum pointer.
6. `STORE_FAST 2 (result)`: Pops the sum pointer and stores it in the local fast-variable array slot for `result`.
7. `RETURN_VALUE`: Pops the top of stack and passes the pointer to the caller frame.

Modern CPython (3.11 to 3.14) adds an **adaptive specializing interpreter**: hot bytecode instructions are rewritten at runtime into specialized opcodes (e.g. `LOAD_FAST_BORROW_LOAD_FAST_BORROW` or `BINARY_OP_MULTIPLY_INT`) to bypass generic type dispatch overhead.

---

## 3. Variables as Names (Pointers), Not Memory Boxes

This is the fundamental mental model difference between Python and C/C++/Java:

* **In C++ or Java:** A variable is a named, typed memory location (a box). Assigning a value copies raw bits into that box.
* **In Python:** A variable is merely a **name tag (pointer)** bound to an object living in the heap.

```text
C++ Model (Typed Memory Boxes):
  int a = 10;          [ Memory Address: 0x7fff01 ] -> Contains raw 32-bit int: 10
  int b = a;           [ Memory Address: 0x7fff05 ] -> Contains raw 32-bit int: 10 (Copied bits)

Python Model (Names Pointing to Heap Objects):
  a = 10
  b = a

       Names (Stack/Namespace)                 Heap Object (PyObject)
      ┌──────────┐                            ┌────────────────────────┐
      │    a     │───────────────────────────>│ ob_refcnt: 2           │
      └──────────┘                            │ ob_type:   &PyLong_Type│
                                              │ ob_digit:  10          │
      ┌──────────┐                            └────────────────────────┘
      │    b     │───────────────────────────>            ▲
      └──────────┘                                        │
           │                                              │
           └──────────────────────────────────────────────┘
```

When executing `b = a`, Python **never copies the underlying data**. It increments the object's reference counter and binds the name `b` to the identical heap address.

---

## 4. Object Identity: Memory Addresses, `id()`, `is`, and `==`

Every object in Python possesses:
1. **An Identity:** The physical memory address of the C struct (`id(obj)`).
2. **A Type:** Defines valid operations and internal memory layout (`type(obj)`).
3. **A Value:** The payload data encapsulated in the object.

### The Strict Distinction Between `is` and `==`

| Operator | Comparison Type | Equivalent in C / Java | What it Checks |
| :--- | :--- | :--- | :--- |
| `a is b` | Identity | `a == b` (pointer comparison) | `id(a) == id(b)` (Same physical memory address) |
| `a == b` | Value Equality | `a.equals(b)` / overloaded `==` | `a.__eq__(b)` (Equivalent value contents) |

```python
# Two distinct list objects with identical contents
list_one = [1, 2, 3]
list_two = [1, 2, 3]

print(list_one == list_two)  # True: Values are identical
print(list_one is list_two)  # False: Distinct heap objects

print(f"id(list_one): {hex(id(list_one))}")
print(f"id(list_two): {hex(id(list_two))}")

# Aliasing (binding a second name to the same object)
list_three = list_one
print(list_one is list_three)  # True: Exact same memory address
```

---

## 5. Memory Management: Reference Counting and Cyclic Garbage Collection

CPython manages heap memory through a dual-engine architecture:
1. **Primary Engine:** Reference Counting (Immediate, deterministic deallocation).
2. **Secondary Engine:** Generational Cyclic Garbage Collector (Detects isolated reference cycles).

### Engine 1: Reference Counting
Every `PyObject` header contains `ob_refcnt`.
* When a name is bound, passed to a function, or stored in a container: `ob_refcnt += 1`.
* When a name goes out of scope, is reassigned, or deleted with `del`: `ob_refcnt -= 1`.
* **The moment `ob_refcnt == 0`:** The memory is immediately freed back to Python's small object allocator (`pymalloc`).

```python
import sys

x = [10, 20, 30]
# sys.getrefcount() takes x as a parameter
print(sys.getrefcount(x))  # Typically 2 (variable x + function argument)

y = x
print(sys.getrefcount(x))  # Prints 3 (x, y + function argument)

del y
print(sys.getrefcount(x))  # Prints 2 (y reference released)
```

### Engine 2: The Generational Garbage Collector (Cycle Detector)
Reference counting alone has one fatal flaw: **Circular References**.

```text
  Node A (refcnt: 1) ─────────── points to ───────────> Node B (refcnt: 1)
         ▲                                                     │
         │                                                     │
         └────────────────────── points to ────────────────────┘
```

If the external variables pointing to `Node A` and `Node B` are deleted, their internal cross-references keep `ob_refcnt = 1`. Reference counting alone will never reclaim them.

To solve this, CPython runs a **Generational Garbage Collector** (`gc` module) that tracks container objects (lists, dictionaries, classes, tuples) across 3 generations:
* **Generation 0:** Young, newly allocated containers. Inspected frequently.
* **Generation 1:** Objects that survived Gen 0 collection.
* **Generation 2:** Long-lived objects that survived Gen 1. Inspected least frequently.

The GC periodically executes cycle-detection by creating trial reference counts, decrementing references between tracked containers, and collecting unreachable cyclic clusters.

```python
import gc

class Node:
    def __init__(self, name: str):
        self.name = name
        self.partner = None

node_a = Node("A")
node_b = Node("B")
node_a.partner = node_b
node_b.partner = node_a

# Drop external name bindings
del node_a
del node_b

# Objects remain in memory until cyclic GC executes
collected = gc.collect()
print(f"Cyclic objects collected: {collected}")
```

---

## 6. CPython Optimizations: Small Integer and String Interning

CPython utilizes memory-saving optimizations that every systems engineer must understand to avoid subtle identity bugs.

### 1. Small Integer Caching (`[-5, 256]`)
During interpreter initialization, CPython allocates an internal array of 262 integer objects covering the range `-5` to `256`. Any time integer computation or parsing yields a value in this range, CPython returns a reference to the existing singleton.

```python
# Values inside the pre-allocated cache share identity
val_a = int(str(250))
val_b = int(str(250))
print(val_a is val_b)  # True: Points to the global singleton

# Values outside the cache allocate distinct heap objects
val_x = int(str(1000))
val_y = int(str(1000))
print(val_x is val_y)  # False: Distinct heap objects
print(val_x == val_y)  # True: Equivalent values
```

*Rule: Never rely on `is` for integer value comparison. Always use `==`.*

### 2. String Interning
CPython automatically interns string literals matching identifier syntax (alphanumerics and underscores) and dictionary keys. Interned strings share the identical memory address, converting string comparisons in dictionary lookups from an $O(N)$ character comparison (`memcmp`) into an instantaneous $O(1)$ pointer comparison.

You can explicitly intern runtime strings using `sys.intern(s)` when parsing millions of repetitive tokens (e.g. genomic chromosome names or HTTP headers).

---

## 7. The Frame Object and Call Stack (`PyFrameObject`)

Every function call in CPython creates a **frame object** (`PyFrameObject` in C). A frame encapsulates local variables, the bytecode being evaluated, and a pointer to the caller frame.

### C-Level Frame Attributes

| Attribute | C Struct Member | Description |
| :--- | :--- | :--- |
| `f_code` | `PyCodeObject*` | The compiled bytecode, argument names, and constants |
| `f_locals` | `PyObject*` (dict/array) | Fast-locals array or dict of local variable bindings |
| `f_globals` | `PyDictObject*` | Module-level global namespace dictionary |
| `f_back` | `PyFrameObject*` | Pointer to the calling parent frame (`None` at top level) |
| `f_lineno` | `int` | Current source line number being executed |

### ASCII Diagram: Call Stack Execution Flow

```text
  CPython Evaluation Loop (ceval.c)
  ┌─────────────────────────────────┐
  │  <module> Frame                 │  <-- Bottom of stack
  │  f_locals: {x: 10}              │
  │  f_back: None                   │
  └────────────────┬────────────────┘
                   │ calls outer()
  ┌────────────────▼────────────────┐
  │  outer() Frame                  │
  │  f_locals: {y: 20}              │
  │  f_back: <module> Frame         │
  └────────────────┬────────────────┘
                   │ calls inner()
  ┌────────────────▼────────────────┐
  │  inner() Frame                  │  <-- Top of stack (currently active)
  │  f_locals: {z: 30}              │
  │  f_back: outer() Frame          │
  └─────────────────────────────────┘
```

### Inspecting Frames Programmatically

```python
import inspect

def inner():
    frame = inspect.currentframe()
    if frame is not None:
        print(f"Active function: {frame.f_code.co_name}")
        print(f"Caller function: {frame.f_back.f_code.co_name}")
        print(f"Locals:          {list(frame.f_locals.keys())}")

def outer():
    token = "session_token"  # noqa: F841
    inner()

outer()
```

> **Memory Warning:** Holding long-lived references to frame objects (such as in exception tracebacks or logging structures) keeps all local variables alive on the heap. Always drop frame references after inspection: `del frame`.

---

## 8. The Global Interpreter Lock (GIL) and Concurrency Boundaries

The **Global Interpreter Lock (GIL)** is a mutual exclusion lock inside CPython designed to protect the interpreter's internal state.

### Why the GIL Exists
CPython manages memory via reference counting (`ob_refcnt`). Modifying reference counters concurrently across multiple OS threads without synchronization causes race conditions and memory corruption.

Rather than adding fine-grained, high-overhead atomic locks to every individual `PyObject`, CPython uses a single global mutex: **only one OS thread can execute Python bytecode at any physical instant**.

```text
  Timeline: Two Threads Contending for the GIL
  Thread 1: [== Bytecode Evaluation ==][   Waiting for GIL   ][== Bytecode Evaluation ==]
                                       │                      │
  GIL:      [ Held by Thread 1        ][ Held by Thread 2    ][ Held by Thread 1        ]
                                       │                      │
  Thread 2: [   Waiting for GIL       ][== Bytecode Eval ==  ][   Waiting for GIL       ]
```

### Practical Concurrency Characteristics

| Workload Type | Multi-Threading (`threading`) | Multi-Processing (`multiprocessing`) |
| :--- | :--- | :--- |
| **CPU-Bound** (Math, parsing, compression) | **No speedup** (GIL serializes execution) | **True Parallelism** (Each process has separate heap & GIL) |
| **I/O-Bound** (Network, disk, DB queries) | **Effective** (GIL is dropped during system calls) | Higher memory overhead, but functional |

The GIL is automatically released during:
* Blocking OS system calls (file reads/writes, network socket operations).
* `time.sleep()`.
* C-extension operations explicitly calling `Py_BEGIN_ALLOW_THREADS` (e.g. NumPy matrix operations).

### Free-Threading (PEP 703 / Python 3.13+)
Python 3.13 introduced experimental free-threaded builds (`python3.13t` / `--disable-gil`), replacing the GIL with mimalloc-based thread-safe allocation and biased reference counting. In standard production environments, the GIL remains the default.

---

## 9. Non-Retaining References: `weakref` and Weak Caches

A **weak reference** points to a target object without incrementing its `ob_refcnt`. If all strong references to the object are dropped, CPython reclaims the object immediately, regardless of active weak references.

### ASCII Diagram: Strong vs Weak Reference Mechanics

```text
  Strong Reference:
  ┌──────────┐  ob_refcnt += 1  ┌──────────────┐
  │  name    │ ───────────────> │   Object     │  (Remains alive)
  └──────────┘                  └──────────────┘

  Weak Reference:
  ┌──────────┐  ob_refcnt is 0  ┌──────────────┐
  │  weakref │ ───────────────> │   Object     │  (Collected by GC)
  └──────────┘                  └──────────────┘
                                       ▲
                            GC reclaims object memory
                            when strong references reach 0
```

### `weakref.WeakValueDictionary` for Automatic Eviction
In caching systems, storing strong references causes memory leaks because cached objects never reach refcount 0. `WeakValueDictionary` solves this by automatically evicting keys as soon as external owners drop their strong references.

```python
import gc
import weakref

class CacheItem:
    def __init__(self, key: str, payload: str):
        self.key = key
        self.payload = payload

cache = weakref.WeakValueDictionary()

item1 = CacheItem("config_a", "payload_data")
cache["a"] = item1

print("Cached keys:", list(cache.keys()))  # ['a']

# Drop the only strong reference
del item1
gc.collect()

print("Cached keys after del:", list(cache.keys()))  # [] - Evicted automatically
```

### The CPython Header Nuance: Built-ins vs User Classes
Why does `weakref.ref([1, 2, 3])` fail with `TypeError: cannot create weak reference to 'list' object`?

In CPython, supporting weak references requires an extra 8-byte pointer (`tp_weaklistoffset`) in the object's C header struct. To keep basic containers lightweight, CPython omits this slot from built-in types (`list`, `dict`, `int`, `tuple`). User-defined classes include `__weakref__` by default unless explicitly disabled with `__slots__`.

---

## 10. Common Systems Traps and Pitfalls

### Pitfall 1: Container Multiplication Creates Shared Pointers
```python
# Pitfall: Multiplying a list containing a mutable list
matrix = [[0] * 3] * 3

# Appears to be a 3x3 grid: [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
matrix[0][0] = 99

# BUG: All 3 rows point to the exact same inner list in heap!
# Result: [[99, 0, 0], [99, 0, 0], [99, 0, 0]]
print(matrix)

# FIX: Allocate distinct row objects using a comprehension
clean_matrix = [[0] * 3 for _ in range(3)]
clean_matrix[0][0] = 99
# Result: [[99, 0, 0], [0, 0, 0], [0, 0, 0]]
print(clean_matrix)
```

### Pitfall 2: Mutable Default Arguments Bound to `__defaults__`
In Python, default arguments are evaluated **once at function definition time**, not at invocation time. The default object is stored directly in the `PyFunctionObject.__defaults__` tuple on the heap.

```python
# BUG: Mutable default is shared across every call to the function
def append_log(event: str, log_buffer: list = []) -> list:
    log_buffer.append(event)
    return log_buffer

print(append_log("event_1"))  # ['event_1']
print(append_log("event_2"))  # ['event_1', 'event_2'] - State leaked!

# FIX: Use None as default sentinel and allocate inside the call frame
def safe_append_log(event: str, log_buffer: list | None = None) -> list:
    if log_buffer is None:
        log_buffer = []
    log_buffer.append(event)
    return log_buffer
```

### Pitfall 3: Premature Use of `is` for Value Equality
```python
status = get_http_status()

# BAD: Undefined behavior. Small integers [-5, 256] pass by coincidence,
# but larger integers fail. Triggers SyntaxWarning in Python 3.8+.
if status is 200:
    pass

# CORRECT: Value equality
if status == 200:
    pass

# EXCEPTION: Use 'is' strictly for singletons:
if status is None:
    pass
```

---

## 11. Capstone Hands-On Systems Challenge: Unified Lifecycle, Frame & Weakref Tracker

### The Problem
Implement a production-grade diagnostic subsystem that synthesizes Day 01 concepts:
1. **Allocation & Deallocation Tracking:** Tracks deterministic `__del__` reclamation.
2. **Provenance Call Site Logging:** Traverses `f_back` frame pointers to capture the exact file and line number where each resource was allocated.
3. **Circular Reference Diagnosis:** Constructs an isolated cross-referenced graph and verifies that immediate deallocation is blocked until `gc.collect()` runs.
4. **Non-Retaining Weak Cache:** Maintains an active registry of resources that automatically evaporates as caller scopes release strong references.

### Complete Runnable Reference Implementation

```python
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
        # Holding a frame reference creates a reference cycle with the frame f_locals,
        # which would delay deterministic reclamation. Always clean up frame references.
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
        resource = TrackedResource(name, on_dealloc=self._record_dealloc)
        self.registry[name] = resource
        return resource

    def execute_lifecycle_suite(self) -> dict[str, Any]:
        gc.collect()

        # Step 1: Immediate refcount destruction
        res1 = self.allocate("Resource_Alpha")
        self.assert_in_registry("Resource_Alpha")
        del res1
        immediate_success = "Resource_Alpha" in self.dealloc_events

        # Step 2: Cyclic reference retention
        res_a = self.allocate("Node_A")
        res_b = self.allocate("Node_B")
        res_a.partner = res_b
        res_b.partner = res_a

        del res_a
        del res_b

        # Cycle holds objects in memory; immediate destruction must not occur
        cycle_delayed = (
            "Node_A" not in self.dealloc_events and "Node_B" not in self.dealloc_events
        )

        # Step 3: Forcing GC collection
        reclaimed_cycles = gc.collect()
        cycle_collected = (
            "Node_A" in self.dealloc_events and "Node_B" in self.dealloc_events
        )

        return {
            "immediate_refcount_success": immediate_success,
            "cycle_delayed_properly": cycle_delayed,
            "cycle_collected_by_gc": cycle_collected,
            "reclaimed_cycle_objects": reclaimed_cycles,
            "weakref_registry_empty": len(self.registry) == 0,
        }

    def assert_in_registry(self, name: str) -> bool:
        return name in self.registry


if __name__ == "__main__":
    harness = SystemLifecycleHarness()
    results = harness.execute_lifecycle_suite()
    print("=== Day 01 Capstone Verification Results ===")
    for metric, status in results.items():
        print(f"  {metric:<30}: {status}")
```

### Running the Accompanying Lab Suite
All exercises and unit tests corresponding to Day 01 are runnable directly from the project directory:

```bash
# Execute CLI demonstrations
PYTHONPATH=src python3 -m comprehensive_python.cli --day 1

# Execute comprehensive unit test suite
PYTHONPATH=src python3 -m unittest discover tests -v
```

---

## 12. Master Systems Verification Checklist

Before advancing to Day 02, verify your systems mental model against each criterion:

- [ ] **Execution Model:** Trace the exact path from `.py` text, through AST parsing, `.pyc` serialization, to `ceval.c` opcode evaluation.
- [ ] **Bytecode Analysis:** Use `dis.dis()` to analyze value stack pushes, arithmetic opcodes, and return semantics.
- [ ] **Pointer Mechanics:** Articulate why assignment `b = a` binds a name pointer rather than copying bytes into a typed box.
- [ ] **Identity vs Equality:** Explain the physical difference between pointer identity (`is` / `id()`) and value equality (`==` / `__eq__`).
- [ ] **Reference Counting:** Describe how `ob_refcnt` manages immediate reclamation and why local frames in modern CPython use borrowed references.
- [ ] **Cyclic Garbage Collection:** Explain why reference counting fails on circular graphs, and how CPython's generational GC (Gen 0, 1, 2) breaks unreachable loops.
- [ ] **Interning Optimizations:** State the exact bounds of the small integer cache (`[-5, 256]`) and how string interning accelerates dictionary key lookups.
- [ ] **Frame Stack Architecture:** Identify the fields of `PyFrameObject` (`f_code`, `f_locals`, `f_globals`, `f_back`) and explain how frames form a singly-linked stack.
- [ ] **The GIL:** Explain why the GIL exists to protect reference counting integrity, and contrast its impact on CPU-bound vs I/O-bound concurrency.
- [ ] **Weak References:** Explain how `weakref.ref` and `WeakValueDictionary` provide non-retaining pointers, and why built-in types lack weakref slots.
- [ ] **Reference Traps:** Diagnose why `[[0] * 3] * 3` creates shared inner pointers and why mutable default arguments persist inside `func.__defaults__`.
- [ ] **Verification Testing:** Execute `PYTHONPATH=src python3 -m unittest discover tests -v` and confirm 100% test pass rate across Day 01 diagnostics.
