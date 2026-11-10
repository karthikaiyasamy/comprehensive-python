# Day 01: Execution Model and Memory Architecture

---

## 1. The Systems Mental Model: How Python Runs Code

Engineers coming from C++ or Java often ask: *Is Python compiled or interpreted?*

The precise answer is: **Python is compiled to bytecode, which is then interpreted by a stack-based virtual machine (CPython).**

```
 [Source Code: app.py]
          │
          ▼  Compilation Phase (AST Parsing & Symbol Table)
 [Bytecode: app.cpython-312.pyc] (Platform-independent bytecode instructions)
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
CPython is implemented in C. At its heart lies `Python/ceval.c`, a giant evaluation loop (historically a massive `switch` statement, now heavily optimized with computed gotos in modern Python 3.11+). 

The CPython VM is a **stack machine** (similar to the JVM). It does not use CPU registers directly for intermediate arithmetic; it pushes and pops object references onto a value stack.

---

## 2. Inspecting Bytecode with `dis`

To understand what Python does under the hood, use the standard library `dis` (disassembler) module.

```python
import dis

def calculate(a: int, b: int) -> int:
    result = a + b * 2
    return result

dis.dis(calculate)
```

### Output Analysis
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
1. `LOAD_FAST 0 (a)`: Pushes a pointer to object `a` onto the stack.
2. `LOAD_FAST 1 (b)`: Pushes a pointer to object `b` onto the stack.
3. `LOAD_CONST 1 (2)`: Pushes a pointer to the integer constant `2` onto the stack.
4. `BINARY_OP 5 (*)`: Pops `2` and `b`, invokes the C-level multiplication slot, pushes the result pointer.
5. `BINARY_OP 0 (+)`: Pops the product and `a`, invokes addition, pushes the sum pointer.
6. `STORE_FAST 2 (result)`: Pops the sum pointer and binds it to the local name `result`.
7. `RETURN_VALUE`: Pops the top of stack and returns it to the caller frame.

---

## 3. Variables as Names (Pointers), Not Memory Boxes

This is the single most critical conceptual difference between Python and C/C++/Java:

* **In C++ or Java:** A variable is a named, typed memory location (a box). Assigning a value copies bits into that box.
* **In Python:** A variable is merely a **name tag (pointer)** bound to an object living in the heap.

```text
C++ Model (Typed Memory Boxes):
  int a = 10;          [ Memory Address: 0x7fff01 ] -> Contains raw 32-bit int: 10
  int b = a;           [ Memory Address: 0x7fff05 ] -> Contains raw 32-bit int: 10 (Copied)

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

When you execute `b = a`, Python **does not copy the data**. It merely increments the object's reference counter and binds the name `b` to the exact same heap address.

---

## 4. Object Identity: `id()`, `is`, and `==`

Every object in Python has:
1. **An Identity:** The physical memory address of the C struct (`id(obj)`).
2. **A Type:** Defines what operations are valid (e.g., `int`, `list`, `function`).
3. **A Value:** The payload data stored inside the object.

### The Strict Distinction Between `is` and `==`

| Operator | Comparison Type | Equivalent in C / Java | What it Checks |
| :--- | :--- | :--- | :--- |
| `a is b` | Identity | `a == b` (pointer comparison) | `id(a) == id(b)` (Same physical object in RAM) |
| `a == b` | Value Equality | `a.equals(b)` / overloaded `==` | `a.__eq__(b)` (Equivalent contents or values) |

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

## 5. Memory Management: Reference Counting and Cyclic GC

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
# sys.getrefcount passes x into the function, temporarily adding 1 reference
print(sys.getrefcount(x))  # Prints 2 (x itself + argument to getrefcount)

y = x
print(sys.getrefcount(x))  # Prints 3 (x, y + argument)

del y
print(sys.getrefcount(x))  # Prints 2 (y removed)
```

### Engine 2: The Generational Garbage Collector (Cycle Detector)
Reference counting alone has one fatal flaw: **Circular References**.

```text
  Node A (refcnt: 1) ─────────── points to ───────────> Node B (refcnt: 1)
         ▲                                                     │
         │                                                     │
         └────────────────────── points to ────────────────────┘
```

If the external variables pointing to `Node A` and `Node B` are deleted, their internal cross-references keep `ob_refcnt = 1`. Reference counting will never free them.

To solve this, CPython runs a **Generational Garbage Collector** (`gc` module) that tracks container objects (lists, dictionaries, classes, tuples) across 3 generations (Gen 0, Gen 1, Gen 2). It periodically performs cycle-detection by temporarily decrementing trial counts to identify unreachable islands of memory.

```python
import gc

