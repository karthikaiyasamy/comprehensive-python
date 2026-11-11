# Day 11: Concurrency, The GIL, Threading, and Asyncio

---

## 1. The Systems Mental Model: Concurrency vs Parallelism

In Java or C++, threads map 1:1 to OS kernel threads, and multi-threading naturally achieves parallel execution across all CPU cores.

In Python, the landscape is shaped by the **Global Interpreter Lock (GIL)**. To design concurrent systems in Python, you must understand the distinction between:
* **Concurrency:** Managing multiple tasks simultaneously (interleaving execution on 1 or more cores).
* **Parallelism:** Executing multiple computational tasks at the exact same physical instant on multiple CPU cores.

```text
ASCII Diagram: The Three Concurrency Architectures in Python

  1. Multi-Threading (threading, ThreadPoolExecutor):
     One Process, Shared Heap, Multiple Threads, Serialized by GIL for Bytecode
     ┌────────────────────────────────────────────────────────┐
     │ Process RAM (Shared Heap)                              │
     │  Thread 1 ──>[ GIL ] ──> Executes Bytecode             │
     │  Thread 2 ──>[ Wait] ──> Blocked until Thread 1 drops  │
     └────────────────────────────────────────────────────────┘

  2. Multi-Processing (multiprocessing, ProcessPoolExecutor):
     Multiple Isolated Processes, Separate Heaps, Separate GILs (True Parallelism)
     ┌──────────────────────┐    ┌──────────────────────┐
     │ Process 1 (Core 1)   │    │ Process 2 (Core 2)   │
     │ Heap A + Private GIL │    │ Heap B + Private GIL │
     └──────────────────────┘    └──────────────────────┘

  3. Asynchronous Coroutines (asyncio):
     One Process, One Thread, One Event Loop (Cooperative Non-Blocking I/O)
     ┌────────────────────────────────────────────────────────┐
     │ Event Loop ──> Task A (runs until await)               │
     │            ──> Task B (runs while Task A waits for OS) │
     └────────────────────────────────────────────────────────┘
```

---

## 2. Deep Dive into the Global Interpreter Lock (GIL)

### Why Does the GIL Exist?
CPython's internal memory manager uses **reference counting** (`ob_refcnt`). 
* In a multi-threaded C application, updating a reference count requires atomic operations (`atomic_inc`) or fine-grained locks around every pointer update.
* Atomic operations on modern CPUs incur bus synchronization overhead that would slow down single-threaded Python by 30% to 50%.
* The GIL solves this by using **one global mutex** protecting the entire interpreter state.

### How the GIL Behaves in Practice
* **Bytecode Execution:** Only one thread executes Python bytecode at any moment. Every 5 milliseconds (`sys.getswitchinterval()`), CPython drops the lock and allows waiting threads to contest for it.
* **When the GIL is Released Automatically:**
  1. **All Blocking OS I/O Calls:** `file.read()`, `socket.recv()`, `time.sleep()`, and database network calls release the GIL while waiting for the OS kernel.
  2. **C-Extensions and Numerical Libraries:** NumPy, SciPy, OpenBLAS, OpenCV, and compression libraries (`zlib`, `gzip`) explicitly release the GIL during heavy vector calculations, achieving true multi-core parallel execution.

---

## 3. Multi-Threading: `concurrent.futures.ThreadPoolExecutor`

Use threads for **I/O-bound operations**: downloading files, querying databases, calling external REST APIs, or reading data over network sockets.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def fetch_patient_data(patient_id: int) -> dict:
    # Simulating blocking network I/O (GIL is released during sleep!):
    time.sleep(0.1)
    return {"id": patient_id, "status": "ACTIVE"}

def run_thread_pool():
    patient_ids = list(range(100, 120))
    start_time = time.perf_counter()

    # Pool of 5 worker threads:
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks:
        future_to_id = {executor.submit(fetch_patient_data, pid): pid for pid in patient_ids}

        # Gather results as they complete:
        for future in as_completed(future_to_id):
            pid = future_to_id[future]
            try:
                data = future.result()
            except Exception as err:
                print(f"Failed for patient {pid}: {err}")

    elapsed = time.perf_counter() - start_time
    # 20 calls taking 0.1s each sequentially would take 2.0s.
    # With 5 worker threads, it finishes in ~0.4s:
    print(f"Fetched 20 records in {elapsed:.3f}s with ThreadPoolExecutor.")

