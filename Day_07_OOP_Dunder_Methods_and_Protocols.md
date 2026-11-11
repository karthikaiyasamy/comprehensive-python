# Day 07: Object-Oriented Programming and Dunder Protocols

---

## 1. The Systems Mental Model: Classes as Heap Objects

In C++ or Java, a class is a compile-time blueprint. After compilation, classes do not exist as independent, mutable heap entities; objects are simply typed byte arrays whose method calls resolve via a virtual method table (vtable).

In Python, **classes are live heap objects created at runtime**.
* Every class you define is an instance of the metaclass `type`.
* When Python executes a `class` statement, it runs the body like a script, gathers all local definitions into a dictionary (the class namespace), and passes them to `type()` to allocate a `PyTypeObject`.

```text
ASCII Diagram: The Object-Class-Metaclass Hierarchy

  ┌─────────────────────────────────────────────────────────────┐
  │ Metaclass: type (PyTypeObject in C)                         │
  │ Instances of type are Classes                               │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ allocates at runtime
  ┌──────────────────────────────▼──────────────────────────────┐
  │ Class: GenomicSample (Heap object, instance of type)        │
  │ Holds shared methods, class attributes, __dict__            │
  └──────────────────────────────┬──────────────────────────────┘
                                 │ instantiates
  ┌──────────────────────────────▼──────────────────────────────┐
  │ Instance: sample_01 (PyObject in heap)                      │
  │ Holds instance __dict__ (pointers to local attributes)      │
  └─────────────────────────────────────────────────────────────┘
```

### The Allocation Lifecycle: `__new__` vs `__init__`

Instantiating a class involves two distinct phases:

1. **`__new__(cls, ...)`:** The static constructor. Allocates the raw uninitialized `PyObject` in heap memory and returns it.
2. **`__init__(self, ...)`:** The initializer. Receives the allocated instance from `__new__` and initializes its fields.

```python
class SingletonService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        # Intercept allocation to enforce singleton pattern:
        if cls._instance is None:
            # Allocate raw object in heap:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, service_name: str):
        self.service_name = service_name

s1 = SingletonService("AUTH")
s2 = SingletonService("DATABASE")

# Both point to the exact same heap address:
print(s1 is s2)            # True
print(s1.service_name)     # "DATABASE" (Overwritten by second __init__ call)
```

---

## 2. Instance Attributes and the `__dict__` Memory Footprint

By default, every Python instance stores its attributes in an internal dictionary called `self.__dict__`.

```python
class Record:
    def __init__(self, sample_id: str, depth: int):
        self.sample_id = sample_id
        self.depth = depth

r = Record("SAM_01", 30)

# Attributes live directly in the instance __dict__:
print(r.__dict__)  # {'sample_id': 'SAM_01', 'depth': 30}

# Dynamic attribute addition at runtime:
r.qc_status = "PASS"
print(r.__dict__)  # {'sample_id': 'SAM_01', 'depth': 30, 'qc_status': 'PASS'}
```

### The Hidden Memory Cost
Because `self.__dict__` is a full hash table, each standard instance consumes approximately **150 to 200 bytes** of memory before storing any actual data. If you instantiate 1,000,000 records, you waste over 150 MB of RAM on empty hash table structures. (Day 08 will show how `__slots__` eliminates this).

---

## 3. String Representation: `__repr__` vs `__str__`

Python distinguishes between developer-facing representation and user-facing presentation.

| Dunder Method | Intended Audience | Goal | Fallback Behavior |
| :--- | :--- | :--- | :--- |
| `__repr__(self)` | Developers & Debuggers | Unambiguous; ideally valid Python code (`eval(repr(obj)) == obj`) | Built-in default: `<ClassName object at 0x...>` |
| `__str__(self)` | End-users & Logs | Human-readable and clean presentation | Falls back to `__repr__` if omitted |

