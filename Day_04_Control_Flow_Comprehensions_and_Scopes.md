# Day 04: Control Flow, Scopes, and Comprehensions

---

## 1. The Systems Mental Model: Scope and the LEGB Rule

In C++ or Java, variable scope is strictly block-scoped by curly braces `{}`. A variable declared inside an `if` block or `for` loop does not exist outside that block.

In Python, **blocks (like `if`, `for`, `while`, `try`) do NOT create new scopes**. Only functions, classes, and modules create new namespaces.

```python
if True:
    message = "created inside if-block"

# In C++/Java, this is a compilation error.
# In Python, this is completely valid:
print(message)  # "created inside if-block"
```

### The LEGB Scope Resolution Hierarchy

When CPython resolves a variable name, it searches four nested namespaces in strict sequential order:

```text
  Local (L)         -> Names assigned inside the currently executing function
       │
       ▼
  Enclosing (E)     -> Names in the local scope of any enclosing functions (closures)
       │
       ▼
  Global (G)        -> Names assigned at the top-level of the current module/file
       │
       ▼
  Built-in (B)      -> Pre-loaded names in standard library (len, range, ValueError)
```

```text
ASCII Diagram: The LEGB Lookup Chain

  ┌───────────────────────────────────────────────────────────┐
  │ Built-in Scope (len, str, int, dict, Exception)          │
  │  ┌─────────────────────────────────────────────────────┐  │
  │  │ Global Scope (module-level functions & variables)   │  │
  │  │  ┌───────────────────────────────────────────────┐  │  │
  │  │  │ Enclosing Scope (outer enclosing function)    │  │  │
  │  │  │  ┌─────────────────────────────────────────┐  │  │  │
  │  │  │  │ Local Scope (current function frame)    │  │  │  │
  │  │  │  │ Name: x  ───[Found here? Stop search]───┼──┼──┼──┤
  │  │  │  └─────────────────────────────────────────┘  │  │  │
  │  │  └───────────────────────────────────────────────┘  │  │
  │  └─────────────────────────────────────────────────────┘  │
  └───────────────────────────────────────────────────────────┘
```

If a name is not found in any of these four scopes, CPython raises a `NameError`.

---

## 2. Modifying Outer Scopes: `global` and `nonlocal`

Because Python binds variables upon assignment, assigning to a name inside a function automatically creates a **local variable**, shadowing any outer variable with the same name.

### The `UnboundLocalError` Trap

```python
counter = 0

def bad_increment():
    # CPython inspects the function at compile-time and marks 'counter' as local
    # because of the assignment below.
    # Therefore, reading it before assignment raises an error:
    counter += 1  # UnboundLocalError: local variable 'counter' referenced before assignment

def good_increment():
    global counter
    counter += 1  # Explicitly points to the module-level global namespace
```

### The `nonlocal` Keyword (Enclosing Scopes)

In closures, you often need to mutate a variable in the enclosing outer function without promoting it to a global variable.

```python
def make_accumulator(initial_value: int = 0):
    total = initial_value  # Enclosing scope variable

    def accumulate(delta: int) -> int:
        nonlocal total     # Rebinds to enclosing frame, NOT global
        total += delta
        return total

    return accumulate

acc = make_accumulator(10)
print(acc(5))  # 15
print(acc(3))  # 18
```

| Keyword | Modifies Scope | Use Case |
| :--- | :--- | :--- |
| *(None)* | Local | Normal variable assignment inside function. |
| `nonlocal` | Enclosing | Stateful closures and function factories. |
| `global` | Global (Module) | Shared module state (use sparingly in production). |

---

## 3. Structural Pattern Matching (`match/case`)

Introduced in Python 3.10 (PEP 634), `match/case` is not a simple C-style switch statement. It is a full **structural pattern matcher** with destructuring, type checking, and conditional guards.

### Comparing C-Style Switch vs Python Pattern Matching

```text
C / Java Switch:
  - Matches primitive values, enums, or strings against constants.
  - Fall-through semantics require explicit 'break'.

Python match/case:
  - Destructures complex nested objects (dicts, lists, dataclasses, tuples).
  - Extracts bound variables during the match.
  - Validates types and nested structural shapes.
  - Zero fall-through: only the first matching branch executes.
```

