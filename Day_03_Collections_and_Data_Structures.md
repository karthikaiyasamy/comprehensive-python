# Day 03: Collections, Hash Maps, and Computational Complexity

---

## 1. Lists Under the Hood: Dynamic Contiguous Arrays

In Java, an `ArrayList<Object>` is a dynamic array of object references. In C++, a `std::vector<void*>` is a contiguous array of pointers.

In Python, a `list` is implemented in C as a **contiguous dynamic array of pointers** (`PyObject**`).

```text
CPython C-Level Struct (Include/cpython/listobject.h):

typedef struct {
    PyObject_VAR_HEAD
    PyObject **ob_item;   // Pointer to array of pointers to elements
    Py_ssize_t allocated; // Total allocated capacity in memory
} PyListObject;
```

### The Over-Allocation Strategy (Amortized Growth)
When you call `list.append()`, Python does not reallocate memory on every insertion. That would result in $O(N^2)$ cumulative overhead.

Instead, CPython uses an **over-allocation algorithm** (in `Objects/listobject.c`):
$$\text{new\_allocated} = \text{new\_size} + (\text{new\_size} \gg 3) + (\text{new\_size} < 9 \ ? \ 3 : 6)$$

The capacity sequence grows as follows:
$$0 \rightarrow 4 \rightarrow 8 \rightarrow 16 \rightarrow 25 \rightarrow 35 \rightarrow 46 \rightarrow 58 \rightarrow 72 \rightarrow 88 \dots$$

```python
import sys

nums = []
prev_capacity = sys.getsizeof(nums)

for i in range(30):
    nums.append(i)
    current_capacity = sys.getsizeof(nums)
    if current_capacity != prev_capacity:
        print(f"Length: {len(nums):2d} | Memory Allocated: {current_capacity} bytes")
        prev_capacity = current_capacity
```

### Time Complexity of List Operations

| Operation | Complexity | Physical Reason in C |
| :--- | :--- | :--- |
| `list.append(x)` | $O(1)$ amortized | Appends to pre-allocated contiguous slot. |
| `list.pop()` | $O(1)$ | Decrements `ob_size`. No shifting. |
| `list.insert(0, x)` | $O(N)$ | Must `memmove` every pointer one slot to the right. |
| `list.pop(0)` | $O(N)$ | Must `memmove` all $N-1$ pointers one slot to the left. |
| `list[i]` | $O(1)$ | Direct pointer arithmetic: `ob_item + i * 8`. |
| `list[a:b]` (Slice) | $O(K)$ | Allocates a **new list** and copies $K$ pointers. |

---

## 2. Tuples: Static Arrays with Free Lists

A `tuple` is an immutable sequence of object pointers. Because it cannot grow or shrink:
* It has **no over-allocation overhead** (`allocated == ob_size`).
* CPython maintains a **free list** for small tuples (up to 20 elements). When a tuple is destroyed, its memory is not released to the OS; it is cached for instant re-allocation.

```python
import sys

sample_list = [1, 2, 3, 4]
sample_tuple = (1, 2, 3, 4)

print(f"List memory footprint:  {sys.getsizeof(sample_list)} bytes")  # Includes over-allocation buffer
print(f"Tuple memory footprint: {sys.getsizeof(sample_tuple)} bytes") # Compact, zero buffer
```

---

## 3. Dictionaries: Modern Compact Hash Tables

The Python dictionary (`dict`) is one of the most engineered hash table implementations in computer science.

Prior to Python 3.6, dictionaries consumed massive memory because each hash table bucket stored a 24-byte entry (`hash`, `key*`, `value*`) in a sparse array that had to remain 1/3 empty to avoid collision clustering.

PEP 468 introduced the **Compact Dict Architecture**, cutting memory consumption by 30% to 40% while preserving insertion order.

### The Compact Hash Table Layout

```text
Indices Array (Sparse array of small integer offsets):
  Hash % 8 ───> [ -1, 0, -1, 1, -1, -1, 2, -1 ]

Entries Array (Dense, tightly packed in insertion order):
  Index 0: { hash: 0x8f2a, key: ptr->'id',     value: ptr->101 }
  Index 1: { hash: 0x14b3, key: ptr->'status', value: ptr->'OK' }
  Index 2: { hash: 0x992c, key: ptr->'retries',value: ptr->3 }
```

### How a Lookup Works: `d["status"]`
1. **Hash Calculation:** Python computes `hash("status")`.
2. **Modulo Mask:** `index_slot = hash & (size - 1)` points into the small `indices` array.
3. **Lookup Index:** The `indices` array returns `1`.
4. **Retrieve Entry:** Directly index `entries[1]`.
5. **Collision Check:** If the key doesn't match, Python uses **open addressing with pseudo-random perturbation**:
   $$j = (5 \times j + 1 + \text{perturb}) \pmod{\text{size}}$$
   where `perturb` is shifted right by 5 bits each iteration. This avoids clustering without linked-list chaining.

