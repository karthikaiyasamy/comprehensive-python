# Day 09: Static Typing, Mypy, and Defensive Code Architecture

---

## 1. The Systems Mental Model: Gradual Typing and Type Erasure

In statically typed languages like C++ or Java, type annotations are strictly enforced by the compiler and dictate physical memory layout (e.g., allocating a 32-bit register for `int32_t`).

In Python, **type hints have zero effect on runtime execution or memory layout**.
* The CPython interpreter parses type annotations and stores them in `__annotations__`.
* It then **erases them from bytecode execution**.
* A function annotated as `def add(a: int, b: int) -> int:` will happily accept strings, lists, or custom classes at runtime without raising an error.

```text
ASCII Diagram: The Static Analysis vs Runtime Execution Split

  [ Source Code with Type Hints ]
               │
       ┌───────┴────────────────────────┐
       ▼                                ▼
  [ Static Analyzer: Mypy / Pyright ] [ CPython Interpreter: python app.py ]
  ├─ Inspects AST & types             ├─ Ignores type hints completely!
  ├─ Enforces API contracts           ├─ Compiles opcodes to bytecode
  └─ Blocks build if types mismatch   └─ Executes dynamically at runtime
```

### Why Use Static Typing in Python?
1. **Prevents Runtime Disasters:** Catches `NoneType has no attribute`, key errors, and type mismatches before deploying to cluster environments.
2. **Self-Documenting Codebase:** Replaces ambiguous docstring comments with IDE-verifiable signatures.
3. **Refactoring Safety:** Renaming parameters or altering data structures immediately highlights all broken call sites across hundreds of files.

---

## 2. Modern Type Hinting Syntax (Python 3.10+)

Modern Python eliminates the need to import legacy collection types from `typing`.

```python
# Modern Python 3.10+ Standard Syntax:
def process_pipeline(
    sample_ids: list[str],                  # Built-in list generic (not typing.List)
    metadata: dict[str, int | float],       # Union operator '|' (not typing.Union)
    threshold: float | None = None          # 'T | None' (replaces typing.Optional[T])
) -> set[tuple[str, bool]]:
    results: set[tuple[str, bool]] = set()
    for sid in sample_ids:
        score = metadata.get(sid, 0.0)
        passed = score >= (threshold if threshold is not None else 10.0)
        results.add((sid, passed))
    return results
```

### The Strict Distinction: `Any` vs `object`

| Type | Meaning to Mypy | Type Safety | What Operations Are Allowed? |
| :--- | :--- | :--- | :--- |
| `Any` | "Turn off type checking completely" | Zero safety | Everything (dynamically checked at runtime, dangerous) |
| `object` | "Any valid Python object" | 100% type-safe | Only operations valid on the base `object` class |

```python
from typing import Any

def unsafe_handler(val: Any):
    # Mypy allows this, but it crashes at runtime if val is an int:
    val.trim_whitespace()

def safe_handler(val: object):
    # Mypy BLOCKS this at compile time:
    # val.trim_whitespace()  # Error: "object" has no attribute "trim_whitespace"

    # You must narrow the type with isinstance:
    if isinstance(val, str):
        val.strip()  # Safe! Mypy narrows 'val' to str here.
```

---

## 3. Specialized Typing Constructs

### 1. `Literal`: Restricting Values to Exact Constants
Replaces magic strings and enums with strict literal checks:

```python
from typing import Literal

BuildMode = Literal["DEBUG", "RELEASE", "PROFILE"]

def compile_binary(mode: BuildMode) -> str:
    return f"Building target with {mode} flags"

compile_binary("RELEASE")  # Valid
# compile_binary("OPTIMIZED")  # Mypy Error: Argument has incompatible type Literal['OPTIMIZED']
```

### 2. `TypedDict`: Type-Safe Dictionary Schemas
Standard dictionaries have heterogeneous values (`dict[str, Any]`), which destroys type safety. `TypedDict` gives dictionary objects static schema validation without the overhead of converting to a class:

```python
from typing import TypedDict

class VariantPayload(TypedDict):
    chrom: str
    pos: int
    quality: float
    filter_pass: bool

# Mypy validates keys and value types:
valid_variant: VariantPayload = {
    "chrom": "chr1",
    "pos": 10450,
    "quality": 99.5,
    "filter_pass": True
}

# Mypy flags missing keys or wrong types:
# bad_variant: VariantPayload = {"chrom": "chr1", "pos": "WRONG_TYPE"} # Compile error!
```

