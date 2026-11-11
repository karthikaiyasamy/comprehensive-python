# Day 05: Functions, Closures, and Decorators

---

## 1. The Systems Mental Model: Functions as First-Class Heap Objects

In C and C++, a function is a block of machine code loaded into the text/code segment of memory. You can take its address via a function pointer, but the function itself is not a dynamically allocated object.

In Python, **functions are first-class heap objects** (`PyFunctionObject` in C).

```text
CPython C-Level Struct (Include/cpython/funcobject.h):

typedef struct {
    PyObject_HEAD
    PyObject *func_code;        // Bytecode and parameter metadata (PyCodeObject)
    PyObject *func_globals;     // Dict of the module global namespace
    PyObject *func_defaults;    // Tuple of default positional parameter values
    PyObject *func_kwdefaults;  // Dict of default keyword-only parameter values
    PyObject *func_closure;     // Tuple of cell objects for free variables
    PyObject *func_doc;         // The __doc__ string
    PyObject *func_name;        // The __name__ string
    PyObject *func_dict;        // Custom attributes dict on the function
    PyObject *func_annotations; // Type annotations dict
} PyFunctionObject;
```

Because functions are heap objects, they can be:
1. Assigned to variables and stored in lists or dictionaries.
2. Passed as arguments to other functions.
3. Returned dynamically from other functions.
4. Decorated or modified at runtime.

---

## 2. Parameter Passing Mechanics: Call-by-Object-Sharing

Is Python pass-by-value or pass-by-reference?

The technical term is **Call-by-Object-Sharing** (or pass-by-object-reference):
* **Pointers to objects are copied by value** onto the callee's execution stack frame.
* The callee receives a copy of the pointer, pointing to the exact same object in the heap.

```text
ASCII Diagram: Caller vs Callee Frame

  Caller Frame:
    numbers = [1, 2] ────────┐
                             │
  Stack Pass:                ▼  Heap Object (PyListObject at 0x9000)
    mutate(numbers) ─────────┼─> [ Pointer->1, Pointer->2 ]
                             │
  Callee Frame:              │
    target = numbers ────────┘
```

### The In-Place Mutation vs Reassignment Rule

```python
def test_mutations(lst: list, scalar: int):
    # In-place mutation affects caller because both point to the same list:
    lst.append(999)

    # Reassignment breaks the link; 'scalar' now points to a new int in the heap:
    scalar = 42

caller_list = [1, 2]
caller_int = 10

test_mutations(caller_list, caller_int)

print(caller_list)  # [1, 2, 999] -> Mutated!
print(caller_int)   # 10          -> Unchanged!
```

---

## 3. The Mutable Default Argument Trap

This is one of the most infamous interview and production bugs in Python.

```python
# THE DANGEROUS PATTERN:
def append_event(event: str, registry: list = []):
    registry.append(event)
    return registry

print(append_event("LOGIN"))    # ['LOGIN']
print(append_event("LOGOUT"))   # ['LOGIN', 'LOGOUT'] ! Where did LOGIN come from?
```

### Why Does This Happen?
* Default argument expressions are evaluated **ONCE at function definition time (compilation)**, NOT when the function is called!
* The list `[]` is allocated in the heap when the module is imported, and stored inside `append_event.__defaults__`.
* Every invocation that omits `registry` shares that exact same heap list.

```python
# Inspecting the shared default object:
print(append_event.__defaults__)  # (['LOGIN', 'LOGOUT'],)
```

### The Idiomatic Production Pattern: Sentinel `None`

```python
def append_event_safe(event: str, registry: list | None = None) -> list:
    if registry is None:
        registry = []  # Fresh list allocated on each invocation
    registry.append(event)
    return registry
```

---

## 4. Advanced Function Signatures: Positional-Only and Keyword-Only

Modern Python (PEP 570 and PEP 3102) allows systems engineers to explicitly control how arguments are passed using `/` and `*`.

```text
      def func(pos_only_1, pos_only_2, /, standard, *, kw_only_1, kw_only_2):
               ▲                       ▲  ▲         ▲  ▲
               └─────── Positional ────┘  │         │  └──── Keyword ───────┘
                        Only              │         │        Only
                                          │         │
                                   Positional     Keyword
                                  or Keyword       Only
```

