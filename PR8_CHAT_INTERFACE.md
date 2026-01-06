# PR#8: Chat Interface for LLM-driven Patch Proposals

**Status**: ✅ Complete (Demo Mode)
**Branch**: `main`
**Dependencies**: PR#1-7 (Tab shell, state model, SpecStore, patch ops, runs, evidence, draft/promote/branch)

## Overview

PR#8 completes the Agent Workbench by adding a **chat interface** for natural language interaction with an AI assistant. This enables LLM-driven spec iteration where the assistant can:

- Analyze parse errors and anomalies
- Propose targeted patch fixes
- Answer questions about schema improvements
- Guide users through iterative refinement

**Current Implementation**: Demo mode with placeholder responses. Real LLM integration is deferred for production deployment.

## Architecture

### Component Structure

```
Column 1: Versions & Chat
├─ TabbedContent (id: versions-chat-tabs)
│  ├─ TabPane: "Versions" (existing from PR#3)
│  │  └─ ScrollableContainer
│  │     └─ OptionList (version list)
│  │     └─ Container (inspector with buttons)
│  └─ TabPane: "Chat" (NEW in PR#8)
│     └─ Vertical (id: chat-container)
│        ├─ ScrollableContainer (id: chat-log-scroll)
│        │  └─ Static (id: chat-log)
│        └─ Vertical (id: chat-input-area)
│           ├─ Input (id: chat-input)
│           └─ Horizontal (id: chat-buttons)
│              ├─ Button: "Send" (id: btn-chat-send)
│              └─ Button: "Suggest Patch" (id: btn-suggest-patch)
```

### Data Model

**Chat Message History**:
```python
self._chat_messages: list[tuple[str, str]] = []
# Format: [(role, content), ...]
# Roles: "user", "assistant", "system"
```

**Context Preparation** (for LLM):
```python
{
    "schema": str,                    # Current spec YAML text
    "file_size": int,                 # Binary file size
    "coverage_percentage": float,     # Parse coverage %
    "record_count": int,              # Number of parsed records
    "error_count": int,               # Parse error count
    "errors": list[str],              # First 5 errors
    "anomaly_count": int,             # Anomaly count
    "anomalies": list[dict],          # First 5 anomalies
}
```

## User Workflows

### 1. Chat with Assistant

**User Action**: Type question, press Enter or click "Send"

**Flow**:
1. User types message in input field
2. Press Enter or click "Send"
3. Message added to chat history with role="user"
4. Assistant generates response (demo mode)
5. Response added to history with role="assistant"
6. Chat log updated with full conversation

**Example Messages**:
- "Suggest a patch to fix errors"
- "Why is coverage low?"
- "How can I improve the schema?"

### 2. Suggest Patch

**User Action**: Click "Suggest Patch" button

**Flow**:
1. System checks if version is selected
2. Retrieves current version and run artifact
3. Builds context with schema, errors, anomalies
4. Generates patch suggestion (demo mode)
5. Displays suggestion in chat log

**Context Prepared**:
- Current spec YAML text
- File size and coverage stats
- First 5 parse errors
- First 5 anomalies (type, severity, message, offset)

## Implementation Details

### Chat Handlers

**`on_input_submitted()`**: Handles Enter key in chat input
```python
def on_input_submitted(self, event: Input.Submitted) -> None:
    if event.input.id == "chat-input":
        self._handle_chat_send()
```

**`_handle_chat_send()`**: Processes user messages
```python
def _handle_chat_send(self) -> None:
    # Extract user message
    user_message = self._chat_input.value.strip()
    if not user_message:
        return

    # Add to history
    self._chat_messages.append(("user", user_message))

    # Generate response (demo mode)
    assistant_response = self._generate_demo_response(user_message)
    self._chat_messages.append(("assistant", assistant_response))

    # Update display
    self._update_chat_log()
```

