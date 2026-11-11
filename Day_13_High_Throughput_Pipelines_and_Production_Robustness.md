# Day 13: High-Throughput Pipelines, Memory Discipline & Production Robustness

## 1. Architecture Overview: The Production High-Throughput Challenge

In enterprise data platforms, bioinformatics clusters, and high-concurrency backend services, data volumes frequently exceed available system memory. A single sequencing run, transaction log, or event stream can range from 20 GB to 1 TB. 

When engineers transition from languages like Java or C++ to Python, they often encounter sudden pipeline crashes on shared compute nodes (such as SLURM HPC clusters or Kubernetes pods). The root cause is almost always the same: treating Python as an in-memory scripting language rather than engineering for memory discipline and operating system realities.

```
ANTI-PATTERN: BATCH IN-MEMORY BUFFERING (Causes SLURM OOM Killer / Exit Code 137)
+---------------+      +-------------------------+      +-------------------+
| 50 GB Input   | ---> | RAM: Buffers all lines  | ---> | OS OOM Killer     |
| (VCF / FASTQ) |      | Consumes 80 GB+ memory  |      | SIGKILL (137)     |
+---------------+      +-------------------------+      +-------------------+

PRODUCTION PATTERN: O(1) STREAMING GENERATOR PIPELINE (RAM < 25 MB Constant)
+---------------+      +-------------+      +-------------+      +---------------+
| 50 GB Stream  | ---> | Chunk / Row | ---> | Filter &    | ---> | Atomic Output |
| (Gzip / Disk) |      | Generator   |      | Transform   |      | Writer        |
+---------------+      +-------------+      +-------------+      +---------------+
                              |                    |                     |
                              +--- Yields 1 record at a time ------------+
```

### The Three Tenets of High-Throughput Systems Engineering in Python
1. **Memory Discipline Over Brute Force:** Operate in $O(1)$ auxiliary space regardless of input scale. Understand the Linux Out-Of-Memory (OOM) Killer, virtual memory vs. resident set size (RSS), and why memory is not always returned to the operating system.
2. **C-Level Overhead Awareness:** Understand how CPython allocates memory under the hood. Avoid object allocation amplification by leveraging `__slots__`, string interning (`sys.intern`), zero-copy buffer views, and contiguous C-memory layouts.
3. **Production Robustness & Test Isolation:** Write fault-tolerant pipelines with atomic file outputs (`os.replace`), POSIX signal trapping (`SIGTERM`), structured logging, and deterministic `pytest` fixtures using in-memory streams.

---

## 2. Memory Discipline 1: Resident Set Size (RSS), Virtual Memory & Linux OOM Mechanics

### Virtual Memory (VSZ) vs. Resident Set Size (RSS)
* **Virtual Memory Size (VSZ):** The total memory address space the process has requested from the OS kernel. This includes mapped libraries, allocated heap space, shared memory, and uncommitted pages. A high VSZ does not necessarily consume physical RAM.
* **Resident Set Size (RSS):** The portion of memory currently held in physical RAM for the process. This is the metric tracked by OS schedulers (SLURM, Kubernetes, systemd cgroups).
* **Dirty Pages:** Memory pages modified by the process that must remain in RAM (or swap) because they differ from what is stored on disk.

```
+-----------------------------------------------------------------------+
| TOTAL PROCESS VIRTUAL ADDRESS SPACE (VSZ)                             |
|  +-------------------------+ +-------------------+ +----------------+ |
|  | Shared Libraries (.so)  | | Mapped Files      | | CPython Heap   | |
|  +-------------------------+ +-------------------+ +----------------+ |
|               |                                            |          |
|               +--------------------+   +-------------------+          |
|                                    v   v                              |
|                    +------------------------------------+             |
|                    | PHYSICAL RAM: RESIDENT SET SIZE    |             |
|                    | (Monitored by SLURM / cgroups)     |             |
|                    +------------------------------------+             |
+-----------------------------------------------------------------------+
```

### The Linux OOM Killer and Exit Code 137
When a task running inside a Docker container, Kubernetes pod, or SLURM cluster allocation exceeds its memory ceiling, the Linux kernel triggers the Out-Of-Memory Killer (`oom-killer`). 

1. The kernel selects the offending process based on its `oom_score` (a ratio of its RSS relative to the cgroup memory limit).
2. The kernel dispatches an uncatchable `SIGKILL` (signal 9) directly to the process.
3. The process terminates immediately without executing `finally` blocks, flushing file buffers, or closing database connections.
4. The scheduler reports exit code `137` ($128 + 9 = 137$).