```python
class PatientLocus:
    def __init__(self, chrom: str, pos: int, ref: str, alt: str):
        self.chrom = chrom
        self.pos = pos
        self.ref = ref
        self.alt = alt

    def __repr__(self) -> str:
        # Unambiguous code representation:
        return f"PatientLocus(chrom={self.chrom!r}, pos={self.pos!r}, ref={self.ref!r}, alt={self.alt!r})"

    def __str__(self) -> str:
        # Standard biological notation:
        return f"{self.chrom}:{self.pos}:{self.ref}>{self.alt}"

locus = PatientLocus("chr7", 140453136, "A", "T")

print(str(locus))   # chr7:140453136:A>T
print(repr(locus))  # PatientLocus(chrom='chr7', pos=140453136, ref='A', alt='T')
```

---

## 4. Arithmetic and Rich Comparison Protocols

Python does not require custom methods like `add()` or `compareTo()`. You implement native operator overloading via dunder methods.

### Comparison Operators

To make instances sortable and comparable, implement the rich comparison dunders:

```python
from functools import total_ordering

# total_ordering generates __le__, __gt__, __ge__ automatically
# as long as __eq__ and one ordering method (__lt__) are provided:
@total_ordering
class GenomicVariant:
    def __init__(self, chrom: str, pos: int):
        self.chrom = chrom
        self.pos = pos

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GenomicVariant):
            return NotImplemented
        return (self.chrom, self.pos) == (other.chrom, other.pos)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, GenomicVariant):
            return NotImplemented
        # Sort by chromosome string, then by integer coordinate:
        return (self.chrom, self.pos) < (other.chrom, other.pos)

v1 = GenomicVariant("chr1", 1000)
v2 = GenomicVariant("chr1", 2000)
v3 = GenomicVariant("chr2", 500)

print(v1 < v2)   # True
print(v2 > v3)   # False ("chr1" < "chr2")
print(v1 == v1)  # True

# Automatically sortable in lists:
variants = [v2, v3, v1]
variants.sort()
print(variants)  # [v1, v2, v3]
```

### The `NotImplemented` Sentinel
When comparing against an incompatible type, **never raise `TypeError` directly**. Return the singleton `NotImplemented`. This signals to Python to try the reflected operation on the other operand (`other.__ge__(self)`) before raising `TypeError`.

---

## 5. The Hashing Protocol and the Hash-Equality Contract

To store custom objects in a `set` or use them as `dict` keys, they must fulfill the **Hash Contract**:

1. **If two objects are equal (`a == b`), their hashes MUST be equal (`hash(a) == hash(b)`).**
2. An object's hash must never change during its lifetime (it must be immutable).

### The Automatic Disabling Rule
If you override `__eq__` in a class, Python automatically sets `__hash__ = None`. This prevents mutable objects from corrupting hash table buckets.

```python
class ReadCoord:
    def __init__(self, chrom: str, pos: int):
        self._chrom = chrom
        self._pos = pos

    @property
    def chrom(self) -> str:
        return self._chrom

    @property
    def pos(self) -> int:
        return self._pos

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ReadCoord):
            return NotImplemented
        return (self._chrom, self._pos) == (other._chrom, other._pos)

    def __hash__(self) -> int:
        # Hash a tuple of the immutable identity attributes:
        return hash((self._chrom, self._pos))

rc1 = ReadCoord("chr17", 43044295)
rc2 = ReadCoord("chr17", 43044295)

# Equal objects:
assert rc1 == rc2
# Equal hashes:
assert hash(rc1) == hash(rc2)

# Usable as dictionary keys and set members:
coordinate_cache = {rc1: "BRCA1_EXON"}
print(coordinate_cache[rc2])  # "BRCA1_EXON" (Instant lookup!)
```

---

## 6. Encapsulation: Protected (`_`) vs Private Mangling (`__`)

Unlike Java or C++, Python does not have compiler-enforced access modifiers (`public`, `protected`, `private`). It uses naming conventions.

| Syntax | Convention | Mechanics | Intended Meaning |
| :--- | :--- | :--- | :--- |
| `self.name` | Public | Standard attribute | Public API, safe for external use |
| `self._name` | Protected | Standard attribute | Internal implementation detail; do not touch outside module |
| `self.__name` | Private | Name Mangling (`_ClassName__name`) | Avoids collision in inheritance hierarchies |