### 3. `NewType`: Zero-Overhead Semantic Type Safety
In C++, a `typedef` is just an alias. In Rust or Haskell, you can create a distinct newtype. In Python, `NewType` creates distinct semantic types with **zero runtime overhead**:

```python
from typing import NewType

PatientId = NewType("PatientId", str)
SampleId = NewType("SampleId", str)

def register_sample(pid: PatientId, sid: SampleId) -> None:
    print(f"Registering Sample {sid} for Patient {pid}")

p = PatientId("PATIENT_909")
s = SampleId("SAMPLE_101")

register_sample(p, s)  # Valid

# Accidental parameter swap caught by Mypy:
# register_sample(s, p)
# Mypy Error: Argument 1 has incompatible type "SampleId"; expected "PatientId"
```

---

## 4. Generics and `TypeVar`

To write reusable, type-safe data structures and algorithms, use `TypeVar` and `Generic`.

```python
from typing import TypeVar, Generic

T = TypeVar("T")

class Stack(Generic[T]):
    """Type-safe LIFO stack."""
    def __init__(self):
        self._items: list[T] = []

    def push(self, item: T) -> None:
        self._items.append(item)

    def pop(self) -> T:
        if not self._items:
            raise IndexError("pop from empty stack")
        return self._items.pop()

# Concrete usage:
int_stack: Stack[int] = Stack()
int_stack.push(10)
# int_stack.push("hello")  # Mypy Error: Argument 1 to "push" has incompatible type "str"; expected "int"
val: int = int_stack.pop()
```

---

## 5. Defensive Exception Architecture

In production software engineering, clean error handling requires structured domain exception hierarchies and explicit causal chaining.

### 1. Designing Domain Exception Trees
Always create a base exception for your module/system so consumers can catch all domain-specific errors without catching unrelated system errors:

```text
  Exception (Built-in Python base)
     └── BasePipelineError (Your root module exception)
            ├── IngestionError (Parsing / format failures)
            ├── AlignmentError (Cluster tool crashes)
            └── QCValidationError (Threshold / quality failures)
```

```python
class BasePipelineError(Exception):
    """Base class for all genomic pipeline errors."""
    pass

class IngestionError(BasePipelineError):
    """Raised when parsing or input validation fails."""
    pass

class QCValidationError(BasePipelineError):
    """Raised when quality scores fail clinical thresholds."""
    def __init__(self, sample_id: str, score: float, min_threshold: float):
        self.sample_id = sample_id
        self.score = score
        self.min_threshold = min_threshold
        super().__init__(
            f"Sample '{sample_id}' failed QC: Score {score:.1f} is below minimum {min_threshold:.1f}"
        )
```

### 2. Explicit Exception Chaining: `raise ... from`
When wrapping low-level errors (like `KeyError` or `IOError`) inside high-level domain exceptions, use `from` (PEP 3134) to preserve the original causal stack trace:

```python
def load_sample_file(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return {"data": f.read()}
    except FileNotFoundError as original_err:
        # Preserves original error in traceback (__cause__):
        raise IngestionError(f"Could not load sample file: {path}") from original_err

# If you intentionally want to suppress low-level internal traceback:
def sanitize_secret_error():
    try:
        connect_to_internal_vault()
    except Exception:
        # Suppresses __context__; hides internal server details from logs:
        raise PermissionError("Access denied") from None
```

---

## 6. PEP 8 Standards and Clean Code Rules

Adhering to PEP 8 ensures that code is immediately readable and maintainable across enterprise teams.

### Naming Conventions

| Entity | Convention | Example |
| :--- | :--- | :--- |
| **Modules / Files** | `snake_case.py` | `variant_caller.py` |
| **Classes / Exceptions** | `PascalCase` | `GenomicRecord`, `QCValidationError` |
| **Functions & Methods** | `snake_case()` | `align_reads()`, `calculate_gc()` |
| **Constants** | `SCREAMING_SNAKE_CASE` | `MAX_CLUSTER_CORES = 64` |
| **Internal Attributes** | `_leading_underscore` | `self._internal_cache = {}` |
| **Type Variables** | Single letter or `PascalCase` | `T = TypeVar("T")`, `RecordT` |

### PEP 257 Docstring Standards
Every public module, class, and method must have a structured docstring. Follow the **Google Python Style Guide**:

