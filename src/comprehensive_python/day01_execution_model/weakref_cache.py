"""
Weak Reference Lifetime Management and Non-Retaining Caches.

This module provides cache structures utilizing weakref semantics, allowing
cached objects to be collected automatically by the GC when all external
strong references are dropped.
"""

from __future__ import annotations

import gc
import weakref
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class ExpiringWeakCache(Generic[T]):
    """
    An in-memory object cache backed by weakref.WeakValueDictionary.

    Objects stored in this cache do not have their ob_refcnt incremented.
    When caller scopes release all strong references, the CPython GC reclaims
    the object and the cache entry automatically evaporates.
    """

    def __init__(self) -> None:
        self._cache: weakref.WeakValueDictionary[str, T] = weakref.WeakValueDictionary()
        self._finalization_log: list[str] = []

    def set(
        self,
        key: str,
        value: T,
        on_finalize: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Store a strong object weakly in the cache.

        Optionally attaches a weakref.finalize callback that executes when the
        underlying object is destroyed by the GC.
        """
        self._cache[key] = value

        if on_finalize is not None:
            weakref.finalize(value, on_finalize, key)

    def get(self, key: str) -> Optional[T]:
        """Retrieve an object if it has not yet been collected."""
        return self._cache.get(key)

    def contains(self, key: str) -> bool:
        """Check if an active, uncollected entry exists under key."""
        return key in self._cache

    def live_keys(self) -> list[str]:
        """Return list of active keys whose objects are still alive in memory."""
        return list(self._cache.keys())

    def __len__(self) -> int:
        return len(self._cache)


class SamplePayload:
    """Sample class with identity for weak reference demonstration."""

    def __init__(self, identifier: str, payload_size: int = 1024) -> None:
        self.identifier = identifier
        self.payload = bytearray(payload_size)

    def __repr__(self) -> str:
        return f"SamplePayload({self.identifier!r}, bytes={len(self.payload)})"


def run_demo() -> None:
    """Command-line runnable demonstration of weak reference eviction."""
    print("=== Weak Reference Auto-Eviction Demonstration ===")

    cache = ExpiringWeakCache[SamplePayload]()
    finalized: list[str] = []

    def handle_eviction(k: str) -> None:
        finalized.append(k)

    # Step 1: Create objects with strong references
    obj1: Optional[SamplePayload] = SamplePayload("resource_persistent")
    obj2: Optional[SamplePayload] = SamplePayload("resource_transient")

    cache.set("k1", obj1, handle_eviction)
    cache.set("k2", obj2, handle_eviction)

    print(f"Initial cache entries: {cache.live_keys()}")
    print(f"Retrieving 'k1': {cache.get('k1')}")

    # Step 2: Drop strong reference to obj2
    print("\nReleasing strong reference to 'resource_transient' (del obj2)...")
    del obj2
    gc.collect()

    print(f"Live keys remaining in cache: {cache.live_keys()}")
    print(f"Retrieving 'k2' returns: {cache.get('k2')}")
    print(f"Finalization callbacks invoked: {finalized}")

    # Step 3: Clean up remaining reference
    del obj1
    gc.collect()
    print(f"\nAfter releasing obj1, live keys: {cache.live_keys()}")
    print(f"Finalization callbacks invoked: {finalized}")


if __name__ == "__main__":
    run_demo()