```python
class BasePipeline:
    def __init__(self):
        self.public_id = "PIPE_100"
        self._internal_buffer = []      # Protected convention
        self.__secret_key = "SEC_9921"  # Name-mangled

class SubPipeline(BasePipeline):
    def inspect(self):
        print(self.public_id)           # OK
        print(self._internal_buffer)    # OK by convention
        # print(self.__secret_key)      # Fails! Raises AttributeError

p = SubPipeline()
p.inspect()

# Name mangling transforms __secret_key into _BasePipeline__secret_key:
print(p._BasePipeline__secret_key)  # "SEC_9921" (Accessible, but heavily discouraged)
```

---

## 7. The Property Protocol: Encapsulation with Zero Call-Site Overhead

In Java, all fields are made private and accessed via verbose `getDepth()` and `setDepth()` getters/setters.

In Python, you expose attributes as public fields directly. If you later need validation, caching, or access logging, you wrap them in `@property` **without breaking existing call-site syntax**.

```python
class SequencingRun:
    def __init__(self, run_id: str, raw_reads: int):
        self.run_id = run_id
        # Calls the setter for initial validation:
        self.raw_reads = raw_reads

    @property
    def raw_reads(self) -> int:
        """Getter: returns internal integer."""
        return self._raw_reads

    @raw_reads.setter
    def raw_reads(self, value: int) -> None:
        """Setter: validates data types and invariants."""
        if not isinstance(value, int):
            raise TypeError(f"raw_reads must be integer, got {type(value).__name__}")
        if value < 0:
            raise ValueError(f"raw_reads cannot be negative: {value}")
        self._raw_reads = value

run = SequencingRun("RUN_2026_A", 500_000)
# Accesses via getter:
print(run.raw_reads)  # 500000

# Triggers setter validation:
try:
    run.raw_reads = -10
except ValueError as err:
    print(f"Validation caught: {err}")
```

---

## 8. Inheritance, `super()`, and C3 Linearization (MRO)

Python supports multiple inheritance. When resolving method calls, CPython follows the **C3 Linearization Algorithm** to establish the Method Resolution Order (MRO).

### The Diamond Problem and Cooperative `super()`

```text
ASCII Diagram: Diamond Inheritance

            ┌───────────────┐
            │   Device      │
            │  (setup())    │
            └───────┬───────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
  ┌──────────────┐      ┌──────────────┐
  │ NetworkDevice│      │ StorageDevice│
  │  (setup())   │      │  (setup())   │
  └──────┬───────┘      └──────┬───────┘
         │                     │
         └──────────┬──────────┘
                    ▼
            ┌───────────────┐
            │ SmartSensor   │
            │  (setup())    │
            └───────────────┘
```

```python
class Device:
    def setup(self):
        print("Device initialized")

class NetworkDevice(Device):
    def setup(self):
        print("Network interface configured")
        super().setup()

class StorageDevice(Device):
    def setup(self):
        print("Storage drive mounted")
        super().setup()

class SmartSensor(NetworkDevice, StorageDevice):
    def setup(self):
        print("SmartSensor booting...")
        super().setup()

sensor = SmartSensor()
sensor.setup()
```

### Execution Output
```text
SmartSensor booting...
Network interface configured
Storage drive mounted
Device initialized
```

### Inspecting the MRO
Every class has an `__mro__` attribute showing the linear search path:
```python
for cls in SmartSensor.__mro__:
    print(cls.__name__)
# SmartSensor -> NetworkDevice -> StorageDevice -> Device -> object
```
Notice that `Device.setup()` was called **exactly once**, and `NetworkDevice` called `StorageDevice` next in line. This cooperative multi-stage resolution only works when every subclass uses `super().setup()`.

---

## 9. Abstract Base Classes (ABCs) and Interface Contracts

In Java, interfaces are enforced at compile time (`implements Interface`).

In Python, use the standard library `abc` module to define runtime-enforced abstract interfaces.

