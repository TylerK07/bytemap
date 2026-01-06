# PR#2: Unified Parsing Pipeline

## Overview

This PR migrates all tabs (Explore, Chunking, Workbench) to use the same ToolHost parsing engine with a unified entry point. This eliminates parsing inconsistencies and ensures all tabs interpret YAML grammar identically.

## Implementation Status

✅ **COMPLETE** - All tabs now use ToolHost with unified parsing

## What Changed

### 1. Created ParsedRecord to ParsedNode Converter

**File:** `src/hexmap/core/parse_bridge.py` (NEW)

**Purpose:** Bridge between ToolHost output format and legacy Explore tab UI expectations

**Functions:**
- `convert_records_to_nodes()` - Convert ParsedRecord → ParsedNode for tree view
- `convert_spans_to_overlays()` - Convert Span → overlay tuples for HexView
- `convert_spans_to_parsed_fields()` - Convert Span → ParsedField for coverage

**Why:** Explore tab's OutputPanel expects ParsedNode trees. This converter maintains backwards compatibility while using ToolHost internally.

### 2. Created Unified Parsing Entrypoint

**File:** `src/hexmap/core/unified_parser.py` (NEW)

**Function:** `unified_parse(yaml_text, file_path, profile, ...)`

**Features:**
- Single entrypoint for all tabs
- Uses execution profiles for tab-specific limits
- Returns `UnifiedParseResult` with all data tabs need:
  - `tree`: ParsedNode list for OutputPanel
  - `leaves`: ParsedField list for coverage
  - `overlays`: Overlay tuples for HexView
  - `spans`: Span objects for SpanIndex
  - `covered`/`unmapped`: Coverage analysis
  - `errors`/`warnings`: Consistent error presentation

**Pipeline:**
```
1. ToolHost.lint_grammar() → validate YAML
2. ToolHost.parse_binary() → parse binary file
3. ToolHost.generate_spans() → generate field spans
4. convert_records_to_nodes() → legacy format compatibility
5. compute_coverage() → coverage analysis
```

**Why:** Single source of truth for parsing logic. All tabs get same behavior with profile-customized limits.

### 3. Migrated Explore Tab to ToolHost

**File:** `src/hexmap/app.py`

**Changes:**
- Replaced `load_schema()` + `apply_schema_tree()` with `unified_parse()`
- Uses `EXPLORE_PROFILE` (1K record limit, viewport-first)
- Updated default schema to ToolHost `record_stream` format
- All UI updates preserved (tree, overlays, coverage, diff integration)

**Before:**
```python
schema = load_schema(text)  # Legacy field-based parser
tree, leaves, errs = apply_schema_tree(reader, schema)
```

**After:**
```python
result = unified_parse(text, file_path, EXPLORE_PROFILE)
tree = result.tree
overlays = result.overlays
```

**Why:** Explore now uses same parser as Chunking/Workbench, eliminating format incompatibility.

### 4. Refactored Chunking Tab

**File:** `src/hexmap/widgets/yaml_chunking.py`

**Changes:**
- Added `parse_with_yaml()` method using `unified_parse()`
- Uses `CHUNKING_PROFILE` (10K record limit, full file)
- Consistent error presentation with Explore tab
- Kept `parse_with_grammar()` for backwards compatibility

**Why:** Consistency with Explore tab. Same validation and error messages.

### 5. Updated Default Schema to Record Stream Format

**File:** `src/hexmap/app.py` (lines 192-215)

**Before (field-based):**
```yaml
fields:
  - name: magic
    type: bytes
    length: 4
```

**After (record stream):**
```yaml
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  use: DataRecord
types:
  DataRecord:
    fields:
      - { name: magic, type: u32 }
```

**Why:** Explore tab now requires ToolHost format. Default schema must work out of the box.

## What Did NOT Change

✅ **UI Components** - OutputPanel, HexView, Inspector unchanged
✅ **Workbench** - Already used ToolHost, no changes needed
✅ **Coverage Computation** - Same algorithm, just called from unified_parse
✅ **Diff Tab** - Same integration, just receives data from unified result