class Node:
    def __init__(self, name: str):
        self.name = name
        self.neighbor = None

# Create circular reference
node_a = Node("A")
node_b = Node("B")
node_a.neighbor = node_b
node_b.neighbor = node_a

# Break external roots
del node_a
del node_b

# The two nodes still exist in RAM due to circular references
print(f"Unreachable objects before GC: {gc.collect()}")
```

---

## 6. CPython Optimizations: Interning

CPython uses memory-saving optimizations that every systems engineer must understand to avoid subtle identity bugs.

### 1. Small Integer Caching (`[-5, 256]`)
During CPython startup, an array of 262 integer objects covering the range `-5` to `256` is allocated in C. Any time your code references an integer in this range, CPython returns a reference to the existing singleton.

```python
x = 250
y = 250
print(x is y)  # True: Points to pre-allocated global singleton

a = 1000
b = 1000
print(a is b)  # False (in REPL/interactive mode): Two distinct heap objects
print(a == b)  # True: Value equality
```

*Note: In modern Python compilers, constants within the same code object or file may be folded together during compilation, but you must never rely on `is` for value comparisons.*

### 2. String Interning
CPython automatically interns string literals that look like Python identifiers (ASCII letters, digits, underscores) and dictionary keys. Interned strings share the same memory address, turning string comparison in dictionary lookups from an $O(N)$ `memcmp` into an $O(1)$ pointer comparison.

---

## 7. Common Pitfalls and Systems Traps

### Pitfall 1: Using `is` for Literal Comparisons
```python
# BAD: Non-deterministic behavior depending on optimization level and Python version
status_code = get_http_status()
if status_code is 200:  # SyntaxWarning in Python 3.8+
    pass

# CORRECT: Always use value equality for literals
if status_code == 200:
    pass

# THE EXCEPTION: Use 'is' strictly for singletons (None, True, False, sentinel objects)
if status_code is None:
    pass
```

### Pitfall 2: Mutating Objects Through Shared References
```python
# Creating a list of lists with multiplication:
matrix = [[0] * 3] * 3

# Looks like a 3x3 matrix: [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
matrix[0][0] = 99

# TRAP: All 3 rows point to the EXACT SAME list in heap!
# Result: [[99, 0, 0], [99, 0, 0], [99, 0, 0]]
print(matrix)

# CORRECT: Create distinct row objects using a comprehension
clean_matrix = [[0] * 3 for _ in range(3)]
clean_matrix[0][0] = 99
print(clean_matrix)  # Result: [[99, 0, 0], [0, 0, 0], [0, 0, 0]]
```

---

## 8. Hands-On Systems Challenge: Object Lifecycle Tracker

### The Problem
Write a lightweight utility class `MemoryTracker` that:
1. Tracks when an object is created and when its memory is reclaimed by the OS.
2. Demonstrates the difference between immediate reference-count destruction and cyclic garbage collection.

### Complete Runnable Implementation

```python
import gc
import sys
import weakref

class TrackedResource:
    def __init__(self, name: str):
        self.name = name
        print(f"[ALLOCATED] {self.name} at {hex(id(self))}")

    def __del__(self):
        # Called when refcount reaches 0
        print(f"[DEALLOCATED] {self.name} reclaimed from memory")

def run_demonstration():
    print("--- Test 1: Deterministic Reference Counting ---")
    resource_1 = TrackedResource("Buffer_Alpha")
    ref_count = sys.getrefcount(resource_1) - 1
    print(f"Current reference count: {ref_count}")
    
    print("Deleting primary reference:")
    del resource_1  # Reclaimed immediately
    print("Finished Test 1\n")

    print("--- Test 2: Circular Reference Delay ---")
    res_a = TrackedResource("Cycle_Node_A")
    res_b = TrackedResource("Cycle_Node_B")
    
    # Create cycle
    res_a.partner = res_b
    res_b.partner = res_a

    print("Deleting external variables res_a and res_b:")
    del res_a
    del res_b
    print("Variables deleted, but objects remain in memory due to cycle!")

    print("Manually invoking gc.collect():")
    collected = gc.collect()
    print(f"Garbage collector ran: {collected} unreachable cyclic objects collected.")
    print("Finished Test 2")

if __name__ == "__main__":
    run_demonstration()