### Hashability Requirements
For an object to be used as a dictionary key or set element, it must be **hashable**:
1. It must implement `__hash__()` returning an integer that never changes during its lifetime.
2. It must implement `__eq__()` for equality comparison.
3. If two objects are equal (`a == b`), their hashes MUST be identical (`hash(a) == hash(b)`).

*All built-in immutable types (`int`, `str`, `tuple`, `bytes`) are hashable. Mutable containers (`list`, `dict`, `set`) are unhashable.*

---

## 4. Sets: Hash Tables Without Values

A `set` is a dictionary that stores only keys without values. 

It provides $O(1)$ average-time complexity for membership testing, deduplication, and mathematical set operations.

```python
set_a = {1, 2, 3, 4}
set_b = {3, 4, 5, 6}

# Set operators operate at C-level speed:
print(set_a | set_b)  # Union: {1, 2, 3, 4, 5, 6}
print(set_a & set_b)  # Intersection: {3, 4}
print(set_a - set_b)  # Difference: {1, 2}
print(set_a ^ set_b)  # Symmetric Difference: {1, 2, 5, 6}
```

---

## 5. High-Performance Standard Collections

When the standard `list` or `dict` is an architectural bottleneck, use the specialized structures in the standard library `collections` module.

### 1. `collections.deque` (Double-Ended Queue)
A list has $O(N)$ insertion and removal at index 0. A `deque` is a doubly linked list of fixed-size blocks (62 elements per block in CPython).
* `deque.append()`: $O(1)$
* `deque.appendleft()`: $O(1)$
* `deque.pop()`: $O(1)$
* `deque.popleft()`: $O(1)$

```python
from collections import deque

# High-speed FIFO Queue:
queue = deque(maxlen=1000)  # Automatically drops oldest items when full
queue.append("task_1")
queue.append("task_2")
processed = queue.popleft() # O(1) instantaneous pop
```

### 2. `collections.defaultdict`
Avoids explicit existence checks or `.setdefault()` overhead:
```python
from collections import defaultdict

# Grouping items by key:
grouped_events = defaultdict(list)
events = [("auth", "login"), ("db", "query"), ("auth", "logout")]

for category, action in events:
    grouped_events[category].append(action) # No if-key-exists check required
```

### 3. `collections.Counter`
A specialized dictionary for multiset frequency counts:
```python
from collections import Counter

tokens = ["error", "warn", "error", "info", "error"]
frequency = Counter(tokens)
print(frequency.most_common(1))  # [('error', 3)]
```

---

## 6. Common Pitfalls and Systems Traps

### Pitfall 1: Mutating Collections During Iteration
```python
# FATAL TRAP: Modifying a collection while iterating over it
data = {"a": 1, "b": 2, "c": 3}

# Raises RuntimeError: dictionary changed size during iteration
try:
    for k, v in data.items():
        if v == 2:
            del data[k]
except RuntimeError as err:
    print(f"Caught expected error: {err}")

# CORRECT: Iterate over a snapshot list of keys or use a comprehension
for k in list(data.keys()):
    if data[k] == 2:
        del data[k]
```

### Pitfall 2: Using `list` as a FIFO Queue in Production
```python
# SLOW ANTI-PATTERN (O(N) per pop):
def process_jobs(jobs: list):
    while jobs:
        job = jobs.pop(0)  # Shifting N elements on every iteration!
        pass

# FAST PRODUCTION PATTERN (O(1) per pop):
from collections import deque

def process_jobs_fast(jobs: list):
    q = deque(jobs)
    while q:
        job = q.popleft() # Instant pointer adjustment
        pass
```

---

## 7. Hands-On Systems Challenge: High-Performance Ring Buffer

### The Problem
In high-throughput logging, telemetry, and metrics systems, you need a **Circular Buffer (Ring Buffer)** that:
1. Has a fixed maximum capacity.
2. Accepts continuous stream writes.
3. Automatically overwrites the oldest entries when capacity is reached.
4. Provides $O(1)$ appends and $O(1)$ reads without triggering memory reallocations or memory leaks.

### Complete Runnable Implementation