**`_handle_suggest_patch()`**: Generates patch suggestions
```python
def _handle_suggest_patch(self) -> None:
    # Check preconditions
    if self.manager is None or self.state.selected_version_id is None:
        # Show error message
        return

    # Get version and run data
    version_id = self.state.selected_version_id
    metadata = self.manager.get_version_metadata(version_id)
    run = metadata.run_artifact

    # Build context
    context = self._build_patch_context(version_id, run)

    # Generate suggestion (demo mode)
    suggestion = self._generate_demo_patch_suggestion(context)
    self._chat_messages.append(("assistant", suggestion))

    # Update display
    self._update_chat_log()
```

### Context Preparation

**`_build_patch_context()`**: Prepares structured context for LLM
```python
def _build_patch_context(self, version_id: str, run: RunArtifact) -> dict:
    version = self.manager.get_version(version_id)

    context = {
        "schema": version.spec_text,
        "file_size": run.file_size,
        "coverage_percentage": run.stats.coverage_percentage,
        "record_count": run.stats.record_count,
        "error_count": run.stats.error_count,
        "errors": run.parse_result.errors[:5],  # First 5
        "anomaly_count": run.stats.anomaly_count,
        "anomalies": [
            {
                "type": a.type,
                "severity": a.severity,
                "message": a.message,
                "offset": a.record_offset
            }
            for a in run.anomalies[:5]  # First 5
        ],
    }

    return context
```

### Demo Mode Responses

**`_generate_demo_response()`**: Placeholder for general chat
```python
def _generate_demo_response(self, user_message: str) -> str:
    message_lower = user_message.lower()

    if "patch" in message_lower or "fix" in message_lower:
        return (
            "I can suggest patches to improve your schema! "
            "Click 'Suggest Patch' to get a specific recommendation..."
        )
    elif "help" in message_lower:
        return (
            "I can help you iterate on binary format specifications!\n\n"
            "Try:\n- 'Suggest a patch to fix errors'\n..."
        )
    else:
        return (
            f"You said: '{user_message}'\n\n"
            "This is demo mode. In production, an LLM would analyze..."
        )
```

**`_generate_demo_patch_suggestion()`**: Placeholder for patch suggestions
```python
def _generate_demo_patch_suggestion(self, context: dict) -> str:
    coverage = context.get("coverage_percentage", 0)
    error_count = context.get("error_count", 0)
    anomaly_count = context.get("anomaly_count", 0)

    response = "Based on the current version:\n\n"
    response += f"- Coverage: {coverage:.1f}%\n"
    response += f"- Errors: {error_count}\n"
    response += f"- Anomalies: {anomaly_count}\n\n"

    if error_count > 0:
        errors = context.get("errors", [])
        if errors:
            response += f"First error: {errors[0][:80]}...\n\n"

    response += "Demo mode suggestion:\n"
    response += "In production, an LLM would:\n"
    response += "1. Analyze parse errors and anomalies\n"
    response += "2. Propose specific field type changes\n"
    response += "3. Suggest length adjustments\n"
    response += "4. Recommend registry additions\n\n"

    response += "For now, try using the 'Branch' button to create test versions manually.\n\n"
    response += "To integrate real LLM: See PR8_CHAT_INTERFACE.md"

    return response
```

### Display Update

**`_update_chat_log()`**: Renders conversation history
```python
def _update_chat_log(self) -> None:
    lines = []
    for role, content in self._chat_messages:
        if role == "user":
            lines.append(f"You: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
        elif role == "system":
            lines.append(f"[System] {content}")
        lines.append("")  # Blank line between messages

    if not lines:
        lines = [
            "Chat: Ask the assistant to suggest spec improvements.",
            "",
            'Try: "Suggest a patch to fix the parse errors"'
        ]

    self._chat_log.update("\n".join(lines))
```

## CSS Styling

**Added to `src/hexmap/ui/theme.tcss`**:

