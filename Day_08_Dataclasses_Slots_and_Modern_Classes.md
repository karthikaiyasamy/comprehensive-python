# Day 08: Dataclasses, Slots, and Modern Object Design

---

## 1. The Systems Mental Model: The Memory Cost of Millions of Objects

In enterprise backend applications, processing a few dozen records using standard Python classes works fine.

In high-throughput genomic data pipelines, financial risk feeds, and metrics ingestion, you routinely instantiate **millions of records in memory**.

```text
Memory Breakdown for 1,000,000 Instances of an Object with 3 Attributes:

  Standard Python Class (with __dict__):
    1,000,000 instances x ~152 bytes = ~152 MB overhead (excluding data payloads!)

  Class with __slots__ or @dataclass(slots=True):
    1,000,000 instances x ~48 bytes  = ~48 MB overhead (68% memory reduction!)
```

```text
ASCII Diagram: Standard Class vs Slots Memory Architecture

  Standard Class Instance (0x1000):
  ┌─────────────────────────────────────────────────────────────┐
  │ PyObject Header (16 bytes)                                  │
  ├─────────────────────────────────────────────────────────────┤
  │ Pointer to __dict__ (8 bytes) ───> [ PyDictObject: ~128 B ] │
  │                                    ├─ 'chrom'  -> 0xAAA     │
  │                                    ├─ 'pos'    -> 0xBBB     │
  │                                    └─ 'depth'  -> 0xCCC     │
  └─────────────────────────────────────────────────────────────┘

  Slots Instance (0x2000) (No __dict__! C-Style Flat Struct Array):
  ┌─────────────────────────────────────────────────────────────┐
  │ PyObject Header (16 bytes)                                  │
  ├─────────────────────────────────────────────────────────────┤
  │ Direct Pointer to 'chrom' (8 bytes)  ───> 0xAAA             │
  │ Direct Pointer to 'pos'   (8 bytes)  ───> 0xBBB             │
  │ Direct Pointer to 'depth' (8 bytes)  ───> 0xCCC             │
  └─────────────────────────────────────────────────────────────┘
```

---

## 2. Modern Dataclasses (PEP 557)

Introduced in Python 3.7, `@dataclass` eliminates the repetitive boilerplate of manually writing `__init__`, `__repr__`, and `__eq__`.

### What `@dataclass` Actually Does Under the Hood
It is not magic. At class definition time, the `@dataclass` decorator inspects your type annotations, generates standard Python code strings for `__init__`, `__repr__`, and `__eq__`, compiles them, and injects them into the class namespace.

```python
from dataclasses import dataclass

@dataclass
class GenomicRead:
    read_id: str
    chrom: str
    pos: int
    quality_score: float = 30.0

# Automatically generates:
# 1. __init__(self, read_id: str, chrom: str, pos: int, quality_score: float = 30.0)
# 2. __repr__(self) returning "GenomicRead(read_id='...', chrom='...', pos=..., quality_score=...)"
# 3. __eq__(self, other) performing field-by-field value comparison

read = GenomicRead("R_101", "chr1", 10450)
print(read)  # GenomicRead(read_id='R_101', chrom='chr1', pos=10450, quality_score=30.0)
```

---

## 3. Configuring Dataclass Parameters

The `@dataclass` decorator takes parameters that control code generation:

```python
@dataclass(
    init=True,       # Generate __init__ (default: True)
    repr=True,       # Generate __repr__ (default: True)
    eq=True,         # Generate __eq__ (default: True)
    order=False,     # Generate __lt__, __le__, __gt__, __ge__ (default: False)
    unsafe_hash=False, # Force generate __hash__ (default: False)
    frozen=False,    # Make instance immutable (default: False)
    slots=False,     # Use __slots__ instead of __dict__ (Python 3.10+, default: False)
    kw_only=False    # Force all fields to be passed as keyword arguments (Python 3.10+)
)
class Config:
    pass
```