```python
from collections import deque
import time
from typing import Generic, TypeVar, Optional

T = TypeVar("T")

class RingBuffer(Generic[T]):
    """
    A high-throughput, memory-bounded circular buffer.
    Backed by collections.deque with C-level block pointers.
    """
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("Capacity must be positive integer")
        self._capacity = capacity
        self._buffer: deque[T] = deque(maxlen=capacity)
        self._total_appended = 0

    def append(self, item: T) -> None:
        """Appends an item in O(1) time, dropping oldest item if full."""
        self._buffer.append(item)
        self._total_appended += 1

    def pop_oldest(self) -> Optional[T]:
        """Pops the oldest item in O(1) time."""
        if not self._buffer:
            return None
        return self._buffer.popleft()

    def to_list(self) -> list[T]:
        """Returns a snapshot of the current window."""
        return list(self._buffer)

    @property
    def is_full(self) -> bool:
        return len(self._buffer) == self._capacity

    @property
    def size(self) -> int:
        return len(self._buffer)

    def __repr__(self) -> str:
        return f"RingBuffer(size={self.size}/{self._capacity}, total_received={self._total_appended})"

def test_ring_buffer_performance():
    capacity = 100_000
    rb = RingBuffer[int](capacity=capacity)
    
    start_time = time.perf_counter()
    # Stream 1 million telemetry readings through a 100,000 capacity buffer:
    for i in range(1_000_000):
        rb.append(i)
    elapsed = time.perf_counter() - start_time
    
    assert rb.size == capacity, "Buffer size exceeded capacity!"
    # Oldest item should be 900,000 (first 900,000 were cleanly evicted)
    assert rb.pop_oldest() == 900_000, "FIFO ordering violation!"
    
    print(f"Pushed 1,000,000 items in {elapsed:.4f}s ({1_000_000 / elapsed:,.0f} ops/sec)")
    print(f"Final State: {rb}")

if __name__ == "__main__":
    test_ring_buffer_performance()
```

---

## 8. Day 03 Summary Checklist

Before moving to Day 04, verify that you can answer these questions with precision:
* [ ] How does CPython's list over-allocation strategy avoid $O(N^2)$ append overhead?
* [ ] Why does `list.pop(0)` have $O(N)$ complexity while `deque.popleft()` has $O(1)$?
* [ ] How does Python 3.6+ compact dictionary layout save memory compared to the legacy implementation?
* [ ] How does CPython resolve hash collisions in dictionaries without linked lists?
* [ ] Why can't a `list` be used as a dictionary key or set element?
* [ ] What happens internally when you delete an item from a dictionary while iterating over it?


---

## 9. List Comprehensions, Generator Expressions, and Memory

A **list comprehension** eagerly builds the entire list in memory at once.
A **generator expression** lazily produces one item at a time, using O(1) memory regardless of dataset size.

```text
List comprehension:
  [x*x for x in range(6)]
  ┌───┬───┬────┬────┬────┬────┐
  │ 0 │ 1 │  4 │  9 │ 16 │ 25 │   <- all values in RAM immediately
  └───┴───┴────┴────┴────┴────┘

Generator expression:
  (x*x for x in range(6))
  ┌──────────────────────┐
  │  <generator object>  │   <- tiny object; values computed on demand
  └──────────────────────┘
         │  next()
         ▼
        0, 1, 4, 9, 16, 25   <- one at a time
```

```python
import sys

# List comprehension: allocates all 1 million integers immediately
squares_list = [x * x for x in range(1_000_000)]

# Generator expression: allocates almost nothing (just the generator object)
squares_gen = (x * x for x in range(1_000_000))

print(f"List size:      {sys.getsizeof(squares_list):>12,} bytes")
print(f"Generator size: {sys.getsizeof(squares_gen):>12,} bytes")

# Generator produces values on demand:
first_five = [next(squares_gen) for _ in range(5)]
print(f"First five: {first_five}")
```

### When to use each

| Use Case | List Comprehension | Generator Expression |
|---|---|---|
| Need random access by index | Yes | No |
| Iterating once through results | Wasteful | Ideal |
| Unknown or huge dataset | Dangerous (memory) | Safe |
| Passing to `sum()`, `max()`, `join()` | Works | Works (generators accepted) |

### Dict and Set Comprehensions

```python
# Dict comprehension
squares_dict = {x: x * x for x in range(6)}
# {0: 0, 1: 1, 2: 4, 3: 9, 4: 16, 5: 25}

# Set comprehension (duplicates removed automatically)
even_remainders = {x % 4 for x in range(10)}
# {0, 1, 2, 3}
```

---

## 10. Sorting: Timsort and the Key Function

Python's sort uses **Timsort**: a hybrid merge/insertion sort.

- **O(N log N)** worst case; **O(N)** for already-sorted data (exploits natural runs).
- **Stable**: equal elements preserve their original relative order.
- Two methods:
  - `list.sort()`: in-place, returns `None`.
  - `sorted(iterable)`: returns a new list, works on any iterable.

