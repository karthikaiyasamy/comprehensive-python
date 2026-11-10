# Day 02: Types, Mutability, and Memory Layout

---

## 1. The Systems Mental Model: Everything is a `PyObject`

In C++ or Java, primitives (`int`, `double`, `boolean`) live directly on the stack as raw bytes (4 bytes for an int, 8 bytes for a double). 

In Python, **there are no raw primitive values**. Every single entity, from the integer `0` to a complex user class, is a heap-allocated C struct called `PyObject`.

```text
CPython C-Level Struct Definition (Include/object.h):

typedef struct _object {
    _PyObject_HEAD_EXTRA // Double-linked list pointers for debug builds
    Py_ssize_t ob_refcnt; // Reference count (64-bit integer = 8 bytes)
    PyTypeObject *ob_type; // Pointer to type descriptor struct = 8 bytes
} PyObject;

Variable-Length Objects (Include/object.h):

typedef struct {
    PyObject ob_base;     // 16 bytes base header
    Py_ssize_t ob_size;   // Number of items in container = 8 bytes
} PyVarObject;
```

### The Cost of Abstraction: Memory Overhead

```python
import sys

# Raw C integer: 4 bytes (or 8 bytes for int64_t)
# Python integer 0:
print(sys.getsizeof(0))    # 28 bytes!
print(sys.getsizeof(1))    # 28 bytes!
print(sys.getsizeof(2**30))# 32 bytes!
```

### Why Does an Integer Take 28 Bytes?
```text
  [ PyObject Base Header: 16 bytes ]
  ├─ ob_refcnt (8 bytes)
  └─ ob_type   (8 bytes -> pointer to &PyLong_Type)
  [ PyLongObject Payload: 12 bytes ]
  ├─ ob_size   (8 bytes -> signed number of digits)
  └─ ob_digit  (4 bytes -> array of 30-bit digit chunks)
  Total = 28 bytes
```

This memory overhead is the trade-off Python makes for dynamic typing, arbitrary precision, and automatic reference counting.

---

## 2. Core Scalar Types Under the Hood

### 1. `int` (Arbitrary-Precision Integers)
Unlike C/C++/Java, Python integers **never overflow**. When a calculation exceeds 64 bits, CPython automatically expands the internal `ob_digit` array:
* C: `INT_MAX + 1` causes undefined behavior or integer wraparound.
* Python: `2**1000` seamlessly allocates more 30-bit digit chunks in memory.

### 2. `float` (IEEE 754 Double Precision)
Python floats are 64-bit double-precision floating-point numbers (equivalent to `double` in C and Java).
* Overhead: 24 bytes (16 bytes `PyObject` header + 8 bytes raw C `double`).

### 3. `bool` (A Specialized Subclass of Integer)
In Python, `bool` is explicitly a subclass of `int`. There are only two singleton instances: `True` and `False`.
```python
print(issubclass(bool, int))  # True
print(True == 1)              # True
print(False == 0)             # True
print(True + True)            # 2 (Arithmetic is valid!)
```

### 4. `str` (Unicode and PEP 393 Flexible Representation)
Strings in Python 3 are immutable sequences of Unicode characters. 

Historically, storing Unicode required 4 bytes per character (UTF-32), which wasted massive amounts of RAM for plain ASCII text. PEP 393 introduced the **Flexible String Representation**:
* **Latin-1 String (ASCII only):** Uses 1 byte per character.
* **BMP String (Greek, Cyrillic, accented):** Uses 2 bytes per character (UCS-2).
* **Extended Unicode (Emojis, Chinese characters):** Uses 4 bytes per character (UCS-4).

```python
import sys

ascii_str = "hello"
unicode_str = "helló"
wide_str = "hello🚀"

# Length in characters is identical (5 or 6), but byte footprints vary:
print(sys.getsizeof(ascii_str))   # Compact 1 byte/char layout
print(sys.getsizeof(unicode_str)) # 2 bytes/char layout
print(sys.getsizeof(wide_str))    # 4 bytes/char layout
```

---

## 3. Mutability vs Immutability

Understanding mutability is essential to predicting program behavior and memory allocation.

| Classification | Types | In-Memory Behavior |
| :--- | :--- | :--- |
| **Immutable** | `int`, `float`, `bool`, `str`, `tuple`, `frozenset`, `bytes` | Value cannot change after allocation. Any "modification" creates a new object in the heap. |
| **Mutable** | `list`, `dict`, `set`, `bytearray`, custom classes | Contents can be modified in-place at the same memory address. |

