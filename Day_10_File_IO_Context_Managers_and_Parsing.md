# Day 10: File I/O, Context Managers, and High-Throughput Parsing

---

## 1. The Systems Mental Model: Operating System I/O and File Descriptors

In low-level systems programming (C/Linux), opening a file requests a **file descriptor (FD)** from the operating system kernel (an integer index into the process file table). Reading data involves transitions between **user space** and **kernel space**.

CPython implements a clean, layered I/O architecture in C (the `_io` module):

```text
ASCII Diagram: CPython 3-Layer I/O Architecture

  User Code:
    f.readline()
         │
         ▼
  Layer 3: TextIOWrapper (Decodes raw bytes into Unicode strings using UTF-8)
         │
         ▼
  Layer 2: BufferedReader / BufferedWriter (C-level 8 KiB buffer in RAM, minimizes syscalls)
         │
         ▼
  Layer 1: FileIO (Raw unbuffered OS bytes, directly invokes read() and write() syscalls)
         │
         ▼
  Operating System Kernel:
    read(fd, buf, count) -> Disk Controller / NVMe / Lustre Network Storage
```

### Why Buffering Matters
A naive `read(1)` makes one OS system call per byte, which drops throughput by orders of magnitude due to context switching between user space and kernel space. 
`BufferedReader` reads in chunks (default: 8,192 bytes / 8 KiB), storing them in RAM so subsequent Python reads complete instantaneously in user space.

---

## 2. The Context Management Protocol (`with` Statement)

In C++, deterministic destruction is achieved via RAII (Resource Acquisition Is Initialization). In Java, it uses `try-with-resources`.

In Python, deterministic cleanup is guaranteed by the **Context Management Protocol**:
1. **`__enter__(self)`:** Invoked before entering the block. Its return value is bound to the name in the `as` clause.
2. **`__exit__(self, exc_type, exc_val, exc_tb)`:** Invoked upon leaving the block, **even if an unhandled exception or crash occurred**.

```python
class ManagedResource:
    def __init__(self, resource_id: str):
        self.resource_id = resource_id

    def __enter__(self):
        print(f"[ACQUIRE] Opening resource: {self.resource_id}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"[RELEASE] Safely closing resource: {self.resource_id}")
        if exc_type is not None:
            print(f"[ERROR HANDLED] Caught exception: {exc_val}")
            # Returning True suppresses the exception; Returning False/None propagates it:
            return False

with ManagedResource("SOCKET_PORT_8080") as resource:
    print(f"Executing work with {resource.resource_id}...")
    # Clean up is guaranteed even if we raise an error here:
```

### Output Analysis
```text
[ACQUIRE] Opening resource: SOCKET_PORT_8080
Executing work with SOCKET_PORT_8080...
[RELEASE] Safely closing resource: SOCKET_PORT_8080
```

---

## 3. Advanced Context Management with `contextlib`

### 1. Generator-Based Context Managers: `@contextlib.contextmanager`
Writing full classes with `__enter__` and `__exit__` is often overkill. Using `@contextmanager`, any generator with a single `yield` becomes a valid context manager.

```python
from contextlib import contextmanager
import tempfile
import os
from typing import Iterator

@contextmanager
def temporary_working_file(prefix: str) -> Iterator[str]:
    """Creates a temporary file, yields its path, and guarantees deletion on exit."""
    fd, path = tempfile.mkstemp(prefix=prefix)
    os.close(fd)  # Close low-level descriptor
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)
            print(f"[CLEANUP] Deleted temporary file: {path}")

# Usage:
with temporary_working_file("pipeline_temp_") as temp_path:
    with open(temp_path, "w") as f:
        f.write("intermediate_alignment_data")
# File is deleted automatically here!
```

### 2. Dynamic Resource Stacking with `contextlib.ExitStack`
When you need to open an arbitrary, dynamic number of files (e.g., splitting a master BAM file into 50 regional files):

```python
from contextlib import ExitStack

def process_multiple_files(file_paths: list[str]):
    with ExitStack() as stack:
        # Dynamically register an unknown number of open file handles:
        file_handles = [stack.enter_context(open(path, "r")) for path in file_paths]
        print(f"Successfully opened {len(file_handles)} files in parallel.")
        # Perform processing...
    # ExitStack guarantees that ALL files are closed safely, even on exception!
```

