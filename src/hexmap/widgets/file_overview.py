from __future__ import annotations

from rich.text import Text
from textual.widget import Widget

from hexmap.ui.palette import PALETTE


class FileOverview(Widget):
    """Vertical minimap-style overview of file coverage and viewport.

    Call update_state with file_size, covered spans (offset,length),
    and current viewport (offset,length).
    """

    def __init__(self) -> None:
        super().__init__()
        self._file_size = 0
        self._covered: list[tuple[int, int]] = []
        self._viewport: tuple[int, int] = (0, 0)

    def update_state(
        self,
        *,
        file_size: int,
        covered: list[tuple[int, int]] | None = None,
        viewport: tuple[int, int] | None = None,
    ) -> None:
        self._file_size = max(0, file_size)
        if covered is not None:
            # Normalize to merged simple ranges
            merged: list[tuple[int, int]] = []
            for s, ln in sorted(((s, ln) for s, ln in covered), key=lambda x: x[0]):
                e = s + ln
                if not merged:
                    merged.append((s, e))
                else:
                    ps, pe = merged[-1]
                    if s <= pe:
                        merged[-1] = (ps, max(pe, e))
                    else:
                        merged.append((s, e))
            self._covered = merged
        if viewport is not None:
            self._viewport = viewport
        self.refresh()

    def render(self) -> Text:  # type: ignore[override]
        height = max(1, self.size.height or 1)
        width = max(1, self.size.width or 1)
        if self._file_size <= 0:
            return Text("\n".join([" " * width] * height), style=f"on {PALETTE.unmapped_bg}")

        vp_start, vp_len = self._viewport
        vp_end = min(self._file_size, vp_start + max(0, vp_len))

        lines: list[Text] = []
        for row in range(height):
            # Determine slice of file this row represents
            row_start = int(row / height * self._file_size)
            row_end = int((row + 1) / height * self._file_size)
            if row_end <= row_start:
                row_end = min(self._file_size, row_start + 1)
            # Decide color: mapped if any covered range overlaps
            mapped = False
            for s, e in self._covered:
                if e <= row_start:
                    continue
                if s >= row_end:
                    break
                mapped = True
                break
            bg = PALETTE.minimap_mapped if mapped else PALETTE.minimap_unmapped
            fg = PALETTE.unmapped_fg

            # Highlight viewport rows
            in_vp = not (vp_end <= row_start or vp_start >= row_end)
            if in_vp:
                bg = PALETTE.minimap_viewport

            lines.append(Text(" " * width, style=f"{fg} on {bg}"))
        out = Text()
        for i, t in enumerate(lines):
            if i:
                out.append("\n")
            out.append(t)
        return out