```

---

## 9. Day 01 Summary Checklist

Before moving to Day 02, verify that you can answer these questions with precision:
* [ ] Can you trace what happens from `.py` source text to CPython `ceval.c` opcode execution?
* [ ] Can you explain why variable assignment in Python is pointer binding rather than memory copying?
* [ ] Can you explain the exact difference between `is` and `==` at the CPU/memory level?
* [ ] Why does Python use both reference counting and a cyclic garbage collector?
* [ ] Why did `matrix = [[0] * 3] * 3` corrupt all rows when only one row was edited?


---

## 10. The Frame Object and Call Stack

Every function call in CPython creates a **frame object** (`PyFrameObject` in C).  
A frame holds the local variables, the bytecode being executed, and a pointer to the calling frame.

**What a frame contains:**

| Attribute    | Description                                      |
|--------------|--------------------------------------------------|
| `f_code`     | The code object (bytecode, argument names, etc.) |
| `f_locals`   | Dict of local variable bindings                  |
| `f_globals`  | Dict of global variable bindings (the module)    |
| `f_back`     | Pointer to the calling frame (or `None` at top)  |
| `f_lineno`   | Current line number being executed               |

**ASCII diagram: call stack during `outer()` → `inner()`:**

```text
  Python C eval loop (ceval.c)
  ┌──────────────────────────────┐
  │  <module> frame              │  ← bottom of stack
  │  f_locals: {}                │
  │  f_back: None                │
  └──────────────┬───────────────┘
                 │ calls outer()
  ┌──────────────▼───────────────┐
  │  outer() frame               │
  │  f_locals: {x: 42}          │
  │  f_back: <module> frame      │
  └──────────────┬───────────────┘
                 │ calls inner()
  ┌──────────────▼───────────────┐
  │  inner() frame               │  ← top of stack (currently executing)
  │  f_locals: {frame: ...}     │
  │  f_back: outer() frame       │
  └──────────────────────────────┘
```

**Inspecting live frames with `inspect`:**

```python
import inspect

def inner():
    frame = inspect.currentframe()
    print(f"Function: {frame.f_code.co_name}")
    print(f"Caller:   {frame.f_back.f_code.co_name}")
    print(f"Locals:   {frame.f_locals}")

def outer():
    x = 42
    inner()

outer()
# Function: inner
# Caller:   outer
# Locals:   {'frame': <frame object at 0x...>}
```

Key points:
- `inspect.currentframe()` returns the frame of the calling function.
- `frame.f_back` walks one level up the call stack.
- Frames are linked in a singly-linked list from innermost to outermost.
- When a function returns, its frame is destroyed (or cached for reuse in CPython).

> **Note:** Holding a reference to a frame object in production code can cause memory leaks because the frame keeps all its locals alive. Always delete the reference when done: `del frame`.

---

## 11. The Global Interpreter Lock (GIL)

The **GIL** is a mutex (mutual exclusion lock) inside CPython.  
It guarantees that **only one thread executes Python bytecode at a time**, even on multi-core hardware.

### Why the GIL exists

CPython manages memory with **reference counting** (Section 5).  
Incrementing and decrementing `ob_refcnt` is not atomic on modern CPUs.  
Without the GIL, two threads could corrupt the reference count simultaneously, causing premature object deletion or memory leaks.  
The GIL is the simplest solution: serialize all bytecode execution.

### ASCII diagram: two threads competing for the GIL

```text
  Time ──────────────────────────────────────────────────►

  Thread A  [== runs bytecode ==][waits][== runs bytecode ==]
                                 │
  GIL ──────────────────────────lock/unlock──────────────────
                                 │
  Thread B  [     waits         ][== runs bytecode ==][waits]
```

Only one thread holds the GIL at any moment. The other is blocked.

### Practical consequences

| Workload Type            | Threads helpful? | Reason                                              |
|--------------------------|------------------|-----------------------------------------------------|
| CPU-bound (heavy math)   | No               | Threads contend for GIL; no true parallelism        |
| I/O-bound (network/disk) | Yes              | GIL is released while waiting for I/O               |
| CPU-bound + parallelism  | Use `multiprocessing` | Each process has its own GIL and its own memory |

The GIL **is released** during:
- System calls (file read/write, network recv/send)
- `time.sleep()`
- Many C extension operations (NumPy array math, etc.)

### Python 3.13 and PEP 703

Python 3.13 introduced **GIL-optional builds**.  
You can compile CPython with `--disable-gil` and run with `PYTHON_GIL=0`.  
This is experimental; most third-party C extensions still assume the GIL exists.

### Runnable demo: threads vs processes for CPU work

```python
import time
import threading
import multiprocessing

