"""Execution profiles for tab-specific parsing behavior.

This module defines how different tabs parse YAML specs with the same grammar
but different execution parameters (limits, budgets, caching strategies).

All tabs use the same YAML grammar and ToolHost parsing engine. Profiles only
configure execution parameters, NOT parsing semantics.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionProfile:
    """Configuration for how a tab executes YAML parsing.

    Attributes:
        name: Profile identifier
        offset: Byte offset to start parsing from
        limit: Maximum number of bytes to parse (None = no limit)
        max_records: Maximum number of records to parse (None = no limit)
        parse_full_file: Whether to parse entire file or just viewport
        enable_coverage_analysis: Whether to run coverage analysis
        enable_span_generation: Whether to generate field spans
        cache_parse_results: Whether to cache parse results
    """

    name: str
    offset: int = 0
    limit: Optional[int] = None
    max_records: Optional[int] = None
    parse_full_file: bool = True
    enable_coverage_analysis: bool = True
    enable_span_generation: bool = True
    cache_parse_results: bool = False


# ============================================================================
# PROFILE DEFINITIONS
# ============================================================================

EXPLORE_PROFILE = ExecutionProfile(
    name="explore",
    max_records=1000,  # Fast partial runs for interactive exploration
    parse_full_file=False,  # Viewport-first updates
    enable_coverage_analysis=True,
    enable_span_generation=True,
    cache_parse_results=False,  # Always fresh parse for responsiveness
)

CHUNKING_PROFILE = ExecutionProfile(
    name="chunking",
    max_records=10000,  # Broader runs for chunk analysis
    parse_full_file=True,  # Need full file for chunk boundaries
    enable_coverage_analysis=True,  # Emphasize chunk/boundary detection
    enable_span_generation=True,
    cache_parse_results=True,  # Cache for stable overlays
)

WORKBENCH_PROFILE = ExecutionProfile(
    name="workbench",
    max_records=None,  # No limits - parse everything for versioned runs
    parse_full_file=True,
    enable_coverage_analysis=True,  # For scoring/diff support
    enable_span_generation=True,
    cache_parse_results=True,  # Versioned runs need stability
)


# ============================================================================
# PROFILE REGISTRY
# ============================================================================

PROFILES = {
    "explore": EXPLORE_PROFILE,
    "chunking": CHUNKING_PROFILE,
    "workbench": WORKBENCH_PROFILE,
}


def get_profile(name: str) -> ExecutionProfile:
    """Get execution profile by name.

    Args:
        name: Profile name (explore, chunking, workbench)

    Returns:
        ExecutionProfile instance

    Raises:
        KeyError: If profile name not found
    """
    return PROFILES[name]