### Runnable Production Example: Parsing Network Events

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class Packet:
    protocol: str
    port: int
    payload: dict[str, Any]

def process_event(event: Any) -> str:
    match event:
        # 1. Matching primitive literal values:
        case 200:
            return "HTTP OK"

        # 2. Sequence destructuring with wildcard capture:
        case ["AUTH", username, ("ADMIN" | "ROOT")]:
            return f"Privileged login for user: {username}"

        case ["AUTH", username, role]:
            return f"Standard login for user: {username} with role: {role}"

        # 3. Object / Dataclass pattern matching with conditional guards:
        case Packet(protocol="TLS", port=443, payload={"cmd": "PING"}):
            return "Secure ping received"

        case Packet(protocol="HTTP", port=port) if port != 80:
            return f"Non-standard HTTP port: {port}"

        # 4. Dictionary shape matching:
        case {"type": "METRIC", "cpu": float(usage)} if usage > 90.0:
            return f"ALERT: High CPU utilization: {usage}%"

        # 5. Wildcard default catch-all:
        case _:
            return "Unknown event format"

print(process_event(["AUTH", "karthik", "ADMIN"]))
print(process_event(Packet("TLS", 443, {"cmd": "PING"})))
print(process_event({"type": "METRIC", "cpu": 94.5}))
print(process_event("unexpected_string"))
```

---

## 4. The `for/else` and `while/else` Loop Construct

In Python, loops have an optional `else` block. 

The `else` block executes **only if the loop completed normally without hitting a `break` statement**.

```text
Loop Execution Flow:

  [Start Loop] ───> [Condition / Items Exhausted?] ──YES──> [Execute ELSE Block] ──> [Done]
           │
           NO
           │
     [Execute Body]
           │
     [Hit 'break'?] ──YES───────────────────────────────────> [Skip ELSE Block] ───> [Done]
           │
           NO
           │
           └───> (Next iteration)
```

### The Production Pattern: Search and Fallback

Without `for/else`, engineers use awkward flag variables (`found = False`).

```python
# ANTI-PATTERN: Flag variable clutter
def find_user_legacy(users: list[dict], target_id: int):
    found = False
    for user in users:
        if user["id"] == target_id:
            found = True
            process_user(user)
            break
    if not found:
        handle_user_not_found()

# IDIOMATIC PYTHON: for/else clean search
def find_user(users: list[dict], target_id: int):
    for user in users:
        if user["id"] == target_id:
            return user
    # If loop finishes without returning/breaking:
    raise ValueError(f"User {target_id} not found")
```

---

## 5. Comprehensions Under the Hood

Comprehensions are not merely syntactic sugar for `for` loops. They compile to specialized bytecode that executes at C-level speed.

### Bytecode Comparison: `for` Loop vs List Comprehension

```python
import dis

def loop_build():
    result = []
    for x in range(100):
        result.append(x * 2)
    return result

def comp_build():
    return [x * 2 for x in range(100)]
```

### Why Comprehensions are Asymptotically Faster
1. **Direct C-level appending:** Comprehensions use the dedicated opcode `LIST_APPEND`, which pushes pointers directly to the internal C array without looking up the `.append` attribute on each iteration.
2. **Eliminates method lookup overhead:** In `result.append(x)`, Python must resolve `getattr(result, 'append')` on every loop iteration unless locally bound.

### Dict and Set Comprehensions

```python
# Dict Comprehension: Mapping IDs to usernames:
raw_users = [("usr_101", "alice"), ("usr_102", "bob"), ("usr_103", "charlie")]
user_map = {uid: name.title() for uid, name in raw_users if not name.startswith("a")}

# Set Comprehension: Deduplicating normalized domains:
emails = ["karthik@work.com", "dev@WORK.COM", "support@phsa.ca", "info@work.com"]
unique_domains = {email.split("@")[1].lower() for email in emails}
print(unique_domains)  # {'work.com', 'phsa.ca'}
```

---

## 6. Common Pitfalls and Systems Traps

### Pitfall 1: Late Binding in Closures and Loops
When creating functions or lambdas inside a loop, variables are looked up **at call time, not definition time**.

```python
# FATAL BUG: Late binding closure
callbacks = []
for i in range(3):
    callbacks.append(lambda: i)

