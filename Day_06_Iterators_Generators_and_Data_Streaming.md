# Day 06: Iterators, Generators, and Stream Processing

---

## 1. The Systems Mental Model: The Iteration Protocol

In C++ or Java, iteration typically uses iterator objects with `hasNext()` and `next()` methods.

In Python, iteration is governed by two complementary dunder protocols:
1. **Iterable:** Any object that can produce an iterator via `__iter__()`.
2. **Iterator:** A stateful object that produces the next value via `__next__()` and raises `StopIteration` when exhausted.

```text
CPython Bytecode Lowering of a For-Loop:

  Python:
    for item in collection:
        process(item)

  Equivalent Bytecode Opcode Sequence:
    1. GET_ITER     -> Calls iter(collection), pushes iterator to stack
    2. FOR_ITER 10  -> Calls next(iterator). If StopIteration raised, jumps to offset 10
    3. STORE_FAST   -> Binds yielded object to 'item'
    4. (execute loop body)
    5. JUMP_BACKWARD-> Jumps back to FOR_ITER
```

```text
ASCII Diagram: The Iterator State Machine

           iter(obj)
  [Iterable] ───────> [Iterator Object]
                             │
                             ├──── next() ───> Returns Value 1
                             │
                             ├──── next() ───> Returns Value 2
                             │
                             └──── next() ───> Raises StopIteration (Exhausted!)
```

### Writing a Custom Iterator from Scratch

```python
class FibonacciIterator:
    """An iterator that produces Fibonacci numbers up to a maximum count."""
    def __init__(self, limit: int):
        self.limit = limit
        self.count = 0
        self.a, self.b = 0, 1

    def __iter__(self):
        # An iterator must return itself from __iter__
        return self

    def __next__(self) -> int:
        if self.count >= self.limit:
            # Signaling exhaustion to the C eval loop:
            raise StopIteration

        val = self.a
        self.a, self.b = self.b, self.a + self.b
        self.count += 1
        return val

# Standard for-loop automatically catches StopIteration:
for num in FibonacciIterator(6):
    print(num, end=" ")  # 0 1 1 2 3 5
print()
```

---

## 2. Generators and the `yield` Keyword

Writing class-based iterators with manual state tracking is verbose and error-prone. 

A **generator function** is a function that contains the `yield` keyword. 

### What Happens When Python Compiles a Generator?
1. At compilation time, CPython detects `yield` and sets the `CO_GENERATOR` flag on the code object (`f_code.co_flags`).
2. When the function is called, **it does not execute any code**. Instead, it returns a heap-allocated **`PyGenObject`**.
3. When `next(gen)` is called, the CPython evaluation loop executes bytecode until it hits `yield`.
4. It then **suspends the execution frame**:
   * It freezes local variables (`f_locals`).
   * It records the bytecode instruction pointer (`f_lasti`).
   * It yields the value back to the caller.
5. On the next call to `next(gen)`, CPython restores the exact execution frame and resumes immediately after the `yield` statement.

```text
ASCII Diagram: Generator Frame Suspension and Resumption

  Caller                     Generator Frame (Heap-Persisted PyGenObject)
  ───────────────────────────────────────────────────────────────────────
  gen = count_up()   ────>   Allocates frame object (no execution yet)
  
  val1 = next(gen)   ────>   Executes to 'yield 1'
                     <────   Suspends frame! (Local state & IP frozen)
  
  val2 = next(gen)   ────>   Resumes from line after 'yield 1'
                             Executes to 'yield 2'
                     <────   Suspends frame!
```

---

## 3. Memory Comparison: Eager Lists vs Lazy Generators

This is the foundational pattern for processing high-throughput genomic data, server logs, and financial transactions.

```python
import sys
import tracemalloc

# Scenario: Processing 10,000,000 integers

# Approach A: Eager List (Loads entire sequence into RAM)
tracemalloc.start()
eager_list = [x for x in range(1_000_000)]
peak_eager = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()

# Approach B: Lazy Generator (O(1) Memory Stream)
tracemalloc.start()
lazy_gen = (x for x in range(1_000_000))
peak_lazy = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()

print(f"Eager List Peak Memory: {peak_eager / (1024 * 1024):.2f} MB") # ~40 MB
print(f"Lazy Gen Peak Memory:   {peak_lazy / 1024:.2f} KB")            # ~0.5 KB!
```

If the dataset scales from 1 million to 100 million items:
* Approach A crashes the machine with an Out-of-Memory (OOM) kill.
* Approach B runs in identical constant memory ($O(1)$ RAM).

---

## 4. Advanced Generator Protocols: `send()`, `throw()`, and `close()`

