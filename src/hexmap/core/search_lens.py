"""Search lens mode - find patterns in binary files."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from hexmap.core.io import PagedReader


@dataclass(frozen=True)
class LengthType:
    """Combined length field type and endianness specification."""

    size: int  # 1, 2, or 4 bytes
    endian: Literal["little", "big"] | None  # None for u8 (endian-agnostic)
    label: str  # Display label (e.g., "u16 LE")

    @classmethod
    def u8(cls) -> LengthType:
        return cls(size=1, endian=None, label="u8")

    @classmethod
    def u16_le(cls) -> LengthType:
        return cls(size=2, endian="little", label="u16 LE")

    @classmethod
    def u16_be(cls) -> LengthType:
        return cls(size=2, endian="big", label="u16 BE")

    @classmethod
    def u32_le(cls) -> LengthType:
        return cls(size=4, endian="little", label="u32 LE")

    @classmethod
    def u32_be(cls) -> LengthType:
        return cls(size=4, endian="big", label="u32 BE")

    @classmethod
    def from_label(cls, label: str) -> LengthType:
        """Create LengthType from label string."""
        mapping = {
            "u8": cls.u8(),
            "u16 LE": cls.u16_le(),
            "u16 BE": cls.u16_be(),
            "u32 LE": cls.u32_le(),
            "u32 BE": cls.u32_be(),
        }
        return mapping.get(label, cls.u16_le())  # Default to u16 LE


@dataclass(frozen=True)
class PointerType:
    """Pointer field type and endianness specification."""

    size: int  # 2, 4, or 8 bytes
    endian: Literal["little", "big"]
    label: str  # Display label (e.g., "u32 LE")

    @classmethod
    def u16_le(cls) -> PointerType:
        return cls(size=2, endian="little", label="u16 LE")

    @classmethod
    def u16_be(cls) -> PointerType:
        return cls(size=2, endian="big", label="u16 BE")

    @classmethod
    def u32_le(cls) -> PointerType:
        return cls(size=4, endian="little", label="u32 LE")

    @classmethod
    def u32_be(cls) -> PointerType:
        return cls(size=4, endian="big", label="u32 BE")

    @classmethod
    def u64_le(cls) -> PointerType:
        return cls(size=8, endian="little", label="u64 LE")

    @classmethod
    def u64_be(cls) -> PointerType:
        return cls(size=8, endian="big", label="u64 BE")

    @classmethod
    def from_label(cls, label: str) -> PointerType:
        """Create PointerType from label string."""
        mapping = {
            "u16 LE": cls.u16_le(),
            "u16 BE": cls.u16_be(),
            "u32 LE": cls.u32_le(),
            "u32 BE": cls.u32_be(),
            "u64 LE": cls.u64_le(),
            "u64 BE": cls.u64_be(),
        }
        return mapping.get(label, cls.u32_le())  # Default to u32 LE


@dataclass
class MatchDetail:
    """Details about one encoding match at a location."""

    encoding: str  # e.g. "unix_s", "DOS datetime", "ASCII MM/DD/YY"
    summary: str  # Human-readable decoded value
    details: dict  # Additional info (value, type, endian, etc.)


@dataclass
class SearchSpan:
    """A span within a search hit with a specific rendering role."""

    offset: int
    length: int
    role: str  # "hit" | "length" | "payload" | "pointer" | "target_preview"


@dataclass
class SearchHit:
    """A single search result (possibly matching multiple encodings)."""

    offset: int
    length: int
    summary: str  # Best/primary decoded value
    matches: list[MatchDetail]  # All encodings that matched here
    spans: list[SearchSpan] | None = None  # Optional multi-span hits (e.g., length + payload)


class SearchState:
    """State for active search lens."""

    def __init__(self) -> None:
        # "none" | "date" | "chunk" | "string" | "bytes" | "u16" | "pointer"
        self.mode: str = "none"
        self.params: dict = {}
        self.results: list[SearchHit] = []
        self.index: int = -1  # current selected hit

    def is_active(self) -> bool:
        return self.mode != "none"

    def clear(self) -> None:
        self.mode = "none"
        self.params = {}
        self.results = []
        self.index = -1

    def has_results(self) -> bool:
        return len(self.results) > 0

    def current_hit(self) -> SearchHit | None:
        if 0 <= self.index < len(self.results):
            return self.results[self.index]
        return None

    def next_hit(self) -> SearchHit | None:
        if not self.results:
            return None
        self.index = (self.index + 1) % len(self.results)
        return self.results[self.index]

    def prev_hit(self) -> SearchHit | None:
        if not self.results:
            return None
        self.index = (self.index - 1) % len(self.results)
        return self.results[self.index]


def search_date_unix_s(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 4,
) -> list[SearchHit]:
    """Search for unix timestamp (u32 LE) within date range.

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 4)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Convert dates to unix timestamps (UTC)
    start_ts = int(start_date.replace(tzinfo=UTC).timestamp())
    end_ts = int(end_date.replace(tzinfo=UTC).timestamp())

    # Scan file
    size = reader.size
    if size < 4:
        return hits

    pos = 0
    while pos <= size - 4:
        data = reader.read(pos, 4)
        if len(data) == 4:
            try:
                # Read as u32 little-endian
                value = struct.unpack("<I", data)[0]

                # Check if in range (allow some reasonable bounds)
                if start_ts <= value <= end_ts:
                    # Convert to datetime
                    dt = datetime.fromtimestamp(value, tz=UTC)
                    summary = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

                    match = MatchDetail(
                        encoding="unix_s (u32 LE)",
                        summary=summary,
                        details={
                            "type": "u32",
                            "endian": "little",
                            "value": value,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=4,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid timestamp, skip
                pass

        pos += alignment

    return hits


def search_date_unix_ms(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 8,
) -> list[SearchHit]:
    """Search for unix timestamp in milliseconds (u64 LE) within date range.

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 8)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Convert dates to unix timestamps in milliseconds (UTC)
    start_ts = int(start_date.replace(tzinfo=UTC).timestamp() * 1000)
    end_ts = int(end_date.replace(tzinfo=UTC).timestamp() * 1000)

    # Scan file
    size = reader.size
    if size < 8:
        return hits

    pos = 0
    while pos <= size - 8:
        data = reader.read(pos, 8)
        if len(data) == 8:
            try:
                # Read as u64 little-endian
                value = struct.unpack("<Q", data)[0]

                # Check if in range (reasonable bounds for milliseconds)
                if start_ts <= value <= end_ts:
                    # Convert to datetime
                    dt = datetime.fromtimestamp(value / 1000.0, tz=UTC)
                    summary = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

                    match = MatchDetail(
                        encoding="unix_ms (u64 LE)",
                        summary=summary,
                        details={
                            "type": "u64",
                            "endian": "little",
                            "value": value,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=8,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid timestamp, skip
                pass

        pos += alignment

    return hits


def search_date_filetime(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 8,
) -> list[SearchHit]:
    """Search for Windows FILETIME (u64 LE) within date range.

    FILETIME is 100-nanosecond intervals since January 1, 1601 UTC.

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 8)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # FILETIME epoch: January 1, 1601
    filetime_epoch = datetime(1601, 1, 1, tzinfo=UTC)

    # Convert dates to FILETIME values (100-nanosecond intervals)
    start_ts = int((start_date.replace(tzinfo=UTC) - filetime_epoch).total_seconds() * 10_000_000)
    end_ts = int((end_date.replace(tzinfo=UTC) - filetime_epoch).total_seconds() * 10_000_000)

    # Scan file
    size = reader.size
    if size < 8:
        return hits

    pos = 0
    while pos <= size - 8:
        data = reader.read(pos, 8)
        if len(data) == 8:
            try:
                # Read as u64 little-endian
                value = struct.unpack("<Q", data)[0]

                # Check if in range
                if start_ts <= value <= end_ts:
                    # Convert to datetime
                    dt = filetime_epoch + timedelta(microseconds=value / 10)
                    summary = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

                    match = MatchDetail(
                        encoding="FILETIME (u64 LE)",
                        summary=summary,
                        details={
                            "type": "u64",
                            "endian": "little",
                            "value": value,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=8,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid timestamp, skip
                pass

        pos += alignment

    return hits


def search_date_dos_datetime(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 4,
) -> list[SearchHit]:
    """Search for DOS datetime (2×u16 LE) within date range.

    DOS datetime is packed as:
    - date_u16: year (bits 9-15), month (bits 5-8), day (bits 0-4)
    - time_u16: hour (bits 11-15), minute (bits 5-10), second/2 (bits 0-4)

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 4)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Scan file
    size = reader.size
    if size < 4:
        return hits

    pos = 0
    while pos <= size - 4:
        data = reader.read(pos, 4)
        if len(data) == 4:
            try:
                # Read as 2×u16 little-endian
                date_u16, time_u16 = struct.unpack("<HH", data)

                # Decode date
                year = 1980 + ((date_u16 >> 9) & 0x7F)
                month = (date_u16 >> 5) & 0x0F
                day = date_u16 & 0x1F

                # Decode time
                hour = (time_u16 >> 11) & 0x1F
                minute = (time_u16 >> 5) & 0x3F
                second = (time_u16 & 0x1F) * 2

                # Validate ranges
                if not (1 <= month <= 12 and 1 <= day <= 31):
                    raise ValueError("Invalid date")
                if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                    raise ValueError("Invalid time")

                # Construct datetime (assume UTC for comparison)
                dt = datetime(year, month, day, hour, minute, second, tzinfo=UTC)

                # Check if in range
                if start_date.replace(tzinfo=UTC) <= dt <= end_date.replace(tzinfo=UTC):
                    summary = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

                    match = MatchDetail(
                        encoding="DOS datetime (2×u16 LE)",
                        summary=summary,
                        details={
                            "type": "2×u16",
                            "endian": "little",
                            "date_u16": date_u16,
                            "time_u16": time_u16,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=4,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid datetime, skip
                pass

        pos += alignment

    return hits


def search_date_ole_date(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 8,
) -> list[SearchHit]:
    """Search for OLE Automation DATE (f64 LE) within date range.

    OLE DATE is a floating point number representing days since 1899-12-30.

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 8)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # OLE DATE epoch: December 30, 1899
    ole_epoch = datetime(1899, 12, 30, tzinfo=UTC)

    # Scan file
    size = reader.size
    if size < 8:
        return hits

    pos = 0
    while pos <= size - 8:
        data = reader.read(pos, 8)
        if len(data) == 8:
            try:
                # Read as f64 little-endian
                value = struct.unpack("<d", data)[0]

                # Reject invalid values
                # NaN, inf, or values that would overflow datetime (year 9999 limit)
                # OLE epoch is 1899-12-30, so ~3M days = year ~9999
                if value != value or abs(value) > 3000000:
                    raise ValueError("Invalid OLE DATE")

                # Convert to datetime (with overflow protection)
                try:
                    dt = ole_epoch + timedelta(days=value)
                except (OverflowError, OSError):
                    raise ValueError("Invalid OLE DATE") from None

                # Check if in range
                if start_date.replace(tzinfo=UTC) <= dt <= end_date.replace(tzinfo=UTC):
                    summary = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

                    match = MatchDetail(
                        encoding="OLE DATE (f64 LE)",
                        summary=summary,
                        details={
                            "type": "f64",
                            "endian": "little",
                            "value": value,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=8,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid OLE DATE, skip
                pass

        pos += alignment

    return hits


def search_date_ascii_text(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
) -> list[SearchHit]:
    """Search for ASCII date text within date range.

    Searches for these patterns:
    - MM/DD/YY (e.g., 12/18/91)
    - MM/DD/YYYY (e.g., 12/18/1991)
    - YYYY-MM-DD (e.g., 1991-12-18)

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Read entire file as ASCII (ignore decoding errors)
    size = reader.size
    if size == 0:
        return hits

    # Read in chunks to avoid memory issues with large files
    max_chunk_size = 10 * 1024 * 1024  # 10 MB
    chunk_size = min(size, max_chunk_size)

    # Patterns for date matching
    patterns = [
        (r"(\d{2})/(\d{2})/(\d{2})\b", "MM/DD/YY"),  # 12/18/91
        (r"(\d{2})/(\d{2})/(\d{4})\b", "MM/DD/YYYY"),  # 12/18/1991
        (r"(\d{4})-(\d{2})-(\d{2})\b", "YYYY-MM-DD"),  # 1991-12-18
    ]

    pos = 0
    seen_offsets: set[int] = set()  # Track seen offsets to avoid duplicates

    while pos < size:
        # Read chunk with overlap for pattern matching at boundaries
        overlap = 20  # Enough for longest date pattern
        chunk_start = max(0, pos - overlap)
        chunk_data = reader.read(chunk_start, chunk_size + overlap)

        # Decode as ASCII, replacing errors
        try:
            text = chunk_data.decode("ascii", errors="replace")
        except Exception:
            pos += chunk_size
            continue

        # Search for each pattern
        for pattern, label in patterns:
            for match in re.finditer(pattern, text):
                match_offset = chunk_start + match.start()

                # Skip if we've already processed this offset
                if match_offset < pos or match_offset in seen_offsets:
                    continue

                seen_offsets.add(match_offset)

                try:
                    groups = match.groups()

                    # Parse based on pattern
                    if label == "MM/DD/YY":
                        month, day, year_2digit = int(groups[0]), int(groups[1]), int(groups[2])
                        # Map 2-digit year: 00-69 => 2000-2069, 70-99 => 1970-1999
                        year = 2000 + year_2digit if year_2digit <= 69 else 1900 + year_2digit
                    elif label == "MM/DD/YYYY":
                        month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                    elif label == "YYYY-MM-DD":
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    else:
                        continue

                    # Validate month/day
                    if not (1 <= month <= 12 and 1 <= day <= 31):
                        continue

                    # Construct date (time=00:00:00)
                    dt = datetime(year, month, day, tzinfo=UTC)

                    # Check if in range
                    if start_date.replace(tzinfo=UTC) <= dt <= end_date.replace(tzinfo=UTC):
                        summary = dt.strftime("%Y-%m-%d")

                        match_detail = MatchDetail(
                            encoding=f"ASCII {label}",
                            summary=summary,
                            details={
                                "type": "ascii_text",
                                "pattern": label,
                                "text": match.group(0),
                            },
                        )
                        hits.append(
                            SearchHit(
                                offset=match_offset,
                                length=len(match.group(0)),
                                summary=summary,
                                matches=[match_detail],
                            )
                        )
                except (ValueError, OSError):
                    # Invalid date, skip
                    continue

        pos += chunk_size

    return hits


def search_date_dos_date(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 2,
) -> list[SearchHit]:
    """Search for DOS date only (u16 LE) within date range.

    DOS date is packed as:
    - year (bits 9-15), month (bits 5-8), day (bits 0-4)
    - No time component (date only)

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 2)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Scan file
    size = reader.size
    if size < 2:
        return hits

    pos = 0
    while pos <= size - 2:
        data = reader.read(pos, 2)
        if len(data) == 2:
            try:
                # Read as u16 little-endian
                date_u16 = struct.unpack("<H", data)[0]

                # Decode date
                year = 1980 + ((date_u16 >> 9) & 0x7F)
                month = (date_u16 >> 5) & 0x0F
                day = date_u16 & 0x1F

                # Validate ranges
                if not (1 <= month <= 12 and 1 <= day <= 31):
                    raise ValueError("Invalid date")

                # Construct datetime (no time component)
                dt = datetime(year, month, day, tzinfo=UTC)

                # Check if in range
                if start_date.replace(tzinfo=UTC) <= dt <= end_date.replace(tzinfo=UTC):
                    summary = dt.strftime("%Y-%m-%d")

                    match = MatchDetail(
                        encoding="DOS date (u16 LE)",
                        summary=summary,
                        details={
                            "type": "u16",
                            "endian": "little",
                            "date_u16": date_u16,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=2,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid date, skip
                pass

        pos += alignment

    return hits


def search_date_days_since_1970(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 2,
) -> list[SearchHit]:
    """Search for days since 1970-01-01 (u16 LE) within date range.

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 2)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Epoch: January 1, 1970
    epoch = datetime(1970, 1, 1, tzinfo=UTC)

    # Scan file
    size = reader.size
    if size < 2:
        return hits

    pos = 0
    while pos <= size - 2:
        data = reader.read(pos, 2)
        if len(data) == 2:
            try:
                # Read as u16 little-endian
                days = struct.unpack("<H", data)[0]

                # Convert to datetime (u16 max is 65535 days ~= 179 years)
                dt = epoch + timedelta(days=days)

                # Check if in range
                if start_date.replace(tzinfo=UTC) <= dt <= end_date.replace(tzinfo=UTC):
                    summary = dt.strftime("%Y-%m-%d")

                    match = MatchDetail(
                        encoding="Days since 1970 (u16 LE)",
                        summary=summary,
                        details={
                            "type": "u16",
                            "endian": "little",
                            "days": days,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=2,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid date, skip
                pass

        pos += alignment

    return hits


def search_date_days_since_1980(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 2,
) -> list[SearchHit]:
    """Search for days since 1980-01-01 (u16 LE) within date range.

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 2)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Epoch: January 1, 1980
    epoch = datetime(1980, 1, 1, tzinfo=UTC)

    # Scan file
    size = reader.size
    if size < 2:
        return hits

    pos = 0
    while pos <= size - 2:
        data = reader.read(pos, 2)
        if len(data) == 2:
            try:
                # Read as u16 little-endian
                days = struct.unpack("<H", data)[0]

                # Convert to datetime (u16 max is 65535 days ~= 179 years)
                dt = epoch + timedelta(days=days)

                # Check if in range
                if start_date.replace(tzinfo=UTC) <= dt <= end_date.replace(tzinfo=UTC):
                    summary = dt.strftime("%Y-%m-%d")

                    match = MatchDetail(
                        encoding="Days since 1980 (u16 LE)",
                        summary=summary,
                        details={
                            "type": "u16",
                            "endian": "little",
                            "days": days,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=2,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid date, skip
                pass

        pos += alignment

    return hits


def search_length_prefixed_strings(
    reader: PagedReader,
    length_type: LengthType | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    alignment: int = 1,
) -> list[SearchHit]:
    """Search for length-prefixed (Pascal-style) strings with configurable length field type.

    Args:
        reader: File to search
        length_type: Length field type (u8, u16 LE/BE, u32 LE/BE). Defaults to u16 LE.
        min_length: Minimum payload length (None = no minimum)
        max_length: Maximum payload length (None = no maximum)
        alignment: Byte alignment for scanning (default 1)

    Returns:
        List of SearchHit objects with multi-span hits (length + payload)
    """
    # Default to u16 LE if not specified
    if length_type is None:
        length_type = LengthType.u16_le()

    hits: list[SearchHit] = []

    # Scan file for length fields
    size = reader.size
    len_size = length_type.size
    if size < len_size:
        return hits

    pos = 0
    while pos <= size - len_size:
        data = reader.read(pos, len_size)
        if len(data) == len_size:
            try:
                # Read length based on type
                if len_size == 1:
                    # u8 - no endianness
                    length = data[0]
                else:
                    # u16 or u32 with endianness
                    length = int.from_bytes(data, byteorder=length_type.endian)  # type: ignore[arg-type]

                # Apply filters
                if min_length is not None and length < min_length:
                    pos += alignment
                    continue
                if max_length is not None and length > max_length:
                    pos += alignment
                    continue

                # Skip zero-length strings
                if length == 0:
                    pos += alignment
                    continue

                # Calculate payload bounds (may be capped at EOF)
                payload_start = pos + len_size
                payload_end = min(payload_start + length, size)
                actual_payload_len = payload_end - payload_start

                # Build summary
                if actual_payload_len < length:
                    summary = f"Length: {length} (payload capped at EOF: {actual_payload_len} bytes)"
                else:
                    summary = f"Length: {length} (payload: {actual_payload_len} bytes)"

                # Create multi-span hit: length field + payload
                spans = [
                    SearchSpan(offset=pos, length=len_size, role="length"),
                    SearchSpan(offset=payload_start, length=actual_payload_len, role="payload"),
                ]

                match = MatchDetail(
                    encoding=f"Length-prefixed ({length_type.label})",
                    summary=summary,
                    details={
                        "type": length_type.label,
                        "endian": length_type.endian or "n/a",
                        "length": length,
                        "payload_length": actual_payload_len,
                        "capped": actual_payload_len < length,
                    },
                )

                hits.append(
                    SearchHit(
                        offset=pos,
                        length=len_size + actual_payload_len,
                        summary=summary,
                        matches=[match],
                        spans=spans,
                    )
                )
            except (struct.error, ValueError):
                # Invalid data, skip
                pass

        pos += alignment

    return hits


def search_date_ftm_packed(
    reader: PagedReader,
    start_date: datetime,
    end_date: datetime,
    alignment: int = 2,
) -> list[SearchHit]:
    """Search for FTM Packed Date (4-byte custom format) within date range.

    Format: 4 bytes with packed Y/M/D:
    - byte0: (day << 3) | flags
    - byte1: (month << 1) | must_be_zero
    - byte2-3: year (u16 LE)

    Validation:
    - month low bit must be 0 (byte1 & 0x01 == 0)
    - Confidence: "High" if flags == 0x02, else "Low (unexpected flags)"

    Args:
        reader: File to search
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        alignment: Byte alignment for scanning (default 2)

    Returns:
        List of SearchHit objects sorted by offset
    """
    hits: list[SearchHit] = []

    # Scan file
    size = reader.size
    if size < 4:
        return hits

    pos = 0
    while pos <= size - 4:
        data = reader.read(pos, 4)
        if len(data) == 4:
            try:
                b0, b1, year_lo, year_hi = data

                # Extract fields
                flags = b0 & 0x07
                day = b0 >> 3
                month = b1 >> 1
                year = year_lo | (year_hi << 8)

                # Validate month low bit must be 0
                if b1 & 0x01 != 0:
                    raise ValueError("Invalid month encoding")

                # Validate ranges
                if not (1 <= month <= 12 and 1 <= day <= 31):
                    raise ValueError("Invalid date")

                # Construct datetime (date only, no time component)
                dt = datetime(year, month, day, tzinfo=UTC)

                # Check if in range
                if start_date.replace(tzinfo=UTC) <= dt <= end_date.replace(tzinfo=UTC):
                    # Determine confidence based on flags
                    confidence = (
                        "High"
                        if flags == 0x02
                        else f"Low (unexpected flags: 0x{flags:02x})"
                    )

                    summary = f"{dt.strftime('%Y-%m-%d')} [{confidence}]"

                    match = MatchDetail(
                        encoding="FTM Packed Date (4-byte)",
                        summary=summary,
                        details={
                            "type": "custom_packed",
                            "year": year,
                            "month": month,
                            "day": day,
                            "flags": flags,
                            "confidence": confidence,
                        },
                    )
                    hits.append(
                        SearchHit(
                            offset=pos,
                            length=4,
                            summary=summary,
                            matches=[match],
                        )
                    )
            except (struct.error, ValueError, OSError):
                # Invalid date, skip
                pass

        pos += alignment

    return hits


def search_pointers(
    reader: PagedReader,
    pointer_type: PointerType | None = None,
    base_mode: Literal["absolute", "relative"] = "absolute",
    base_addend: int = 0,
    min_target: int | None = None,
    max_target: int | None = None,
    allow_zero: bool = False,
    target_alignment: int | None = None,
    preview_length: int = 16,
    scan_step: int | None = None,
) -> list[SearchHit]:
    """Search for pointer values (offsets into the file).

    Args:
        reader: File to search
        pointer_type: Pointer field type (u16/u32/u64 LE/BE). Defaults to u32 LE.
        base_mode: "absolute" (ptr from file start) or "relative" (ptr from field location)
        base_addend: Optional offset added to target (for header skipping, etc.)
        min_target: Minimum target offset (None = no minimum)
        max_target: Maximum target offset (None = file size)
        allow_zero: Allow zero pointer values (default False)
        target_alignment: Required alignment for target (None = any, or 2/4/8)
        preview_length: Bytes to preview at target (0 = no preview)
        scan_step: Byte step for scanning (None = auto-detect from pointer size)

    Returns:
        List of SearchHit objects with multi-span hits (pointer + target_preview)
    """
    # Default to u32 LE if not specified
    if pointer_type is None:
        pointer_type = PointerType.u32_le()

    # Default scan step to pointer size
    if scan_step is None:
        scan_step = pointer_type.size

    hits: list[SearchHit] = []

    # Scan file for pointer fields
    size = reader.size
    ptr_size = pointer_type.size
    if size < ptr_size:
        return hits

    # Cap max_target to file size
    max_target = size if max_target is None else min(max_target, size)

    pos = 0
    seen_offsets: set[int] = set()  # De-dup by offset

    while pos <= size - ptr_size:
        # Skip if already seen
        if pos in seen_offsets:
            pos += scan_step
            continue

        data = reader.read(pos, ptr_size)
        if len(data) == ptr_size:
            try:
                # Decode pointer value
                ptr_value = int.from_bytes(data, byteorder=pointer_type.endian)

                # Skip zero if not allowed
                if ptr_value == 0 and not allow_zero:
                    pos += scan_step
                    continue

                # Compute base
                base = 0 if base_mode == "absolute" else pos

                # Compute target
                target = base + base_addend + ptr_value

                # Validate target is within file
                if not (0 <= target < size):
                    pos += scan_step
                    continue

                # Apply target constraints
                if min_target is not None and target < min_target:
                    pos += scan_step
                    continue
                if target >= max_target:
                    pos += scan_step
                    continue

                # Check alignment
                if target_alignment is not None and target % target_alignment != 0:
                    pos += scan_step
                    continue

                # Mark as seen
                seen_offsets.add(pos)

                # Compute preview span
                actual_preview_len = min(preview_length, size - target) if preview_length > 0 else 0

                # Determine confidence based on heuristics
                confidence = "High"
                if actual_preview_len < preview_length and preview_length > 0:
                    confidence = "Low"  # Preview capped at EOF
                elif target_alignment is not None and target % target_alignment == 0:
                    confidence = "High"  # Aligned as expected

                # Build summary
                base_desc = "file start" if base_mode == "absolute" else f"relative (+0x{pos:x})"

                if base_addend != 0:
                    base_desc += f" + {base_addend}"

                summary = f"→ 0x{target:x} ({base_desc})"
                if confidence == "Low":
                    summary += " [Low confidence]"

                # Create multi-span hit: pointer field + target preview
                spans = [
                    SearchSpan(offset=pos, length=ptr_size, role="pointer"),
                ]

                if actual_preview_len > 0:
                    spans.append(
                        SearchSpan(offset=target, length=actual_preview_len, role="target_preview")
                    )

                match = MatchDetail(
                    encoding=f"Pointer ({pointer_type.label})",
                    summary=summary,
                    details={
                        "pointer_type": pointer_type.label,
                        "ptr_value": ptr_value,
                        "target": target,
                        "base_mode": base_mode,
                        "base_addend": base_addend,
                        "preview_length": actual_preview_len,
                        "confidence": confidence,
                    },
                )

                hits.append(
                    SearchHit(
                        offset=pos,
                        length=ptr_size,
                        summary=summary,
                        matches=[match],
                        spans=spans,
                    )
                )
            except (struct.error, ValueError):
                # Invalid data, skip
                pass

        pos += scan_step

    return hits
