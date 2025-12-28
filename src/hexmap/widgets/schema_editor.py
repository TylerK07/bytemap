from __future__ import annotations

from textual.widgets import TextArea


class SchemaEditor(TextArea):
    """TextArea that requests schema apply on blur and line changes."""

    def on_blur(self, event) -> None:  # type: ignore[override]
        # Apply immediately when leaving the editor
        if hasattr(self.app, "schedule_schema_apply"):
            # Use a small positive delay to avoid zero-interval timer issues
            self.app.schedule_schema_apply(0.05)  # type: ignore[attr-defined]

    def on_key(self, event) -> None:  # type: ignore[override]
        # If user likely changed line / navigated between lines, schedule apply
        key = event.key.lower()
        if key in {"enter", "up", "down", "pageup", "pagedown"} and hasattr(
            self.app, "schedule_schema_apply"
        ):
            self.app.schedule_schema_apply(0.2)  # type: ignore[attr-defined]
