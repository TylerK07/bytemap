from __future__ import annotations
# ruff: noqa: I001

from dataclasses import dataclass
from collections.abc import Iterable

from rich.console import Group
from rich.text import Text
from textual.widget import Widget

from hexmap.core.io import PagedReader
from hexmap.ui.palette import PALETTE


@dataclass(frozen=True)
class StripRow:
    label: str
    data: bytes


class ByteStrip(Widget):
    """Compact per-file byte visualization (hex + ASCII) with selection highlight.

    Call update_state(...) to refresh with current start/selection/readers.
    """

    DEFAULT_BYTES: int = 32
    LABEL_W: int = 14

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[StripRow] = []
        self._start: int = 0
        self._sel: tuple[int, int] | None = None
        self._sel_len: int = 1
        self._w_hex: int = self.DEFAULT_BYTES
        self._w_ascii: int = self.DEFAULT_BYTES * 2

    def update_state(
        self,
        files: Iterable[tuple[str, PagedReader]],
        start: int,
        selection: tuple[int, int] | None,
    ) -> None:
        self._start = max(0, int(start))
        self._sel = selection if selection and selection[1] > 0 else None
        self._sel_len = int(selection[1]) if selection and selection[1] > 0 else 1
        rows: list[StripRow] = []
        # Compute bytes per row W_hex and W_ascii from available width
        total_w = max(0, int(self.size.width))
        available = max(0, total_w - self.LABEL_W - 1)
        # Hex uses 3*W - 1 characters (AA BB ...)
        W_hex = (available + 1) // 3 if available > 0 else self.DEFAULT_BYTES
        W_hex = max(8, min(64, W_hex))
        available_ascii = max(0, total_w - self.LABEL_W)
        desired_ascii = max(W_hex * 2, W_hex)
        W_ascii = max(8, min(128, desired_ascii, available_ascii))
        self._w_hex = W_hex
        self._w_ascii = W_ascii
        for (label, r) in files:
            data = r.read(self._start, max(W_hex, W_ascii))
            rows.append(StripRow(label=label, data=data))
        self._rows = rows
        self.refresh()

    def _style_role_for_index(self, i: int, L: int) -> str:
        if i < 0:
            return PALETTE.viz_unselected_dim
        if i < L:
            return PALETTE.viz_selected
        # continuation chunks after selection in blocks of L
        blk = ((i - L) // L) % 2 if L > 0 else 0
        return PALETTE.viz_pattern_a if blk == 0 else PALETTE.viz_pattern_b

    def _render_hex_row(self, label: str, data: bytes, start: int) -> Text:
        t = Text()
        t.append(f"{label:<{self.LABEL_W}}", style=PALETTE.parsed_offset)
        W = self._w_hex
        for i in range(W):
            b = data[i] if i < len(data) else None
            cell = f"{b:02X}" if b is not None else "  "
            # Style by selection and continuation blocks
            role = self._style_role_for_index(i, self._sel_len)
            t.append(cell, style=role)
            if i < W - 1:
                t.append(" ")
        return t

    def _render_ascii_row(self, label: str, data: bytes, start: int) -> Text:
        t = Text()
        t.append(f"{label:<{self.LABEL_W}}", style=PALETTE.parsed_offset)
        W = self._w_ascii
        for i in range(W):
            b = data[i] if i < len(data) else None
            ch = (chr(b) if (b is not None and 32 <= b <= 126) else "·") if b is not None else " "
            role = self._style_role_for_index(i, self._sel_len)
            t.append(ch, style=role)
        return t

    def render(self) -> Group:  # type: ignore[override]
        # Title rows
        out: list[Text] = []
        # Header with selection/window sizes
        out.append(
            Text(
                f"Selection len: {self._sel_len}   Window hex={self._w_hex} ascii={self._w_ascii}",
                style=PALETTE.parsed_type,
            )
        )
        # Hex header
        out.append(Text("HEX", style=PALETTE.parsed_type))
        for row in self._rows:
            out.append(self._render_hex_row(row.label, row.data, self._start))
        # ASCII header
        out.append(Text("ASCII", style=PALETTE.parsed_type))
        for row in self._rows:
            out.append(self._render_ascii_row(row.label, row.data, self._start))
        return Group(*out)

    # Test helpers
    def _compute_window(self) -> int:
        total_w = max(0, int(self.size.width))
        available = max(0, total_w - self.LABEL_W - 1)
        bpr = (available + 1) // 3 if available > 0 else self.DEFAULT_BYTES
        return max(8, min(64, bpr))

    # Test helper exposing both windows
    def _compute_windows(self) -> tuple[int, int]:
        total_w = max(0, int(self.size.width))
        available = max(0, total_w - self.LABEL_W - 1)
        W_hex = (available + 1) // 3 if available > 0 else self.DEFAULT_BYTES
        W_hex = max(8, min(64, W_hex))
        available_ascii = max(0, total_w - self.LABEL_W)
        desired_ascii = max(W_hex * 2, W_hex)
        W_ascii = max(8, min(128, desired_ascii, available_ascii))
        return (W_hex, W_ascii)