### Why Python Does Not Return Memory to the OS
In CPython, memory management operates in three tiers:
1. **Small Object Allocator (`pymalloc`):** Manages allocations $\le 512$ bytes. It groups memory into Arenas (256 KB), Pools (4 KB), and Blocks (size-classed in multiples of 8 bytes).
2. **System Allocator (`malloc` / `mmap`):** Used for allocations $> 512$ bytes.

```
+------------------------------------------------------------------+
| CPython 256 KB Arena                                             |
|  +--------------------+  +--------------------+  +-------------+ |
|  | 4 KB Pool (Size A) |  | 4 KB Pool (Size B) |  | 4 KB Pool...| |
|  | [B][B][B][B][B][B] |  | [B][B][B][B][B][B] |  |             | |
|  +--------------------+  +--------------------+  +-------------+ |
+------------------------------------------------------------------+
```

An entire 256 KB Arena can only be released back to the OS via `free()` if **every single 4 KB pool inside it is completely empty**. If a single small object remains alive in one pool, the entire arena remains pinned in process RSS. 

**Rule:** Never allocate temporary multi-million object collections into Python heap memory with the expectation that `del` and `gc.collect()` will immediately shrink the process RSS back to the OS.

---

## 3. Memory Discipline 2: O(1) Generator Pipelines & Stream Buffering

### The Anti-Pattern: Reading Entire Files into RAM
```python
# ANTI-PATTERN: Attempts to read all lines into a Python list
# A 20 GB file creates hundreds of millions of string objects,
# causing an immediate memory spike of 60 GB+ and triggering OOM.
def process_data_bad(filepath: str):
    with open(filepath, "r") as f:
        records = f.readlines()  # Catastrophic memory exhaustion
    return [parse(r) for r in records if is_valid(r)]
```

### The Production Pattern: Multi-Stage Generator Pipelines
A pipeline should be constructed as a sequence of independent generator stages connected through `yield`. Memory remains constant ($O(1)$) because only one record is in flight at any given moment.

```python
"""Memory-efficient multi-stage generator streaming pipeline."""

from pathlib import Path
from typing import Iterator, NamedTuple
import gzip


class RawRecord(NamedTuple):
    line_number: int
    content: str


class ParsedRecord(NamedTuple):
    chrom: str
    pos: int
    ref: str
    alt: str


def source_stream(path: Path) -> Iterator[RawRecord]:
    """Stage 1: Stream uncompressed or gzipped lines in O(1) auxiliary space."""
    is_gz = path.suffix == ".gz"
    open_fn = gzip.open if is_gz else open
    mode = "rt" if is_gz else "r"

    with open_fn(path, mode=mode, encoding="utf-8", errors="replace") as stream:
        for idx, line in enumerate(stream, start=1):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                yield RawRecord(line_number=idx, content=stripped)


def transform_stream(records: Iterator[RawRecord]) -> Iterator[ParsedRecord]:
    """Stage 2: Parse raw string lines into structured tuples."""
    for record in records:
        parts = record.content.split("\t")
        if len(parts) >= 5:
            yield ParsedRecord(
                chrom=parts[0],
                pos=int(parts[1]),
                ref=parts[3],
                alt=parts[4],
            )


def filter_stream(records: Iterator[ParsedRecord], target_chrom: str) -> Iterator[ParsedRecord]:
    """Stage 3: Apply business logic filters on the fly."""
    for record in records:
        if record.chrom == target_chrom:
            yield record


def sink_stream(records: Iterator[ParsedRecord], output_path: Path) -> int:
    """Stage 4: Write transformed records to disk with buffered I/O."""
    count = 0
    with open(output_path, "w", encoding="utf-8", buffering=64 * 1024) as out:
        for record in records:
            out.write(f"{record.chrom}\t{record.pos}\t{record.ref}\t{record.alt}\n")
            count += 1
    return count
```

### Buffer Sizing: 64 KB / 128 KB Chunking
By default, Python file I/O uses system default buffering (often 8 KB). On high-throughput network storage (NFS, Lustre, GPFS) or enterprise SSDs, small 8 KB buffers cause high syscall frequency (`read()` / `write()`) and CPU context switching.

Specifying `buffering=64 * 1024` (64 KB) or `buffering=128 * 1024` (128 KB) matches the underlying filesystem block boundaries, maximizing throughput and reducing system call overhead.

---

## 4. Memory Discipline 3: Zero-Copy Slicing with `memoryview` & `bytearray`

