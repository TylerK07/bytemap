from __future__ import annotations

import os
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass

try:
    import mmap as _mmap_mod  # type: ignore
except Exception:  # pragma: no cover - platform-specific
    _mmap_mod = None  # type: ignore


class InvalidOffset(ValueError):
    """Raised when an invalid (e.g., negative) offset is provided."""


@dataclass(frozen=True)
class _Page:
    index: int
    data: bytes


class PagedReader:
    """Efficient, bounds-checked reader for large binary files.

    Prefers `mmap` for zero-copy slices; falls back to buffered reads with a small LRU page cache.
    The full file is never loaded into memory at once.
    """

    def __init__(
        self,
        path: str,
        *,
        page_size: int = 64 * 1024,
        cache_pages: int = 16,
        use_mmap: bool = True,
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        if cache_pages <= 0:
            raise ValueError("cache_pages must be positive")

        self._path = path
        try:
            st = os.stat(path)
        except FileNotFoundError:
            # Provide a clear exception as requested.
            raise FileNotFoundError(f"File not found: {path}") from None

        self._size = int(st.st_size)
        # Open file handle (kept for the lifetime of the reader)
        self._fh = open(path, "rb", buffering=0)  # noqa: SIM115
        self._page_size = int(page_size)
        self._cache_limit = int(cache_pages)
        self._cache: OrderedDict[int, _Page] = OrderedDict()

        self._mmap = None
        if use_mmap and _mmap_mod is not None and self._size > 0:
            try:
                self._mmap = _mmap_mod.mmap(
                    self._fh.fileno(),
                    length=0,
                    access=_mmap_mod.ACCESS_READ,
                )
            except Exception:
                # Fall back to buffered cache path if mmap fails.
                self._mmap = None

    # Context management for explicit close in long-running apps
    def close(self) -> None:
        if getattr(self, "_mmap", None) is not None:
            with suppress(Exception):
                self._mmap.close()  # type: ignore[union-attr]
            self._mmap = None
        with suppress(Exception):
            self._fh.close()

    def __enter__(self) -> PagedReader:  # pragma: no cover - sugar
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - sugar
        self.close()

    @property
    def size(self) -> int:
        """File size in bytes."""
        return self._size

    @property
    def path(self) -> str:
        """File path."""
        return self._path

    # Internal: fetch a page (LRU-cached) in buffered mode
    def _get_page(self, index: int) -> _Page:
        if index in self._cache:
            page = self._cache.pop(index)
            self._cache[index] = page  # move to end (most-recent)
            return page

        start = index * self._page_size
        if start >= self._size:
            data = b""
        else:
            to_read = min(self._page_size, self._size - start)
            self._fh.seek(start)
            data = self._fh.read(to_read)
        page = _Page(index=index, data=data)

        self._cache[index] = page
        if len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)  # evict LRU
        return page

    def read(self, offset: int, length: int) -> bytes:
        """Read up to `length` bytes starting at `offset`.

        - Negative `offset` or `length` raises `InvalidOffset`.
        - If `offset` >= size, returns b"".
        - Reading past EOF returns the truncated data.
        """
        if offset < 0:
            raise InvalidOffset("offset must be >= 0")
        if length < 0:
            raise InvalidOffset("length must be >= 0")
        if length == 0:
            return b""
        if offset >= self._size:
            return b""

        end = min(self._size, offset + length)
        if self._mmap is not None:
            # mmap slicing gracefully truncates at EOF
            return bytes(self._mmap[offset:end])  # type: ignore[index]

        # Buffered path with page cache
        result = bytearray()
        pos = offset
        while pos < end:
            page_index = pos // self._page_size
            page = self._get_page(page_index)
            within = pos - (page_index * self._page_size)
            take = min(len(page.data) - within, end - pos)
            if take <= 0:
                break
            result += page.data[within : within + take]
            pos += take
        return bytes(result)

    def byte_at(self, offset: int) -> int | None:
        """Return the byte value at `offset`, or None if at EOF.

        Negative offsets raise `InvalidOffset`.
        """
        if offset < 0:
            raise InvalidOffset("offset must be >= 0")
        if offset >= self._size:
            return None

        if self._mmap is not None:
            return self._mmap[offset]  # type: ignore[index]

        page_index = offset // self._page_size
        within = offset - page_index * self._page_size
        page = self._get_page(page_index)
        if within >= len(page.data):
            return None
        return page.data[within]

    def slice(self, offset: int, length: int) -> memoryview | bytes:
        """Return a cheap slice view when possible, else bytes.

        - Negative `offset`/`length` raises `InvalidOffset`.
        - If `offset` >= size, returns empty bytes.
        - Truncates at EOF.
        """
        if offset < 0:
            raise InvalidOffset("offset must be >= 0")
        if length < 0:
            raise InvalidOffset("length must be >= 0")
        if length == 0 or offset >= self._size:
            return b""
        end = min(self._size, offset + length)

        if self._mmap is not None:
            # memoryview to avoid copying; safe while the PagedReader is open
            return memoryview(self._mmap)[offset:end]  # type: ignore[index]

        # Buffered path: return bytes
        return self.read(offset, length)