if __name__ == "__main__":
    run_thread_pool()
```

### Thread Safety and Synchronization (`threading.Lock`)
Because threads share the same heap memory, mutating shared Python structures without locks causes data corruption:

```python
import threading

class SafeCounter:
    def __init__(self):
        self.value = 0
        self._lock = threading.Lock()

    def increment(self):
        # acquire() and release() guaranteed via context manager:
        with self._lock:
            self.value += 1
```

---

## 4. Multi-Processing: True Multi-Core CPU Parallelism

For **CPU-bound operations** (data hashing, image processing, genomic alignment, matrix math), multi-threading provides zero speedup. You must use **`ProcessPoolExecutor`**.

```python
from concurrent.futures import ProcessPoolExecutor
import time
import math

def cpu_heavy_hash(n: int) -> int:
    """CPU-intensive computation."""
    count = 0
    for i in range(1, n):
        count += int(math.sqrt(i * 1.5))
    return count

def run_process_pool():
    workloads = [2_000_000] * 4

    # 1. Sequential Benchmark:
    start = time.perf_counter()
    res_seq = [cpu_heavy_hash(w) for w in workloads]
    seq_time = time.perf_counter() - start

    # 2. Multi-Process Parallel Benchmark (Bypasses GIL across 4 CPU cores):
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as executor:
        res_proc = list(executor.map(cpu_heavy_hash, workloads))
    proc_time = time.perf_counter() - start

    print(f"Sequential Execution:  {seq_time:.3f}s")
    print(f"ProcessPool Execution: {proc_time:.3f}s (Speedup: {seq_time / proc_time:.1f}x)")

if __name__ == "__main__":
    run_process_pool()
```

### The Cost of Multi-Processing: Serialization (Pickling)
Processes do not share heap memory. Every argument passed to a process and every return value sent back must be **serialized using `pickle`** and sent across inter-process pipes. 
* Passing a 10 GB list to a subprocess serializes 10 GB into bytes and copies it, creating massive memory overhead.
* Use shared memory (`multiprocessing.shared_memory`) or file paths for massive datasets.

---

## 5. Asynchronous Programming with `asyncio`

`asyncio` is a framework for writing single-threaded concurrent code using coroutines, multiplexing I/O over an OS event loop (like `epoll` on Linux or `kqueue` on macOS).

### Key Mental Concepts
* **`async def`:** Declares a coroutine function.
* **`await`:** Yields control back to the event loop while waiting for an asynchronous operation.
* **Event Loop:** The coordinator that pauses and resumes coroutines as network sockets become ready.

```python
import asyncio
import time

async def async_fetch_locus(locus_id: str) -> dict:
    # Non-blocking async sleep (simulates network call):
    await asyncio.sleep(0.1)
    return {"locus": locus_id, "score": 98.4}

async def main():
    loci = ["LOC_A", "LOC_B", "LOC_C", "LOC_D"]
    start = time.perf_counter()

    # Modern Python 3.11+ TaskGroup (Structural Concurrency):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(async_fetch_locus(locus)) for locus in loci]

    # All tasks completed concurrently:
    results = [task.result() for task in tasks]
    elapsed = time.perf_counter() - start

    print(f"Fetched {len(results)} loci in {elapsed:.3f}s using asyncio.TaskGroup.")
    print(f"Results: {results}")

if __name__ == "__main__":
    asyncio.run(main())