When slicing a standard Python `bytes` or `str` object, Python allocates a brand-new object on the heap and copies the underlying bytes into the new memory buffer.

```python
data = b"X" * 100_000_000  # 100 MB buffer
chunk = data[10:20]          # Allocates a new 10-byte object on the heap
```

If a binary protocol or fixed-width parser slices millions of records from a large buffer, memory copying creates high GC pressure and CPU churn.

### Zero-Copy Architecture via `memoryview`
The `memoryview` type uses Python's C-level Buffer Protocol. It exposes the underlying memory buffer of an object without copying bytes. Slicing a `memoryview` produces another `memoryview` that points directly to the original memory slice.

```python
"""Demonstration of zero-copy slicing with memoryview."""

import sys

# Allocate a 50 MB bytearray
raw_payload = bytearray(b"A" * (50 * 1024 * 1024))

# Standard slicing: Allocates a new 10 MB bytes object
standard_slice = bytes(raw_payload[0:10_000_000])
print(f"Standard slice size: {sys.getsizeof(standard_slice)} bytes")
# Output: ~10,000,033 bytes allocated

# Zero-copy view
view = memoryview(raw_payload)
zero_copy_slice = view[0:10_000_000]

print(f"Zero-copy slice view object size: {sys.getsizeof(zero_copy_slice)} bytes")
# Output: 200 bytes (Only the view metadata wrapper, 0 bytes duplicated)
```

Use `memoryview` when parsing:
1. Binary telemetry or medical device packet streams.
2. Large BAM/CRAM alignment blocks in genomics.
3. Memory-mapped files (`mmap`).

---

## 5. C-Level Overhead 1: The Anatomy of a `PyObject`

In languages like C or Rust, an unsigned integer consumes 4 or 8 bytes of memory. In Java, an `int` consumes 4 bytes. 

In CPython, **everything is a heap-allocated pointer to a `PyObject` structure**.

```
STANDARD 64-BIT CPYTHON PyObject HEADER
+---------------------------------------------------------------+
| Offset 0x00 - 0x08 : ob_refcnt (uint64_t / 8 bytes)           |
+---------------------------------------------------------------+
| Offset 0x08 - 0x10 : ob_type   (struct _typeobject* / 8 bytes)|
+---------------------------------------------------------------+
Total header overhead: 16 bytes minimum before any data payload.
```

For variable-sized objects (strings, lists, tuples, dictionaries), CPython uses `PyVarObject`:

```
STANDARD 64-BIT CPYTHON PyVarObject HEADER
+---------------------------------------------------------------+
| Offset 0x00 - 0x08 : ob_refcnt (8 bytes)                      |
+---------------------------------------------------------------+
| Offset 0x08 - 0x10 : ob_type   (8 bytes)                      |
+---------------------------------------------------------------+
| Offset 0x10 - 0x18 : ob_size   (ssize_t / 8 bytes)            |
+---------------------------------------------------------------+
Total header overhead: 24 bytes minimum.
```

### Why a Simple Python Integer Consumes 28 Bytes
In Python 3, integers have arbitrary precision (they do not overflow at 64 bits). The CPython implementation is `PyLongObject`:
* `ob_refcnt`: 8 bytes
* `ob_type`: 8 bytes
* `ob_size`: 8 bytes
* `ob_digit[1]`: 4 bytes (holds the 30-bit integer value)
* **Total:** $8 + 8 + 8 + 4 = 28\text{ bytes}$

```python
import sys

val = 42
print(sys.getsizeof(val))  # Prints 28 bytes
```

### String Internals: PEP 393 Flexible String Representation
Python strings (`PyUnicodeObject`) do not store raw ASCII bytes directly. CPython inspects the characters in the string and uses one of three internal representations:
1. **1 byte per character (Latin-1):** If all characters fit in ASCII/Latin-1 ($U+0000$ to $U+00FF$).
2. **2 bytes per character (UCS-2):** If all characters fit in the Basic Multilingual Plane ($U+0000$ to $U+FFFF$).
3. **4 bytes per character (UCS-4):** If characters include emojis or complex scripts ($U+10000$ to $U+10FFFF$).

The string header itself adds **48 to 80 bytes** of metadata:
* Refcount, type pointer, length, hash cache, state flags, and UTF-8 buffer pointer.

```python
import sys

empty_str = ""
print(sys.getsizeof(empty_str))  # 49 bytes (Compact ASCII base header)

short_str = "chr1"
print(sys.getsizeof(short_str))  # 49 + 4 = 53 bytes for just 4 characters
```