```python
from abc import ABC, abstractmethod

class BaseVariantCaller(ABC):
    """Abstract interface defining required pipeline methods."""

    @abstractmethod
    def align_reads(self, fastq_path: str) -> str:
        """Aligns FASTQ and returns BAM path."""
        pass

    @abstractmethod
    def call_variants(self, bam_path: str) -> str:
        """Calls variants from BAM and returns VCF path."""
        pass

# Attempting to instantiate an incomplete subclass:
class IncompleteCaller(BaseVariantCaller):
    def align_reads(self, fastq_path: str) -> str:
        return "output.bam"

try:
    caller = IncompleteCaller()
except TypeError as err:
    print(f"Interface enforcement: {err}")
    # TypeError: Can't instantiate abstract class IncompleteCaller without an implementation for abstract method 'call_variants'
```

---

## 10. Common Pitfalls and Systems Traps

### Pitfall 1: Mutating Class-Level Attributes via an Instance
```python
class PipelineConfig:
    active_threads = 4  # Class-level attribute shared by all instances

cfg1 = PipelineConfig()
cfg2 = PipelineConfig()

# TRAP: This does NOT modify the class attribute!
# It creates a shadowed instance attribute inside cfg1.__dict__!
cfg1.active_threads = 16

print(cfg1.active_threads)         # 16 (Local instance attribute)
print(cfg2.active_threads)         # 4  (Unchanged class attribute)
print(PipelineConfig.active_threads) # 4

# CORRECT: Always mutate class attributes via the class name directly:
PipelineConfig.active_threads = 8
print(cfg2.active_threads)         # 8 (Both instances see update)
```

### Pitfall 2: Overriding `__eq__` Without `__hash__` in Cache Keys
Overriding `__eq__` causes Python to set `__hash__ = None`. If you put that object into a `set` or use it with `@functools.lru_cache`, your program crashes with `TypeError: unhashable type`. Always implement `__hash__` alongside `__eq__` for value objects.

---

## 11. Hands-On Systems Challenge: Telemetry Batch Buffer Container

### The Problem
Build an enterprise-grade container class `TelemetryBatch` that:
1. Implements the Sequence protocol (`__len__`, `__getitem__`, `__iter__`).
2. Implements addition (`__add__`) to allow combining two batches cleanly with `batch1 + batch2`.
3. Implements rich comparison (`__lt__`, `__eq__`) to sort batches by timestamp using `@total_ordering`.
4. Enforces type safety on all additions using defensive checks.

### Complete Runnable Implementation

```python
from functools import total_ordering
from typing import Iterator

@total_ordering
class TelemetryBatch:
    def __init__(self, batch_id: str, timestamp: float, readings: list[float] | None = None):
        self.batch_id = batch_id
        self.timestamp = timestamp
        self._readings: list[float] = list(readings) if readings else []

    # Sequence Protocol:
    def __len__(self) -> int:
        return len(self._readings)

    def __getitem__(self, index: int) -> float:
        return self._readings[index]

    def __iter__(self) -> Iterator[float]:
        return iter(self._readings)

    # Arithmetic Protocol:
    def __add__(self, other: "TelemetryBatch") -> "TelemetryBatch":
        if not isinstance(other, TelemetryBatch):
            return NotImplemented
        combined_id = f"{self.batch_id}+{other.batch_id}"
        min_time = min(self.timestamp, other.timestamp)
        combined_readings = self._readings + other._readings
        return TelemetryBatch(combined_id, min_time, combined_readings)

    # Comparison Protocol (Ordered by timestamp):
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TelemetryBatch):
            return NotImplemented
        return (self.timestamp, self.batch_id) == (other.timestamp, other.batch_id)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, TelemetryBatch):
            return NotImplemented
        return self.timestamp < other.timestamp

    # Representation:
    def __repr__(self) -> str:
        return f"TelemetryBatch(id={self.batch_id!r}, time={self.timestamp}, count={len(self)})"

def test_telemetry_batch():
    b1 = TelemetryBatch("B1", timestamp=100.0, readings=[12.4, 15.1])
    b2 = TelemetryBatch("B2", timestamp=50.0, readings=[18.9, 21.0, 24.5])

    # Sequence access:
    assert len(b1) == 2
    assert b1[0] == 12.4
    assert list(b1) == [12.4, 15.1]

    # Arithmetic combination:
    b3 = b1 + b2
    assert len(b3) == 5
    assert b3.timestamp == 50.0

    # Sorting using total_ordering:
    batch_list = [b1, b2]
    batch_list.sort()
    assert batch_list[0].batch_id == "B2"  # Earlier timestamp sorted first

    print("TelemetryBatch verified successfully:")
    print(f"  Merged batch: {b3}")
    print(f"  Sorted list:  {batch_list}")

if __name__ == "__main__":
    test_telemetry_batch()
```