### Code Example

```python
def configure_engine(
    buffer_size: int,      # Positional-only (before '/')
    /,
    timeout: float = 5.0,  # Either positional or keyword
    *,
    enable_tls: bool,      # Keyword-only (after '*')
    retry_limit: int = 3   # Keyword-only (after '*')
) -> dict:
    return {
        "buffer_size": buffer_size,
        "timeout": timeout,
        "enable_tls": enable_tls,
        "retry_limit": retry_limit,
    }

# Valid calls:
configure_engine(1024, 2.0, enable_tls=True)
configure_engine(1024, timeout=3.5, enable_tls=False, retry_limit=5)

# INVALID: Calling positional-only parameter with keyword name:
# configure_engine(buffer_size=1024, enable_tls=True)  # TypeError!

# INVALID: Calling keyword-only parameter positionally:
# configure_engine(1024, 2.0, True)                    # TypeError!
```

### Why Use These in Production?
* **Positional-Only (`/`):** Allows you to rename parameters in library APIs in future versions without breaking callers who might have passed them by keyword.
* **Keyword-Only (`*`):** Forces callers to be explicit for boolean flags or configuration knobs (e.g., `enable_tls=True` is self-documenting; passing `True` alone at call site is ambiguous).

---

## 5. Closures and Cell Objects

When a function returns an inner function that references variables from its enclosing scope, those variables are captured in a **closure**.

In C, returning a pointer to a stack-allocated local variable causes undefined behavior (dangling stack pointer). 

In CPython, any variable referenced by an inner function is automatically wrapped in a heap-allocated **`PyCellObject`**.

```text
ASCII Diagram: PyCellObject Bridging Scopes

  outer() stack frame collapses...
  BUT local variable 'x' survives in a Cell:
  
  [ inner() function object ]
         │
         └─> func_closure ───> ( PyCellObject at 0x5000 )
                                       │
                                       ▼
                                 PyLongObject: 42
```

```python
def make_multiplier(factor: int):
    # 'factor' is stored in a cell object:
    def multiply(val: int) -> int:
        return val * factor
    return multiply

doubler = make_multiplier(2)
print(doubler(10))  # 20

# Inspecting the closure cell directly:
print(doubler.__closure__)               # (<cell at 0x...: int object at 0x...>,)
print(doubler.__closure__[0].cell_contents)  # 2
```

---

## 6. Decorators from Scratch

A decorator is a callable that takes a function as input, extends or modifies its behavior, and returns a new callable.

### Step 1: The Basic Wrapper Pattern

```python
import functools
import time
from typing import Callable, Any

def timing_decorator(func: Callable) -> Callable:
    # functools.wraps copies __name__, __doc__, and __annotations__ from func
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start_time
        print(f"[METRIC] {func.__name__} executed in {elapsed:.6f}s")
        return result
    return wrapper

@timing_decorator
def compute_heavy_task(n: int) -> int:
    """Computes the sum of squares."""
    return sum(i * i for i in range(n))

print(compute_heavy_task(100_000))
print(f"Name preserved: {compute_heavy_task.__name__}")
print(f"Doc preserved:  {compute_heavy_task.__doc__}")
```

### Step 2: Parameterized Decorators (3-Level Function Architecture)

When a decorator needs its own configuration arguments (e.g., `@retry(max_retries=3)`), you need a function that returns a decorator.

```text
Level 1: Decorator Factory (accepts configuration arguments)
  Level 2: Actual Decorator (accepts target function)
    Level 3: Wrapper Function (executes on each function call)
```

```python
import functools
import time
import logging

def retry(max_attempts: int = 3, delay_sec: float = 0.5, backoff_factor: float = 2.0):
    """
    Decorator factory that retries a function with exponential backoff.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay_sec
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as err:
                    if attempt == max_attempts:
                        print(f"[RETRY FAILED] All {max_attempts} attempts exhausted.")
                        raise err
                    print(f"[RETRY WARN] {func.__name__} failed (attempt {attempt}/{max_attempts}): {err}. Retrying in {current_delay:.2f}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff_factor
        return wrapper
    return decorator

# Usage:
@retry(max_attempts=3, delay_sec=0.1, backoff_factor=2.0)
def unstable_network_call(success_on_attempt: int):
    unstable_network_call.attempts = getattr(unstable_network_call, "attempts", 0) + 1
    if unstable_network_call.attempts < success_on_attempt:
        raise ConnectionResetError("Socket reset by peer")
    return "Data packet received"

print(unstable_network_call(2))
```