### Visualizing In-Place Modification vs Re-Allocation

```text
Case A: Immutable Modification (String)
  s = "cat"           [ Heap Address: 0x100 ] -> "cat"
  s = s + "s"         [ Heap Address: 0x200 ] -> "cats" (NEW OBJECT ALLOCATED)
                      (Old object at 0x100 is orphaned and refcount drops)

Case B: Mutable Modification (List)
  nums = [1, 2]       [ Heap Address: 0x500 ] -> [ ptr->1, ptr->2 ]
  nums.append(3)      [ Heap Address: 0x500 ] -> [ ptr->1, ptr->2, ptr->3 ]
                      (SAME OBJECT IN MEMORY, array resized in-place)
```

---

## 4. Shallow Copy vs Deep Copy

When you pass or duplicate data structures in Python, you must know whether you are creating an **alias**, a **shallow copy**, or a **deep copy**.

```text
1. Assignment (Alias):
   b = a
   (Zero objects copied; both names point to the exact same memory address).

2. Shallow Copy (copy.copy(a) or a.copy() or a[:]):
   b = copy.copy(a)
   (The outer container is duplicated, but all inner items are shared pointers).

3. Deep Copy (copy.deepcopy(a)):
   b = copy.deepcopy(a)
   (The outer container AND all recursive inner objects are duplicated).
```

### Memory Diagram: Shallow vs Deep Copy

```text
Original Container:
  original = [[1, 2], [3, 4]]
  
  [original] ───────────> [ Container 0xAAA ]
                             ├─ Pointer 0 ───> [ List 0x111: 1, 2 ]
                             └─ Pointer 1 ───> [ List 0x222: 3, 4 ]

Shallow Copy:
  shallow = copy.copy(original)
  
  [shallow]  ───────────> [ Container 0xBBB ] (New outer container)
                             ├─ Pointer 0 ───> [ List 0x111: 1, 2 ] (SHARED!)
                             └─ Pointer 1 ───> [ List 0x222: 3, 4 ] (SHARED!)

Deep Copy:
  deep = copy.deepcopy(original)
  
  [deep]     ───────────> [ Container 0xCCC ] (New outer container)
                             ├─ Pointer 0 ───> [ List 0x333: 1, 2 ] (DUPLICATED!)
                             └─ Pointer 1 ───> [ List 0x444: 3, 4 ] (DUPLICATED!)
```

### The Production Bug: Mutating Inside a Shallow Copy

```python
import copy

original = [["A", "B"], ["C", "D"]]
shallow_clone = copy.copy(original)

# Mutating the outer structure does not affect original:
shallow_clone.append(["E", "F"])
print(len(original))      # 2 (Unaffected)
print(len(shallow_clone)) # 3

# Mutating an INNER nested structure corrupts original:
shallow_clone[0][0] = "MODIFIED"
print(original[0][0])     # "MODIFIED" - BUG! Shared inner pointer!

# Using deepcopy prevents this entirely:
deep_clone = copy.deepcopy(original)
deep_clone[0][0] = "ISOLATED"
print(original[0][0])     # "MODIFIED" (Unaffected by deep_clone)
```

---

## 5. The Paradox: Immutable Containers with Mutable Elements

A `tuple` is immutable. Its sequence of pointers cannot be extended, shortened, or reassigned. 

However, **if a tuple holds a pointer to a mutable object (like a list), that list can be mutated in-place**.

```python
# A tuple containing an integer and a list:
mixed_tuple = (42, ["alpha", "beta"])

print(f"Tuple ID: {hex(id(mixed_tuple))}")
print(f"List ID inside tuple: {hex(id(mixed_tuple[1]))}")

# This will fail with a TypeError:
# mixed_tuple[0] = 99  # Cannot reassign tuple slots

# But this succeeds completely:
mixed_tuple[1].append("gamma")
print(mixed_tuple)  # (42, ['alpha', 'beta', 'gamma'])
```

### Rule for Production Systems
Immutability in Python is **shallow**. A container is only as immutable as its contents. If you need guaranteed end-to-end immutability (for hash keys, caching, or thread safety), all nested members must also be immutable.

---

## 6. Common Pitfalls and Systems Traps

### Pitfall 1: String Concatenation Inside Loops ($O(N^2)$ Trap)
Because strings are immutable, using `+=` inside a loop repeatedly allocates new memory and copies the previous string contents.