Generators are not just data producers; they can also be **data consumers (coroutines)**.

### 1. `gen.send(value)`
Passes a value back into the generator frame, which becomes the return value of the `yield` expression.

```python
def running_average():
    """A stateful generator that calculates moving averages on streamed inputs."""
    total = 0.0
    count = 0
    average = None
    
    while True:
        # yield produces 'average', pauses, and waits to receive 'new_val' from send():
        new_val = yield average
        if new_val is None:
            break
        total += new_val
        count += 1
        average = total / count

avg_stream = running_average()
next(avg_stream)  # Prime the generator (advances to first yield)

print(avg_stream.send(10))  # 10.0
print(avg_stream.send(20))  # 15.0
print(avg_stream.send(30))  # 20.0
```

### 2. `gen.close()`
Raises a `GeneratorExit` exception inside the suspended frame, triggering any cleanup `finally` blocks.

```python
def stream_resource():
    try:
        yield "payload_data"
    finally:
        print("[CLEANUP] Releasing file handle or network socket.")

gen = stream_resource()
next(gen)
gen.close()  # Triggers finally block immediately
```

---

## 5. Sub-Generators: `yield from`

The `yield from <iterable>` syntax (PEP 380) establishes a transparent bi-directional communication pipeline between the caller and a sub-generator.

```python
def read_chunk_a():
    yield "A1"
    yield "A2"

def read_chunk_b():
    yield "B1"
    yield "B2"

def combined_pipeline():
    # ELEGANT & FAST: Automatically delegates iteration, send(), and exceptions:
    yield from read_chunk_a()
    yield from read_chunk_b()

print(list(combined_pipeline()))  # ['A1', 'A2', 'B1', 'B2']
```

---

## 6. High-Performance Stream Tooling: `itertools`

The Python standard library `itertools` module contains C-implemented streaming primitives that chain together with zero intermediate list allocations.

```python
import itertools

# 1. islice: Stream slicing (O(1) memory, skips initial items without list slicing)
large_stream = (x * 2 for x in range(1_000_000))
first_ten = list(itertools.islice(large_stream, 0, 10))

# 2. chain: Seamless stream concatenation
stream_1 = ("header_1", "header_2")
stream_2 = ("data_1", "data_2")
unified = itertools.chain(stream_1, stream_2)

# 3. batched (Python 3.12+): Chunking streams into fixed batch sizes
data_feed = range(10)
batches = list(itertools.batched(data_feed, 3))
print(batches)  # [(0, 1, 2), (3, 4, 5), (6, 7, 8), (9,)]
```

---

## 7. Common Pitfalls and Systems Traps

### Pitfall 1: Generator Exhaustion
Generators are **single-pass data streams**. Once iterated, they cannot be restarted.

```python
numbers = (x for x in [1, 2, 3])

total = sum(numbers)      # Consumes the entire generator
count = len(numbers)      # TypeError: object of type 'generator' has no len()
retry_total = sum(numbers)# Returns 0! Generator is already exhausted.
```

### Pitfall 2: Memory Leaks from Generator References
If you keep a reference to a suspended generator that holds large local variables in its frame, those variables will not be garbage collected until the generator is exhausted or deleted.

---

## 8. Hands-On Systems Challenge: High-Throughput Log Stream Pipeline

### The Problem
In production systems, server log files can be 100 GB in size. Reading them with `f.readlines()` causes immediate system crashes.

Build a multi-stage streaming pipeline using generators that:
1. Lazily streams lines from an iterable data source.
2. Strips whitespace and filters out comment lines starting with `#`.
3. Parses structured tab-separated fields (`timestamp`, `level`, `service`, `latency_ms`).
4. Filters for slow requests where `latency_ms > 100.0`.
5. Yields micro-batches of 3 parsed records at a time.
6. Operates in strict $O(1)$ memory.

### Complete Runnable Implementation