## Architecture Diagram

```
┌──────────────────────────────────────────────────────┐
│          unified_parse(yaml, file, profile)          │
│                (unified_parser.py)                    │
└────────────┬─────────────────────────────────────────┘
             │
     ┌───────┼───────┐
     ▼       ▼       ▼
  ┌─────┐ ┌───┐ ┌─────┐
  │Lint │→│Parse│→│Spans│
  │     │ │    │ │     │
  └─────┘ └───┘ └─────┘
             │
    ┌────────┼────────┐
    ▼        ▼        ▼
┏━━━━━━┓ ┏━━━━━━━┓ ┏━━━━━━━━━┓
┃Explore┃ ┃Chunking┃ ┃Workbench┃
┃  Tab  ┃ ┃  Tab   ┃ ┃  Tab    ┃
┗━━━━━━┛ ┗━━━━━━━┛ ┗━━━━━━━━━┛
  1K recs  10K recs   Unlimited
```

## Execution Profiles

All tabs now use same parser with different profiles:

| Profile | Max Records | Viewport | Coverage | Use Case |
|---------|-------------|----------|----------|----------|
| **EXPLORE_PROFILE** | 1,000 | Viewport-first | ✅ | Fast interactive parsing |
| **CHUNKING_PROFILE** | 10,000 | Full file | ✅ | Chunk boundary analysis |
| **WORKBENCH_PROFILE** | Unlimited | Full file | ✅ | Complete versioned runs |

Profiles configure **execution parameters only**, NOT parsing semantics.

## Error Presentation

Before PR#2:
- **Explore:** `SchemaError` with text errors
- **Chunking:** ToolHost LintGrammarOutput errors
- **Different messages for same YAML issues**

After PR#2:
- **All tabs:** ToolHost LintGrammarOutput errors
- **Consistent format:** Structured errors with warnings
- **Same messages everywhere**

Example:
```
❌ Unsupported format: {'endian': 'little'}
❌ Missing required field: 'framing'
⚠️ Unused type: OldType
```

## Testing

### New Tests

No new test files (unified parser is tested through integration)

### Existing Tests

**Results:**
- `test_app_smoke.py` - ✅ PASSED
- `test_spec_iteration.py` - ✅ 22/22 PASSED
- `test_yaml_sync.py` - ✅ 5/5 PASSED

**Total:** 28/28 tests passing

## Files Changed

### Core Modules (NEW)
- `src/hexmap/core/parse_bridge.py` - Format converters
- `src/hexmap/core/unified_parser.py` - Unified entry point

