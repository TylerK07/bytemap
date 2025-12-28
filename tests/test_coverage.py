from __future__ import annotations

from hexmap.core.coverage import compute_coverage
from hexmap.core.parse import ParsedField


def _pf(name: str, off: int, ln: int) -> ParsedField:
    return ParsedField(name, off, ln, "u8", 0, None)


def test_coverage_basic_gaps() -> None:
    leaves = [_pf("a", 0, 4), _pf("b", 10, 2)]
    cov, unmapped = compute_coverage(leaves, 20)
    assert cov[0][:2] == (0, 4)
    assert cov[1][:2] == (10, 2)
    # gaps: [4,10) and [12,20)
    assert unmapped[0] == (4, 6)
    assert unmapped[1] == (12, 8)


def test_coverage_all_covered() -> None:
    leaves = [_pf("a", 0, 10)]
    cov, unmapped = compute_coverage(leaves, 10)
    assert unmapped == []


def test_coverage_none_covered() -> None:
    cov, unmapped = compute_coverage([], 16)
    assert unmapped == [(0, 16)]


def test_coverage_adjacent_fields() -> None:
    leaves = [_pf("a", 0, 4), _pf("b", 4, 4)]
    cov, unmapped = compute_coverage(leaves, 10)
    # single gap at [8,10)
    assert unmapped == [(8, 2)]