---

## 7. Common Pitfalls and Systems Traps

### Pitfall 1: Forgetting `functools.wraps`
Without `@functools.wraps(func)`, the decorated function loses its identity:
* `func.__name__` becomes `"wrapper"`.
* `func.__doc__` is erased.
* Docstring generators, loggers, and unit test runners can no longer identify the function.

### Pitfall 2: Decorator Stacking Order
Decorators are applied from the **bottom up** (inside out):
```python
@decorator_one
@decorator_two
def target():
    pass

# Is semantically equivalent to:
target = decorator_one(decorator_two(target))
# Execution order: decorator_one wrapper runs first, then decorator_two, then target.
```

---

## 8. Hands-On Systems Challenge: Sliding Window Rate Limiter Decorator

### The Problem
In distributed APIs and database ingest pipelines, client calls must be restricted to prevent hammering downstream services.

Implement a parameterized decorator `@rate_limit(max_calls: int, period_seconds: float)` that:
1. Tracks timestamps of calls for the decorated function using `collections.deque`.
2. Evicts expired timestamps in $O(1)$ time.
3. If the call rate exceeds `max_calls` within the rolling `period_seconds`, raises a custom `RateLimitExceededError`.
4. Accurately preserves all function metadata using `functools.wraps`.

### Complete Runnable Implementation

```python
from collections import deque
import functools
import time
from typing import Callable, Any

class RateLimitExceededError(Exception):
    pass

def rate_limit(max_calls: int, period_seconds: float):
    """
    Sliding window rate-limiter decorator.
    """
    if max_calls <= 0 or period_seconds <= 0:
        raise ValueError("max_calls and period_seconds must be positive numbers")

    def decorator(func: Callable) -> Callable:
        # Each decorated function gets its own isolated timestamp window:
        call_timestamps: deque[float] = deque()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            now = time.monotonic()
            
            # Step 1: Evict timestamps that fall outside the active sliding window:
            while call_timestamps and (now - call_timestamps[0]) > period_seconds:
                call_timestamps.popleft()

            # Step 2: Check limit:
            if len(call_timestamps) >= max_calls:
                oldest = call_timestamps[0]
                retry_after = period_seconds - (now - oldest)
                raise RateLimitExceededError(
                    f"Rate limit exceeded for '{func.__name__}'. "
                    f"Max {max_calls} calls per {period_seconds}s. Retry in {retry_after:.3f}s"
                )

            # Step 3: Record current call timestamp and execute:
            call_timestamps.append(now)
            return func(*args, **kwargs)

        return wrapper
    return decorator

def test_rate_limiter():
    # Allow at most 3 calls per 0.5 seconds:
    @rate_limit(max_calls=3, period_seconds=0.5)
    def query_database(record_id: int) -> str:
        return f"Record_{record_id}"

    # 3 calls should succeed immediately:
    assert query_database(1) == "Record_1"
    assert query_database(2) == "Record_2"
    assert query_database(3) == "Record_3"

    # 4th call should immediately raise RateLimitExceededError:
    try:
        query_database(4)
        assert False, "Rate limit did not fire!"
    except RateLimitExceededError as err:
        print(f"Caught expected rate limit: {err}")

    # Wait for the sliding window to clear:
    time.sleep(0.55)
    assert query_database(5) == "Record_5"
    print("Rate limiter verified successfully.")

if __name__ == "__main__":
    test_rate_limiter()
```

---

## 9. Function Introspection and Signatures with `inspect`

In enterprise frameworks, dependency injection containers, RPC routers, and test runners, inspecting function signatures at runtime is essential.

The standard library `inspect` module parses the underlying `PyCodeObject` and returns a structured `Signature` object.