# Expected: [0, 1, 2]
# Actual: [2, 2, 2] ! Because 'i' is looked up when called, and loop ended at 2!
print([cb() for cb in callbacks])

# FIX: Force early binding using default argument trick or functools.partial:
callbacks_fixed = []
for i in range(3):
    callbacks_fixed.append(lambda val=i: val)  # Evaluated and bound at definition time

print([cb() for cb in callbacks_fixed])  # [0, 1, 2]
```

### Pitfall 2: Modifying Loop Variable Inside `for` Loop
In C/C++, changing the loop index variable changes the loop trajectory:
```c
for (int i = 0; i < 10; i++) {
    if (skip_condition) i++; // Skips next iteration in C++
}
```
In Python, modifying the loop variable has **zero effect** on the next iteration because `for` calls `next()` on the underlying iterator:
```python
for i in range(5):
    if i == 2:
        i = 99  # Does NOT change the next value produced by range(5)!
    print(i, end=" ")
# Output: 0 1 99 3 4 (Next iteration returns 3 as planned)
```

---

## 7. Hands-On Systems Challenge: Telemetry Packet Router

### The Problem
In distributed healthcare and telemetry platforms, ingestion engines receive high-volume JSON-like event dictionaries.

Build an event router `RouteEngine` that:
1. Uses `match/case` to parse and route structured packets.
2. Extracts payload metadata using destructuring and guards.
3. Tracks telemetry counters per event type using a stateful closure.
4. Rejects malformed packets with defensive custom exceptions.

### Complete Runnable Implementation

```python
from dataclasses import dataclass
from typing import Any

class InvalidPacketError(Exception):
    pass

@dataclass
class RouteResult:
    destination: str
    device_id: str
    metric: float
    status: str

def make_metrics_tracker():
    """Stateful closure tracking routed packet counts across scopes."""
    counts: dict[str, int] = {}
    
    def record(category: str) -> dict[str, int]:
        nonlocal counts
        counts[category] = counts.get(category, 0) + 1
        return dict(counts)  # Return snapshot
        
    return record

class RouteEngine:
    def __init__(self):
        self.tracker = make_metrics_tracker()

    def route(self, packet: dict[str, Any]) -> RouteResult:
        match packet:
            # Match heart rate / critical telemetry
            case {
                "source": "BIOSENSOR",
                "device_id": str(did),
                "vital": "HR",
                "value": (int() | float()) as bpm
            } if bpm > 140 or bpm < 40:
                self.tracker("CRITICAL_ALARM")
                return RouteResult("EMERGENCY_QUEUE", did, float(bpm), "CRITICAL")

            # Match standard telemetry
            case {
                "source": "BIOSENSOR",
                "device_id": str(did),
                "vital": str(vital_type),
                "value": (int() | float()) as val
            }:
                self.tracker("NORMAL_TELEMETRY")
                return RouteResult("ANALYTICS_STREAM", did, float(val), "NORMAL")

            # Match network keep-alive
            case {"source": "GATEWAY", "device_id": str(did), "ping": True}:
                self.tracker("HEALTHCHECK")
                return RouteResult("HEARTBEAT_LOG", did, 0.0, "OK")

            # Malformed catch-all
            case _:
                self.tracker("MALFORMED")
                raise InvalidPacketError(f"Rejected unsupported packet shape: {packet}")

def test_route_engine():
    engine = RouteEngine()
    
    # 1. Critical alarm test
    res1 = engine.route({"source": "BIOSENSOR", "device_id": "DEV_01", "vital": "HR", "value": 155})
    assert res1.destination == "EMERGENCY_QUEUE"
    assert res1.status == "CRITICAL"
    
    # 2. Normal telemetry test
    res2 = engine.route({"source": "BIOSENSOR", "device_id": "DEV_02", "vital": "SPO2", "value": 98.0})
    assert res2.destination == "ANALYTICS_STREAM"
    
    # 3. Heartbeat test
    res3 = engine.route({"source": "GATEWAY", "device_id": "GW_ALPHA", "ping": True})
    assert res3.destination == "HEARTBEAT_LOG"
    
    # 4. Error test
    try:
        engine.route({"source": "CORRUPTED_SOURCE"})
        assert False, "Should have raised InvalidPacketError"
    except InvalidPacketError:
        pass
        
    summary = engine.tracker("REPORT")
    print("Routing engine executed successfully:")
    for category, count in summary.items():
        if category != "REPORT":
            print(f"  {category:<20}: {count} packets")