```css
/* ============================================================================
   PR#8: Chat Interface (Column 1)
   ============================================================================ */

#versions-chat-tabs {
  height: 1fr;
}

#chat-container {
  layout: vertical;
  height: 1fr;
}

#chat-log-scroll {
  height: 1fr;
  overflow: auto;
}

#chat-log {
  padding: 1;
  color: $text-muted;
}

#chat-input-area {
  height: auto;
  padding: 1;
  border-top: solid $panel-lighten-1;
}

#chat-input {
  margin-bottom: 1;
}

#chat-buttons {
  height: auto;
}

#chat-buttons Button {
  margin-right: 1;
}
```

## State Integration

### Selection Cascade

Chat interface respects the existing selection cascade:
1. User selects version in Column 1
2. `state.selected_version_id` updates
3. "Suggest Patch" uses selected version for context

### Manager Integration

Chat handlers use `WorkbenchManager` APIs:
- `get_version(version_id)` - fetch version for schema text
- `get_version_metadata(version_id)` - fetch metadata with run artifact
- `get_version_display_info(version_id)` - fetch display info

No new manager methods required; chat is purely UI layer.

## Testing

### Manual Testing

**Chat Send Flow**:
1. Select a version with errors
2. Click "Chat" tab
3. Type "help" → press Enter
4. Verify demo response appears
5. Type "suggest a patch" → press Enter
6. Verify demo response appears

**Suggest Patch Flow**:
1. Select version with errors
2. Click "Chat" tab
3. Click "Suggest Patch" button
4. Verify:
   - Coverage stats displayed
   - First error shown
   - Demo mode explanation provided

**Error Handling**:
1. Click "Suggest Patch" with no version selected
2. Verify system message: "Please select a version first..."
3. Select version with no run data
4. Click "Suggest Patch"
5. Verify: "No run data available..."

### Automated Testing

No automated tests included in PR#8. Future work could add:
- Unit tests for context preparation
- Mock tests for demo response generation
- Integration tests for chat message flow

## Future Work: Real LLM Integration

### Design Considerations

**LLM Provider Options**:
1. **Anthropic Claude** (recommended)
   - Strong reasoning and code generation
   - Structured output support
   - Good at analyzing technical errors
2. **OpenAI GPT-4**
   - Alternative option
   - Similar capabilities
3. **Local Models** (Ollama, etc.)
   - Privacy-focused deployments
   - Lower latency but less capable

### Integration Points

**Replace `_generate_demo_response()` with**:
```python
def _generate_llm_response(self, user_message: str) -> str:
    # Build prompt with conversation history
    prompt = self._build_chat_prompt(user_message)

    # Call LLM API
    response = await llm_client.complete(prompt)

    return response
```

**Replace `_generate_demo_patch_suggestion()` with**:
```python
def _generate_llm_patch_suggestion(self, context: dict) -> str:
    # Build structured prompt
    prompt = self._build_patch_prompt(context)

    # Call LLM API with structured output
    response = await llm_client.complete(prompt, response_schema=PatchSchema)

    # Parse patch from response
    patch = self._parse_patch_from_llm(response)

    # Display patch with review UI
    self._display_patch_proposal(patch)

    return f"Proposed patch:\n{patch.description}\n\n[Review and Apply]"
```

### Prompt Engineering

**Chat Prompt Template**:
```
You are an expert in binary format analysis and YAML grammar design.

The user is working with a binary file and a YAML grammar specification.

Current context:
- Schema: {schema}
- Coverage: {coverage}%
- Errors: {errors}

Conversation history:
{history}

User: {user_message}

Provide helpful, actionable advice. If suggesting changes, be specific about field types, lengths, and byte offsets.
```

