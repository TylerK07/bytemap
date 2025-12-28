# Repository Guidelines

## Project Structure & Module Organization
- src/hexmap/: app + libraries for the TUI.
  - app.py: Textual App and layout.
  - widgets/: HexView, ParsedTree, StatusBar, CommandPalette.
  - core/: io.py, types.py, schema.py, parse.py, diff.py.
- tests/: unit tests (core) + smoke test (app boot).
- fixtures/: sample binaries and schemas used in tests.

## Build, Test, and Development Commands
- Run tests: `pytest -q` — executes unit and smoke tests.
- Lint: `ruff check .` — static checks and import order.
- Format: `ruff format .` — apply code formatting.
- App (smoke run): `python -m hexmap.app` — starts the TUI if implemented.
- Optional: `PYTHONPATH=src pytest -q` if your editor needs explicit path.

## Coding Style & Naming Conventions
- Python 3.11+; 4‑space indent; UTF‑8; type hints required for public APIs.
- Naming: packages/modules `snake_case`, classes `CamelCase`, functions/vars `snake_case`, tests `test_*.py`.
- Imports: standard, third‑party, local (in that order). Prefer absolute imports from `hexmap`.
- Keep UI responsive: no blocking I/O in widgets; use reactive state and lazy rendering.

## Testing Guidelines
- Framework: `pytest` with fixtures under `fixtures/`.
- Location: tests mirror `src/hexmap/` structure; name files `test_*.py`.
- Coverage: prioritize core modules (`core/*.py`); aim for ~80%+ on core logic.
- Include: bounds checks, malformed input cases, and a TUI boot smoke test.

## Commit & Pull Request Guidelines
- Commits: concise, imperative. Prefer Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
- Branches: `feature/<short-topic>` or `fix/<issue-id>`.
- PRs must include: description of change, linked issues, testing notes, and screenshots/GIFs for UI changes.
- CI expectations: `ruff check` and `pytest` pass; no regressions in smoke test.

## Safety & Non‑Negotiables
- Never modify input files in place; write to a new file by default.
- All decoding is bounds‑checked and deterministic; no heuristic guessing.
- Maintain page‑based reading and lazy rendering for large files.