def cpu_task(n=50_000_000):
    """Pure Python CPU work: count down."""
    while n > 0:
        n -= 1

# --- Threads (GIL prevents true parallelism) ---
start = time.perf_counter()
t1 = threading.Thread(target=cpu_task)
t2 = threading.Thread(target=cpu_task)
t1.start(); t2.start()
t1.join();  t2.join()
thread_time = time.perf_counter() - start

# --- Processes (each has its own GIL) ---
start = time.perf_counter()
p1 = multiprocessing.Process(target=cpu_task)
p2 = multiprocessing.Process(target=cpu_task)
p1.start(); p2.start()
p1.join();  p2.join()
process_time = time.perf_counter() - start

print(f"Threads:   {thread_time:.2f}s")
print(f"Processes: {process_time:.2f}s")
# On a dual-core machine you will typically see:
#   Threads:   ~same as running sequentially (GIL serialises)
#   Processes: ~half the sequential time (true parallelism)
```

---

## 12. `weakref`: References That Don't Keep Objects Alive

A **weak reference** points to an object without incrementing its `ob_refcnt`.  
If no strong references remain, the GC collects the object even if weak references exist.

### Why use weak references?

| Use case          | Problem with strong ref          | Weak ref solves it by…              |
|-------------------|----------------------------------|-------------------------------------|
| Cache             | Cached objects never released    | Letting GC evict them when needed   |
| Event listeners   | Listener keeps source alive      | Allowing source to be collected     |
| Observer pattern  | Observers prevent subject GC     | Decoupling object lifetimes         |

### ASCII diagram: strong vs weak reference

```text
  Strong reference:
  ┌──────────┐  ob_refcnt += 1  ┌──────────────┐
  │  name    │ ───────────────► │   Object     │  stays alive
  └──────────┘                  └──────────────┘

  Weak reference:
  ┌──────────┐  ob_refcnt unchanged ┌──────────────┐
  │  weakref │ ────────────────────►│   Object     │  may be collected
  └──────────┘                      └──────────────┘
                                     ▲
                              GC can delete this
                              when no strong refs remain
```

### `weakref.ref()`: basic weak reference

```python
import weakref
import gc

class Node:
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        return f"Node({self.value})"

obj = Node(99)
weak = weakref.ref(obj)        # weak reference; ob_refcnt stays at 1

print(weak())                  # Node(99) : object still alive

del obj                        # remove the only strong reference
gc.collect()                   # force collection (usually instant here)

print(weak())                  # None     : object has been collected
```

### `weakref.WeakValueDictionary`: cache that doesn't prevent GC

```python
import weakref
import gc

class Resource:
    def __init__(self, name):
        self.name = name

cache = weakref.WeakValueDictionary()

r1 = Resource("alpha")
r2 = Resource("beta")
cache["a"] = r1
cache["b"] = r2

print(list(cache.keys()))   # ['a', 'b']

del r2                      # drop strong ref to "beta"
gc.collect()

print(list(cache.keys()))   # ['a'] : "beta" entry removed automatically
```

Key points:
- `weak()` returns the object if alive, or `None` if collected.
- `WeakValueDictionary` automatically removes entries when values are GC'd.
- Never use a weak reference as the sole way to keep an important object alive.
- Use `weakref.finalize()` to register a cleanup callback that fires when the object is collected.

---

## 13. Updated Checklist

Use this to verify your understanding before moving on.

- [ ] Describe the path from `.py` source file to CPython VM execution.
- [ ] Use `dis.dis()` to read bytecode for a simple function.
- [ ] Explain why `a = b` copies a name binding, not an object.
- [ ] Distinguish `is` (identity) from `==` (equality) with an example.
- [ ] Explain reference counting and the role of the cyclic garbage collector.
- [ ] State the integer intern range `[-5, 256]` and why it exists.
- [ ] Identify the two shared-reference mutation pitfalls from Section 7.
- [ ] What is a `PyFrameObject` and how are frames linked on the call stack?
- [ ] What is the GIL and why does CPython need it for reference counting safety?
- [ ] Why do CPU-bound threads not get a speedup on CPython, while I/O-bound threads do?
- [ ] What is a weak reference and when would you use one instead of a regular reference?