---

## 4. Text I/O vs Binary I/O

Opening files requires selecting the correct mode and specifying character encodings.

```python
# Text Mode ('r', 'w', 'a'):
# Translates bytes <-> Unicode strings using encoding:
with open("data.txt", "w", encoding="utf-8") as f:
    f.write("Genomic Coordinates: chr1:1000\n")

# Binary Mode ('rb', 'wb', 'ab'):
# Operates directly on raw bytes (no encoding/decoding overhead):
with open("data.bin", "wb") as f:
    f.write(b"\x1f\x8b\x08\x00")  # Gzip magic header bytes
```

### The Production Encoding Rule
**Always pass `encoding="utf-8"` explicitly.**
If omitted, Python falls back to `locale.getpreferredencoding()`, which might be `cp1252` on Windows and `UTF-8` on Linux, leading to corrupted text and crashes across platforms.

---

## 5. Memory-Mapped Files with `mmap`

For massive binary datasets, BAM indices, or genomic reference genomes (often 10 GB to 100 GB in size), standard file reads consume excessive CPU cycles and memory.

The `mmap` module maps a disk file **directly into the process virtual address space**.
* **Zero-Copy Reads:** Bytes are paged directly from the OS page cache into user space memory without executing `read()` system calls.
* **Array-Like Slicing:** You can slice bytes (`mm[100:200]`) as if the multi-gigabyte file were a local in-memory bytearray.

```python
import mmap
import os

def demo_mmap():
    filename = "large_reference.dat"
    # Create synthetic 1 MB binary file:
    with open(filename, "wb") as f:
        f.write(b"HEADER_START" + b"\x00" * 100_000 + b"TARGET_GENOMIC_SEQUENCE" + b"\x00" * 100_000)

    with open(filename, "r+b") as f:
        # Map entire file into virtual memory (length=0 maps whole file):
        with mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
            print(f"Memory-mapped file size: {len(mm):,} bytes")

            # High-speed search directly in OS page cache:
            target = b"TARGET_GENOMIC_SEQUENCE"
            position = mm.find(target)
            print(f"Found target sequence at byte offset: {position}")

            # Slice without loading entire file:
            extracted = mm[position : position + len(target)]
            print(f"Extracted payload: {extracted.decode('ascii')}")

    os.remove(filename)

if __name__ == "__main__":
    demo_mmap()
```

---

## 6. High-Throughput Structured File Parsing

### 1. TSV / CSV Parsing
```python
import csv

# Approach A: csv.reader (Fastest, tuple-like positional access)
def parse_variants_tsv(tsv_path: str):
    with open(tsv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if row and not row[0].startswith("#"):
                chrom, pos, ref, alt = row[0], int(row[1]), row[2], row[3]

# Approach B: csv.DictReader (Self-documenting, dict-access)
def parse_metadata_csv(csv_path: str):
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sample_id = row["sample_id"]
            qc_pass = row["qc_status"] == "PASS"
```

### 2. Streaming Line-Delimited JSON (JSONL)
In distributed microservices and logging, standard JSON arrays require loading the entire multi-gigabyte file before parsing. **JSONL (JSON Lines)** formats one valid JSON object per line.

```python
import json

def stream_jsonl(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        # Lazy generator: parses line by line in O(1) RAM:
        for line in f:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)
```

---

## 7. Modern Filesystem Operations with `pathlib` (PEP 428)

Legacy Python used `os.path.join()`, `os.path.exists()`, and `glob.glob()`. 

Modern Python standardizes on **`pathlib.Path`**, treating paths as first-class objects with operator overloading:

```python
from pathlib import Path

# Path arithmetic using the '/' operator:
base_dir = Path("/data/runs")
sample_dir = base_dir / "2026_Q4" / "SAMPLE_01"

print(f"Full Path:  {sample_dir}")
print(f"Parent Dir: {sample_dir.parent}")
print(f"File Name:  {sample_dir.name}")
print(f"File Stem:  {sample_dir.stem}")
print(f"File Ext:   {sample_dir.suffix}")

# Convenient high-speed helpers:
config_path = Path("sample_config.json")
config_path.write_text('{"status": "READY"}', encoding="utf-8")
contents = config_path.read_text(encoding="utf-8")
print(f"Read text directly: {contents}")

config_path.unlink()  # Deletes file cleanly
```

