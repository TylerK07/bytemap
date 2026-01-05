# Tool Host Quick Start

## What We Built

A **deterministic, pure-function API layer** for binary analysis that's safe for LLM/agent usage.

## Current Status: Phase 1 Complete ✅

### Available Tool: `lint_grammar`

```python
from hexmap.core.tool_host import ToolHost, LintGrammarInput

# Validate YAML grammar
result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_str))

if result.success:
    grammar = result.grammar  # Use this for parsing
    print(f"✓ Valid: {len(grammar.types)} types defined")
    if result.warnings:
        print(f"⚠ {result.warnings[0]}")
else:
    print(f"✗ Error: {result.errors[0]}")
```

## Key Properties

| Property | Description | Benefit |
|----------|-------------|---------|
| **Pure** | No side effects | Predictable behavior |
| **Deterministic** | Same input → same output | Safe for caching, testing |
| **Typed** | Explicit schemas | Clear API contracts |
| **Immutable** | Frozen dataclasses | Thread-safe, cacheable |
| **Safe** | No file mutation | LLM/agent ready |

## Files

```
src/hexmap/core/tool_host.py          # Core implementation
tests/test_tool_host.py                # 19 comprehensive tests
demo_tool_host.py                      # Usage examples
TOOL_HOST_IMPLEMENTATION.md            # Full documentation
TOOL_HOST_QUICKSTART.md                # This file
```

## Test Results

```
✅ 19 new tests (Tool Host)
✅ 207 existing tests (still pass)
✅ 0 regressions
```

## Demo

```bash
python demo_tool_host.py
```

## Next Tools to Build

1. **`parse_binary`** - Parse binary files with grammar
2. **`generate_spans`** - Generate viewport spans
3. **`analyze_coverage`** - Report parse coverage (NEW)
4. **`decode_field`** - Decode field values
5. **`query_records`** - Filter/search records (NEW)

## Pattern to Follow

Every tool follows this structure:

```python
# 1. Input schema (frozen dataclass)
@dataclass(frozen=True)
class ToolInput:
    param1: str
    param2: int = 0

# 2. Output schema (frozen dataclass)
@dataclass(frozen=True)
class ToolOutput:
    success: bool
    data: Any
    errors: tuple[str, ...]

# 3. Tool implementation (static method)
class ToolHost:
    @staticmethod
    def tool_name(input: ToolInput) -> ToolOutput:
        """Tool description."""
        try:
            # Do work (deterministic, pure)
            result = process(input)
            return ToolOutput(success=True, data=result, errors=())
        except Exception as e:
            return ToolOutput(success=False, data=None, errors=(str(e),))
```

## Why This Matters

### For UI Development
- Widgets call tools, don't implement parsing
- Clear separation of concerns
- Easy to test widget logic separately

### For Testing
- Test tools without UI context
- Fast, deterministic tests
- Easy to mock tool responses

### For LLM/Agents
- **Safe to call** - No file system damage possible
- **Deterministic** - Predictable outcomes
- **Explicit** - Clear input/output contracts
- **Budgetable** - Can add resource limits

## Example: Agent Usage

```python
# Agent can safely call tools
def agent_validate_grammar(yaml_text: str) -> str:
    """Agent function to validate binary grammar."""
    result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_text))

    if result.success:
        return f"Grammar valid. Types: {list(result.grammar.types.keys())}"
    else:
        return f"Grammar invalid: {result.errors[0]}"
```

Agent can:
- ✅ Validate grammars
- ✅ Get structured feedback
- ✅ Iterate on fixes
- ❌ Cannot damage files
- ❌ Cannot corrupt state
- ❌ Cannot cause unpredictable behavior

## Commands

```bash
# Run Tool Host tests
pytest tests/test_tool_host.py -v

# Run all parsing tests
pytest tests/test_chunking.py tests/test_tool_host.py -v

# Run demo
python demo_tool_host.py

# Check implementation
cat src/hexmap/core/tool_host.py
```

## What Changed in UI

### Before
```python
try:
    grammar = parse_yaml_grammar(yaml_text)
    # use grammar
except Exception as e:
    show_error(str(e))
```

### After
```python
result = ToolHost.lint_grammar(LintGrammarInput(yaml_text=yaml_text))

if result.success:
    if result.warnings:
        show_warning(result.warnings[0])  # NEW: warnings
    # use result.grammar
else:
    show_error(result.errors[0])
```

**Improvements:**
- Structured error handling
- Warning detection (unused types)
- Better separation of concerns
- Widget doesn't import parsing internals

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│              UI Layer (Widgets)              │
│  - Display results                           │
│  - Handle user input                         │
│  - Call tools                                │
└─────────────────┬───────────────────────────┘
                  │ Calls (frozen inputs)
                  ▼
┌─────────────────────────────────────────────┐
│              Tool Host Layer                 │
│  ┌──────────────────────────────────────┐   │
│  │ lint_grammar(input) -> output       │   │
│  │ parse_binary(input) -> output       │◄──┤ Pure functions
│  │ generate_spans(input) -> output     │   │ Deterministic
│  │ analyze_coverage(input) -> output   │   │ Immutable outputs
│  │ decode_field(input) -> output       │   │ No side effects
│  │ query_records(input) -> output      │   │
│  └──────────────────────────────────────┘   │
└─────────────────┬───────────────────────────┘
                  │ Returns (frozen outputs)
                  ▼
┌─────────────────────────────────────────────┐
│           Core Parsing Layer                 │
│  - Grammar parsing                           │
│  - Binary parsing                            │
│  - Span generation                           │
│  - Field decoding                            │
└─────────────────────────────────────────────┘
```

## Benefits Summary

| Stakeholder | Benefit |
|-------------|---------|
| **UI Developers** | Simpler widget code, clear APIs |
| **Test Writers** | Fast tests, no UI context needed |
| **LLM/Agents** | Safe, deterministic tools to call |
| **Maintainers** | Clear boundaries, easy to refactor |
| **Users** | Better error messages, warnings |

## Current Limitations

1. Only grammar validation available (Phase 1)
2. Binary parsing still uses old API (Phase 2 needed)
3. No coverage analysis yet (Phase 4 planned)
4. No record querying yet (Phase 6 planned)

## Roadmap

- ✅ **Phase 1:** Grammar validation (`lint_grammar`)
- ⏳ **Phase 2:** Binary parsing (`parse_binary`)
- ⏳ **Phase 3:** Span generation (`generate_spans`)
- ⏳ **Phase 4:** Coverage analysis (`analyze_coverage`) - NEW
- ⏳ **Phase 5:** Field decoding (`decode_field`)
- ⏳ **Phase 6:** Record querying (`query_records`) - NEW

## Questions?

See **TOOL_HOST_IMPLEMENTATION.md** for:
- Detailed design rationale
- Complete API reference
- Implementation notes
- Next steps

## Success ✅

**The Tool Host foundation is built and working.**

All tests pass. UI integration complete. Pattern established.

Ready to build remaining tools following the same design.