### Memory Footprint Comparison

| Data Type | C / Rust Primitive | Java Primitive / Object | CPython Equivalent | CPython Memory Size |
| :--- | :--- | :--- | :--- | :--- |
| Integer | 4 bytes (`int32_t`) | 4 bytes (`int`) | `int` (`PyLongObject`) | **28 bytes** |
| Float | 8 bytes (`double`) | 8 bytes (`double`) | `float` (`PyFloatObject`) | **24 bytes** |
| Boolean | 1 byte (`bool`) | 1 byte (`boolean`) | `bool` (`PyBoolObject`) | **28 bytes** |
| 4-char string | 4 bytes (`char[4]`) | ~24 bytes (`String`) | `str` (`PyUnicodeObject`) | **53 bytes** |

---

## 6. C-Level Overhead 2: Object Footprints & Instance Dictionaries

When creating an instance of a standard Python class, CPython allocates a dictionary (`__dict__`) for that instance to support dynamic attribute assignment at runtime.

```
STANDARD PYTHON OBJECT IN MEMORY
+----------------------------------+
| PyObject Header (16 bytes)       |
+----------------------------------+
| Pointer to __dict__ (8 bytes)    | ---> +--------------------------------+
+----------------------------------+      | Instance __dict__ (Hash Table) |
| Pointer to __weakref__ (8 bytes) |      | Keys, Hashes, Values           |
+----------------------------------+      | Consumes ~104 to 152 bytes     |
                                          +--------------------------------+
```

### The Benchmark: Standard Class vs. `__slots__` vs. `@dataclass(slots=True)`

```python
"""Memory footprint comparison of standard classes vs slots."""

from dataclasses import dataclass
import sys


class StandardVariant:
    def __init__(self, chrom: str, pos: int, ref: str, alt: str):
        self.chrom = chrom
        self.pos = pos
        self.ref = ref
        self.alt = alt


class SlottedVariant:
    __slots__ = ("chrom", "pos", "ref", "alt")

    def __init__(self, chrom: str, pos: int, ref: str, alt: str):
        self.chrom = chrom
        self.pos = pos
        self.ref = ref
        self.alt = alt


@dataclass(slots=True)
class ModernDataclassVariant:
    chrom: str
    pos: int
    ref: str
    alt: str


v_std = StandardVariant("chr1", 100450, "A", "G")
v_slot = SlottedVariant("chr1", 100450, "A", "G")
v_data = ModernDataclassVariant("chr1", 100450, "A", "G")

# Calculate direct memory consumption
std_size = sys.getsizeof(v_std) + sys.getsizeof(v_std.__dict__)
slot_size = sys.getsizeof(v_slot)
data_size = sys.getsizeof(v_data)

print(f"Standard Class Instance:  {std_size} bytes")
print(f"Slotted Class Instance:   {slot_size} bytes")
print(f"Modern Dataclass (slots): {data_size} bytes")
```

### Output Analysis
* **Standard Class:** ~152 bytes per instance (Object pointer + dynamic dictionary hash table).
* **Slotted Class:** ~56 bytes per instance (Fixed C-array of attribute pointers, no `__dict__`).
* **Memory Reduction:** **Over 60% memory savings per instance**.

```
SCALING TO 10 MILLION OBJECTS IN RAM:
+-------------------------------+-----------------------+
| Object Representation         | RAM Required          |
+-------------------------------+-----------------------+
| Standard Class (__dict__)     | ~1.52 GB              |
| __slots__ / Dataclass(slots)  | ~0.56 GB              |
| Net Memory Saved              | ~0.96 GB (63% savings)|
+-------------------------------+-----------------------+
```

---

## 7. C-Level Overhead 3: String Interning (`sys.intern`) for Low-Cardinality Fields

When processing tabular datasets, log streams, or genomic callsets, certain categorical string values appear millions of times (e.g. chromosome names: `chr1`, `chr2`, HTTP status codes, status flags: `PASS`, `FILTERED`).

By default, every time Python reads `"chr1"` from a file, it allocates a distinct `PyUnicodeObject` in memory. If 5 million rows contain `"chr1"`, you allocate 5 million separate 53-byte string objects ($5{,}000{,}000 \times 53\text{ bytes} \approx 265\text{ MB}$).

### The String Interning Solution
`sys.intern()` forces CPython to look up the string in its global internal dictionary of interned strings. If the string already exists, it returns a pointer to the existing singleton object.