```python
import time

# ANTI-PATTERN: O(N^2) memory reallocations
def slow_string_builder(chunks: list[str]) -> str:
    result = ""
    for chunk in chunks:
        result += chunk  # Allocates new string every iteration
    return result

# IDIOMATIC & FAST: Single allocation O(N)
def fast_string_builder(chunks: list[str]) -> str:
    return "".join(chunks)  # Pre-computes total buffer length, copies once
```

### Pitfall 2: The `+=` Operator on Lists vs Reassignment
```python
# In-place extension:
list_a = [1, 2]
alias_a = list_a
list_a += [3]  # Calls __iadd__ -> Mutates list_a in place!
print(alias_a) # [1, 2, 3] (alias_a sees the change)

# Reassignment:
list_b = [1, 2]
alias_b = list_b
list_b = list_b + [3]  # Calls __add__ -> Allocates new list, rebinds name!
print(alias_b) # [1, 2] (alias_b is unchanged)
```

---

## 7. Hands-On Systems Challenge: Safe Deep Snapshot Utility

### The Problem
In financial and high-throughput data processing systems, passing mutable configurations or state dictionaries to background worker threads can cause race conditions and data corruption.

Write a function `snapshot_state(state: dict)` that:
1. Validates that the input is a dictionary.
2. Creates an isolated deep copy that handles nested lists, dictionaries, and custom objects.
3. Automatically breaks any potential circular references to ensure the snapshot cannot cause cyclic memory leaks.

### Complete Runnable Implementation

```python
import copy
from typing import Any

class ConfigNode:
    def __init__(self, key: str, value: Any):
        self.key = key
        self.value = value
        self.parent = None

    def __repr__(self) -> str:
        return f"ConfigNode({self.key}={self.value})"

def snapshot_state(state: dict[str, Any]) -> dict[str, Any]:
    """
    Creates an isolated, deeply copied snapshot of a configuration dictionary,
    protecting it from concurrent mutations by the caller.
    """
    if not isinstance(state, dict):
        raise TypeError(f"Expected dict, got {type(state).__name__}")
    
    # deepcopy handles object graph traversal and memoizes visited IDs
    # preventing infinite recursion on circular dependencies.
    isolated_snapshot = copy.deepcopy(state)
    return isolated_snapshot

def verify_snapshot_integrity():
    # Setup shared mutable state
    shared_config = {
        "timeout_ms": 5000,
        "nodes": [ConfigNode("db_primary", "10.0.0.1"), ConfigNode("db_replica", "10.0.0.2")],
        "metadata": {"env": "production", "retries": [1, 2, 5]}
    }
    
    # Take snapshot
    safe_copy = snapshot_state(shared_config)
    
    # Mutate original deeply
    shared_config["timeout_ms"] = 9999
    shared_config["nodes"][0].value = "MUTATED_IP"
    shared_config["metadata"]["retries"].append(10)
    
    # Verify snapshot was unaffected
    assert safe_copy["timeout_ms"] == 5000, "Scalar leaked!"
    assert safe_copy["nodes"][0].value == "10.0.0.1", "Object pointer leaked!"
    assert safe_copy["metadata"]["retries"] == [1, 2, 5], "Nested list leaked!"
    
    print("Snapshot integrity verified: Deep copy successfully isolated all state.")

if __name__ == "__main__":
    verify_snapshot_integrity()
```

---

## 8. Day 02 Summary Checklist

Before moving to Day 03, verify that you can answer these questions with precision:
* [ ] What is the structural memory layout of a `PyObject` in C?
* [ ] Why does an integer in Python consume 28 bytes on 64-bit platforms?
* [ ] How does PEP 393 save memory when storing ASCII vs Unicode strings?
* [ ] What is the concrete difference between a shallow copy and a deep copy in memory?
* [ ] Can you explain why modifying `my_tuple[1].append(10)` works even though a tuple is immutable?
* [ ] Why is `"".join(list_of_strings)` asymptotically faster than `+=` in a loop?


---

## 9. bytes and bytearray: Binary Data Types

`bytes` is an **immutable** sequence of integers, each in the range 0–255.
`bytearray` is the **mutable** equivalent.
Neither is a string: indexing returns an `int`, not a character.

### Memory Layout Comparison