---

## 8. Common Pitfalls and Systems Traps

### Pitfall 1: Reading Large Files with `f.readlines()`
```python
# FATAL CRASH: Loads 50 GB file into RAM as a massive Python list:
with open("massive_alignment.sam") as f:
    lines = f.readlines()  # Out of Memory (OOM) kill!

# IDIOMATIC & FAST: The file object itself is an iterator of lines:
with open("massive_alignment.sam") as f:
    for line in f:  # Constant O(1) memory! Uses internal 8 KiB buffer
        process(line)
```

### Pitfall 2: Forgetting to Flush Buffered Writes
Data written with `f.write()` sits in CPython's user space `BufferedWriter` RAM buffer. It is only flushed to the OS kernel when:
1. The buffer fills up (8 KiB).
2. The file is closed.
3. You explicitly call `f.flush()`.
If another process or subprocess inspects the file before closing, the file appears empty!

---

## 9. Hands-On Systems Challenge: Fast Streaming VCF/TSV Parser with Auto-Cleanup

### The Problem
Write a high-throughput, memory-bounded variant parser `VariantStreamParser` that:
1. Uses `pathlib.Path` to validate file existence.
2. Automatically manages file lifecycles via the Context Manager protocol.
3. Streams lines in $O(1)$ memory, ignoring comments (`#`).
4. Converts valid genomic rows into structured dataclasses.
5. Uses `contextlib.ExitStack` to safely process input files and stream output to a new file.

### Complete Runnable Implementation

```python
from dataclasses import dataclass
from pathlib import Path
from contextlib import ExitStack
from typing import Iterator

@dataclass(slots=True, frozen=True)
class VariantRecord:
    chrom: str
    pos: int
    ref: str
    alt: str
    quality: float

class VariantStreamParser:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        if not self.file_path.exists():
            raise FileNotFoundError(f"Missing input file: {self.file_path}")

    def stream_variants(self) -> Iterator[VariantRecord]:
        """Streams records lazily in O(1) memory."""
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"):
                    continue
                
                parts = clean_line.split("\t")
                if len(parts) < 5:
                    continue

                yield VariantRecord(
                    chrom=parts[0],
                    pos=int(parts[1]),
                    ref=parts[2],
                    alt=parts[3],
                    quality=float(parts[4])
                )

def run_parser_pipeline():
    test_file = Path("synthetic_variants.vcf")
    output_file = Path("filtered_variants.tsv")

    # Generate synthetic VCF data:
    vcf_content = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tREF\tALT\tQUAL\n"
        "chr1\t10450\tA\tC\t95.5\n"
        "chr1\t20910\tG\tT\t12.0\n"
        "chr2\t50120\tT\tC\t99.0\n"
    )
    test_file.write_text(vcf_content, encoding="utf-8")

    # Streaming transformation using ExitStack:
    with ExitStack() as stack:
        parser = VariantStreamParser(test_file)
        out_f = stack.enter_context(open(output_file, "w", encoding="utf-8"))

        out_f.write("CHROM\tPOS\tREF\tALT\tQUAL\n")
        passed_count = 0

        for variant in parser.stream_variants():
            if variant.quality >= 30.0:  # High-quality filter
                out_f.write(f"{variant.chrom}\t{variant.pos}\t{variant.ref}\t{variant.alt}\t{variant.quality}\n")
                passed_count += 1

    print(f"Successfully filtered and wrote {passed_count} high-quality variants.")
    print("Filtered output contents:")
    print(output_file.read_text(encoding="utf-8"))

    # Cleanup:
    test_file.unlink()
    output_file.unlink()

if __name__ == "__main__":
    run_parser_pipeline()
```

---

## 10. File I/O Performance & Method Comparison Table

| Method | Memory Usage | Syscall Frequency | Best For |
| :--- | :--- | :--- | :--- |
| `for line in f:` | $O(1)$ constant | Low (8 KiB buffered) | Large text files, logs, CSV, VCF |
| `f.read()` | $O(N)$ full file | High (one big read) | Small config files (< 10 MB) |
| `f.readlines()` | $O(N)$ list overhead | Low | Small files needing random line access |
| `mmap.mmap()` | $O(1)$ page-cached | Zero (virtual memory) | Massive binary files (> 10 GB), search |
| `Path.read_text()` | $O(N)$ full file | Low | Clean one-liner scripts for small configs |