```
WITHOUT INTERNING (5 Million Duplicates)
Row 1: "chr1" ---> Heap Object 0x7f01 (53 bytes)
Row 2: "chr1" ---> Heap Object 0x7f02 (53 bytes)
Row 3: "chr1" ---> Heap Object 0x7f03 (53 bytes)
Total: 265 MB allocated

WITH sys.intern() (Singleton Pointer Reuse)
Row 1: intern("chr1") ---> +---------------------------------+
Row 2: intern("chr1") ---> | Shared Singleton 0x7f01        | (53 bytes total)
Row 3: intern("chr1") ---> +---------------------------------+
Total: 53 bytes + 8-byte pointer references
```

```python
"""Benchmark showing memory savings with sys.intern()."""

import sys

# Simulating parsing 1,000,000 records with repeated chromosome names
CHROM_LABEL = "chr1_gl000191_random"

# Without interning: Allocates new strings
raw_list = [f"{CHROM_LABEL}" for _ in range(1_000_000)]
first_ptr = id(raw_list[0])
second_ptr = id(raw_list[1])
print(f"Without interning: Same memory address? {first_ptr == second_ptr}")
# Output: False (Separate allocations)

# With interning: Reuses single canonical instance
interned_list = [sys.intern(f"{CHROM_LABEL}") for _ in range(1_000_000)]
first_intern_ptr = id(interned_list[0])
second_intern_ptr = id(interned_list[1])
print(f"With interning: Same memory address? {first_intern_ptr == second_intern_ptr}")
# Output: True (All pointers reference the exact same object in CPython heap)
```

### Performance Bonus: Pointer Comparison
When comparing interned strings with `is`, Python performs an $O(1)$ memory address comparison (single CPU instruction) rather than an $O(n)$ character-by-character string traversal.

```python
# O(1) pointer comparison on interned strings:
if record.chrom is TARGET_CHROM_INTERNED:
    process(record)
```

---

## 8. C-Level Overhead 4: Memory-Mapped Files (`mmap`) & OS Page Cache

When an application needs fast, random-access lookups into a massive multi-gigabyte reference file (e.g. genomic index files, binary lookups, static dictionaries), loading the file into Python RAM requires huge allocations.

### Operating System Memory-Mapping (`mmap`)
The `mmap` module maps a file directly into the virtual address space of the process using the OS kernel's virtual memory subsystem.
* **Zero Initial Heap Allocation:** The file is not read into RAM upfront.
* **On-Demand Page In:** When bytes are accessed, the OS kernel brings only the requested 4 KB physical memory pages into the OS page cache.
* **Shared Across Processes:** If multiple worker processes map the same file on Linux, they share the exact same physical memory pages in the kernel page cache.

```python
"""Random-access lookups on large files using mmap."""

from pathlib import Path
import mmap


def inspect_large_binary_index(file_path: Path, offset: int, length: int) -> bytes:
    """Read a specific slice of a 10 GB file in constant O(1) memory space."""
    with open(file_path, "rb") as f:
        # Map the entire file read-only
        with mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
            # Random seek and read without loading the preceding bytes
            mm.seek(offset)
            data_slice = mm.read(length)
            return data_slice
```

---

## 9. Production Robustness 1: Atomic File Replacement (`os.replace`)

### The Vulnerability: Non-Atomic File Writes
If a pipeline process writes directly to `final_output.tsv` and is suddenly terminated by the SLURM OOM Killer, network disconnect, or power failure, `final_output.tsv` is left in a corrupted, truncated state. Downstream pipeline stages may read this partial file and produce silent analytical errors.

```
VULNERABLE WRITE (Corrupts on crash):
open("final_output.tsv", "w").write(...)
            ^
            |--- Process dies here -> final_output.tsv is left half-written!
```

### The Solution: POSIX Atomic Rename Guarantee
On POSIX filesystems (Linux, macOS), the `rename` system call (`os.replace` in Python) is guaranteed to be **atomic** as long as both paths reside on the same filesystem mount:
1. The output is written to a hidden temporary file in the destination directory (`.final_output.tsv.tmp.12345`).
2. The file is flushed to physical media using `os.fsync()`.
3. `os.replace(temp_path, final_path)` is executed. The directory entry flips atomically. Downstream processes either see the old complete file or the new complete file; they never see a partial file.

