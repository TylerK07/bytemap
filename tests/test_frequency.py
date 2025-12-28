from __future__ import annotations

from pathlib import Path

from hexmap.core.frequency import compute_frequency_map
from hexmap.core.io import PagedReader


def write_bytes(p: Path, data: bytes) -> Path:
    p.write_bytes(data)
    return p


def test_frequency_n1_behaves_like_diff(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.bin", b"abcd")
    b = write_bytes(tmp_path / "b.bin", b"abXd")
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb:
        counts, stats = compute_frequency_map(ra, [rb], chunk_size=2)
    assert len(counts) == 4
    assert counts[2] == 1 and counts[0] == 0
    assert int(stats["N"]) == 1


def test_frequency_n2_counts(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.bin", b"abcd")
    b1 = write_bytes(tmp_path / "b1.bin", b"abXd")
    b2 = write_bytes(tmp_path / "b2.bin", b"Ybcd")
    with PagedReader(str(a)) as ra, PagedReader(str(b1)) as r1, PagedReader(str(b2)) as r2:
        counts, stats = compute_frequency_map(ra, [r1, r2], chunk_size=2)
    assert counts[0] == 1 and counts[1] == 0 and counts[2] == 1 and counts[3] == 0
    assert int(stats["N"]) == 2


def test_frequency_tail_counts(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.bin", b"abcd")
    b = write_bytes(tmp_path / "b.bin", b"ab")
    with PagedReader(str(a)) as ra, PagedReader(str(b)) as rb:
        counts, stats = compute_frequency_map(ra, [rb], chunk_size=2)
    # Tail (2..3) differs since b is shorter
    assert counts[2] == 1 and counts[3] == 1


def test_frequency_chunk_boundary(tmp_path: Path) -> None:
    base = bytearray(range(32))
    m1 = bytearray(base)
    m2 = bytearray(base)
    m1[7] ^= 0xFF
    m2[8] ^= 0xFF
    a = write_bytes(tmp_path / "a.bin", bytes(base))
    b1 = write_bytes(tmp_path / "b1.bin", bytes(m1))
    b2 = write_bytes(tmp_path / "b2.bin", bytes(m2))
    with PagedReader(str(a)) as ra, PagedReader(str(b1)) as r1, PagedReader(str(b2)) as r2:
        counts, _ = compute_frequency_map(ra, [r1, r2], chunk_size=8)
    assert counts[7] == 1 and counts[8] == 1