---

## 12. Object-Oriented Design Decision Guide & Decision Flowchart

```text
OBJECT-ORIENTED DESIGN DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
Read-only value record with named fields                tuple / namedtuple
Data container with type hints & auto methods           @dataclass (Day 08)
Massive object volumes (> 100k instances in RAM)        __slots__ (Day 08)
Enforcing formal method contracts across teams          abc.ABC + @abstractmethod
Custom operators (+, -, ==, len, in)                    Dunder methods (__add__, etc.)
Validating or transforming field access                 @property + @setter
Linearizing cooperative multi-class inheritance         super() + C3 MRO
─────────────────────────────────────────────────────────────────────────────
```

### Architecture Decision Flowchart

```text
Do you need custom operator overloading (+, ==, len, indexing)?
  YES ──> Implement corresponding Dunder Methods (__add__, __getitem__)
  NO  ──> Are you building an abstract contract for multiple implementations?
            YES ──> abc.ABC with @abstractmethod
            NO  ──> Do you primarily need data storage with minimal boilerplate?
                      YES ──> @dataclass (see Day 08)
                      NO  ──> Standard Python Class
```

---

## 13. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 08:

- [ ] Explain why classes in Python are live heap objects created by `type`.
- [ ] What is the structural difference between `__new__` and `__init__`?
- [ ] Why does a standard Python object instance consume approximately 150 bytes in memory?
- [ ] What is the difference between `__repr__` and `__str__`?
- [ ] How does `@functools.total_ordering` simplify rich comparisons?
- [ ] Why should you return `NotImplemented` instead of raising `TypeError` in comparison dunders?
- [ ] What happens to `__hash__` when a class overrides `__eq__` without declaring `__hash__`?
- [ ] How does Python name mangling (`__var`) operate physically in memory?
- [ ] How does `super()` resolve methods in diamond inheritance using the C3 MRO?
- [ ] How do Abstract Base Classes (`abc.ABC`) enforce interface contracts at runtime?


---

## 14. Class Methods and Static Methods

Python provides two decorators that alter how a method receives its first argument.

```text
Method Type       First Argument    Receives Class?    Receives Instance?
--------------    --------------    ---------------    ------------------
instance method   self              No (via self)      Yes
@classmethod      cls               Yes                No
@staticmethod     (none)            No                 No
```

**When to use each:**

- **Instance method**: the default. Operates on instance data via `self`.
- **`@classmethod`**: use for alternate constructors or operations that need the class but not a specific instance.
- **`@staticmethod`**: use for utility/validation logic that belongs conceptually to the class but needs no class or instance state.

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class SequencingRun:
    run_id: str
    sample_count: int
    created_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "SequencingRun":
        """Alternate constructor: creates instance from raw dictionary."""
        return cls(
            run_id=data["run_id"],
            sample_count=data["sample_count"],
            created_at=data.get("created_at", datetime.now().isoformat())
        )

    @classmethod
    def from_id(cls, run_id: str) -> "SequencingRun":
        """Another alternate constructor: minimal data only."""
        return cls(run_id=run_id, sample_count=0, created_at=datetime.now().isoformat())

    @staticmethod
    def validate_run_id(run_id: str) -> bool:
        """Validation logic that doesn't need instance or class state."""
        return run_id.startswith("RUN_") and len(run_id) > 4

# Usage:
run = SequencingRun.from_dict({"run_id": "RUN_2026_A", "sample_count": 48})
print(run)

run2 = SequencingRun.from_id("RUN_2026_B")
print(run2)