```python
import inspect

def process_sample(
    sample_id: str,
    depth: int = 30,
    *,
    qc_pass: bool = True
) -> dict:
    """Processes a biological sample."""
    return {"id": sample_id, "depth": depth, "qc": qc_pass}

sig = inspect.signature(process_sample)

print(f"Function Name: {process_sample.__name__}")
print(f"Return Type:   {sig.return_annotation}")

# Inspecting individual parameters:
for name, param in sig.parameters.items():
    print(f"  Parameter: {name:<10} | Kind: {param.kind.name:<20} | Default: {param.default}")
```

### Parameter Kinds in Python

| Kind Enum | Description | Example Syntax |
| :--- | :--- | :--- |
| `POSITIONAL_ONLY` | Bound positionally before `/` | `def f(a, /):` |
| `POSITIONAL_OR_KEYWORD` | Standard parameters | `def f(a, b=2):` |
| `VAR_POSITIONAL` | Variable positional arguments tuple | `def f(*args):` |
| `KEYWORD_ONLY` | Required keyword argument after `*` | `def f(*, flag=True):` |
| `VAR_KEYWORD` | Variable keyword arguments dict | `def f(**kwargs):` |

---

## 10. Class-Based Decorators vs Function-Based Decorators

Decorators can also be implemented as classes by implementing the `__call__` dunder method.

### When to Use Class-Based Decorators
* When the decorator needs to maintain rich internal state across calls (e.g., metrics dashboards, connection pools).
* When you need to provide administrative methods (like `.reset()` or `.clear()`) directly on the decorated object.

```python
import functools
from typing import Callable, Any

class CallCounter:
    """Class-based decorator tracking execution statistics."""
    def __init__(self, func: Callable):
        self.func = func
        self.call_count = 0
        self.failure_count = 0
        functools.update_wrapper(self, func)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.call_count += 1
        try:
            return self.func(*args, **kwargs)
        except Exception as e:
            self.failure_count += 1
            raise e

    def reset_stats(self) -> None:
        self.call_count = 0
        self.failure_count = 0

@CallCounter
def parse_payload(data: str) -> int:
    return int(data)

# Usage:
print(parse_payload("100"))
print(parse_payload("200"))
print(f"Total calls: {parse_payload.call_count}")

parse_payload.reset_stats()
print(f"Calls after reset: {parse_payload.call_count}")
```

---

## 11. Built-in Performance Decorators: `@functools.lru_cache`

Writing custom memoization logic is unnecessary because CPython provides a C-optimized implementation in `functools`.

### Least Recently Used (LRU) Cache

```python
import functools
import time

# Least Recently Used cache with bounded capacity:
@functools.lru_cache(maxsize=128)
def fetch_user_permissions(user_id: int) -> tuple[str, ...]:
    # Simulating expensive database query:
    time.sleep(0.05)
    return ("READ_PATIENT_RECORDS", "WRITE_LAB_RESULTS")

# First call: Cache miss (takes 50ms)
start = time.perf_counter()
perms1 = fetch_user_permissions(101)
time_miss = time.perf_counter() - start

# Second call: Cache hit (O(1) dictionary lookup, instant)
start = time.perf_counter()
perms2 = fetch_user_permissions(101)
time_hit = time.perf_counter() - start

print(f"Cache Miss: {time_miss:.5f}s | Cache Hit: {time_hit:.5f}s (Speedup: {time_miss / time_hit:,.0f}x)")
print(fetch_user_permissions.cache_info())
# CacheInfo(hits=1, misses=1, maxsize=128, currsize=1)
```

### The Strict Hashability Requirement
Because `lru_cache` uses a dictionary under the hood:
* **All arguments passed to cached functions MUST be hashable.**
* Passing a `list` or `dict` to an `@lru_cache` function raises `TypeError: unhashable type: 'list'`.
* Always pass `tuple` or immutable types instead.

---

## 12. Decision Guide: Closure vs Class vs Decorator

```text
CHOOSING THE RIGHT STATE ARCHITECTURE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
Lightweight state with a single callable action         Closure (Factory Function)
Multiple methods modifying shared mutable state         Standard Class
Cross-cutting concerns (logging, timing, auth, retries) Function Decorator
Decorator needing administrative inspection/reset API   Class Decorator (__call__)
Fast in-memory caching of pure deterministic functions  @functools.lru_cache
─────────────────────────────────────────────────────────────────────────────
```