if __name__ == "__main__":
    test_route_engine()
```

---

## 9. The Walrus Operator (`:=` Assignment Expressions)

Introduced in Python 3.8 (PEP 572), the walrus operator allows you to **assign a value to a variable within an expression**, eliminating redundant function calls and awkward multi-line setup loops.

### Syntax and Comparison

```text
Without Walrus Operator (Repeated execution or outer variable clutter):
  line = stream.readline()
  while line:
      process(line)
      line = stream.readline()

With Walrus Operator (Assignment and condition evaluated in one step):
  while (line := stream.readline()):
      process(line)
```

### Runnable Production Examples

```python
import re

# Example 1: Stream chunk reader
def mock_network_stream():
    chunks = ["chunk_alpha", "chunk_beta", "chunk_gamma", ""]
    return iter(chunks)

stream = mock_network_stream()
# Reads and binds chunk simultaneously:
while (chunk := next(stream)):
    print(f"Processing: {chunk}")

# Example 2: Regex extraction without re-matching
log_entry = "ERROR 2026-11-10 [lims-db] Connection timeout after 5000ms"
pattern = re.compile(r"timeout after (\d+)ms")

# Assign match object directly inside the if guard:
if (match := pattern.search(log_entry)):
    timeout_duration = int(match.group(1))
    print(f"Extracted timeout: {timeout_duration} ms")

# Example 3: List comprehension filtering and transforming expensive calls
def expensive_metric_calc(val: int) -> float:
    return (val * 1.85) ** 1.2

raw_readings = [10, 45, 80, 120, 200]
# Without walrus: calls expensive_metric_calc(x) TWICE per item
# With walrus: calls it ONCE and binds to 'm':
filtered_metrics = [m for x in raw_readings if (m := expensive_metric_calc(x)) > 100.0]
print(f"Filtered metrics: {filtered_metrics}")
```

---

## 10. Exception Control Flow: `try / except / else / finally`

In Python, exceptions are not just for fatal errors; they are an integral part of control flow (following the EAFP principle: *Easier to Ask for Forgiveness than Permission*).

### The Complete 4-Part Structure

```text
  try:
      # Code that might raise an exception
  except SpecificError as err:
      # Runs ONLY if SpecificError occurred
  else:
      # Runs ONLY if NO exception was raised in try block
  finally:
      # ALWAYS runs, regardless of whether exceptions were raised or caught
```

### Why the `else` Block is Essential
Putting code in `else` rather than at the end of `try` prevents inadvertently catching exceptions raised by your success handler.

```python
def load_and_process_config(filepath: str) -> dict:
    try:
        with open(filepath, "r") as f:
            raw_text = f.read()
    except FileNotFoundError:
        # Strictly handles missing file
        return {"status": "DEFAULT_CONFIG"}
    else:
        # Runs ONLY if file opened and read successfully.
        # If parsing fails here, it is NOT caught by FileNotFoundError!
        return parse_custom_json(raw_text)
    finally:
        # Guarantee audit trail or metrics recording
        record_access_attempt(filepath)