```

### The Cardinal Rule of Asyncio
**NEVER execute blocking code (e.g., `time.sleep()`, heavy CPU loops, or synchronous `requests.get()`) inside an async coroutine.**
Doing so freezes the single-threaded event loop, stopping all other concurrent tasks. 

If you must run blocking synchronous code inside asyncio, offload it to a thread pool via `asyncio.to_thread(blocking_func, *args)`.

---

## 6. Concurrency Architecture Comparison Table

| Attribute | `threading` | `multiprocessing` | `asyncio` |
| :--- | :--- | :--- | :--- |
| **Model** | Preemptive OS threads | Preemptive OS processes | Cooperative user-space tasks |
| **Memory Architecture** | Shared heap RAM | Isolated memory spaces | Single-threaded shared memory |
| **Memory Overhead** | ~8 MB stack per thread | ~20-50 MB per process | ~2 KiB per task (Ultra-light) |
| **Bypasses GIL?** | No (Bytecode serialized) | Yes (Independent GILs) | No (Single thread) |
| **Data Sharing** | Shared pointers (Use Locks) | IPC / Pickle serialization | Shared variables |
| **Maximum Concurrency** | Hundreds of threads | Tens (Number of CPU cores) | Tens of thousands of tasks |
| **Best For** | Blocking I/O, C-extensions | Heavy CPU math, alignment | High-concurrency Web / APIs |

---

## 7. Common Pitfalls and Systems Traps

### Pitfall 1: Using Threads for CPU-Bound Work
Running 4 threads on a CPU-heavy task on Python often runs **slower** than single-threaded execution due to constant GIL acquisition contention and thread context-switch overhead. Always use `multiprocessing` for CPU-bound tasks.

### Pitfall 2: The Fork Safety Trap on macOS and Linux
In Python 3.8+, macOS changed the default process start method from `fork` to `spawn`. 
* Under `spawn`, subprocesses re-import the main script. 
* Any code not protected by `if __name__ == '__main__':` will execute repeatedly in an infinite recursive loop!
* **Rule:** Always guard process execution with `if __name__ == '__main__':`.

---

## 8. Hands-On Systems Challenge: Multi-Core Genomic Variant Batch Processor

### The Problem
In genomic pipelines, computing variant metrics across 200,000 variants is CPU-bound.

Write a parallel processor `ParallelVariantScorer` that:
1. Partitions a list of synthetic variants into balanced chunks.
2. Distributes the chunks across all available CPU cores using `ProcessPoolExecutor`.
3. Computes complex mathematical scores for each variant in parallel.
4. Gathers and aggregates results into a unified summary list.

### Complete Runnable Implementation

```python
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import time
import math

@dataclass(slots=True, frozen=True)
class Variant:
    chrom: str
    pos: int
    depth: int
    alt_count: int

def compute_chunk_scores(chunk: list[Variant]) -> list[float]:
    """Worker function executed inside independent process heaps."""
    scores = []
    for v in chunk:
        # Simulate heavy statistical calculation (e.g. allele frequency & log odds):
        vaf = v.alt_count / max(v.depth, 1)
        score = math.log1p(v.depth) * math.sqrt(vaf * 100.0)
        # Extra math iteration to simulate compute intensity:
        for _ in range(50):
            score = math.sqrt(score * score + 1.0)
        scores.append(score)
    return scores

def chunkify(lst: list, num_chunks: int) -> list[list]:
    """Splits a list into balanced sublists."""
    k, m = divmod(len(lst), num_chunks)
    return [lst[i * k + min(i, m) : (i + 1) * k + min(i + 1, m)] for i in range(num_chunks)]

def run_parallel_scorer():
    total_variants = 100_000
    cores = 4

    print(f"Generating {total_variants:,} synthetic variants...")
    variants = [
        Variant("chr1", 10_000 + i, depth=60, alt_count=15)
        for i in range(total_variants)
    ]

    # Split into chunks:
    chunks = chunkify(variants, cores)

    start_time = time.perf_counter()
    with ProcessPoolExecutor(max_workers=cores) as executor:
        # Map chunks across worker processes:
        chunk_results = list(executor.map(compute_chunk_scores, chunks))

    # Flatten results:
    all_scores = [score for sublist in chunk_results for score in sublist]
    elapsed = time.perf_counter() - start_time

    assert len(all_scores) == total_variants
    print(f"Scored {total_variants:,} variants in {elapsed:.3f}s across {cores} processes.")
    print(f"Throughput: {total_variants / elapsed:,.0f} variants/sec.")

if __name__ == "__main__":
    run_parallel_scorer()