### Decision Flowchart

```text
Do you need to wrap existing functions with reusable cross-cutting logic?
  YES ──> Does the decorator need its own reset/inspection methods?
            YES ──> Class-Based Decorator (with __call__)
            NO  ──> Standard Function Decorator (@functools.wraps)
  NO  ──> Do you need to bundle multiple methods with state?
            YES ──> Standard Python Class
            NO  ──> Stateful Closure (Function Factory)
```

---

## 13. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 06:

- [ ] What is the internal C struct representation of a Python function object?
- [ ] Can you explain the difference between pass-by-value and call-by-object-sharing?
- [ ] Why are default function arguments evaluated only once at definition time?
- [ ] How do `/` and `*` in function signatures protect public API contracts?
- [ ] How does a `PyCellObject` allow closure variables to outlive their enclosing function frame?
- [ ] Why is `@functools.wraps` strictly mandatory when authoring production decorators?
- [ ] In what order do stacked decorators execute?
- [ ] How do you inspect function parameter metadata using `inspect.signature`?
- [ ] When would you author a class-based decorator implementing `__call__`?
- [ ] Why must all arguments to an `@functools.lru_cache` function be hashable?



---

## 14. functools.partial: Fixing Arguments to Create Specialized Functions

`functools.partial` returns a new callable with one or more arguments pre-filled.
The original function is unchanged; the partial object wraps it.

**Common use cases:** configuration factories, callbacks, adapters, reducing repetition.

```python
import functools

def send_alert(level: str, service: str, message: str) -> str:
    return f"[{level}] [{service}] {message}"

# Create specialized versions with level pre-filled:
send_critical = functools.partial(send_alert, "CRITICAL")
send_warning  = functools.partial(send_alert, "WARNING")

# Now service and message are the only required args:
print(send_critical("lims-db", "Connection pool exhausted"))
print(send_warning("auth-service", "Token expiring in 5 minutes"))

# Partial with keyword arguments:
def connect(host: str, port: int = 5432, ssl: bool = False) -> str:
    return f"Connecting to {host}:{port} (ssl={ssl})"

connect_prod_db = functools.partial(connect, host="10.0.0.1", ssl=True)
print(connect_prod_db(port=5433))  # host and ssl pre-filled
```

**How pre-filling works:**

```text
send_alert(level, service, message)
           ^
           | pre-filled by partial
           |
send_critical("lims-db", "Connection pool exhausted")
              ^^^^^^^^^   ^^^^^^^^^^^^^^^^^^^^^^^^^^
              service      message  (still required)
```

**partial vs lambda: key differences:**

| Feature            | functools.partial          | lambda                      |
|--------------------|----------------------------|-----------------------------|
| `__name__`         | Preserved from original    | Always `<lambda>`           |
| `__doc__`          | Inherited from original    | None                        |
| Introspection      | `.func`, `.args`, `.keywords` attributes | Opaque        |
| Keyword pre-fill   | Yes                        | Yes (via default args)      |
| Readability        | Intent is explicit         | Can be terse / cryptic      |

Use `partial` when the wrapped function's identity and documentation matter (e.g., logging, debugging, frameworks that inspect callables).

---

## 15. functools.cache and functools.cached_property

### functools.cache (Python 3.9+)

`@functools.cache` is an unbounded memoization cache.
It is equivalent to `@functools.lru_cache(maxsize=None)` but with less overhead.
Use it for **pure functions** whose input space is small and bounded.

### functools.cached_property

`@functools.cached_property` computes a property **once** on first access and stores
the result directly on the instance's `__dict__`. Subsequent accesses bypass the
descriptor entirely and read from the instance dictionary.