```

### Python 3.11+ Zero-Cost Exception Handling
In Python 3.11+, CPython replaced runtime stack unwinding setup with a **static table-based exception system** (similar to DWARF unwinding in C++).
* When no exception is raised, `try` blocks execute with **zero performance overhead** (no extra opcodes).
* Only when an exception is raised does CPython consult the exception table.

---

## 11. Control Flow Comparison: `match/case` vs `if/elif` vs Dispatch Table

| Feature | `if / elif / else` | `match / case` | Dictionary Dispatch Table |
| :--- | :--- | :--- | :--- |
| **Primary Strength** | Simple boolean conditions | Structural shape and destructuring | High-speed exact-key lookup |
| **Destructuring Support** | Manual unpacking | Native automatic unpacking | No |
| **Type Checking** | Manual `isinstance()` | Native type patterns | No |
| **Time Complexity** | $O(N)$ linear checks | $O(N)$ branch checks | $O(1)$ constant time lookup |
| **Best Use Case** | Numeric ranges, simple flags | AST parsing, packets, nested JSON | Dynamic commands, event routing |

---

## 12. Control Flow Decision Guide & ASCII Decision Flowchart

```text
CONTROL FLOW DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                            USE THIS
─────────────────────────────────────────────────────────────────────────────
Evaluating simple boolean conditions                if / elif / else
Extracting values from complex nested structures    match / case with destructuring
Validating types and guards in one step             match / case with 'if' guard
Searching for an item with fallback on not-found    for / else (break on found)
Mapping exact keys to handler functions             Dictionary dispatch table
Assigning and checking an expression in one line    Walrus operator (:=)
Cleaning up resources regardless of success/error   try / finally or context manager
Running success logic only when try block succeeds  try / except / else
─────────────────────────────────────────────────────────────────────────────
```

### Decision Flowchart

```text
Do you need to match against structured or nested shapes?
  YES ──> match / case (with pattern destructuring)
  NO  ──> Is it an exact-match command or token dispatch?
            YES ──> Dictionary Dispatch Table (O(1) lookup)
            NO  ──> Are you searching an iterable for a target?
                      YES ──> for / else (break when found)
                      NO  ──> if / elif / else
```

---

## 13. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 05:

- [ ] Explain the exact search order of the LEGB rule.
- [ ] Why does Python not have block scope for `if` and `for` statements?
- [ ] What causes an `UnboundLocalError` when modifying a global counter inside a function?
- [ ] How does `nonlocal` differ from `global` in nested closures?
- [ ] How does `match/case` destructuring differ from a traditional C switch statement?
- [ ] When does the `else` block of a `for` loop execute?
- [ ] Why does `[lambda: i for i in range(3)]` fail to bind unique values, and how do you fix it?
- [ ] How does the walrus operator (`:=`) eliminate redundant calculations in loops and comprehensions?
- [ ] What is the exact execution guarantee of `try / except / else / finally`?
- [ ] Why is a dictionary dispatch table faster than long chains of `if/elif`?



---

## 14. Nested Comprehensions and Performance Traps

A nested comprehension follows the same left-to-right order as the equivalent nested `for` loops. The outer loop comes first, the inner loop second.

```text
[expression  for outer in iterable  for inner in outer]
 ^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^
 what to     outer loop (runs        inner loop (runs
 collect     once per row)           once per element)
```

**Flattening a 2D matrix:**

```python
# 2D matrix flattening:
matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
flat = [x for row in matrix for x in row]
print(flat)  # [1, 2, 3, 4, 5, 6, 7, 8, 9]

# Conditional nested: only even values from matrix
even_values = [x for row in matrix for x in row if x % 2 == 0]
print(even_values)  # [2, 4, 6, 8]

# When this gets unreadable, use a generator pipeline instead:
def flatten(matrix):
    for row in matrix:
        yield from row

# Equivalent and readable:
even_generator = (x for x in flatten(matrix) if x % 2 == 0)
print(list(even_generator))  # [2, 4, 6, 8]
```

**When nested comprehensions help vs. hurt:**

| Situation | Recommendation |
|---|---|
| Simple 2-level flatten, short variable names | Nested comprehension is fine |
| Three or more levels of nesting | Split into named loops or generator functions |
| Logic requires intermediate variables | Use explicit loops for clarity |
| Large dataset, need lazy evaluation | Use a generator pipeline (`yield from`) |

**Key point:** A nested comprehension builds the entire result list in memory at once. A generator pipeline produces values one at a time, using far less memory for large datasets.

---

## 15. Dictionary Dispatch Tables

A dispatch table is a plain `dict` that maps keys (usually strings or enums) to callable functions. Looking up a key in a dict is O(1) regardless of the number of entries. An `if/elif` chain is O(N): Python evaluates each condition in sequence until one matches.

```text
if/elif chain (O(N)):              Dispatch table (O(1)):
                                   
command == "start"?  -> check 1    hash("start") -> bucket -> handler
command == "stop"?   -> check 2    Hash computed once. No scanning.
command == "status"? -> check 3
command == "reset"?  -> check 4    With 1000 commands:
...                                  if/elif: up to 1000 checks
N commands = up to N checks          dispatch: always 1 lookup
```

```python
from typing import Callable