print(SequencingRun.validate_run_id("RUN_2026_A"))  # True
print(SequencingRun.validate_run_id("BAD_ID"))       # False
```

**Key point:** `@classmethod` is the idiomatic Python solution for multiple constructors. It avoids overloading `__init__` with complex conditional logic and works correctly with subclasses because `cls` refers to the actual class being called.

---

## 15. `__slots__` in Standard Classes (Pre-Dataclass)

For standard (non-dataclass) classes, Python stores instance attributes in a `__dict__` per object. This is flexible but has memory overhead.

Declaring `__slots__` replaces `__dict__` with a fixed, compact structure.

**Rules for `__slots__`:**
- List every attribute name the class will use.
- Instances can no longer have arbitrary new attributes (typo protection included).
- Do not mix `__slots__` with inheritance carelessly: a parent without `__slots__` re-introduces `__dict__`.

```python
import sys

class StandardPoint:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

class SlottedPoint:
    __slots__ = ("x", "y")
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

sp = StandardPoint(1.0, 2.0)
sl = SlottedPoint(1.0, 2.0)

print(f"Standard: {sys.getsizeof(sp)} bytes, has __dict__: {'__dict__' in dir(sp)}")
print(f"Slotted:  {sys.getsizeof(sl)} bytes, has __dict__: {'__dict__' in dir(sl)}")

# Slots prevents new attribute assignment (typo protection):
try:
    sl.z = 3.0  # AttributeError!
except AttributeError as e:
    print(f"Slots protection: {e}")
```

**When to reach for `__slots__`:**
Use it when you create a large number of instances of a simple, fixed-schema class and memory or attribute-access speed matters. Dataclasses support `__slots__` via `@dataclass(slots=True)` (Python 3.10+).

---

## 16. Descriptor Protocol (`__get__`, `__set__`, `__delete__`)

A **descriptor** is any object that defines at least one of `__get__`, `__set__`, or `__delete__`. When such an object is assigned as a **class attribute**, Python calls those methods instead of doing plain attribute storage/retrieval.

`@property` is itself built on the descriptor protocol: it is a descriptor object that the interpreter calls transparently.

**Attribute lookup chain (simplified):**

```text
obj.attr
    |
    v
Does type(obj).__mro__ contain a data descriptor for 'attr'?
    YES -> call descriptor.__get__(obj, type(obj))
    |
    NO
    v
Does obj.__dict__ contain 'attr'?
    YES -> return obj.__dict__['attr']
    |
    NO
    v
Does type(obj).__mro__ contain a non-data descriptor for 'attr'?
    YES -> call descriptor.__get__(obj, type(obj))
    |
    NO -> AttributeError
```

A **data descriptor** defines both `__get__` and `__set__` (or `__delete__`).
A **non-data descriptor** defines only `__get__` (e.g., a plain function).

```python
class TypedField:
    """A descriptor that enforces a type constraint on assignment."""
    def __init__(self, name: str, expected_type: type):
        self.name = name
        self.expected_type = expected_type
        self.private_name = f"_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self  # Accessed on the class itself
        return getattr(obj, self.private_name, None)

    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(
                f"Field '{self.name}' expects {self.expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        setattr(obj, self.private_name, value)

class SensorReading:
    value   = TypedField("value", float)
    unit    = TypedField("unit", str)
    channel = TypedField("channel", int)

    def __init__(self, value: float, unit: str, channel: int):
        self.value   = value   # Calls TypedField.__set__
        self.unit    = unit
        self.channel = channel

reading = SensorReading(36.6, "celsius", 1)
print(reading.value)   # 36.6

try:
    reading.value = "hot"  # TypeError!
except TypeError as e:
    print(f"Type guard: {e}")
```

**Practical rule:** Reach for `@property` for simple per-class computed or validated attributes. Reach for a custom descriptor when the same validation or access logic must be reused across many different classes without repetition.

---

## 17. Extended Checklist

In addition to the checklist in section 13, verify you can answer the following:

- [ ] What is the difference between `@classmethod`, `@staticmethod`, and an instance method?
- [ ] Why would you use `@classmethod` as an alternate constructor instead of overloading `__init__`?
- [ ] What is a descriptor and how does the descriptor protocol relate to `@property`?