```python
from dataclasses import dataclass
from typing import Iterator, Iterable

@dataclass
class LogRecord:
    timestamp: str
    level: str
    service: str
    latency_ms: float

# Stage 1: Raw line streamer
def stream_raw_lines(raw_data: str) -> Iterator[str]:
    for line in raw_data.strip().split("\n"):
        yield line

# Stage 2: Filter and clean lines (Generator)
def clean_lines(lines: Iterable[str]) -> Iterator[str]:
    for line in lines:
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            yield cleaned

# Stage 3: Parse into structured objects (Generator)
def parse_records(cleaned_lines: Iterable[str]) -> Iterator[LogRecord]:
    for line in cleaned_lines:
        parts = line.split("\t")
        if len(parts) == 4:
            yield LogRecord(
                timestamp=parts[0],
                level=parts[1],
                service=parts[2],
                latency_ms=float(parts[3])
            )

# Stage 4: Filter by latency threshold (Generator)
def filter_slow_requests(records: Iterable[LogRecord], threshold_ms: float) -> Iterator[LogRecord]:
    for rec in records:
        if rec.latency_ms >= threshold_ms:
            yield rec

# Stage 5: Batching stage (Generator yielding chunks)
def batch_stream(items: Iterable[LogRecord], batch_size: int) -> Iterator[list[LogRecord]]:
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch

def run_log_pipeline():
    synthetic_log_data = """
    # Server Log Stream - Host cluster 04
    2026-11-10T10:00:01\tINFO\tauth-service\t12.4
    2026-11-10T10:00:02\tWARN\tlims-database\t145.8
    # Keepalive ping
    2026-11-10T10:00:03\tINFO\tgateway\t8.2
    2026-11-10T10:00:04\tERROR\tbwa-aligner\t350.2
    2026-11-10T10:00:05\tWARN\tvariant-caller\t112.9
    2026-11-10T10:00:06\tINFO\tauth-service\t15.1
    2026-11-10T10:00:07\tERROR\tpipeline-qc\t210.0
    """

    # Assemble streaming pipeline (Zero data is processed yet! Pure composition):
    raw_stream = stream_raw_lines(synthetic_log_data)
    cleaned_stream = clean_lines(raw_stream)
    record_stream = parse_records(cleaned_stream)
    slow_requests = filter_slow_requests(record_stream, threshold_ms=100.0)
    batched_alerts = batch_stream(slow_requests, batch_size=2)

    # Pull data through the pipeline lazily:
    print("Processing batched alerts (O(1) memory):")
    batch_count = 0
    for batch in batched_alerts:
        batch_count += 1
        print(f"--- Alert Batch #{batch_count} ({len(batch)} records) ---")
        for alert in batch:
            print(f"  [{alert.service}] Latency: {alert.latency_ms}ms (Timestamp: {alert.timestamp})")

if __name__ == "__main__":
    run_log_pipeline()
```

---

## 9. Advanced `itertools` Streaming Arsenal

The `itertools` library provides high-speed, C-implemented combinatoric and filtering iterators.

```python
import itertools

# 1. accumulate: Running totals / prefixes (like std::partial_sum in C++)
numbers = [1, 3, 5, 7, 9]
running_sums = list(itertools.accumulate(numbers))
print(f"Running sums: {running_sums}")  # [1, 4, 9, 16, 25]

# Running maximum:
running_max = list(itertools.accumulate([3, 1, 4, 1, 5, 9, 2], max))
print(f"Running max:  {running_max}")   # [3, 3, 4, 4, 5, 9, 9]

# 2. compress: Boolean mask filtering (vectorized filtering without numpy)
records = ["sample_A", "sample_B", "sample_C", "sample_D"]
qc_flags = [True, False, True, False]
passed_samples = list(itertools.compress(records, qc_flags))
print(f"Passed samples: {passed_samples}")  # ['sample_A', 'sample_C']

# 3. takewhile & dropwhile: Conditional stream slicing
sensor_readings = [12, 14, 18, 95, 104, 15, 11]
# Takes elements until condition fails:
normal_prefix = list(itertools.takewhile(lambda x: x < 90, sensor_readings))
print(f"Normal prefix: {normal_prefix}")  # [12, 14, 18]

# 4. product: Cartesian product (replaces nested loops without indentation)
chromosomes = ["chr1", "chr2"]
strands = ["+", "-"]
loci = list(itertools.product(chromosomes, strands))
print(f"Loci: {loci}")  # [('chr1', '+'), ('chr1', '-'), ('chr2', '+'), ('chr2', '-')]
```

---

## 10. Turning Generators into Context Managers with `@contextlib.contextmanager`

One of the most elegant architectural applications of generators is writing **reusable context managers** using the standard library `@contextlib.contextmanager`.

Everything before `yield` acts as `__enter__()`. Everything after `yield` acts as `__exit__()`.

```python
from contextlib import contextmanager
import time
from typing import Iterator

@contextmanager
def execution_timer(label: str) -> Iterator[dict]:
    """
    Context manager created from a generator that measures block execution time.
    """
    stats = {"elapsed": 0.0}
    start = time.perf_counter()
    try:
        # yield suspends execution and passes 'stats' to the 'as' clause:
        yield stats
    finally:
        # Resumes on block exit (even if an exception occurred):
        stats["elapsed"] = time.perf_counter() - start
        print(f"[TIMER] {label}: {stats['elapsed']:.5f}s")

# Usage:
with execution_timer("Matrix computation") as timer_info:
    total = sum(i * i for i in range(500_000))

print(f"Timer captured externally: {timer_info['elapsed']:.5f}s")
```

