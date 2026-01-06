# Agent Workbench Usage Guide

## Quick Start

The Agent Workbench provides an LLM-driven interface for iterating on binary format specifications.

### First Time Setup

1. **Open the application** with a binary file:
   ```bash
   python -m hexmap your_file.bin
   ```

2. **The app will load with a default schema** in the Explore tab

3. **Switch to the Workbench tab** by pressing `4`

4. **The workbench will automatically initialize** with the current schema

### What to Expect

When you first open the Workbench tab, you should see:

- **Column 1: Versions & Chat**
  - **Versions tab**: List of spec versions (starting with "Current Schema")
  - **Chat tab**: LLM chat interface (demo mode)

- **Column 2: Patches & Runs**
  - Shows patch operations and parse runs for selected version

- **Column 3: Evidence**
  - Displays parse errors, anomalies, and coverage information

### Initial Version

The workbench automatically creates an **initial version** from your current schema:

- **Label**: "Current Schema" (or "Initial" if loaded from file)
- **Role**: `[baseline]` - the reference version for comparisons
- **Status**: ✓ or ✗ depending on parse results
- **Score**: 0-100 based on coverage and error count

If you see no versions or an error message, try:

1. **Switch to the Explore tab** (press `1`)
2. **Verify the schema editor has content** (you should see YAML text)
3. **Switch back to Workbench** (press `4`)

## Troubleshooting

### "Waiting for schema initialization..."

**Cause**: You opened the Workbench tab before the schema was loaded.

**Solution**:
1. Switch to Explore tab (`1`)
2. Wait for schema to load
3. Return to Workbench tab (`4`)

### "No schema available"

**Cause**: No schema loaded in the schema editor.

**Solution**:
1. Switch to Explore tab (`1`)
2. Create or load a schema (the app provides a default schema on startup)
3. Return to Workbench tab (`4`)

### "Manager not initialized"

**Cause**: Workbench manager failed to initialize.

**Solution**:
1. Check that you opened the app with a valid binary file
2. Restart the application
3. If problem persists, check the console for error messages

### "Error: Spec failed lint: [message]"

**Cause**: The current schema has YAML syntax errors or validation issues.

**Solution**:
1. Switch to Explore tab (`1`)
2. Fix the schema errors shown in the output panel
3. Return to Workbench tab (`4`)

## Workflow

### 1. Select a Version

- Click on a version in the **Versions tab** (Column 1)
- The version inspector shows: status, lint results, coverage, score
- Column 2 populates with patch operations and runs
- Column 3 shows evidence (errors, anomalies)

### 2. Review Parse Results

- Select a **run** in Column 2 to see parse results
- Column 3 (Evidence) displays:
  - Parse errors with byte offsets
  - Anomalies (warnings about suspicious data)
  - Coverage information
- Hex view automatically highlights problem areas

### 3. Chat with Assistant (Demo Mode)

- Switch to **Chat tab** in Column 1
- Type a message and press Enter or click "Send"
- Click "Suggest Patch" for automated suggestions
- **Note**: Currently in demo mode - explains what real LLM would do

### 4. Create Branches

- Select a version in Column 1
- Click **"Branch"** button to create a test version
- The new version applies a simple patch (adds a comment field)
- Review the new version's parse results

### 5. Promote Baseline

- Select a version with better results
- Click **"Promote"** button to make it the baseline
- Other versions now show coverage delta vs this baseline

### 6. Checkout Working Version

- Select a version to work with
- Click **"Checkout"** button
- This marks it as the current working version

## Understanding Version Roles

- **`[baseline]`**: Reference version for comparisons (promoted with "Promote")
- **`[candidate]`**: Branch version being tested
- **`[checked_out]`**: Current working version (marked with ⬤)

## Understanding Status Indicators

- **✓**: Parse succeeded, no critical errors
- **✗lint**: Schema has YAML/validation errors
- **✗parse**: Parse succeeded but has runtime errors or high-severity anomalies
- **?**: Unknown status (no run data)

## Keyboard Shortcuts

- **`1`**: Switch to Explore tab
- **`2`**: Switch to Diff tab
- **`3`**: Switch to Chunking tab
- **`4`**: Switch to Workbench tab
- **`q`**: Quit application
- **`?`**: Show help

## Next Steps

Once you're comfortable with the workbench:

1. **Review PR8_CHAT_INTERFACE.md** for LLM integration guide
2. **Implement real LLM** to replace demo mode (see "Future Work" section)
3. **Add patch review UI** for applying LLM-suggested patches
4. **Implement automatic testing** (apply patch → run → score)

## Tips

- **Start with the default schema**: The app loads a working example on startup
- **Review evidence carefully**: Column 3 shows exactly where parse issues occur
- **Use Branch liberally**: Test changes without losing your baseline
- **Promote improvements**: Mark better versions as baseline to track progress
- **Chat tab is for guidance**: In demo mode, it explains the workflow

## Common Patterns

### Testing Schema Changes

1. Start with baseline version
2. Edit schema in Explore tab (triggers auto-parse)
3. Check Workbench for updated results
4. If improved, promote to baseline

### Investigating Parse Errors

1. Select version with errors
2. Select run in Column 2
3. Review evidence in Column 3
4. Hex view highlights problem bytes
5. Use chat to ask for suggestions

### Comparing Versions

1. Promote best version to baseline
2. Create branches to test alternatives
3. Compare coverage deltas (Δ: +X%)
4. Promote winner as new baseline

## Limitations (Demo Mode)

- **No real LLM integration**: Chat provides helpful explanations but doesn't generate actual patches
- **Simple branch patches**: Branch button adds generic comment field, not targeted fixes
- **No patch application from chat**: Suggested patches are text-only
- **No history persistence**: Chat history cleared on tab switch

See **PR8_CHAT_INTERFACE.md** for implementation roadmap to add these features.

## Support

If you encounter issues:

1. Check this guide for troubleshooting steps
2. Review error messages in version inspector
3. Check console output for detailed errors
4. Report issues at: https://github.com/anthropics/claude-code/issues

## Architecture

For developers interested in the implementation:

- **PR#1-2**: Tab shell and state model
- **PR#3**: SpecStore integration and version management
- **PR#4**: Patch operations UI
- **PR#5**: Run artifacts and scoring
- **PR#6**: Evidence display with hex view integration
- **PR#7**: Draft/Promote/Branch functionality
- **PR#8**: Chat interface (current - demo mode)

See individual PR documentation for detailed architecture notes.