# Without dispatch table: O(N) linear scan through elif chain
def handle_command_slow(command: str) -> str:
    if command == "start":
        return "Starting pipeline..."
    elif command == "stop":
        return "Stopping pipeline..."
    elif command == "status":
        return "Pipeline running."
    elif command == "reset":
        return "Resetting pipeline..."
    else:
        return f"Unknown command: {command}"

# With dispatch table: O(1) dict lookup
COMMAND_HANDLERS: dict[str, Callable[[], str]] = {
    "start":  lambda: "Starting pipeline...",
    "stop":   lambda: "Stopping pipeline...",
    "status": lambda: "Pipeline running.",
    "reset":  lambda: "Resetting pipeline...",
}

def handle_command_fast(command: str) -> str:
    handler = COMMAND_HANDLERS.get(command)
    if handler is None:
        return f"Unknown command: {command}"
    return handler()

# More advanced: dispatch with arguments using functools.partial
import functools

def process_job(job_type: str, priority: int) -> str:
    return f"Processing {job_type} at priority {priority}"

JOB_DISPATCH: dict[str, Callable] = {
    "URGENT": functools.partial(process_job, priority=1),
    "NORMAL": functools.partial(process_job, priority=5),
    "BATCH":  functools.partial(process_job, priority=10),
}

result = JOB_DISPATCH["URGENT"](job_type="alignment")
print(result)
```

`functools.partial` pre-fills known arguments and returns a new callable. The dispatch table stores these pre-configured callables so callers only supply the remaining arguments.

---

## 16. The `try/except` EAFP vs LBYL Pattern

Python code is typically written in the EAFP style. Most other languages default to LBYL.

**LBYL (Look Before You Leap):** Check whether an operation is safe before performing it.

**EAFP (Easier to Ask Forgiveness than Permission):** Attempt the operation directly and handle the exception if it fails.

```text
LBYL                              EAFP
----                              ----
if key in d:        <-- check     try:
    value = d[key]  <-- access        value = d[key]   <-- attempt
else:                             except KeyError:
    value = default                   value = default
```

| Criterion | LBYL | EAFP |
|---|---|---|
| Style origin | C / Java | Python |
| Success path performance | Slight overhead (double lookup) | Faster (single lookup) |
| Failure path performance | Cheap (no exception) | Slower (exception overhead) |
| Thread safety | Risk: state may change between check and access | Safer (atomic attempt) |
| Readability | Clear intent upfront | Intent visible in `except` clause |
| When to prefer | Failure equally likely; cheap guard check | Success far more common than failure |

```python
# LBYL (Look Before You Leap) - C/Java style
def get_config_value_lbyl(config: dict, key: str) -> str:
    if key in config:          # Check first
        return config[key]
    return "DEFAULT"

# EAFP (Easier to Ask Forgiveness than Permission) - Pythonic
def get_config_value_eafp(config: dict, key: str) -> str:
    try:
        return config[key]     # Try directly
    except KeyError:
        return "DEFAULT"

# EAFP is preferred when:
# - The success path is far more common than failure
# - The check and access are not atomic (race conditions in multithreading)

# LBYL is preferred when:
# - The failure is equally likely as success
# - Exceptions are expensive (e.g., inside hot inner loops)
# - The check is cheap and readable

config = {"timeout": "5000", "mode": "prod"}
print(get_config_value_eafp(config, "timeout"))  # 5000
print(get_config_value_eafp(config, "missing"))  # DEFAULT
```

**Performance note:** In a tight inner loop running millions of iterations, raising and catching exceptions carries interpreter overhead each time the exception path fires. If the failure rate is high inside such a loop, benchmark both styles with `timeit` before choosing.

---

## 17. Checklist (Extended)

> Items 1-13 are retained from the original checklist above. New items added below.

- [ ] How does a nested comprehension `[x for row in matrix for x in row]` read differently from two nested for-loops?
- [ ] Why is a dictionary dispatch table O(1) while an if/elif chain is O(N)?
- [ ] What is the difference between EAFP and LBYL, and when should you prefer each?