### The Power of `frozen=True`
Setting `frozen=True`:
1. Makes instances **immutable** (reassigning any field raises `FrozenInstanceError`).
2. Automatically generates a valid `__hash__()` method based on all fields.
3. Allows instances to be safely placed in sets and used as dictionary keys.

```python
@dataclass(frozen=True)
class TargetLocus:
    gene: str
    chrom: str
    start: int
    end: int

locus = TargetLocus("BRCA1", "chr17", 43044295, 43125483)

# Hashable out of the box:
cache = {locus: "EXON_CAPTURE_PANEL"}
print(cache[locus])  # "EXON_CAPTURE_PANEL"

# Mutations fail at runtime:
try:
    locus.start = 0
except Exception as err:
    print(f"Immutability enforced: {type(err).__name__}")
```

---

## 4. Fine-Grained Field Control with `field()`

When a field requires more than a simple type annotation, use `dataclasses.field()`.

### The Mutable Default Trap Solved: `default_factory`

```python
from dataclasses import dataclass, field

# BAD: Raises ValueError: mutable default [list] is not allowed
# @dataclass
# class Sample:
#     flags: list[str] = []

# CORRECT: Use default_factory
@dataclass
class Sample:
    sample_id: str
    # Fresh list allocated for every instance:
    flags: list[str] = field(default_factory=list)
    # Exclude internal secrets from __repr__:
    auth_token: str = field(default="SECRET", repr=False)
    # Exclude timestamps from __eq__ comparisons:
    created_at: float = field(default=0.0, compare=False)

s1 = Sample("S1")
s1.flags.append("QC_PASS")

s2 = Sample("S2")
print(s2.flags)  # [] (Completely isolated!)
```

### Post-Initialization Processing: `__post_init__`
When attributes need to be validated or calculated from other fields upon construction:

```python
@dataclass
class VariantRecord:
    chrom: str
    pos: int
    ref: str
    alt: str
    hgvs_notation: str = field(init=False)

    def __post_init__(self):
        # Validation:
        if self.pos < 1:
            raise ValueError(f"1-based coordinate must be >= 1, got {self.pos}")
        # Derived attribute calculation:
        self.hgvs_notation = f"{self.chrom}:g.{self.pos}{self.ref}>{self.alt}"

v = VariantRecord("chr7", 140453136, "A", "T")
print(v.hgvs_notation)  # "chr7:g.140453136A>T"
```

---

## 5. Memory Optimization with `__slots__`

In standard classes, you can define `__slots__` to explicitly declare allowed attribute names and eliminate `self.__dict__`.

```python
class SlottedCoordinate:
    __slots__ = ("chrom", "pos", "depth")

    def __init__(self, chrom: str, pos: int, depth: int):
        self.chrom = chrom
        self.pos = pos
        self.depth = depth

c = SlottedCoordinate("chr1", 1000, 50)

# Memory savings:
# print(c.__dict__)  # AttributeError: 'SlottedCoordinate' object has no attribute '__dict__'

# Prevents accidental attribute addition (typo protection):
try:
    c.deptth = 60  # Typo!
except AttributeError as err:
    print(f"Slots prevents attribute typos: {err}")
```

---

## 6. The Modern Standard: `@dataclass(slots=True)`

Prior to Python 3.10, combining dataclasses and slots required manual class definitions.

In **Python 3.10+**, you simply add `slots=True`:

```python
@dataclass(slots=True, frozen=True)
class FastRead:
    read_id: str
    sequence: str
    quality: str
```

This single line gives you:
1. Auto-generated `__init__`, `__repr__`, `__eq__`, `__hash__`.
2. Total immutability (`frozen=True`).
3. Flat C-style struct memory layout (`slots=True`), reducing memory by ~65%.
4. Typo-prevention against accidental attribute assignment.

---