---

## 11. Streaming Memory Profiling on 10,000,000 Datasets

Let us verify the physical memory behavior using `tracemalloc`.

```python
import tracemalloc
import sys

def run_memory_benchmark():
    n = 10_000_000

    # 1. Measure Generator Memory:
    tracemalloc.start()
    gen = (x * 2 for x in range(n))
    gen_current, gen_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Generator Peak Memory: {gen_peak / 1024:.2f} KiB")
    print(f"Generator Shallow Size: {sys.getsizeof(gen)} bytes")

    # 2. Pull first 100,000 items from generator:
    tracemalloc.start()
    first_chunk = [next(gen) for _ in range(100_000)]
    chunk_current, chunk_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"100k Pulled Items Peak Memory: {chunk_peak / (1024 * 1024):.2f} MiB")

if __name__ == "__main__":
    run_memory_benchmark()
```

Output highlights:
* The generator object itself consumes approximately **0.2 KiB** regardless of whether $N = 1,000$ or $N = 1,000,000,000$.
* Memory is only consumed by the downstream consumer holding active references.

---

## 12. Stream vs Batch Architecture Decision Guide

```text
STREAMING VS BATCHING DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
File size exceeds available RAM (> 8 GB)                Generator (yield lines)
Need random access or indexing by position (arr[i])     list
Need fast FIFO queue with max length constraint         collections.deque(maxlen=K)
Transforming infinite or unbounded event streams        Generator pipeline
Combining multiple data feeds without memory copy       itertools.chain
Chunking streaming data into database bulk inserts      itertools.batched
Memory-mapping huge binary arrays on disk               mmap / numpy.memmap
─────────────────────────────────────────────────────────────────────────────
```

### Architecture Decision Flowchart

```text
Do you need to store all items simultaneously for indexing or sorting?
  YES ──> Will the entire dataset fit comfortably in 50% of available RAM?
            YES ──> list / numpy array
            NO  ──> Memory-mapped file (mmap) or chunked disk database (SQLite)
  NO  ──> Do you only need to process items one at a time or in batches?
            YES ──> Generator Pipeline (yield) + itertools.batched
```

---

## 13. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 07:

- [ ] What is the exact difference between an Iterable and an Iterator?
- [ ] How does `for x in iterable` lower to C-level opcodes in CPython?
- [ ] What compiler flag is set on the code object when a function contains `yield`?
- [ ] How does CPython freeze and resume a generator's execution frame without destroying it?
- [ ] Why does processing a 10 GB file with generators consume less than 1 MB of RAM?
- [ ] How does `yield from` simplify sub-generator delegation?
- [ ] Why will calling `len()` on a generator fail with a `TypeError`?
- [ ] How does `itertools.compress` filter items using boolean masks?
- [ ] How does `@contextlib.contextmanager` turn a generator function into a `with` statement?
- [ ] Given a dataset larger than physical RAM, how would you architect an end-to-end processing pipeline?



---

## 14. Chaining Generators into a Pipeline: Design Pattern

Generators are composable. Each stage is a pure function: it accepts an iterable and yields transformed items. No stage stores the full dataset. Data flows one item at a time through every stage simultaneously.

```text
DATA FLOW THROUGH A 4-STAGE PIPELINE
=====================================

  source(1_000_000)
        |
        |  one int at a time
        v
  double(items)         -- multiplies by 2
        |
        |  one int at a time
        v
  keep_even(items)      -- filters: keeps multiples of 4
        |
        |  one int at a time
        v
  stringify(items)      -- formats as "result:N"
        |
        v
  consumer (next / for loop)

At any moment only ONE item exists in the pipeline.
Memory used = O(1), independent of source size.
```

```python
# PIPELINE DESIGN PATTERN
# Each stage: takes Iterable[T] -> yields Iterable[U]
# Data flows one item at a time through ALL stages

from typing import Iterator, Iterable
import sys

# Stage functions
def source(n: int) -> Iterator[int]:
    """Produces raw items."""
    yield from range(n)

def double(items: Iterable[int]) -> Iterator[int]:
    for x in items:
        yield x * 2

def keep_even(items: Iterable[int]) -> Iterator[int]:
    for x in items:
        if x % 4 == 0:
            yield x

def stringify(items: Iterable[int]) -> Iterator[str]:
    for x in items:
        yield f"result:{x}"

# Compose the pipeline (no data processed yet!):
pipeline = stringify(keep_even(double(source(1_000_000))))

# Pull data through lazily:
first_five = [next(pipeline) for _ in range(5)]
print(first_five)
# ['result:0', 'result:4', 'result:8', 'result:12', 'result:16']

# Memory check: the pipeline object is tiny regardless of source(N)
print(f"Pipeline object size: {sys.getsizeof(pipeline)} bytes")
```