```text
str "hi"  (PEP 393 flexible, may store UCS-1/UCS-2/UCS-4 per codepoint)
┌──────────────────────────────────────┐
│ PyObject header │ length │ hash │ ...│  codepoints stored internally
└──────────────────────────────────────┘

bytes b"hi"  (raw byte array, ASCII subset, immutable)
┌──────────────────────────────────────┐
│ PyObject header │ length │ 0x68 0x69 │  each slot = one uint8
└──────────────────────────────────────┘

bytearray b"hi"  (same layout, but mutable buffer)
┌──────────────────────────────────────┐
│ PyObject header │ length │ 0x68 0x69 │  in-place writes allowed
└──────────────────────────────────────┘
```

### Runnable Demo

```python
# bytes: immutable binary data
raw = b"\x00\xFF\x1A\x2B"
print(len(raw))          # 4
print(raw[0])            # 0 (integer, NOT character)
print(type(raw[0]))      # <class 'int'>

# bytearray: mutable
buf = bytearray(b"hello")
buf[0] = 72              # 72 == ord('H')
print(buf)               # bytearray(b'Hello')

# Encoding text to bytes and back:
text = "café"
encoded = text.encode("utf-8")
print(encoded)           # b'caf\xc3\xa9'
decoded = encoded.decode("utf-8")
print(decoded)           # café
```

### Comparison Table

| Type       | Mutable | Element type | Typical use case                        |
|------------|---------|-------------|-----------------------------------------|
| `str`      | No      | Unicode char (str of len 1) | Human-readable text          |
| `bytes`    | No      | `int` 0–255 | Network protocols, file I/O, cryptography |
| `bytearray`| Yes     | `int` 0–255 | Streaming buffers, in-place manipulation |

### When to Use Each

- **`bytes`**: reading binary files, HTTP bodies, TLS frames, hashing inputs.
- **`bytearray`**: building a packet incrementally, decoding a stream chunk by chunk.
- **`str`**: any human-facing text; always encode to `bytes` before writing to a socket.

---

## 10. Type Coercion and Conversion Rules

Python does **not** auto-coerce types the way JavaScript does.
`"3" + 3` raises `TypeError`. Conversion is always explicit.

### Explicit Conversion

```python
int("42")        # 42
float("3.14")    # 3.14
str(100)         # "100"
bool(0)          # False
list((1, 2, 3))  # [1, 2, 3]
```

### Truthiness (Falsy Values)

Every object has a boolean interpretation. These evaluate to `False`:

| Value                          | `bool()` result |
|-------------------------------|-----------------|
| `None`                        | `False`         |
| `0`, `0.0`, `0j`             | `False`         |
| `""` (empty string)           | `False`         |
| `[]`, `{}`, `set()`, `()`    | `False`         |
| Any non-empty / non-zero value | `True`         |

Python consults two dunder methods to decide:
1. `__bool__`: if defined, its return value is used.
2. `__len__`: if `__bool__` is absent, `len(obj) == 0` means falsy.

### Runnable Demo

```python
falsy_values = [None, 0, 0.0, 0j, "", [], {}, set(), ()]

for v in falsy_values:
    if not v:
        print(f"  falsy: {v!r:<12}  type={type(v).__name__}")

# Output: all nine lines printed, confirming each is falsy
```

### Common Trap: `None` vs `""`

```python
user_input = ""   # user submitted an empty form field
result = None     # function returned no result: a different concept

# Both are falsy:
if not user_input:
    print("empty string is falsy")
if not result:
    print("None is falsy")

# But they are semantically different: always test with 'is None':
if result is None:
    print("no result was produced")
if user_input == "":
    print("user sent an empty string")
```

---

## 11. Named Tuples and dataclasses: Structured Immutable Data

Use these when a plain tuple becomes hard to read or a full class adds unnecessary boilerplate.

### `namedtuple`: Immutable, Lightweight

A tuple subclass with named field access.
Memory footprint is identical to a plain tuple (much smaller than a dict or class).

### `dataclass`: Class with Auto-Generated Boilerplate

The `@dataclass` decorator auto-generates `__init__`, `__repr__`, and `__eq__`.
Adding `frozen=True` makes the instance immutable and hashable.

### Runnable Examples

```python
from collections import namedtuple
from dataclasses import dataclass, field

# namedtuple: immutable, lightweight
Point = namedtuple("Point", ["x", "y"])
p = Point(3, 4)
print(p.x, p.y)        # 3 4
print(p[0], p[1])      # 3 4  (also indexable like a tuple)
# p.x = 10             # AttributeError: can't set attribute

# dataclass: class with auto-boilerplate
@dataclass
class Sensor:
    name: str
    value: float
    tags: list[str] = field(default_factory=list)

s = Sensor("temperature", 36.6)
print(s)               # Sensor(name='temperature', value=36.6, tags=[])

# frozen dataclass: immutable and hashable
@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float

gp = GeoPoint(49.1, -122.8)
# gp.lat = 0.0         # Raises FrozenInstanceError
print(hash(gp))        # Hashable: can be used as a dict key or set member
```