**Patch Suggestion Prompt Template**:
```
You are an expert in binary format analysis.

Analyze the following parse results and propose a patch to improve the schema.

Current Schema:
```yaml
{schema}
```

Parse Results:
- Coverage: {coverage}%
- Errors: {errors}
- Anomalies: {anomalies}

Propose a specific patch as a JSON object:
{
  "description": "Brief description of change",
  "patch_ops": [
    {
      "op": "add_field" | "modify_field" | "remove_field",
      "target": "field_path",
      "params": {...}
    }
  ]
}

Focus on fixing the most impactful errors first.
```

### Async Implementation

Textual requires async for non-blocking LLM calls:

```python
async def _handle_suggest_patch_async(self) -> None:
    """Async version with real LLM call."""
    # Show loading indicator
    self._chat_messages.append(("system", "Analyzing schema..."))
    self._update_chat_log()

    # Prepare context
    context = self._build_patch_context(...)

    # Call LLM (async, non-blocking)
    suggestion = await self._generate_llm_patch_suggestion(context)

    # Update UI
    self._chat_messages.append(("assistant", suggestion))
    self._update_chat_log()

def _handle_suggest_patch(self) -> None:
    """Sync wrapper that schedules async work."""
    self.run_worker(self._handle_suggest_patch_async())
```

### Configuration

**Environment Variables**:
```bash
# LLM API Configuration
LLM_PROVIDER=anthropic  # or openai, ollama
LLM_API_KEY=sk-...      # API key
LLM_MODEL=claude-sonnet-4  # Model name
LLM_MAX_TOKENS=2000     # Max response length
```

**Config File** (`~/.hexmap/config.yaml`):
```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4
  max_tokens: 2000
  temperature: 0.7
```

## File Changes Summary

### Modified Files

**`src/hexmap/widgets/agent_workbench.py`**:
- Added imports: `Input`, `TabbedContent`, `TabPane`
- Added instance variables: `_chat_log`, `_chat_input`, `_chat_send_button`, `_suggest_patch_button`, `_chat_messages`
- Modified `compose()`: Added "Chat" tab to Column 1 alongside Versions
- Added `on_input_submitted()`: Handle Enter in chat input
- Modified `on_button_pressed()`: Route chat button presses
- Added `_handle_chat_send()`: Process user messages
- Added `_handle_suggest_patch()`: Generate patch suggestions
- Added `_update_chat_log()`: Render conversation
- Added `_build_patch_context()`: Prepare context for LLM
- Added `_generate_demo_response()`: Demo mode chat responses
- Added `_generate_demo_patch_suggestion()`: Demo mode patch suggestions

**`src/hexmap/ui/theme.tcss`**:
- Added CSS rules for chat interface (lines 375-413)

### Lines of Code

- **agent_workbench.py**: ~200 lines added (chat UI + handlers)
- **theme.tcss**: ~40 lines added (chat styling)
- **Total**: ~240 lines

## Dependencies

### Python Libraries

No new dependencies required for demo mode.

**For real LLM integration**:
```bash
pip install anthropic  # Anthropic Claude
# or
pip install openai     # OpenAI GPT
# or
pip install ollama     # Local models
```

### Textual Widgets

- `TabbedContent` - tabbed interface container
- `TabPane` - individual tab panel
- `Input` - text input field
- `Static` - chat log display
- `Button` - Send and Suggest Patch buttons

All widgets are built-in Textual components, no custom widgets needed.

## Design Decisions

### 1. Demo Mode First

**Decision**: Implement full UI and handlers with demo responses, defer real LLM integration.

**Rationale**:
- Allows testing UI/UX without API costs
- Clarifies integration points for future work
- Users can evaluate workflow before committing to LLM provider
- Reduces dependencies for initial deployment

### 2. Tabbed Interface

**Decision**: Add "Chat" tab alongside "Versions" tab in Column 1.

**Rationale**:
- Keeps chat interface easily accessible for iterative workflow
- Natural organization: Versions = view history, Chat = request changes
- Separates active iteration (Column 1) from passive inspection (Columns 2-3)
- Allows future expansion (could add more tabs: "History", "Logs", etc.)
- Follows Textual best practices for multi-view layouts