```python
import functools
import time

# functools.cache: infinite cache (use for pure functions with bounded inputs)
@functools.cache
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

start = time.perf_counter()
print(fibonacci(50))   # Instant due to memoization
elapsed = time.perf_counter() - start
print(f"Computed in {elapsed:.6f}s")
print(fibonacci.cache_info())  # CacheInfo showing hits vs misses

# functools.cached_property: expensive one-time computation on instance
from dataclasses import dataclass

@dataclass
class GenomicRead:
    sequence: str

    @functools.cached_property
    def gc_content(self) -> float:
        """Computed once; stored as instance attribute after first access."""
        gc = sum(1 for base in self.sequence if base in "GC")
        return gc / len(self.sequence)

read = GenomicRead("AGCTGCATGC")
print(read.gc_content)  # Computed here
print(read.gc_content)  # Retrieved from __dict__, no recomputation
print(read.__dict__)    # Shows 'gc_content' stored directly
```

**Where results are stored:**

```text
@functools.cache              @functools.cached_property
      |                                 |
      v                                 v
 function object                 instance.__dict__
 (shared across                  (per-instance;
  all calls)                      not shared)
```

**Comparison table:**

| Feature               | lru_cache(maxsize=N) | functools.cache       | cached_property          |
|-----------------------|----------------------|-----------------------|--------------------------|
| Applies to            | Functions            | Functions             | Instance methods/props   |
| Cache location        | Function object      | Function object       | Instance `__dict__`      |
| Size limit            | Configurable         | Unlimited             | N/A (one value/instance) |
| Eviction              | LRU                  | Never                 | Never (until del)        |
| Thread-safe           | Yes                  | Yes                   | No (needs locking)       |
| Available since       | 3.2                  | 3.9                   | 3.8                      |

---

## 16. Higher-Order Functions: map, filter, reduce

**Higher-order functions** accept or return other functions.
`map`, `filter`, and `functools.reduce` are the classic trio.

Both `map()` and `filter()` return **lazy iterators**: they produce values on demand.
Wrap with `list()` to materialize all results at once.

```python
import functools

readings = [12.4, -1.0, 45.8, 0.0, 99.1, -3.2, 22.0]

# filter: keep only positive readings (lazy iterator)
positives = list(filter(lambda x: x > 0, readings))
print(f"Positives: {positives}")

# map: normalize all readings to 0-100 scale (lazy iterator)
max_val = max(positives)
normalized = list(map(lambda x: round(x / max_val * 100, 1), positives))
print(f"Normalized: {normalized}")

# reduce: cumulative product (fold left)
values = [2, 3, 4, 5]
product = functools.reduce(lambda acc, x: acc * x, values)
print(f"Product: {product}")  # 120

# Equivalent comprehension (often clearer):
positives_comp = [x for x in readings if x > 0]
normalized_comp = [round(x / max_val * 100, 1) for x in positives_comp]
```

**How reduce accumulates:**

```text
values = [2, 3, 4, 5]

Step 1: acc=2,  x=3  -> 2 * 3  = 6
Step 2: acc=6,  x=4  -> 6 * 4  = 24
Step 3: acc=24, x=5  -> 24 * 5 = 120
                                  ^^^
                              final result
```

**Readability and performance comparison:**

```text
+---------------------+---------------+------------------+---------------------+
| Approach            | Lazy?         | Readable?        | Best for            |
+---------------------+---------------+------------------+---------------------+
| map(fn, iterable)   | Yes           | Moderate         | Passing callables   |
| filter(fn, iter)    | Yes           | Moderate         | Passing predicates  |
| List comprehension  | No (eager)    | High             | Most everyday cases |
| Generator expression| Yes           | High             | Large/streaming data|
| functools.reduce    | No (eager)    | Low (for simple) | Left fold / accum.  |
+---------------------+---------------+------------------+---------------------+
```

**When to prefer each:**
- Use `map`/`filter` when passing an already-named function (avoids a lambda wrapper).
- Use list comprehensions for most transformation and filtering tasks: they are
  easier to read and debug.
- Use generator expressions when memory matters or the result feeds directly into
  another iterator consumer.
- Use `reduce` only when the fold pattern is genuinely cleaner than an explicit loop.

---

## 17. Extended Review Checklist

The items below extend the checklist in section 13. Work through both lists before
moving to Day 06.

- [ ] How does `functools.partial` differ from writing a lambda that wraps a function?
- [ ] What is the difference between `functools.cache`, `functools.lru_cache`, and `functools.cached_property`?
- [ ] When would you choose `map()`/`filter()` over a list comprehension?