```python
"""Production context manager for guaranteed atomic file writes."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
import os
import tempfile


@contextmanager
def atomic_write(target_path: Path, mode: str = "w", encoding: str = "utf-8") -> Iterator:
    """Context manager for atomic file writing.

    Writes to a temporary file in the same directory, flushes to disk,
    and atomically renames to the target path upon clean context exit.
    If an unhandled exception occurs, the temporary file is deleted.
    """
    target_path = Path(target_path)
    parent_dir = target_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    # Prefix with dot so temporary files remain hidden on Unix
    prefix = f".{target_path.name}.tmp_"
    
    # Crucial: Must be created in the SAME directory to guarantee same filesystem mount
    tmp_file = tempfile.NamedTemporaryFile(
        mode=mode,
        dir=parent_dir,
        prefix=prefix,
        delete=False,
        encoding=encoding if "b" not in mode else None,
    )
    tmp_path = Path(tmp_file.name)

    try:
        yield tmp_file
        tmp_file.flush()
        # Force OS to flush kernel buffers to physical storage
        os.fsync(tmp_file.fileno())
        tmp_file.close()

        # Atomic POSIX rename
        os.replace(tmp_path, target_path)
    except Exception:
        tmp_file.close()
        if tmp_path.exists():
            tmp_path.unlink()  # Clean up temporary artifact
        raise
```

---

## 10. Production Robustness 2: POSIX Signal Handling (`SIGTERM`, `SIGINT`) & Clean Shutdown

When cluster workload managers (SLURM, Kubernetes, AWS Batch) preempt a job, reschedule a node, or enforce walltime limits, they do not immediately issue `SIGKILL`. Instead, they issue a polite warning signal: `SIGTERM` (signal 15).
* On SLURM, `SIGTERM` is dispatched typically 30 to 120 seconds before the hard `SIGKILL`.
* If your application does not catch `SIGTERM`, Python immediately terminates, leaving temporary files and unfinished transactions on disk.

### Clean Shutdown Architecture
```python
"""Production signal handling for graceful cluster eviction."""

from typing import Callable
import logging
import signal
import sys

logger = logging.getLogger("PipelineEngine")


class GracefulKiller:
    """Captures SIGINT and SIGTERM to enable clean shutdown loops."""

    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        logger.warning("Received signal %s (%d). Flagging graceful shutdown...", sig_name, signum)
        self.kill_now = True


# Usage in a high-throughput processing loop
def run_pipeline(stream, output_writer):
    killer = GracefulKiller()

    for record in stream:
        if killer.kill_now:
            logger.info("Eviction detected. Flushing buffers and checkpointing...")
            output_writer.flush()
            # Standard Unix exit code for SIGTERM is 128 + 15 = 143
            sys.exit(143)

        output_writer.write(record)
```

---

## 11. Production Robustness 3: Structured Logging & Error Boundaries

### Why `print()` Is Forbidden in Production
1. **Unbuffered Interleaving:** `print()` writes to `sys.stdout`. If multiple threads or sub-processes write simultaneously, lines interleave unpredictably.
2. **No Context:** Missing ISO timestamps, logging severity levels (`INFO`, `WARNING`, `ERROR`), module names, and line numbers.
3. **No Dynamic Filtering:** In production, you cannot switch `print()` statements to quiet mode without editing code.

### Production Structured Logging Configuration
```python
"""Production structured logging setup."""

from pathlib import Path
import logging
import sys


def configure_production_logger(name: str, log_file: Path | None = None) -> logging.Logger:
    """Configure a production logger with standard formatting."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers on re-entry
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [pid:%(process)d] %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    # Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (if requested)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
```

---

## 12. Production Robustness 4: Deterministic Testing with Mock Streams (`pytest`)

Testing high-throughput pipelines that consume 50 GB files does not require generating 50 GB files in CI/CD. Production engineers test data streaming logic in memory using `io.StringIO` and `io.BytesIO`.