---

## 11. File I/O Architecture Decision Guide & ASCII Decision Flowchart

```text
FILE I/O ARCHITECTURE DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
Reading text files of unknown or massive size (> 1 GB)  for line in f:
Managing arbitrary / dynamic multiple files             contextlib.ExitStack
Quick reading/writing of small script configs (< 1 MB)  pathlib.Path.read_text()
Zero-copy random binary access in multi-gigabyte files  mmap.mmap()
Streamlined temp file lifecycle management              @contextlib.contextmanager
Structured tabular text parsing                         csv.reader / csv.DictReader
Heterogeneous microservice log streams                  JSON Lines (JSONL)
─────────────────────────────────────────────────────────────────────────────
```

### Architecture Decision Flowchart

```text
Is the file larger than available RAM?
  YES ──> Is it binary and requires random access?
            YES ──> mmap.mmap()
            NO  ──> Streaming line iterator: for line in open(...):
  NO  ──> Do you need quick one-off reads of a small config file?
            YES ──> Path.read_text()
            NO  ──> Standard with open(...) as f:
```

---

## 12. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 11:

- [ ] Explain the 3-layer architecture of CPython I/O (`FileIO`, `BufferedReader`, `TextIOWrapper`).
- [ ] What is the exact execution contract of `__enter__` and `__exit__` in a `with` statement?
- [ ] How does `contextlib.ExitStack` manage a dynamic number of open files safely?
- [ ] Why should you always specify `encoding="utf-8"` explicitly in `open()`?
- [ ] How does `mmap` achieve zero-copy reads on massive binary files?
- [ ] Why is `for line in f:` asymptotically superior to `f.readlines()`?
- [ ] What is the purpose of `f.flush()` when writing buffered data?
- [ ] How does `pathlib.Path` simplify filesystem paths with operator overloading?


---

## 13. JSON and TOML Parsing

**JSON** is handled by the standard library `json` module. Use `json.loads()` for strings and `json.load()` for file objects. Use `json.dumps()` / `json.dump()` to serialize back.

**TOML** is handled by `tomllib` (Python 3.11+, read-only). It is the preferred format for `pyproject.toml` and tool configuration files.

Always catch `JSONDecodeError` and validate required fields before trusting parsed data.

```python
import json
import io

# JSON: parsing and serializing
raw_json = '{"run_id": "R_001", "samples": ["S1", "S2"], "quality": 99.5}'

# From string:
data = json.loads(raw_json)
print(data["run_id"])         # R_001
print(data["samples"][1])     # S2

# Serializing back to JSON string:
modified = {**data, "quality": 100.0}
output_json = json.dumps(modified, indent=2)
print(output_json)

# To file:
# with open("output.json", "w", encoding="utf-8") as f:
#     json.dump(modified, f, indent=2)

# Defensive parsing with error handling:
def parse_config_json(raw: str) -> dict:
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON config: {e}") from e
    if "run_id" not in config:
        raise ValueError("Config missing required field: run_id")
    return config

# TOML (Python 3.11+):
import tomllib

toml_config = b"""
[pipeline]
run_id = "R_002"
threads = 8
enable_qc = true

[database]
host = "10.0.0.1"
port = 5432
"""

config = tomllib.loads(toml_config.decode())
print(config["pipeline"]["threads"])   # 8
print(config["database"]["host"])      # 10.0.0.1
```

**Key distinctions:**

| Function        | Input type        | Use case                        |
|-----------------|-------------------|---------------------------------|
| `json.loads(s)` | `str` / `bytes`   | Parse JSON already in memory    |
| `json.load(f)`  | file object       | Parse JSON directly from a file |
| `json.dumps(d)` | `dict`            | Serialize to `str`              |
| `json.dump(d,f)`| `dict` + file obj | Serialize directly to a file    |

---

## 14. Atomic File Writes: Preventing Corrupt Output Files

**Problem:** If a program crashes or is killed mid-write, the output file is left partially written and corrupt. Any downstream consumer reading that file will see garbage.