### Comparison Table

| Feature            | `tuple`      | `namedtuple`     | `dataclass`         | `dataclass(frozen=True)` |
|--------------------|-------------|------------------|---------------------|--------------------------|
| Mutable            | No          | No               | Yes (default)       | No                       |
| Named field access | No          | Yes              | Yes                 | Yes                      |
| Hashable           | Yes         | Yes              | No (default)        | Yes                      |
| `__repr__`         | Generic     | Auto-generated   | Auto-generated      | Auto-generated           |
| Memory overhead    | Minimal     | Minimal          | Moderate (dict-backed) | Moderate              |
| Default values     | No          | Via `_make`/defaults | Yes (`field`)   | Yes (`field`)            |
| Inheritance        | Allowed     | Allowed          | Allowed             | Allowed                  |

**Rule of thumb:**
- Use `namedtuple` when you need a lightweight, read-only record and tuple semantics (indexable, unpackable).
- Use `dataclass` when you need mutability, default values, or methods.
- Use `frozen=True` dataclass when you need immutability plus richer behaviour than `namedtuple` offers.

---

## 12. Memory Profiling Tools

Two standard tools to measure Python memory usage:

| Tool            | Scope          | Recursive? | Use case                              |
|-----------------|---------------|------------|---------------------------------------|
| `sys.getsizeof` | Shallow only  | No         | Quick size check of one object        |
| `tracemalloc`   | All allocations | Aggregated | Finding which lines allocate the most |

### `sys.getsizeof`: Shallow Size Only

`sys.getsizeof([1, 2, 3])` returns the size of the **list container** (the array of pointers), not the size of the integers stored inside.

```python
import sys

nums = [1, 2, 3]
print(sys.getsizeof(nums))   # ~88 bytes (list object + 3 pointers)
print(sys.getsizeof(1))      # 28 bytes (one int PyObject)
# Total actual memory: 88 + 3*28 = 172 bytes: getsizeof alone misses this
```

To get the **recursive** (total) size, you must walk the object graph manually:

```python
import sys

def total_size(obj, seen=None):
    """Recursively compute total memory of obj and all objects it references."""
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum(total_size(k, seen) + total_size(v, seen) for k, v in obj.items())
    elif hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
        size += sum(total_size(i, seen) for i in obj)
    return size

nums = [1, 2, 3]
print(f"getsizeof : {sys.getsizeof(nums):,} bytes")
print(f"total_size: {total_size(nums):,} bytes")
```

### `tracemalloc`: Line-Level Allocation Tracing

```python
import tracemalloc
import sys

# tracemalloc: traces Python memory allocations
tracemalloc.start()

# Allocate some objects
big_list = [i for i in range(100_000)]

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics("lineno")

print(f"[Memory] List size (getsizeof): {sys.getsizeof(big_list):,} bytes")
print(f"[Memory] Top allocation:")
print(top_stats[0])

tracemalloc.stop()
```

Expected output (approximate):

```text
[Memory] List size (getsizeof): 800,984 bytes
[Memory] Top allocation:
<string>:4: size=3516 KiB, count=100001, average=36 B
```

`tracemalloc` reveals the **total bytes allocated** across all 100,000 int objects: information `getsizeof` on the list alone does not provide.

---

## 13. Updated Checklist

Work through every item before moving to Day 03.

- [ ] Explain the PyObject struct and why a Python `int` costs at least 28 bytes.
- [ ] What is the difference between arbitrary-precision `int` and IEEE 754 `float`?
- [ ] Which built-in types are mutable? Which are immutable?
- [ ] Draw the memory diagram for a shallow copy vs. a deep copy.
- [ ] Why can a `tuple` be unhashable? Give a concrete example.
- [ ] What two string concatenation patterns cause O(N²) behaviour, and how do you avoid them?
- [ ] What is the difference between `bytes`, `bytearray`, and `str` in terms of mutability and element type?
- [ ] What values are falsy in Python and what dunder method controls this?
- [ ] When would you choose a `namedtuple` over a `dataclass`?
- [ ] Why does `sys.getsizeof([1, 2, 3])` not give you the total memory used by that list?
