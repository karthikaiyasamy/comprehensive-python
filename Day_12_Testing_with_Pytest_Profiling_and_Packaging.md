# Day 12: Production Testing with Pytest, Profiling, and Packaging

---

## 1. The Systems Mental Model: Verification and Engineering Discipline

In enterprise healthcare, genomic science, and mission-critical systems, untested code is broken code.

Python's dynamic nature makes rigorous testing even more crucial than in compiled languages. Without compile-time type enforcement, your test suite serves as the **executable specification and safety harness** of your architecture.

```text
ASCII Diagram: The Modern Python Engineering Toolchain

  [ Source Code: src/pipeline/ ]
            │
            ├─► Static Analysis:   Ruff (Formatting & Linting) + Mypy (Type Checking)
            │
            ├─► Test Execution:    Pytest (Unit, Integration, Parameterized Matrices)
            │
            ├─► Coverage Gate:     Pytest-Cov (Branch & Line Coverage Thresholds)
            │
            ├─► Hotspot Profiler:  cProfile + line_profiler (Eliminating Bottlenecks)
            │
            └─► Standard Package:  pyproject.toml (PEP 621 Distribution & Build)
```

---

## 2. Pytest Foundations and AST Rewriting

Legacy Python testing relied on `unittest.TestCase` (a direct port of Java's JUnit 3.8), requiring boilerplate classes and awkward assertions like `self.assertEqual(a, b)`.

Modern Python uses **`pytest`**:
* Tests are plain Python functions prefixed with `test_`.
* You use standard Python `assert a == b`.
* **AST Rewriting:** Pytest intercepts the Python Abstract Syntax Tree during test discovery, rewriting `assert` statements into rich diagnostic diffs that display full object states on failure.

```python
# test_sample.py
def calculate_vaf(alt_count: int, total_depth: int) -> float:
    if total_depth <= 0:
        raise ValueError("total_depth must be positive")
    return round(alt_count / total_depth, 3)

def test_vaf_calculation_success():
    # Plain assert produces detailed failure reports:
    result = calculate_vaf(15, 60)
    assert result == 0.25

def test_vaf_zero_division():
    import pytest
    # Verifying exceptions and error messages:
    with pytest.raises(ValueError, match="total_depth must be positive") as exc_info:
        calculate_vaf(10, 0)
    assert "total_depth" in str(exc_info.value)
```

---

## 3. Dependency Injection with Pytest Fixtures

Fixtures (`@pytest.fixture`) are modular, reusable setup and teardown functions injected into test functions by matching parameter names.

### Fixture Lifecycle and Scopes
Fixtures can be scoped to control how frequently they are initialized:
* `scope="function"` (Default): Executed once per test function (fresh isolation).
* `scope="module"`: Executed once per test file.
* `scope="session"`: Executed once per entire test suite run (ideal for spin-up of test databases or Docker containers).

### Setup and Teardown via the `yield` Pattern

```python
import pytest
from pathlib import Path
from typing import Iterator

@pytest.fixture
def sample_vcf_file(tmp_path: Path) -> Iterator[Path]:
    """
    Setup: Creates a temporary synthetic VCF file.
    Teardown: Automatically cleaned up by tmp_path fixture.
    """
    vcf_path = tmp_path / "test_sample.vcf"
    vcf_path.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\n"
        "chr1\t10450\trs101\tA\tC\t95.0\n",
        encoding="utf-8"
    )

    # yield delivers the fixture value to the test:
    yield vcf_path

    # Code after yield runs during teardown:
    print(f"\n[FIXTURE TEARDOWN] Test completed for {vcf_path.name}")

def test_vcf_reader(sample_vcf_file: Path):
    # 'sample_vcf_file' is dynamically injected:
    content = sample_vcf_file.read_text(encoding="utf-8")
    assert "rs101" in content
    assert sample_vcf_file.exists()
```

---

## 4. Parameterized Testing (`@pytest.mark.parametrize`)

Instead of writing repetitive test functions, parameterization executes a single test across a matrix of inputs and expected outputs. Each scenario runs as an **independent test case**.

```python
import pytest

def normalize_chromosome(chrom: str) -> str:
    """Standardizes chromosome notation to 'chr1', 'chrX', etc."""
    clean = chrom.strip().upper()
    if not clean.startswith("CHR"):
        clean = f"CHR{clean}"
    if clean == "CHRMT":
        return "CHRM"
    return clean

@pytest.mark.parametrize(
    "raw_input, expected_output",
    [
        ("1", "CHR1"),
        ("chr1", "CHR1"),
        ("CHR1", "CHR1"),
        ("X", "CHRX"),
        ("chrmt", "CHRM"),
        ("22", "CHR22"),
    ]
)
def test_normalize_chromosome(raw_input: str, expected_output: str):
    assert normalize_chromosome(raw_input) == expected_output
```

---

## 5. Mocking Boundary Interfaces with `unittest.mock`

When testing production software, you must decouple unit tests from external systems (REST APIs, databases, slow network storage, hardware biosensors).

### The Golden Rule of Mocking
**Patch the name where it is LOOKED UP, not where it is defined.**
* If `my_service.py` runs `import requests`, patch `my_service.requests`.
* If `my_service.py` runs `from requests import get`, patch `my_service.get`.

```python
from unittest.mock import patch, MagicMock

# Production function calling external LIMS API:
def query_lims_sample_status(sample_id: str) -> str:
    import requests  # Third-party network library
    response = requests.get(f"https://lims.internal/api/samples/{sample_id}", timeout=5.0)
    response.raise_for_status()
    return response.json()["status"]

# Unit test with mock:
@patch("requests.get")
def test_query_lims_sample_status_success(mock_get: MagicMock):
    # Configure mock response:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "SEQUENCING_COMPLETED"}
    mock_get.return_value = mock_response

    # Execute unit under test:
    status = query_lims_sample_status("SAM_9910")

    # Assertions on mock interactions and output:
    assert status == "SEQUENCING_COMPLETED"
    mock_get.assert_called_once_with("https://lims.internal/api/samples/SAM_9910", timeout=5.0)
```

---

## 6. Runtime Performance Profiling with `cProfile`

Before attempting to optimize code, you must measure where CPU time is actually spent.

Python includes **`cProfile`**, a C-extension deterministic profiler that tracks function calls, total execution time, and cumulative time.

```python
import cProfile
import pstats
import io

def heavy_computation():
    total = 0
    # Simulate CPU hotspot:
    for i in range(100_000):
        total += sum(j for j in range(20))
    return total

def profile_target():
    profiler = cProfile.Profile()
    profiler.enable()

    # Target workload:
    result = heavy_computation()

    profiler.disable()

    # Format profile statistics:
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(10)  # Print top 10 bottlenecks

    print(s.getvalue())

if __name__ == "__main__":
    profile_target()
```

### Profile Column Metrics Explained
* `ncalls`: Number of times the function was called.
* `tottime`: Total time spent in the function itself (excluding calls to sub-functions).
* `percall`: `tottime` divided by `ncalls`.
* `cumtime`: Cumulative time spent in this function and all sub-functions it called.
* `filename:lineno(function)`: The exact location of the bottleneck in code.

---

## 7. Modern Project Packaging with `pyproject.toml` (PEP 621)

Modern Python replaces legacy `setup.py` and `requirements.txt` with a single unified configuration standard: **`pyproject.toml`**.

### Standard Production Repository Layout (`src` Layout)

```text
my_genomic_engine/
├── pyproject.toml             <- Single source of truth for build & metadata
├── README.md                  <- Package documentation
├── src/
│   └── genomic_engine/        <- Actual importable package
│       ├── __init__.py
│       ├── core.py
│       └── parsers.py
└── tests/                     <- Isolated test suite
    ├── conftest.py            <- Shared global fixtures
    └── test_parsers.py
```

### Complete `pyproject.toml` Production Specification

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "genomic-engine"
version = "1.0.0"
description = "High-throughput genomic pipeline data processor"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [
    { name = "Karthik Aiyasamy", email = "karthikeyan.a@live.in" }
]
dependencies = [
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "mypy>=1.8.0",
    "ruff>=0.3.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers --tb=short"

[tool.mypy]
strict = true
python_version = "3.10"
disallow_untyped_defs = true

[tool.ruff]
line-length = 100
target-version = "py310"
```

---

## 8. Common Pitfalls and Systems Traps

### Pitfall 1: Over-Mocking and Testing the Mock
When tests mock out everything, they end up verifying mock wiring rather than real system logic. If the underlying third-party API changes, the mocks still pass while production crashes!
* **Rule:** Only mock external network calls, hardware devices, and databases. Use real objects for internal domain calculations.

### Pitfall 2: Mutable Global State Leaking Between Tests
If Test A modifies a class attribute or global setting, Test B may pass when run alone but fail when run as part of the full test suite.
* **Fix:** Use the pytest `monkeypatch` fixture to modify environment variables and attributes; it automatically reverts changes when the test finishes.

---

## 9. Hands-On Systems Challenge: Fully Tested Clinical QC Evaluator

### The Problem
Write a clinical quality control module `ClinicalQCEvaluator` accompanied by a complete `pytest` test suite that:
1. Validates sequencing read quality scores against clinical thresholds.
2. Uses `@pytest.fixture` to generate synthetic patient run payloads.
3. Uses `@pytest.mark.parametrize` to test boundary edge cases.
4. Uses `unittest.mock` to mock sending alerts to an external notifications endpoint.

### Complete Runnable Implementation

```python
from dataclasses import dataclass
from typing import Any
import pytest
from unittest.mock import patch, MagicMock

@dataclass(slots=True, frozen=True)
class QCResult:
    sample_id: str
    passed: bool
    mean_quality: float
    reason: str

class ClinicalQCEvaluator:
    def __init__(self, min_quality_score: float = 30.0):
        self.min_quality_score = min_quality_score

    def evaluate(self, sample_id: str, quality_scores: list[float]) -> QCResult:
        if not quality_scores:
            return QCResult(sample_id, False, 0.0, "EMPTY_READ_SCORES")
        
        mean_qual = sum(quality_scores) / len(quality_scores)
        passed = mean_qual >= self.min_quality_score
        reason = "MEETS_CLINICAL_STANDARD" if passed else "LOW_PHRED_QUALITY"
        
        return QCResult(sample_id, passed, round(mean_qual, 2), reason)

    def evaluate_and_notify(self, sample_id: str, scores: list[float], notifier_api: Any) -> QCResult:
        result = self.evaluate(sample_id, scores)
        if not result.passed:
            notifier_api.send_alert(f"QC FAILURE: {sample_id} ({result.reason})")
        return result

# ==================== PYTEST TEST SUITE ====================

@pytest.fixture
def evaluator() -> ClinicalQCEvaluator:
    return ClinicalQCEvaluator(min_quality_score=30.0)

@pytest.mark.parametrize(
    "scores, expected_pass, expected_reason",
    [
        ([35.0, 38.0, 40.0], True, "MEETS_CLINICAL_STANDARD"),
        ([30.0, 30.0, 30.0], True, "MEETS_CLINICAL_STANDARD"),
        ([22.0, 25.0, 28.0], False, "LOW_PHRED_QUALITY"),
        ([], False, "EMPTY_READ_SCORES"),
    ]
)
def test_qc_evaluator_scenarios(
    evaluator: ClinicalQCEvaluator,
    scores: list[float],
    expected_pass: bool,
    expected_reason: str
):
    result = evaluator.evaluate("SAMPLE_TEST", scores)
    assert result.passed == expected_pass
    assert result.reason == expected_reason

def test_notifier_alert_on_failure(evaluator: ClinicalQCEvaluator):
    mock_notifier = MagicMock()
    
    # Run with failing scores:
    result = evaluator.evaluate_and_notify("SAM_FAIL_01", [15.0, 20.0], mock_notifier)
    
    assert not result.passed
    # Verify notification fired:
    mock_notifier.send_alert.assert_called_once_with("QC FAILURE: SAM_FAIL_01 (LOW_PHRED_QUALITY)")

def test_notifier_silent_on_success(evaluator: ClinicalQCEvaluator):
    mock_notifier = MagicMock()
    
    # Run with passing scores:
    result = evaluator.evaluate_and_notify("SAM_PASS_01", [35.0, 38.0], mock_notifier)
    
    assert result.passed
    # Verify notification did NOT fire:
    mock_notifier.send_alert.assert_not_called()

if __name__ == "__main__":
    # Self-contained pytest run:
    import sys
    sys.exit(pytest.main(["-v", __file__]))
```

---

## 10. Testing and Profiling Tool Comparison Table

| Tool | Category | Primary Focus | When to Run |
| :--- | :--- | :--- | :--- |
| `pytest` | Test Runner | Unit and integration test execution | Every local code change & CI/CD |
| `pytest-cov` | Quality Gate | Measures branch and line test coverage | On pull request creation |
| `unittest.mock` | Test Isolation | Simulating boundary network & database I/O | Inside unit tests |
| `cProfile` | Profiler | Deterministic function call hotspot detection | When pipeline runtimes exceed SLA |
| `line_profiler` | Profiler | Line-by-line inner loop timing analysis | Micro-optimizing critical algorithms |
| `tracemalloc` | Profiler | Tracking Python heap allocations by line | Investigating memory leaks & OOM kills |

---

## 11. Production Readiness Decision Guide & ASCII Decision Flowchart

```text
PRODUCTION READINESS DECISION GUIDE
─────────────────────────────────────────────────────────────────────────────
SCENARIO                                                USE THIS
─────────────────────────────────────────────────────────────────────────────
Need to run unit tests with rich diffs                  pytest
Testing multiple input/output scenarios cleanly         @pytest.mark.parametrize
Providing shared database or temporary paths            @pytest.fixture (tmp_path)
Simulating third-party HTTP or external storage         unittest.mock.patch
Diagnosing why a pipeline step is running slowly        cProfile
Diagnosing memory leaks or unexpected RAM growth        tracemalloc
Defining package metadata, dependencies, and tools      pyproject.toml
─────────────────────────────────────────────────────────────────────────────
```

### Decision Flowchart

```text
Do you need to test system behavior or profile performance?
  TESTING ──> Are you testing external network / database services?
                YES ──> unittest.mock.patch (Mock boundary interfaces)
                NO  ──> Pure domain testing with pytest + fixtures
  PROFILING ─> Is the bottleneck CPU runtime or Memory/RAM?
                CPU ──> cProfile (function level) + line_profiler (line level)
                RAM ──> tracemalloc (allocations by line)
```

---

## 12. Final Master Checklist: 12-Day Curriculum Complete

Congratulations! You have completed the comprehensive 12-day systems curriculum. Verify that you have internalized these core engineering competencies:

- [ ] Day 01: Bytecode execution stack (`ceval.c`), pointers vs memory boxes, `is` vs `==`, reference counting and cyclic GC.
- [ ] Day 02: `PyObject` structure, 28-byte int overhead, mutability vs immutability, shallow vs deep copying.
- [ ] Day 03: Dynamic list over-allocation, compact hash table mechanics, hash collisions, `deque` vs `list`.
- [ ] Day 04: The LEGB scope hierarchy, `global`/`nonlocal`, structural pattern matching (`match/case`), walrus operator (`:=`).
- [ ] Day 05: Functions as first-class heap objects, call-by-object-sharing, mutable default trap, parameterized decorators with `functools.wraps`.
- [ ] Day 06: Iteration protocol (`__iter__`/`__next__`), `yield` and frame freezing, $O(1)$ memory streaming with `itertools`.
- [ ] Day 07: Classes as live heap objects, `__new__` vs `__init__`, dunder protocols, hashing contract, multiple inheritance MRO.
- [ ] Day 08: Modern `@dataclass`, memory optimization with `__slots__` (65% RAM reduction), static duck typing with `typing.Protocol`.
- [ ] Day 09: Gradual typing and type erasure, `Literal`, `TypedDict`, `NewType`, domain exception chaining (`raise from`).
- [ ] Day 10: Layered I/O architecture, context managers (`with`, `@contextmanager`, `ExitStack`), zero-copy `mmap`, `pathlib.Path`.
- [ ] Day 11: Concurrency landscape, the GIL mechanics, `ThreadPoolExecutor` for I/O, `ProcessPoolExecutor` for CPU, `asyncio` TaskGroups.
- [ ] Day 12: Modern verification with `pytest`, fixtures, parameterization, boundary mocking, `cProfile` hotspot analysis, and `pyproject.toml`.

---

## 13. Property-Based Testing with hypothesis

Traditional unit tests are limited to cases you manually think of. Property-based testing lets you describe **mathematical properties** that must hold for all valid inputs, and the library generates hundreds of random edge cases automatically.

```text
Traditional Tests:          Property-Based Tests:
  You pick inputs.            Library generates inputs.
  test add(1,2) == 3          @given(st.integers(), st.integers())
  test add(-1,0) == -1        def test_add_commutative(a, b):
                                  assert add(a,b) == add(b,a)
  5 cases by hand.            100+ cases auto-generated.
  Miss: maxint overflow.      Finds: add(sys.maxsize, 1) crashes!
```

### How hypothesis Works

1. `@given` generates random inputs satisfying the declared strategy.
2. If a test fails, hypothesis **shrinks** the input to the minimal reproducer automatically.
3. Failing examples are stored in a local database and re-run on every future test run.

```python
# Install: pip install hypothesis

# Without hypothesis: show the property pattern manually
def add(a: int, b: int) -> int:
    return a + b

# Properties this function must always satisfy:
# 1. Commutativity: add(a, b) == add(b, a)
# 2. Identity:      add(a, 0) == a
# 3. Associativity: add(add(a, b), c) == add(a, add(b, c))

# Manual property verification (simulates what hypothesis does):
import random

def verify_properties(num_trials: int = 1000) -> None:
    for _ in range(num_trials):
        a = random.randint(-10**9, 10**9)
        b = random.randint(-10**9, 10**9)
        c = random.randint(-10**9, 10**9)

        assert add(a, b) == add(b, a),         f"Commutativity failed: {a}, {b}"
        assert add(a, 0) == a,                  f"Identity failed: {a}"
        assert add(add(a, b), c) == add(a, add(b, c)), "Associativity failed"

    print(f"All {num_trials} property checks passed.")

verify_properties()

# With hypothesis installed, this is equivalent:
#
# from hypothesis import given, strategies as st
#
# @given(st.integers(), st.integers(), st.integers())
# def test_add_properties(a: int, b: int, c: int):
#     assert add(a, b) == add(b, a)
#     assert add(a, 0) == a
#     assert add(add(a, b), c) == add(a, add(b, c))
```

### When to Use Property-Based Tests vs Unit Tests

| Aspect | Unit Tests | Property-Based Tests |
| :--- | :--- | :--- |
| Input coverage | Cases you think of | Hundreds of random cases |
| Edge case discovery | Manual | Automatic |
| Failure diagnosis | Exact case known | Shrinks to minimal case |
| Best for | Specific business rules, regression | Algorithms, parsers, serialization |
| Complement each other? | Yes: use both |  |

---

## 14. pytest-cov and Coverage Thresholds in CI

Coverage measures what percentage of your source code is exercised during the test run.

**Line coverage:** counts whether a line was executed at least once.
**Branch coverage:** also verifies that both True and False branches of every `if` statement were tested.

```text
Example: Why branch coverage matters

def classify(x: int) -> str:
    if x > 0:
        return "positive"
    return "non-positive"

# Test: classify(5) -> "positive"
# Line coverage: 100% (all 3 executable lines hit)
# Branch coverage: 50% (the False branch of 'if x > 0' was never tested!)
```

### Running Coverage

```bash
# Run tests with line + branch coverage, fail if below 90%:
pytest --cov=src --cov-branch --cov-report=term-missing --cov-fail-under=90 tests/
```

### Reading the Coverage Report

```text
Name                           Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------------
src/genomic_engine/core.py        48      3     16      2    91%   L45-47, L89
src/genomic_engine/parsers.py     31      0      8      0   100%
--------------------------------------------------------------------------
TOTAL                             79      3     24      2    94%

REQUIRED: 90% -- PASS
```

Column meanings:
- `Stmts`: Total executable statement lines in the file.
- `Miss`: Lines never executed during the test run.
- `Branch`: Total number of conditional branches (each `if` has 2: True and False).
- `BrPart`: Branches where only one side was tested.
- `Cover`: Overall coverage percentage accounting for both lines and branches.
- `Missing`: Exact line numbers that were never reached.

### .coveragerc Configuration File

Place this at the project root to exclude boilerplate from coverage counts:

```ini
[run]
source = src
branch = true
omit =
    */tests/*
    */__init__.py

[report]
fail_under = 90
show_missing = true
skip_covered = false
```

---

## 15. Performance Benchmarking with timeit

`cProfile` tells you which function takes the most time overall.
`timeit` isolates one specific expression or function for precise microsecond-level measurement.

Use `timeit` when you want to compare two implementation choices head-to-head.

```python
import timeit

# Benchmark three string-building strategies:

concat_code = """
result = ""
for i in range(1000):
    result += str(i)
"""

list_join_code = """
parts = []
for i in range(1000):
    parts.append(str(i))
result = "".join(parts)
"""

gen_join_code = """
result = "".join(str(i) for i in range(1000))
"""

n_runs = 10_000

t1 = timeit.timeit(stmt=concat_code, number=n_runs)
t2 = timeit.timeit(stmt=list_join_code, number=n_runs)
t3 = timeit.timeit(stmt=gen_join_code, number=n_runs)

print(f"String +=      : {t1:.3f}s total  ({t1/n_runs*1e6:.1f} us/run)")
print(f"List + join    : {t2:.3f}s total  ({t2/n_runs*1e6:.1f} us/run)")
print(f"Generator join : {t3:.3f}s total  ({t3/n_runs*1e6:.1f} us/run)")
print(f"Speedup (join vs +=): {t1/t2:.1f}x faster")
```

### Expected Output

```text
String +=      : 1.842s total  (184.2 us/run)
List + join    : 0.531s total  ( 53.1 us/run)
Generator join : 0.612s total  ( 61.2 us/run)
Speedup (join vs +=): 3.5x faster
```

### timeit vs cProfile Decision

```text
USE timeit WHEN:
  - Comparing two algorithms or two implementations of the same function
  - Measuring overhead of a single expression (e.g., dict lookup vs if-else)
  - Verifying that an optimization actually improved speed

USE cProfile WHEN:
  - You don't know WHERE the bottleneck is in a large program
  - You need call counts and cumulative time across a full workload
  - Investigating why a pipeline step is slower than its SLA
```

---

## 16. Extended Final Master Checklist

The original Day 12 checklist remains above. These items cover the new sections:

- [ ] What is the core difference between property-based testing and traditional unit testing?
- [ ] What does hypothesis do when it finds a failing case? (Shrinking)
- [ ] What does branch coverage measure that line coverage alone misses?
- [ ] What does `--cov-fail-under=90` enforce in a CI/CD pipeline?
- [ ] When would you use `timeit` over `cProfile`?
- [ ] Why is `"".join(str(i) for i in range(N))` faster than `result += str(i)` in a loop?