```

---

## 9. Concurrency Architecture Decision Guide & ASCII Decision Flowchart

```text
CONCURRENCY ARCHITECTURE DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
CPU-bound calculations (math, image, alignment, hashing) multiprocessing
I/O-bound with blocking third-party libraries           concurrent.futures.ThreadPoolExecutor
I/O-bound with high concurrency (> 1,000 connections)   asyncio + aiohttp / asyncpg
Offloading CPU work from inside an asyncio service      loop.run_in_executor()
Offloading blocking sync calls inside an async service  asyncio.to_thread()
Sharing massive multi-gigabyte arrays across processes  multiprocessing.shared_memory
Synchronizing shared memory access across threads       threading.Lock / threading.RLock
─────────────────────────────────────────────────────────────────────────────
```

### Architecture Decision Flowchart

```text
Is your task CPU-bound or I/O-bound?
  CPU-BOUND ──> Do you use NumPy/C-extensions that release the GIL?
                  YES ──> ThreadPoolExecutor (Zero serialization overhead)
                  NO  ──> ProcessPoolExecutor (Bypasses GIL across CPU cores)
  I/O-BOUND ──> Do you need to handle > 1,000 concurrent network sockets?
                  YES ──> asyncio (Event loop, cooperative multitasking)
                  NO  ──> ThreadPoolExecutor (Simple, blocking sync APIs)
```

---

## 10. Updated Master Checklist

Work through each item to verify your understanding before moving to Day 12:

- [ ] Explain why the GIL exists and what memory management problem it solves.
- [ ] What two types of operations cause CPython to release the GIL automatically?
- [ ] Why does multi-threading fail to speed up CPU-bound bytecode execution?
- [ ] How does `multiprocessing` achieve true multi-core parallelism in Python?
- [ ] What is the serialization cost of multi-processing and how is `pickle` involved?
- [ ] What is the difference between preemptive threading and cooperative `asyncio` multitasking?
- [ ] What happens if you execute a blocking call (like `time.sleep`) inside an async coroutine?
- [ ] Why must multi-processing execution always be guarded by `if __name__ == '__main__':`?
- [ ] When would you choose `ThreadPoolExecutor` over `asyncio`?

---

## 11. asyncio Primitives: Lock, Queue, and Semaphore

The `asyncio` module provides async-safe equivalents of every threading synchronization primitive. You must use the async versions inside coroutines. Using `threading.Lock` inside an async function will block the entire event loop.

```text
Primitive        | threading equivalent | Purpose
-----------------+----------------------+--------------------------------------
asyncio.Lock     | threading.Lock       | Exclusive access to a shared resource
asyncio.Semaphore| threading.Semaphore  | Limit to N simultaneous coroutines
asyncio.Queue    | queue.Queue          | Producer-consumer pipelines
asyncio.Event    | threading.Event      | Signal across coroutines
```

### asyncio.Semaphore: Concurrency Rate Limiter

```python
import asyncio

async def fetch_data(session_id: int, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:          # At most 3 coroutines inside here at once
        print(f"[Session {session_id}] Fetching...")
        await asyncio.sleep(0.1)   # Simulates async network call
        return {"session": session_id, "data": f"result_{session_id}"}

async def main():
    sem = asyncio.Semaphore(3)     # Maximum 3 concurrent calls
    tasks = [fetch_data(i, sem) for i in range(10)]
    results = await asyncio.gather(*tasks)
    print(f"Completed {len(results)} calls, max 3 concurrent.")

if __name__ == "__main__":
    asyncio.run(main())
```

### asyncio.Queue: Producer-Consumer Pipeline

```python
import asyncio

async def producer(queue: asyncio.Queue, items: list[str]) -> None:
    for item in items:
        await queue.put(item)
        print(f"[Producer] Enqueued: {item}")
    await queue.put(None)          # Sentinel value signals done

async def consumer(queue: asyncio.Queue) -> None:
    while True:
        item = await queue.get()
        if item is None:
            break
        print(f"[Consumer] Processing: {item}")
        await asyncio.sleep(0.05)
        queue.task_done()

async def run_pipeline():
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=5)
    work_items = ["job_A", "job_B", "job_C", "job_D"]
    await asyncio.gather(
        producer(queue, work_items),
        consumer(queue)
    )

if __name__ == "__main__":
    asyncio.run(run_pipeline())