### 3. Message History Format

**Decision**: Store messages as `list[tuple[str, str]]` with format `[(role, content), ...]`.

**Rationale**:
- Simple and lightweight
- Matches common LLM API formats (OpenAI, Anthropic)
- Easy to serialize for persistence
- Straightforward to render

### 4. Context Limitation

**Decision**: Include only first 5 errors and first 5 anomalies in context.

**Rationale**:
- Reduces token usage for LLM calls
- Focuses on most actionable issues
- Prevents context overflow for large files
- First errors often most informative

### 5. No Patch Review UI Yet

**Decision**: Demo mode only displays patch suggestions as text, no apply button.

**Rationale**:
- Patch review UI requires real patch format from LLM
- Premature to design UI without LLM response schema
- Can be added in future PR once LLM integration is working
- Current Branch button provides manual patching workflow

## Integration with Existing PRs

### PR#1-2: Tab Shell & State Model
- Chat interface respects `state.selected_version_id`
- No state model changes required

### PR#3: SpecStore Integration
- Uses `manager.get_version()` for schema text
- Uses `manager.get_version_metadata()` for run artifacts

### PR#4: Patch Ops
- Future: LLM could generate patches compatible with existing `Patch` class
- No changes to patch model required

### PR#5: Runs UI
- Chat uses run artifacts to build context
- Run stats (coverage, errors, anomalies) feed into LLM prompts

### PR#6: Evidence Integration
- Chat tab located in Column 1, Evidence in Column 3
- Both views access same underlying data from WorkbenchManager

### PR#7: Draft/Promote/Branch
- Chat can guide users to use Branch for testing
- Future: LLM could trigger Branch automatically

## Known Limitations

1. **Demo Mode Only**: No real LLM integration
2. **No Patch Application**: Suggestions are text-only, no apply button
3. **No History Persistence**: Chat history lost on tab switch or app restart
4. **No Streaming**: Future LLM integration should stream responses for better UX
5. **No Multi-turn Context**: Demo mode doesn't maintain conversation context
6. **No Error Handling**: No retry logic for failed LLM calls (future work)

## Success Criteria

- ✅ Chat UI renders in Column 1 alongside Versions tab
- ✅ User can send messages via Enter or Send button
- ✅ Assistant responds with demo messages
- ✅ "Suggest Patch" button generates demo suggestions
- ✅ Context preparation extracts schema + errors + anomalies
- ✅ Chat log displays full conversation history
- ✅ No crashes or errors with demo mode
- ✅ CSS styling matches rest of workbench

## Completion Checklist

- ✅ Chat UI components added
- ✅ Button handlers implemented
- ✅ Input submission handler implemented
- ✅ Message history tracking implemented
- ✅ Context preparation implemented
- ✅ Demo mode responses implemented
- ✅ CSS styling added
- ✅ Manual testing completed
- ✅ Documentation written (this file)
- ⏳ Real LLM integration (future work)
- ⏳ Patch review UI (future work)
- ⏳ History persistence (future work)

## Next Steps

After PR#8, the Agent Workbench is feature-complete in demo mode. Future enhancements:

1. **PR#9**: Real LLM integration (Anthropic Claude or OpenAI GPT)
2. **PR#10**: Patch review and apply UI
3. **PR#11**: Chat history persistence
4. **PR#12**: Streaming LLM responses
5. **PR#13**: Multi-turn conversation context
6. **PR#14**: Automated patch testing (apply → run → score)

## Conclusion

PR#8 completes the systematic build of the Agent Workbench by adding a chat interface for LLM-driven spec iteration. The demo mode implementation provides:

- Full UI/UX workflow
- Clear integration points for real LLM
- Structured context preparation
- Extensible message format
- Future-proof architecture

The workbench is now ready for production deployment in demo mode, with a clear path to real LLM integration when ready.