### In-Memory Streaming Fixtures
```python
"""Deterministic unit testing of stream parsers using in-memory fixtures."""

from pathlib import Path
import gzip
import io
import pytest

from genomic_stream_filter import stream_vcf_records, VariantRecord


@pytest.fixture
def sample_vcf_text() -> str:
    """Synthetic VCF dataset for deterministic testing."""
    return (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t1001\trs123\tA\tC\t99.0\tPASS\tDP=50\n"
        "chr2\t2002\t.\tG\tT\t15.0\tLowQual\tDP=5\n"
        "chrX\t3003\trs789\tT\tA\t85.5\tPASS\tDP=30\n"
    )


@pytest.fixture
def mock_gzipped_vcf(tmp_path: Path, sample_vcf_text: str) -> Path:
    """Creates a temporary, valid .vcf.gz file in isolated pytest directory."""
    gz_file = tmp_path / "test_sample.vcf.gz"
    with gzip.open(gz_file, "wt", encoding="utf-8") as f:
        f.write(sample_vcf_text)
    return gz_file


def test_vcf_streaming_parser(mock_gzipped_vcf: Path):
    """Verify that records are streamed and parsed with correct types."""
    records = list(stream_vcf_records(mock_gzipped_vcf))
    assert len(records) == 3

    r1 = records[0]
    assert r1.chrom == "chr1"
    assert r1.pos == 1001
    assert r1.ref == "A"
    assert r1.alt == "C"
    assert r1.qual == 99.0
    assert r1.filter_status == "PASS"


def test_vcf_malformed_lines_graceful_recovery(tmp_path: Path):
    """Verify that corrupted lines are logged and skipped without crashing."""
    corrupted_content = (
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t1001\trs123\tA\n"  # Malformed: Only 4 fields
        "chr1\t1002\trs124\tC\tT\t80.0\tPASS\tDP=20\n"
    )
    vcf_file = tmp_path / "corrupted.vcf"
    vcf_file.write_text(corrupted_content, encoding="utf-8")

    records = list(stream_vcf_records(vcf_file))
    assert len(records) == 1
    assert records[0].pos == 1002
```

---

## 13. Master Production Project: The Hardened High-Throughput Stream Filter

Below is a complete, production-grade CLI utility that incorporates all concepts from Day 13:
* Generator streaming in $O(1)$ memory.
* Modern `@dataclass(slots=True)` data structures.
* String interning (`sys.intern`) for low-cardinality fields.
* Atomic file replacement (`os.replace`).
* POSIX `SIGTERM` signal trap for clean cluster shutdown.
* Structured logging and defensive exception handling.

### `genomic_stream_filter.py`
```python
#!/usr/bin/env python3
"""Hardened high-throughput genomic stream filtering utility.

Engineered to operate in constant O(1) memory space (< 25 MB RAM)
regardless of input file size. Adheres to PEP 8, Google Python Style,
and production HPC robustness patterns.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import gzip
import logging
import os
import signal
import sys
import tempfile

# Configure production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [pid:%(process)d] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("StreamFilter")


class PipelineEvictionError(Exception):
    """Raised when cluster manager evicts the process via SIGTERM."""


class SignalMonitor:
    """Catches POSIX signals and exposes a boolean flag for safe loop exit."""

    def __init__(self):
        self.received_shutdown = False
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        logger.warning("Caught signal %s (%d). Flagging graceful pipeline shutdown.", sig_name, signum)
        self.received_shutdown = True


@dataclass(slots=True, frozen=True)
class VariantRecord:
    """Memory-optimized representation of a genomic variant call.

    Utilizes __slots__ to eliminate __dict__ allocation, saving >60% RAM.
    """
    chrom: str
    pos: int
    ref: str
    alt: str
    qual: float
    filter_status: str


@contextmanager
def atomic_file_writer(target_path: Path) -> Iterator:
    """Atomic write context manager guaranteeing no partial outputs on failure."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        dir=target_path.parent,
        prefix=f".{target_path.name}.tmp_",
        delete=False,
        encoding="utf-8",
    )
    tmp_path = Path(tmp.name)

    try:
        yield tmp
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp_path, target_path)
        logger.info("Successfully committed atomic output to %s", target_path)
    except Exception as exc:
        tmp.close()
        if tmp_path.exists():
            tmp_path.unlink()
        logger.error("Pipeline failure during write. Removed partial file %s. Error: %s", tmp_path, exc)
        raise


def stream_vcf_records(vcf_path: Path) -> Iterator[VariantRecord]:
    """Streams VCF records one by one in O(1) auxiliary memory space."""
    if not vcf_path.exists():
        raise FileNotFoundError(f"Input file not found: {vcf_path}")

    is_gz = vcf_path.suffix == ".gz" or vcf_path.name.endswith(".vcf.gz")
    open_fn = gzip.open if is_gz else open
    mode = "rt" if is_gz else "r"

    logger.info("Streaming variants from %s (GZIP: %s)", vcf_path.name, is_gz)

    with open_fn(vcf_path, mode=mode, encoding="utf-8", errors="replace") as stream:
        for line_num, line in enumerate(stream, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            fields = line.split("\t")
            if len(fields) < 7:
                logger.warning("Skipping malformed row at line %d: insufficient columns", line_num)
                continue

            try:
                pos = int(fields[1])
                qual = float(fields[5]) if fields[5] != "." else 0.0
            except ValueError:
                logger.warning("Skipping malformed row at line %d: non-numeric POS or QUAL", line_num)
                continue

            # Optimize memory: sys.intern() deduplicates repetitive chromosome & filter strings
            yield VariantRecord(
                chrom=sys.intern(fields[0]),
                pos=pos,
                ref=fields[3],
                alt=fields[4],
                qual=qual,
                filter_status=sys.intern(fields[6]),
            )


def filter_and_export(
    input_file: Path,
    output_file: Path,
    min_quality: float = 30.0,
    required_filter: str = "PASS",
) -> int:
    """Executes high-throughput stream filtering with graceful shutdown support."""
    monitor = SignalMonitor()
    interned_required_filter = sys.intern(required_filter)
    processed_count = 0
    passed_count = 0

    with atomic_file_writer(output_file) as out:
        out.write("CHROM\tPOS\tREF\tALT\tQUAL\tFILTER\n")

        for record in stream_vcf_records(input_file):
            if monitor.received_shutdown:
                logger.warning("Graceful shutdown triggered after processing %d records.", processed_count)
                raise PipelineEvictionError("Cluster eviction signal received.")

            processed_count += 1

            # High-efficiency pointer comparison on interned string
            if record.qual >= min_quality and record.filter_status is interned_required_filter:
                out.write(
                    f"{record.chrom}\t{record.pos}\t{record.ref}\t{record.alt}\t"
                    f"{record.qual:.1f}\t{record.filter_status}\n"
                )
                passed_count += 1

    logger.info("Complete. Processed %d records, exported %d passed records.", processed_count, passed_count)
    return passed_count


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python genomic_stream_filter.py <input.vcf[.gz]> <output.tsv>", file=sys.stderr)
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    try:
        filter_and_export(in_path, out_path)
    except PipelineEvictionError:
        logger.error("Terminated due to cluster preemption. Partial output cleaned up.")
        sys.exit(143)  # Standard SIGTERM exit code
    except Exception as err:
        logger.critical("Fatal error: %s", err, exc_info=True)
        sys.exit(1)
```