```

---

## 12. multiprocessing.shared_memory: Zero-Copy Array Sharing

Processes cannot share heap RAM by default. Inter-process communication via `pickle` copies all data. For large arrays (e.g., 500 MB numpy arrays), pickling doubles RAM usage and wastes time.

`multiprocessing.shared_memory` maps the **same physical RAM block** into two or more process address spaces.

```text
ASCII Diagram: Shared Memory Block

  Process A (Core 1)         OS Kernel RAM              Process B (Core 2)
  ┌────────────────┐    ┌──────────────────────┐    ┌────────────────┐
  │ Virtual Addr   │    │  Physical RAM Block  │    │ Virtual Addr   │
  │ 0x7FFF_A000 ───┼───►│  [10, 20, 30, 40]   │◄───┼─ 0x7FFF_B000  │
  └────────────────┘    └──────────────────────┘    └────────────────┘
  No copy. Both processes read and write the same bytes.
```

```python
import multiprocessing
from multiprocessing import shared_memory
import struct

def worker_read(shm_name: str) -> None:
    """Worker process: reads shared memory without copying."""
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    values = struct.unpack_from("4i", existing_shm.buf, 0)
    print(f"[Worker] Read from shared memory: {values}")
    existing_shm.close()

def run_shared_memory_demo():
    # Create shared block: 16 bytes = 4 x int32
    shm = shared_memory.SharedMemory(create=True, size=16)

    # Write 4 integers into shared block:
    values = (10, 20, 30, 40)
    struct.pack_into("4i", shm.buf, 0, *values)
    print(f"[Main] Wrote to shared memory: {values}")

    # Spawn worker that reads same block without pickling:
    p = multiprocessing.Process(target=worker_read, args=(shm.name,))
    p.start()
    p.join()

    # Cleanup:
    shm.close()
    shm.unlink()     # Frees the OS shared memory block

if __name__ == "__main__":
    run_shared_memory_demo()
```

---

## 13. Python 3.13: The GIL-Optional Future (PEP 703)

Python 3.13 introduced experimental **free-threaded builds** where the GIL can be fully disabled per process. This is a historic change to CPython.

```text
Timeline:
  Python 3.12  : GIL always on. No change.
  Python 3.13  : Free-threaded build available as 'python3.13t' (experimental)
  Python 3.14+ : Free-threaded mode stabilizes; more extensions become compatible.
  Python 3.15+ : Likely default for new installs on multi-core systems.
```

```python
import sys

def check_gil_status() -> None:
    if hasattr(sys, "_is_gil_enabled"):
        gil_active = sys._is_gil_enabled()
        status = "ENABLED" if gil_active else "DISABLED (Free-Threaded Mode)"
        print(f"GIL is: {status}")
    else:
        print("Python < 3.13: GIL is always ENABLED")

check_gil_status()

# To disable GIL at runtime (Python 3.13+ free-threaded build only):
# Run as: PYTHON_GIL=0 python3.13t your_script.py
# Or: python3.13t -X gil=0 your_script.py
```

### What Changes in Free-Threaded Mode

| Feature | Today (GIL on) | Free-Threaded (GIL off) |
| :--- | :--- | :--- |
| CPU-bound threads | Serialized by GIL | True parallel (N cores) |
| Reference counting | Protected by GIL | Uses atomic increments (slower) |
| C-extension safety | Guaranteed safe | Extension must opt-in as thread-safe |
| I/O-bound threads | Already good | Same; no change |
| `multiprocessing` needed for CPU | Yes | No (threads suffice) |

### Current Limitations

- Many popular C-extensions (some NumPy operations, certain database drivers) are not yet free-thread safe. They may crash or produce incorrect results.
- CPython's atomic reference counting is slower than the GIL-protected version for single-threaded code (5-10% overhead measured).
- Use `python3.13t` only for experimental multi-threaded CPU workloads until the ecosystem catches up.

---

## 14. Updated Master Checklist

Work through each item to verify your understanding:

- [ ] How does `asyncio.Semaphore` differ from `asyncio.Lock` in terms of concurrency control?
- [ ] How does `asyncio.Queue` implement a producer-consumer pipeline without shared mutable state?
- [ ] How does `multiprocessing.shared_memory` allow two processes to access the same bytes without pickling?
- [ ] What is PEP 703 and what does the Python 3.13 free-threaded build change about the GIL?
- [ ] Why does free-threaded Python have a slight single-threaded performance penalty?