## 7. Structural Subtyping with `typing.Protocol` (PEP 544)

In traditional Object-Oriented design (like Java or C++), polymorphism requires explicit inheritance (`class Cat extends Animal`). This is **Nominal Typing**.

Python has always used **Duck Typing** (*"If it walks like a duck and quacks like a duck, it is a duck"*).

`typing.Protocol` brings static type checking to duck typing. Any class that implements the methods specified in a `Protocol` satisfies the type **without ever subclassing it**.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Alignable(Protocol):
    """Any object with a sequence and length satisfies this protocol."""
    sequence: str

    def get_gc_content(self) -> float:
        ...

# Implementation A: Standard class (No inheritance from Alignable!)
class DNASequence:
    def __init__(self, sequence: str):
        self.sequence = sequence

    def get_gc_content(self) -> float:
        gc_count = self.sequence.count("G") + self.sequence.count("C")
        return (gc_count / len(self.sequence)) * 100.0

# Implementation B: Slotted Dataclass (No inheritance from Alignable!)
@dataclass(slots=True)
class RNASequence:
    sequence: str

    def get_gc_content(self) -> float:
        gc_count = self.sequence.count("G") + self.sequence.count("C")
        return (gc_count / len(self.sequence)) * 100.0

def calculate_metric(target: Alignable) -> float:
    return target.get_gc_content()

dna = DNASequence("AGCTGC")
rna = RNASequence("AGCUG")

# Both work seamlessly and pass static type checks (mypy):
print(f"DNA GC%: {calculate_metric(dna):.1f}%")
print(f"RNA GC%: {calculate_metric(rna):.1f}%")

# Runtime check works because of @runtime_checkable:
print(f"Is DNA Alignable? {isinstance(dna, Alignable)}")  # True
```

---

## 8. Serialization: `asdict()` and `astuple()`

Python provides utilities to convert dataclasses to standard dictionaries or tuples.

```python
from dataclasses import asdict, astuple

@dataclass
class PipelineMeta:
    run_id: str
    cores: int
    tags: list[str]

meta = PipelineMeta("RUN_01", 16, ["pog", "wgs"])

# Convert to dictionary (recursively converts nested dataclasses):
dict_data = asdict(meta)
print(dict_data)  # {'run_id': 'RUN_01', 'cores': 16, 'tags': ['pog', 'wgs']}

# Convert to tuple:
tuple_data = astuple(meta)
print(tuple_data)  # ('RUN_01', 16, ['pog', 'wgs'])
```

*Performance Note: `asdict()` uses deep copying internally to decouple dictionaries. For ultra-high-throughput serialization in inner loops, manual dictionary construction `{"run_id": meta.run_id}` is significantly faster.*

---

## 9. Common Pitfalls and Systems Traps

### Pitfall 1: Inheriting Slotted Classes Without Declaring `__slots__`
If a parent class has `__slots__ = ('a',)`, but a subclass does not define `__slots__`, CPython will **automatically create a `__dict__` for the subclass**, completely defeating the memory optimization.
```python
class Parent:
    __slots__ = ("x",)

class BadChild(Parent):
    pass  # Creates __dict__ for BadChild!

class GoodChild(Parent):
    __slots__ = ("y",)  # Only slots for y; inherits slots for x; NO __dict__!
```

### Pitfall 2: Shallow Immutability in Frozen Dataclasses
Setting `frozen=True` prevents reassigning top-level fields (`obj.field = new_val`). It does **not** make nested mutable containers immutable:
```python
@dataclass(frozen=True)
class Container:
    items: list[int]