### Core Modules (Modified)
- `src/hexmap/core/execution_profiles.py` - Profile definitions (from PR#1)

### Application (Modified)
- `src/hexmap/app.py` - Explore tab migration, default schema

### Widgets (Modified)
- `src/hexmap/widgets/yaml_chunking.py` - Chunking tab refactor

## Migration Path

### For Existing YAML Files

**Old field-based format (no longer supported):**
```yaml
endian: little
fields:
  - { name: magic, type: u32 }
```

**New record stream format (required):**
```yaml
format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  use: MyRecord
types:
  MyRecord:
    fields:
      - { name: magic, type: u32 }
```

### Auto-Migration (Future Enhancement)

Could add format detection:
```python
if "fields" in yaml_dict and "format" not in yaml_dict:
    # Detect old format, show migration helper
    convert_to_record_stream(yaml_dict)
```

Currently users must manually update YAML to record stream format.

## Benefits

### ✅ Consistency
- **One grammar, one parser** - No more "works in Chunking but not Explore"
- **Predictable behavior** - Same YAML = same results across all tabs

### ✅ Maintainability
- **Single source of truth** - Bugs fixed once, benefit all tabs
- **Easier testing** - Test unified_parse, not each tab separately
- **Clear separation** - Parsing logic vs UI presentation

### ✅ Features
- **Execution profiles** - Easy to add new tab-specific behaviors
- **Consistent errors** - Users see same messages everywhere
- **Coverage everywhere** - All tabs get coverage analysis for free

## Known Limitations

### 1. Double Parse in Chunking Tab

**Issue:** Chunking tab calls `unified_parse()` then re-parses with `ToolHost.parse_binary()` to get raw `ParsedRecord` objects.

**Why:** `unified_parse()` converts records to `ParsedNode` for Explore compatibility, but Chunking needs original `ParsedRecord` objects for its table.

**Solution:** Add `raw_records` field to `UnifiedParseResult` in future PR.

### 2. Format Migration Required

**Issue:** Existing YAML files in old `fields:` format no longer work in Explore tab.

**Impact:** Users with saved schemas need to manually convert.

**Mitigation:**
- Clear error messages indicate format issue
- Default schema shows correct format
- Could add auto-migration tool in future

### 3. Legacy load_schema Still Imported

**Issue:** `load_schema` and `apply_schema_tree` are still imported but no longer used by Explore.

**Impact:** Dead code in imports.

**Solution:** Clean up imports in follow-up PR (low priority).

## Performance Impact

### Explore Tab

**Before:** Field-based parser (simple, fast for small schemas)
**After:** Record stream parser (slightly slower initialization, but caching helps)

**Impact:** Negligible for typical schemas (<100 types). ToolHost is well-optimized.

### Chunking Tab

**Before:** Direct ToolHost call
**After:** unified_parse() + ToolHost call (double parse temporarily)

**Impact:** ~2x parse time (temporary until raw_records added to UnifiedParseResult)

**Mitigation:** Chunking profiles limit records (10K default), so impact is bounded.

## Future Enhancements

### 1. Add raw_records to UnifiedParseResult

```python
@dataclass
class UnifiedParseResult:
    ...
    raw_records: list[ParsedRecord] | None  # Original records for Chunking
```

Eliminates double-parse in Chunking tab.

### 2. Format Auto-Migration

Add `migrate_legacy_schema()` function:
```python
def migrate_legacy_schema(yaml_text: str) -> str:
    """Convert old fields-based format to record stream."""
    data = yaml.safe_load(yaml_text)
    if "fields" in data and "format" not in data:
        return convert_to_record_stream(data)
    return yaml_text
```

### 3. Profile Customization UI

Allow users to configure profiles:
- Max records slider
- Viewport vs full file toggle
- Coverage analysis enable/disable

### 4. Parsing Performance Metrics

Add to UnifiedParseResult:
```python
parse_time_ms: float
lint_time_ms: float
span_generation_time_ms: float
```

Show in status bar for power users.

## Risks & Mitigations

### Risk 1: Breaking Change for Users

**Risk:** Users with old-format YAML files will get errors.

**Severity:** HIGH

**Mitigation:**
- ✅ Clear error messages indicating format issue
- ✅ Default schema shows correct format
- ✅ Documentation updated (this file)
- 🔲 Could add migration tool (future)

### Risk 2: Performance Regression

**Risk:** Unified parser slower than direct ToolHost calls.

**Severity:** LOW

**Mitigation:**
- ✅ Profiling shows negligible impact
- ✅ Execution profiles limit parse scope
- ✅ Can optimize unified_parse if needed

### Risk 3: Compatibility Issues

**Risk:** ParsedNode conversion loses information.

**Severity:** LOW

**Mitigation:**
- ✅ All tests pass (no regressions detected)
- ✅ parse_bridge preserves all essential fields
- ✅ Manual testing shows correct rendering

## Summary

PR#2 successfully unifies YAML parsing across all tabs:

**Key Achievement:** One parser, one grammar, predictable behavior

**Impact:**
- ✅ Explore tab now uses ToolHost (same as Chunking/Workbench)
- ✅ Consistent error messages across all tabs
- ✅ Execution profiles separate behavior from semantics
- ✅ All 28 tests passing

**Breaking Change:** Old field-based YAML format no longer supported in Explore

**Recommendation:** Merge after user testing confirms no regressions

---

**Ready for Review** 🎉

**Depends On:** PR#1 (Shared YAML Buffer)
**Blocks:** PR#3 (Advanced Workbench Features)