**Pipeline vs batch processing: the key difference:**

```python
import sys

N = 1_000_000

# BATCH: every intermediate list is fully materialised in memory
batch_stage1 = [x * 2 for x in range(N)]           # ~8 MB
batch_stage2 = [x for x in batch_stage1 if x % 4 == 0]  # ~4 MB
batch_stage3 = [f"result:{x}" for x in batch_stage2]    # ~20+ MB

print(f"Batch stage1 size : {sys.getsizeof(batch_stage1):>12,} bytes")
print(f"Batch stage2 size : {sys.getsizeof(batch_stage2):>12,} bytes")
print(f"Batch stage3 size : {sys.getsizeof(batch_stage3):>12,} bytes")

# PIPELINE: nothing materialised until consumed
pipe = stringify(keep_even(double(range(N))))
print(f"Pipeline size     : {sys.getsizeof(pipe):>12,} bytes")  # ~200 bytes
```

---

## 15. Generator Expression vs genexpr Chaining

Generator expressions can be chained exactly like generator functions. The result is equivalent but more compact. No intermediate lists are created.

```python
source_data = range(1_000_000)

# Chained generator expressions (no intermediate lists!):
doubled     = (x * 2 for x in source_data)
keep_even   = (x for x in doubled if x % 4 == 0)
stringified = (f"result:{x}" for x in keep_even)

# Still O(1) memory:
import sys
print(sys.getsizeof(stringified))  # ~200 bytes regardless of source size

# Pull just what you need:
import itertools
sample = list(itertools.islice(stringified, 5))
print(sample)
# ['result:0', 'result:4', 'result:8', 'result:12', 'result:16']
```

**When to use a generator function vs a generator expression:**

```text
USE A GENERATOR FUNCTION when:
  - The stage has complex branching logic
  - You need multiple yield points
  - You need try/finally for resource cleanup
  - You need to maintain local state across items
  - Readability matters more than brevity

USE A GENERATOR EXPRESSION when:
  - The transformation fits on one line
  - It is a simple map or filter
  - You are composing a quick ad-hoc pipeline inline
```

---

## 16. Async Generators: asyncio + yield

Python 3.6+ allows `async def` combined with `yield`. The result is an **async generator**: a coroutine that produces a stream of values without blocking the event loop between yields. Iterate it with `async for`.

**Use cases:** streaming rows from an async database driver, consuming a WebSocket feed, paginating an async HTTP API.

```python
import asyncio

async def async_sensor_stream(count: int):
    """Async generator simulating a live sensor feed."""
    for i in range(count):
        await asyncio.sleep(0.01)  # Non-blocking wait (simulates network read)
        yield {"sensor_id": f"S_{i:03d}", "value": i * 1.5}

async def process_stream():
    total = 0.0
    readings = 0

    async for reading in async_sensor_stream(10):
        total += reading["value"]
        readings += 1
        print(f"  Received: {reading}")

    print(f"Average value: {total / readings:.2f}")

if __name__ == "__main__":
    asyncio.run(process_stream())
```

**How `async for` interacts with the event loop:**

```text
EVENT LOOP
==========

  process_stream coroutine
        |
        |  async for reading in async_sensor_stream(10):
        |
        v
  async_sensor_stream coroutine
        |
        |  await asyncio.sleep(0.01)
        |  |
        |  +---> suspends generator, returns control to event loop
        |         (other coroutines can run here)
        |  |
        |  +<--- event loop resumes generator after 0.01 s
        |
        |  yield {"sensor_id": ..., "value": ...}
        |  |
        +--+---> async for receives one item, runs loop body
        |
        |  (repeat for next item)
        v
  StopAsyncIteration raised -> async for exits cleanly

Key difference from a regular for loop:
  Regular for   -- blocks the thread until next() returns
  async for     -- suspends the coroutine (not the thread) at each await,
                   freeing the event loop to run other work
```

---

## 17. Extended Checklist

Add these items alongside the existing Day 6 checklist:

- [ ] How does the pipeline design pattern achieve O(1) memory regardless of dataset size?
- [ ] When would you use a generator function over a generator expression for a pipeline stage?
- [ ] What is an async generator and how does `async for` differ from a regular `for` loop?