```python
def filter_variants(
    variants: list[dict],
    min_quality: float = 30.0,
    *,
    require_pass: bool = True
) -> list[dict]:
    """Filters variant dictionaries based on quality and pass criteria.

    Args:
        variants: A list of variant records containing quality scores.
        min_quality: The minimum Phred-scaled quality score required to pass.
        require_pass: If True, filters out variants with FILTER != 'PASS'.

    Returns:
        A list of filtered variant dictionaries matching the criteria.

    Raises:
        ValueError: If min_quality is negative.
    """
    if min_quality < 0:
        raise ValueError(f"min_quality cannot be negative: {min_quality}")
    return [v for v in variants if v.get("qual", 0.0) >= min_quality]
```

---

## 7. Common Pitfalls and Systems Traps

### Pitfall 1: Catching Bare `except:`
```python
# FATAL ANTI-PATTERN:
try:
    long_running_pipeline()
except:
    # Catches KeyboardInterrupt (Ctrl+C) and SystemExit!
    # The process CANNOT BE KILLED or gracefully terminated by SLURM!
    print("Error occurred")

# CORRECT: Always catch Exception:
try:
    long_running_pipeline()
except Exception as err:
    # Lets KeyboardInterrupt and SystemExit propagate normally
    log.error(f"Pipeline error: {err}")
```

### Pitfall 2: Confusing Type Checking with Validation
Type annotations do **not** validate user input at runtime.
```python
def calculate_age(birth_year: int) -> int:
    return 2026 - birth_year

# This passes through without error at runtime if caller passes invalid string:
# calculate_age("1990") # TypeError: unsupported operand type(s) for -: 'int' and 'str'

# DEFENSIVE FIX: Validate data at system boundaries (APIs, files, user inputs)
def calculate_age_defensive(birth_year: int) -> int:
    if not isinstance(birth_year, int):
        raise TypeError(f"Expected int, got {type(birth_year).__name__}")
    return 2026 - birth_year
```

---

## 8. Hands-On Systems Challenge: Fully Typed Event Parser

### The Problem
Build a defensive, statically typed event parser `EventIngestor` that:
1. Defines payload structures using `TypedDict` and `Literal`.
2. Uses `NewType` for distinct `EventId` and `SessionId`.
3. Validates boundary data and raises structured domain exceptions with causal chaining.
4. Passes strict type validation (`mypy --strict`).

### Complete Runnable Implementation

```python
from typing import TypedDict, Literal, NewType
import json

EventId = NewType("EventId", str)
SessionId = NewType("SessionId", str)
EventStatus = Literal["PENDING", "ACTIVE", "COMPLETED", "FAILED"]

class EventPayload(TypedDict):
    event_id: str
    session_id: str
    status: EventStatus
    metric_value: float

class IngestionError(Exception):
    """Base exception for parsing errors."""
    pass

class SchemaValidationError(IngestionError):
    """Raised when JSON payload does not match expected schema."""
    pass

class EventIngestor:
    ALLOWED_STATUSES = {"PENDING", "ACTIVE", "COMPLETED", "FAILED"}

    def parse_raw_json(self, json_str: str) -> EventPayload:
        """Parses and validates boundary JSON into a type-safe TypedDict."""
        try:
            raw_data = json.loads(json_str)
        except json.JSONDecodeError as err:
            raise IngestionError("Malformed JSON input string") from err

        if not isinstance(raw_data, dict):
            raise SchemaValidationError(f"Expected JSON object, got {type(raw_data).__name__}")

        # Defensive runtime boundary validation:
        required_fields = {"event_id", "session_id", "status", "metric_value"}
        missing = required_fields - raw_data.keys()
        if missing:
            raise SchemaValidationError(f"Missing required fields: {sorted(missing)}")

        if raw_data["status"] not in self.ALLOWED_STATUSES:
            raise SchemaValidationError(f"Invalid status: {raw_data['status']}")

        if not isinstance(raw_data["metric_value"], (int, float)):
            raise SchemaValidationError(f"metric_value must be float, got {type(raw_data['metric_value']).__name__}")

        # Cast to validated TypedDict:
        return EventPayload(
            event_id=raw_data["event_id"],
            session_id=raw_data["session_id"],
            status=raw_data["status"],
            metric_value=float(raw_data["metric_value"])
        )

def test_event_ingestor():
    ingestor = EventIngestor()

    # Valid JSON test
    valid_json = '{"event_id": "EVT_01", "session_id": "SES_99", "status": "ACTIVE", "metric_value": 45.2}'
    event = ingestor.parse_raw_json(valid_json)
    assert event["status"] == "ACTIVE"
    assert event["metric_value"] == 45.2

    # Malformed JSON test (Verify causal chaining)
    try:
        ingestor.parse_raw_json("NOT_JSON")
        assert False, "Should have raised IngestionError"
    except IngestionError as err:
        assert err.__cause__ is not None  # JSONDecodeError preserved in chain!
        print(f"Causal error chain verified: {type(err).__name__} caused by {type(err.__cause__).__name__}")

    # Missing field test
    try:
        ingestor.parse_raw_json('{"event_id": "EVT_02"}')
        assert False, "Should have raised SchemaValidationError"
    except SchemaValidationError as err:
        print(f"Schema validation verified: {err}")

if __name__ == "__main__":
    test_event_ingestor()
```