The `key=` argument accepts a function that transforms each element for comparison purposes only. The original elements are stored unchanged.

```python
from dataclasses import dataclass

@dataclass
class Task:
    name: str
    priority: int
    deadline: str

tasks = [
    Task("deploy", 1, "2024-12-01"),
    Task("review", 3, "2024-11-30"),
    Task("test",   2, "2024-11-28"),
]

# Sort by priority ascending:
tasks.sort(key=lambda t: t.priority)
print([t.name for t in tasks])  # ['deploy', 'test', 'review']

# Sort by deadline descending:
by_deadline = sorted(tasks, key=lambda t: t.deadline, reverse=True)
print([t.name for t in by_deadline])

# Multi-key sort: primary=priority, secondary=name alphabetically:
tasks.sort(key=lambda t: (t.priority, t.name))
```

> **Note:** Never use the deprecated `cmp=` parameter. Always use `key=`.

---

## 11. heapq: Priority Queue Using a Binary Heap

A **heap** is a binary tree stored as a plain array where every parent is less than or equal to its children (min-heap property).

```text
  Index: 0   1   2   3   4   5
  Value: 1   3   5   7   8   9

  Tree view:
         1
        / \
       3   5
      / \ /
     7  8 9

  Parent of index i  -->  (i - 1) // 2
  Children of index i --> 2*i + 1  and  2*i + 2
```

The `heapq` module wraps a plain Python list as a min-heap.

| Operation | Complexity |
|---|---|
| `heappush` | O(log N) |
| `heappop` | O(log N) |
| Peek minimum (`heap[0]`) | O(1) |

```python
import heapq

events = []
heapq.heappush(events, (10, "low priority task"))
heapq.heappush(events, (1,  "critical alert"))
heapq.heappush(events, (5,  "normal task"))

while events:
    priority, task = heapq.heappop(events)
    print(f"[Priority {priority}] {task}")
# Output in correct priority order: 1, 5, 10

# nlargest and nsmallest without sorting entire list:
data = [34, 1, 92, 7, 55, 23, 88]
print(heapq.nlargest(3, data))   # [92, 88, 55]
print(heapq.nsmallest(3, data))  # [1, 7, 23]
```

**Use cases:** event schedulers, task queues, Dijkstra's shortest-path algorithm.

---

## 12. bisect: Binary Search on Sorted Lists

`bisect` maintains a sorted list efficiently without re-sorting after every insertion.

- `bisect.bisect_left(a, x)`: returns the leftmost index where `x` can be inserted to keep `a` sorted. O(log N).
- `bisect.insort(a, x)`: inserts `x` at the correct position. O(log N) search + O(N) shift.

```python
import bisect

scores = [10, 20, 30, 40, 50]

# Find where 35 would go:
pos = bisect.bisect_left(scores, 35)
print(f"35 belongs at index {pos}")  # 3

# Insert and keep sorted:
bisect.insort(scores, 35)
print(scores)  # [10, 20, 30, 35, 40, 50]

# Grade lookup with bisect:
breakpoints = [60, 70, 80, 90]
grades = ["F", "D", "C", "B", "A"]

def get_grade(score: int) -> str:
    return grades[bisect.bisect(breakpoints, score)]

print(get_grade(85))  # B
print(get_grade(55))  # F
print(get_grade(92))  # A
```

---

## 13. Choosing the Right Data Structure: Decision Guide

```text
WHAT DO YOU NEED?                    USE THIS
─────────────────────────────────────────────────────────
Ordered, indexed, mixed types        list
Ordered, indexed, immutable          tuple
Fast key -> value lookup             dict
Fast membership test                 set
Fast insert/remove at both ends      collections.deque
Counting frequencies                 collections.Counter
Grouping without key-existence check collections.defaultdict
Priority scheduling                  heapq + list
Sorted insertions, binary search     bisect + list
Immutable record with named fields   namedtuple
Mutable record with type hints       dataclass
Hashable record (dict key safe)      frozen dataclass / namedtuple
```

### Decision Flowchart

```text
Do you need fast lookup by key?
  YES --> Do you care about values?
            YES --> dict
            NO  --> set
  NO  --> Do you need ordering?
            YES --> Do you insert/remove from both ends?
                      YES --> deque
                      NO  --> list
            NO  --> tuple (if fixed size) or list (if variable)
```

---

## 14. Updated Checklist

- [ ] What is the memory difference between a list comprehension and a generator expression?
- [ ] What sort algorithm does Python use and what makes it efficient on nearly-sorted data?
- [ ] When would you use `heapq` over sorting the entire list?
- [ ] How does `bisect.insort` maintain sorted order and what is its time complexity?
- [ ] Given a problem, can you pick the correct data structure from the decision guide?