**Solution:** Write to a temporary file in the same directory first, then rename it over the target. On POSIX systems (Linux, macOS), `rename()` is a single atomic syscall: the target path switches from old to new in one step. No reader ever sees a half-written file.

```text
Crash scenario WITHOUT atomic write:
  pipeline_output.json  <-- being written, process killed at 40%
  Result: corrupt file, 40% of valid JSON + truncated

Crash scenario WITH atomic write:
  pipeline_output.json.tmp  <-- being written, process killed at 40%
  pipeline_output.json      <-- old file untouched, still valid
  Result: temp file is cleaned up, original survives
```

```python
import os
import json
from pathlib import Path
import tempfile

def atomic_write_json(data: dict, target_path: Path) -> None:
    """
    Writes JSON to a temp file in the same directory, then renames atomically.
    If the process crashes mid-write, target_path is never left in a corrupt state.
    """
    target_path = target_path.resolve()
    dir_path = target_path.parent

    # Write to temp file in the same directory (same filesystem = atomic rename):
    fd, temp_path_str = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    temp_path = Path(temp_path_str)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # Force OS kernel to flush to disk

        # Atomic rename: replaces target_path in a single OS syscall
        temp_path.rename(target_path)
        print(f"Wrote atomically to: {target_path}")
    except Exception:
        # Clean up temp file on failure
        if temp_path.exists():
            temp_path.unlink()
        raise

# Demo:
output = Path("/tmp/pipeline_output.json")
atomic_write_json({"run_id": "R_001", "status": "COMPLETE"}, output)
print(output.read_text(encoding="utf-8"))
output.unlink()
```

> **Windows note:** `Path.rename()` is not atomic on Windows. Use `os.replace()` instead: it is atomic on both Windows and POSIX, and also handles overwriting an existing target file correctly on Windows.

---

## 15. Reading and Writing Compressed Files

Python's `gzip`, `bz2`, and `lzma` modules wrap file objects with transparent compression and decompression. The same `for line in f` iteration pattern works: decompression happens on the fly in fixed-size chunks, so memory use stays O(1) regardless of file size.

This matters in genomics and clinical data pipelines where `.fastq.gz`, `.vcf.gz`, and similar files routinely reach gigabytes.

```text
Disk:    [ compressed bytes ]
              |
         gzip.open()
              |
Memory:  [ decompressed chunk ]  <-- only one chunk at a time
              |
         for line in f:          <-- iterate line by line
```

```python
import gzip
import io

# Writing a gzip-compressed text file:
compressed_path = "/tmp/sample_reads.fastq.gz"

with gzip.open(compressed_path, "wt", encoding="utf-8") as f:
    for i in range(5):
        f.write(f"@READ_{i:03d}\n")
        f.write("ACGTACGT\n")
        f.write("+\n")
        f.write("IIIIIIII\n")

# Reading line-by-line (O(1) memory, decompresses on the fly):
with gzip.open(compressed_path, "rt", encoding="utf-8") as f:
    for line in f:
        print(line.rstrip())

# For multi-format support (auto-detect gzip/bz2/plain):
import pathlib
def open_possibly_compressed(path: str):
    p = pathlib.Path(path)
    if p.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    elif p.suffix == ".bz2":
        import bz2
        return bz2.open(path, "rt", encoding="utf-8")
    else:
        return open(path, "r", encoding="utf-8")

import os
os.unlink(compressed_path)
```

**Mode strings for compressed file opens:**

| Mode  | Meaning                              |
|-------|--------------------------------------|
| `"rb"` | Read binary (compressed bytes)      |
| `"rt"` | Read text (decompressed, decoded)   |
| `"wb"` | Write binary (compressed bytes)     |
| `"wt"` | Write text (compress on the fly)    |

Always use `"rt"` / `"wt"` with `encoding="utf-8"` when working with text-based formats (FASTQ, VCF, TSV). Use `"rb"` / `"wb"` only when passing raw bytes to another binary parser.

---

## 16. Extended Checklist

The following items extend the checklist from Section 12. Work through both lists before moving to Day 11.

- [ ] What is the difference between `json.loads()` and `json.load()`?
- [ ] Why does writing to a temp file and then renaming prevent corrupt output?
- [ ] Why is `os.replace()` preferred over temp-and-rename on Windows?
- [ ] How do you read a `.fastq.gz` file line-by-line without loading it entirely into RAM?