c = Container([1, 2, 3])
# c.items = [4, 5]    # FrozenInstanceError (Blocked)
c.items.append(4)      # SUCCEEDS! The list itself was mutated in-place!
```
*Rule: For complete immutability, use tuples or frozensets for nested collections.*

---

## 10. Hands-On Systems Challenge: 1,000,000 Object Benchmark

### The Problem
Write a benchmark script that:
1. Defines a standard Python class, a standard `@dataclass`, and an optimized `@dataclass(slots=True)`.
2. Instantiates 500,000 objects of each type.
3. Measures memory allocation using `tracemalloc`.
4. Measures instantiation runtime performance using `time.perf_counter()`.

### Complete Runnable Implementation

```python
from dataclasses import dataclass
import time
import tracemalloc

# 1. Standard Class
class StandardRecord:
    def __init__(self, locus_id: str, chrom: str, pos: int, depth: int):
        self.locus_id = locus_id
        self.chrom = chrom
        self.pos = pos
        self.depth = depth

# 2. Standard Dataclass (Dict-backed)
@dataclass
class DataclassRecord:
    locus_id: str
    chrom: str
    pos: int
    depth: int

# 3. Slotted Dataclass (C-struct backed)
@dataclass(slots=True)
class SlottedRecord:
    locus_id: str
    chrom: str
    pos: int
    depth: int

def benchmark_class_type(cls, name: str, count: int = 500_000):
    tracemalloc.start()
    start_time = time.perf_counter()

    # Pre-allocated list to isolate object allocation from list overhead:
    records = [
        cls(f"LOC_{i}", "chr1", 10_000 + i, 30)
        for i in range(count)
    ]

    elapsed = time.perf_counter() - start_time
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    print(f"[{name:<18}] Time: {elapsed:.3f}s | Peak RAM: {peak_mb:>6.1f} MB")
    return records

def run_suite():
    count = 300_000
    print(f"Benchmarking {count:,} instances per class type:")
    print("-" * 55)
    r1 = benchmark_class_type(StandardRecord, "Standard Class", count)
    r2 = benchmark_class_type(DataclassRecord, "Dataclass (Dict)", count)
    r3 = benchmark_class_type(SlottedRecord, "Dataclass (Slots)", count)
    print("-" * 55)

if __name__ == "__main__":
    run_suite()
```

### Expected Benchmark Results
```text
Benchmarking 300,000 instances per class type:
-------------------------------------------------------
[Standard Class    ] Time: 0.180s | Peak RAM:   48.2 MB
[Dataclass (Dict)  ] Time: 0.175s | Peak RAM:   48.2 MB
[Dataclass (Slots) ] Time: 0.130s | Peak RAM:   18.4 MB
-------------------------------------------------------
```
Notice that `slots=True` achieves a **~62% reduction in memory consumption** and executes faster due to direct C-pointer indexing!

---

## 11. Object Representation Comparison Table

| Feature | Standard Class | `@dataclass` | `@dataclass(slots=True)` | `namedtuple` |
| :--- | :--- | :--- | :--- | :--- |
| **Storage Mechanism** | `__dict__` hash table | `__dict__` hash table | Flat C pointer array | C tuple array |
| **Memory per Instance** | ~152 bytes | ~152 bytes | ~48 bytes | ~48 bytes |
| **Attribute Addition** | Dynamic at runtime | Dynamic at runtime | Disallowed (Strict) | Disallowed (Strict) |
| **Typo Protection** | None (`obj.typo = 1`) | None (`obj.typo = 1`) | Raises `AttributeError` | Raises `AttributeError` |
| **Auto `__init__`, `__repr__`** | Manual | Auto-generated | Auto-generated | Auto-generated |
| **Indexable as Tuple** | No | No | No | Yes (`obj[0]`) |
| **Unpackable (`a, b = obj`)**| No | No | No | Yes |
| **Best Production Use** | Complex business logic | General domain records | High-volume records | Lightweight tuple API |

---

## 12. Object Modeling Decision Guide & ASCII Decision Flowchart

```text
OBJECT MODELING DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
High-volume records (> 50k instances in RAM)            @dataclass(slots=True)
Immutable value object needed as dict key/cache         @dataclass(frozen=True, slots=True)
Simple unpackable record acting as a tuple replacement  collections.namedtuple
Loose duck typing contract checked by static linters    typing.Protocol
Runtime interface requiring explicit method enforcement abc.ABC + @abstractmethod
Complex domain entity with private state & validation   Standard class with @property
─────────────────────────────────────────────────────────────────────────────
```

### Decision Flowchart

```text
Do you need to instantiate more than 10,000 instances simultaneously?
  YES ──> @dataclass(slots=True)
  NO  ──> Do you need the object to be unpackable like a tuple (x, y = pt)?
            YES ──> namedtuple
            NO  ──> Do you need auto-generated boilerplate (__init__, __repr__)?
                      YES ──> @dataclass
                      NO  ──> Standard Python Class