---

## 9. Data Structure Representation Comparison Table

| Approach | Type Checking | Memory Overhead | Field Access | Mutability |
| :--- | :--- | :--- | :--- | :--- |
| `dict[str, Any]` | Weak | High (~152 B) | `d["key"]` | Mutable |
| `TypedDict` | Static only (Mypy) | High (~152 B) | `d["key"]` | Mutable |
| `namedtuple` | Static & Runtime | Minimal (~48 B) | `obj.key` or `obj[0]` | Immutable |
| `@dataclass` | Static & Optional Runtime | High (~152 B) | `obj.key` | Mutable by default |
| `@dataclass(slots=True)` | Static & Optional Runtime | Minimal (~48 B) | `obj.key` | Configurable |

---

## 10. Type System Decision Guide & ASCII Decision Flowchart

```text
TYPE SYSTEM DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
Heterogeneous dictionary from JSON API endpoint         TypedDict
Restricting a string/integer parameter to exact values  Literal["A", "B"]
Preventing accidental parameter swaps of same raw type  NewType("IdType", str)
Generic container or algorithm operating on any type    TypeVar / Generic[T]
Nullable return values or optional arguments            Type | None
Declaring that a function must return a specific type   Callable[[int], str]
Declaring a variable that must never be reassigned      Final[int]
─────────────────────────────────────────────────────────────────────────────
```

### Decision Flowchart

```text
Do you need to validate a dictionary without creating a class instance?
  YES ──> TypedDict
  NO  ──> Do you need distinct semantic identity for a primitive (e.g. UserId vs OrderId)?
            YES ──> NewType("UserId", str)
            NO  ──> Are you building an algorithm that operates across types?
                      YES ──> TypeVar / Generic[T]
                      NO  ──> Standard type hints (int, str, list[T], dict[K, V])
```

---

## 11. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 10:

- [ ] Explain why Python type hints have zero impact on runtime execution speed or memory layout.
- [ ] What is the exact difference between `Any` and `object` in Mypy?
- [ ] How does `Literal` provide strict compile-time value constraints?
- [ ] What is `TypedDict` and when is it preferred over a dataclass?
- [ ] How does `NewType` create zero-cost semantic types?
- [ ] How does `raise ... from original_err` preserve causal exception context?
- [ ] Why should you never use a bare `except:` clause?
- [ ] What is the difference between a `TypeVar` and a standard type hint?
- [ ] How do you document parameters and exceptions according to PEP 257 / Google style?


---

## 12. ParamSpec and Concatenate: Preserving Callable Signatures

When a decorator wraps a function, the inner `wrapper(*args, **kwargs)` discards
the original parameter names and types. Mypy then sees the decorated function as
`(*args: Any, **kwargs: Any) -> R`, which loses all call-site type checking.

`ParamSpec` (Python 3.10+) captures the full parameter specification of the
wrapped callable and threads it through the decorator so the signature survives.

```
Without ParamSpec                 With ParamSpec
----------------------            ----------------------
process_sample(...)               process_sample(sample_id: str,
  -> (*args, **kwargs)                             depth: int = 30,
     Mypy sees nothing                             *, qc_pass: bool = True)
                                     Mypy sees everything
```

```python
from typing import ParamSpec, TypeVar, Callable
import functools

P = ParamSpec("P")
R = TypeVar("R")

def audit_log(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that logs function calls while preserving exact signature."""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        print(f"[AUDIT] Calling: {func.__name__}")
        result = func(*args, **kwargs)
        print(f"[AUDIT] Done: {func.__name__}")
        return result
    return wrapper

@audit_log
def process_sample(sample_id: str, depth: int = 30, *, qc_pass: bool = True) -> dict:
    return {"id": sample_id, "depth": depth, "qc": qc_pass}

# Mypy now knows the decorated function has the exact same signature:
result = process_sample("S_001", depth=60, qc_pass=True)
print(result)
```

