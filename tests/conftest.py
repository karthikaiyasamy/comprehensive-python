"""
Shared pytest fixtures and test configuration.
"""

from __future__ import annotations

import gc
from typing import Generator

# When pytest is installed, these fixtures are auto-discovered.
# They are written so that importing conftest directly doesn't fail even if pytest isn't present.
try:
    import pytest

    @pytest.fixture
    def clean_gc() -> Generator[None, None, None]:
        """Ensure garbage collection state is cleanly flushed before and after test."""
        gc.collect()
        yield
        gc.collect()

except ImportError:
    pass