```

---

## 13. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 09:

- [ ] What is the physical memory difference between `self.__dict__` and `__slots__`?
- [ ] How does `@dataclass` generate `__init__` and `__repr__` methods at runtime?
- [ ] Why is `default_factory=list` required instead of `flags: list = []` in dataclasses?
- [ ] What happens when a dataclass is declared with `frozen=True`?
- [ ] How does `__post_init__` allow validation and derived attribute computation?
- [ ] How does `typing.Protocol` enable compile-time structural subtyping (static duck typing)?
- [ ] What is the difference between `@runtime_checkable` Protocol and `abc.ABC`?
- [ ] Why does inheriting from a slotted class without defining `__slots__` in the child create a `__dict__`?
- [ ] What percentage of RAM is saved when switching from standard dataclasses to slotted dataclasses?


---

## 14. Inheritance with Dataclasses

Dataclasses support inheritance. The child class inherits all parent fields. Python's MRO applies: parent fields appear first in `__init__`, then child fields.

**Key pitfall:** If a parent field has a default value and a child field has no default, Python raises a `TypeError` because a non-default argument cannot follow a default argument in the generated `__init__` signature.

```python
from dataclasses import dataclass

@dataclass
class BaseRecord:
    record_id: str
    created_at: str = "2026-01-01"

@dataclass
class VariantRecord(BaseRecord):
    chrom: str = "unknown"
    pos: int = 0
    quality: float = 0.0

v = VariantRecord(record_id="V_001", chrom="chr1", pos=10450, quality=99.5)
print(v)
# VariantRecord(record_id='V_001', created_at='2026-01-01', chrom='chr1', pos=10450, quality=99.5)

# PITFALL: Parent with no defaults, child adds defaults: breaks if parent field has no default
# This works because parent field (record_id: str) comes before child fields
# If a parent had a field WITH a default, and child adds field WITHOUT a default: TypeError!

@dataclass
class GoodParent:
    name: str         # No default

@dataclass
class GoodChild(GoodParent):
    value: int = 0    # Child has default: this is fine

@dataclass
class BadParent:
    name: str = "default"  # Parent has default

# @dataclass
# class BadChild(BadParent):
#     value: int     # Child has NO default: TypeError: non-default arg follows default!
```

**Field ordering rule (ASCII diagram):**

```text
__init__ signature order = [parent fields] + [child fields]

SAFE:
  parent: required_field (no default)
  child:  optional_field (has default)
  -> __init__(self, required_field, optional_field=...)   OK

BROKEN:
  parent: optional_field (has default)
  child:  required_field (no default)
  -> __init__(self, optional_field=..., required_field)   TypeError!
```

**Workarounds:**
- Give the child field a default value or `field(default=...)`.
- Use `kw_only=True` on the child class (Python 3.10+): all child fields become keyword-only, breaking the positional ordering conflict.

```python
from dataclasses import dataclass

@dataclass
class BadParent:
    name: str = "default"

@dataclass(kw_only=True)   # Python 3.10+
class FixedChild(BadParent):
    value: int              # Required, but keyword-only: no TypeError

