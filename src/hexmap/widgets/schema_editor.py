from __future__ import annotations

from textual.reactive import var
from textual.widgets import TextArea


class SchemaEditor(TextArea):
    """TextArea that requests schema apply on blur and line changes.

    Also syncs text changes to app.spec_store for shared YAML buffer.
    """

    _last_synced_text: var[str] = var("")  # Track last synced text to avoid loops

    def on_blur(self, event) -> None:  # type: ignore[override]
        # Sync to spec_store when leaving editor
        self._sync_to_spec_store()

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

    def _sync_to_spec_store(self) -> None:
        """Sync current text to app.spec_store (shared YAML buffer)."""
        if hasattr(self.app, "spec_store"):
            current_text = self.text
            self.app._debug_log(f"[SchemaEditor._sync] current_text: {len(current_text)} chars, hash: {hash(current_text)}")  # type: ignore[attr-defined]
            self.app._debug_log(f"[SchemaEditor._sync] _last_synced_text: {len(self._last_synced_text)} chars, hash: {hash(self._last_synced_text)}")  # type: ignore[attr-defined]
            if current_text != self._last_synced_text:
                self.app.spec_store.set_working_text(current_text)  # type: ignore[attr-defined]
                self._last_synced_text = current_text
                self.app._debug_log(f"[SchemaEditor] ✅ Synced to spec_store: {len(current_text)} chars")  # type: ignore[attr-defined]
            else:
                self.app._debug_log(f"[SchemaEditor] ⏭️  No sync needed (text unchanged)")  # type: ignore[attr-defined]

    def load_from_spec_store(self) -> None:
        """Load text from app.spec_store (called when switching to Explore tab)."""
        if hasattr(self.app, "spec_store"):
            stored_text = self.app.spec_store.get_working_text()  # type: ignore[attr-defined]
            if stored_text and stored_text != self.text:
                self.load_text(stored_text)
                self._last_synced_text = stored_text
                self.app._debug_log(f"[SchemaEditor] Loaded from spec_store: {len(stored_text)} chars")  # type: ignore[attr-defined]
            else:
                self.app._debug_log(f"[SchemaEditor] No reload needed (text matches spec_store)")  # type: ignore[attr-defined]
