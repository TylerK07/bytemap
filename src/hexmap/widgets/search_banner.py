"""Green search banner that appears above hex view."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from hexmap.ui.palette import PALETTE


class SearchBanner(Static):
    """Banner showing active search with cancel button."""

    def __init__(self) -> None:
        super().__init__()
        self._mode = ""
        self._params_text = ""
        self._hit_count = 0

    def update_search(self, mode: str, params_text: str, hit_count: int) -> None:
        """Update banner content."""
        self._mode = mode
        self._params_text = params_text
        self._hit_count = hit_count
        self._render_content()

    def _render_content(self) -> None:
        # Build banner text
        text = Text()
        style = f"{PALETTE.search_banner_fg} on {PALETTE.search_banner_bg}"
        bold_style = f"bold {style}"

        text.append("Searching for: ", style=bold_style)
        text.append(f"{self._mode} {self._params_text}", style=style)
        hits_text = f" | {self._hit_count} hit{'s' if self._hit_count != 1 else ''}"
        text.append(hits_text, style=style)
        text.append("   [✕ Cancel]", style=bold_style)

        self.update(text)

    def on_click(self, event) -> None:  # type: ignore[no-untyped-def, override]
        """Cancel search when banner is clicked."""
        if hasattr(self.app, "cancel_search"):
            self.app.cancel_search()  # type: ignore[attr-defined]