obj = FixedChild(value=42)
print(obj)  # FixedChild(name='default', value=42)
```

---

## 15. Pydantic vs Dataclasses: When to Use Each

`@dataclass` uses type hints for documentation only. No runtime type checking or coercion occurs. Pydantic's `BaseModel` validates and coerces data at runtime: essential at system boundaries.

**Comparison table:**

```text
Feature                          @dataclass            Pydantic BaseModel
---------------------------------------------------------------------------
Runtime type validation          No                    Yes
JSON serialization               Manual                model.model_dump_json()
Coercion (str "5" -> int 5)      No                    Yes
Performance overhead             Minimal               Moderate
Use at internal domain layer     Yes (recommended)     Avoid (overkill)
Use at API boundary / config     No (too weak)         Yes (recommended)
Standard library                 Yes                   No (pip install pydantic)
```

**Runnable comparison:**

```python
from dataclasses import dataclass

@dataclass
class DataclassUser:
    name: str
    age: int

# No validation at all:
u = DataclassUser(name=123, age="thirty")  # No error! Type hints ignored at runtime
print(u)  # DataclassUser(name=123, age='thirty')

# To show Pydantic behavior without installing it, explain what it would do:
print("""
# With Pydantic:
# from pydantic import BaseModel
# class PydanticUser(BaseModel):
#     name: str
#     age: int
#
# u = PydanticUser(name=123, age="thirty")
# -> Coerces name to str "123", age to int 30 (or raises ValidationError)
#
# u = PydanticUser(name="Alice", age="not_a_number")
# -> Raises: ValidationError: age must be an integer
""")
```

**Decision rule:**

```text
Internal domain objects (business logic, in-memory computation)
  -> Use @dataclass. Lightweight, no overhead, no third-party dependency.

API boundary / config file / user input / external data parsing
  -> Use Pydantic BaseModel. Runtime validation catches bad data early.
```

---

## 16. dataclasses.replace(): Immutable Update Pattern

Frozen dataclasses cannot have their fields modified after creation. `dataclasses.replace()` creates a **new** instance with selected fields overridden. The original instance is untouched.

This pattern is common in functional programming and event sourcing, where state is never mutated: a new version of the object is produced instead.

```python
from dataclasses import dataclass, replace

@dataclass(frozen=True, slots=True)
class PipelineConfig:
    sample_id: str
    threads: int = 4
    timeout_ms: int = 5000
    enable_qc: bool = True

config = PipelineConfig(sample_id="S_001")
print(config)
# PipelineConfig(sample_id='S_001', threads=4, timeout_ms=5000, enable_qc=True)

# Create modified version without mutating original:
high_perf_config = replace(config, threads=16, timeout_ms=10000)
print(high_perf_config)
# PipelineConfig(sample_id='S_001', threads=16, timeout_ms=10000, enable_qc=True)

# Original is unchanged:
print(config.threads)            # 4
print(high_perf_config.threads)  # 16

# Both are distinct objects:
print(config is high_perf_config)  # False
```

**ASCII diagram: immutable update pattern:**

```text
Original object (frozen, immutable)
  config = PipelineConfig(sample_id="S_001", threads=4, timeout_ms=5000)
      |
      |   replace(config, threads=16, timeout_ms=10000)
      |         |
      v         v
  config      high_perf_config
  threads=4   threads=16
  timeout=5000 timeout=10000
  (unchanged)  (new object, fields copied + overrides applied)
```

`replace()` copies all fields from the source object, then applies only the keyword arguments you provide as overrides. It never modifies the original.

---

## 17. Updated Checklist

All items from the previous checklist apply. Additional questions covering sections 14-16:

- [ ] Why does placing a child field without a default after a parent field with a default cause a `TypeError` in dataclass inheritance?
- [ ] When would you choose Pydantic `BaseModel` over `@dataclass`?
- [ ] How does `dataclasses.replace()` implement the immutable update pattern?