---

## 14. Production Decision Matrix & Systems Checklist

### High-Throughput Production Architecture Matrix

| Strategy | When to Use | Memory Impact | CPU / Latency Impact |
| :--- | :--- | :--- | :--- |
| **Generators (`yield`)** | Sequential file, stream, or row parsing. | **$O(1)$ constant RAM** ($< 25$ MB). | Minimal; avoids huge GC pauses. |
| **`__slots__` / `@dataclass(slots=True)`** | Instantiating $> 100{,}000$ structured records. | **60% to 65% memory reduction** per object. | Faster attribute lookup (C-offset vs hash lookup). |
| **`sys.intern()`** | Categorical strings with low cardinality (chromosomes, flags). | Dedupes millions of instances to **a single pointer**. | Speeds up comparison from $O(n)$ to $O(1)$ (`is`). |
| **Zero-Copy (`memoryview`)** | Binary protocols, network buffers, large slices. | Eliminates intermediate allocations completely. | Drastically reduces buffer copy overhead. |
| **Atomic Writes (`os.replace`)** | All persistent production file writing. | Zero memory impact. | Single filesystem metadata swap; prevents data corruption. |
| **POSIX Signal Traps** | Cluster, Docker, Kubernetes, and HPC batch jobs. | Zero memory impact. | Catastrophic OOM/Kill converted to clean flush. |

---

### The Production Pipeline Engineering Checklist
Before deploying any Python pipeline to production or submitting to a cluster:

- [ ] **No `readlines()` or `read()`:** Does the code stream records via iterators/generators without loading entire files into memory?
- [ ] **Class Memory Optimization:** Are high-volume record classes defined with `@dataclass(slots=True)` or `__slots__`?
- [ ] **String Interning:** Are low-cardinality categorical fields interned via `sys.intern()`?
- [ ] **Buffer Sizing:** Are file streams using 64 KB or 128 KB buffer sizes (`buffering=64*1024`) on disk I/O?
- [ ] **Atomic File Outputs:** Are all output files written to temporary paths and renamed via `os.replace` to prevent corrupted partial files?
- [ ] **Signal Handling:** Does the process trap `SIGTERM` and `SIGINT` to allow graceful shutdown and buffer flushing?
- [ ] **Zero `print()` Statements:** Is all diagnostic and operational output emitted via standard library `logging`?
- [ ] **Deterministic Unit Testing:** Are stream parsing edge cases (empty files, malformed rows, gzipped inputs) tested with `pytest` using `io.StringIO` / `io.BytesIO`?