Key points:
- `P = ParamSpec("P")` acts like `TypeVar` but for a full parameter list.
- `wrapper(*args: P.args, **kwargs: P.kwargs)` is the required spelling; both
  annotations are needed together.
- Without `ParamSpec`, passing a wrong keyword argument to a decorated function
  would not be caught by Mypy at all.

---

## 13. Self Type and Fluent Builder Pattern

`Self` (Python 3.11+, or via `from __future__ import annotations` + `typing_extensions`
for earlier versions) lets a method declare that it returns the *actual* class of
the instance, not the base class.

This matters for the **fluent builder pattern**, where every method returns `self`
to allow chaining. Without `Self`, subclass chains break: Mypy would infer the
return as the base class and flag the next chained call as an error.

```
QueryBuilder()
    .from_table("variants")   -> Self (still QueryBuilder or any subclass)
    .where("quality >= 30")   -> Self
    .limit(1000)              -> Self
    .build()                  -> str
```

```python
from __future__ import annotations
from typing import Self

class QueryBuilder:
    """Fluent builder for constructing typed database queries."""

    def __init__(self):
        self._table: str = ""
        self._conditions: list[str] = []
        self._limit: int | None = None

    def from_table(self, table: str) -> Self:
        self._table = table
        return self

    def where(self, condition: str) -> Self:
        self._conditions.append(condition)
        return self

    def limit(self, n: int) -> Self:
        self._limit = n
        return self

    def build(self) -> str:
        query = f"SELECT * FROM {self._table}"
        if self._conditions:
            query += " WHERE " + " AND ".join(self._conditions)
        if self._limit is not None:
            query += f" LIMIT {self._limit}"
        return query

# Method chaining:
query = (
    QueryBuilder()
    .from_table("variants")
    .where("quality >= 30")
    .where("chrom = 'chr1'")
    .limit(1000)
    .build()
)
print(query)
# SELECT * FROM variants WHERE quality >= 30 AND chrom = 'chr1' LIMIT 1000
```

Key points:
- `Self` binds to whatever class `self` actually is at runtime.
- If `ExtendedQueryBuilder(QueryBuilder)` overrides `where`, the return type is
  still `Self`: the subclass: not the base `QueryBuilder`.
- Before Python 3.11, import `Self` from `typing_extensions`.

---

## 14. Runtime Type Narrowing with isinstance and TypeGuard

**isinstance narrowing** is built into Mypy. Inside an `if isinstance(x, SomeType)`
block, Mypy automatically treats `x` as `SomeType`. No extra tooling needed.

**TypeGuard** (Python 3.10+) extends this to *custom* predicate functions. A
function that returns `TypeGuard[T]` tells Mypy: "if this function returns True,
the argument has type T inside the guarded block."

```
isinstance check                TypeGuard check
-----------------------         -----------------------
if isinstance(x, int):          if is_list_of_str(data):
    x + 1  # Mypy: safe             data[0].upper()  # Mypy: safe
                                # Mypy narrows data -> list[str]
```

```python
from typing import TypeGuard

def is_list_of_str(val: list) -> TypeGuard[list[str]]:
    """Custom type guard: narrows list[unknown] to list[str]."""
    return all(isinstance(item, str) for item in val)

def process_names(data: list) -> None:
    if is_list_of_str(data):
        # Mypy now treats 'data' as list[str] inside this block:
        for name in data:
            print(name.upper())  # .upper() is safe -- mypy knows these are str
    else:
        print(f"Unexpected data types: {data}")

process_names(["alice", "bob", "carol"])
process_names([1, 2, 3])

# Standard isinstance narrowing (Mypy understands this natively):
def handle(value: int | str | None) -> str:
    if value is None:
        return "nothing"
    elif isinstance(value, int):
        return f"integer: {value * 2}"
    else:
        return f"string: {value.upper()}"
```

Key distinction:
- `isinstance` works on a single variable with a known type.
- `TypeGuard` works on *any* predicate logic, including checking the contents of
  a collection, which `isinstance` cannot express for generic types like
  `list[str]`.

---

## 15. Extended Checklist

The following items extend the checklist in Section 11. Answer all previous items
plus these before moving to Day 10.

- [ ] Why does a decorator that uses `(*args, **kwargs)` lose the wrapped
      function's signature for Mypy?
- [ ] How does `ParamSpec` solve the decorator signature loss problem?
- [ ] What is the `Self` type and how does it support fluent builder patterns?
- [ ] How does `TypeGuard` differ from `isinstance()` in terms of Mypy's type
      narrowing?
