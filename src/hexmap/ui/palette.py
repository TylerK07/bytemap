from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    footer_bg: str
    footer_fg: str
    accent: str
    accent_dim: str
    focus_border: str
    panel_border: str
    byte_cursor_bg: str
    byte_cursor_fg: str
    shortcut_fg: str
    shortcut_bg: str
    unmapped_fg: str
    unmapped_bg: str
    parsed_name: str
    parsed_value: str
    parsed_index: str
    parsed_offset: str
    parsed_type: str
    parsed_punct: str
    parsed_error: str
    minimap_mapped: str
    minimap_unmapped: str
    minimap_viewport: str
    minimap_cursor: str
    hex_unmapped_fg: str
    hex_type_int_fg: str
    hex_type_float_fg: str
    hex_type_string_fg: str
    hex_type_bytes_fg: str
    hex_selection_bg: str
    hex_cursor_bg: str
    hex_selected_fg: str
    diff_changed_fg: str
    diff_changed_punct: str
    inspector_label: str
    inspector_value: str
    inspector_dim: str
    inspector_warning: str
    inspector_header: str
    inspector_accent: str
    freq_low_fg: str
    freq_mid_fg: str
    freq_high_fg: str
    # Search lens roles
    search_banner_bg: str
    search_banner_fg: str
    search_hit_fg: str
    search_payload_bg: str  # Background highlight for payload regions
    search_inspector_bg: str
    search_inspector_fg: str
    # Visualization roles
    viz_selected: str
    viz_unselected_dim: str
    viz_pattern_a: str
    viz_pattern_b: str


DEFAULT = Palette(
    footer_bg="#1f2430",
    footer_fg="#d8dee9",
    accent="#5ea1ff",
    accent_dim="#4c75c6",
    focus_border="#ffa657",
    panel_border="#3b4252",
    byte_cursor_bg="#314f76",
    byte_cursor_fg="#ffffff",
    shortcut_fg="#ffffff",
    shortcut_bg="#5ea1ff",
    unmapped_fg="#6b7280",
    unmapped_bg="#0f1117",
    parsed_name="#d8dee9",
    parsed_value="#ffffff",
    parsed_index="#5ea1ff",
    parsed_offset="#8892a0",
    parsed_type="#4c75c6",
    parsed_punct="#6b7280",
    parsed_error="#ff5555",
    minimap_mapped="#5ea1ff",
    minimap_unmapped="#0f1117",
    minimap_viewport="#314f76",
    minimap_cursor="#ffa657",
    hex_unmapped_fg="#6b7280",
    hex_type_int_fg="#9cdcfe",
    hex_type_float_fg="#b3ecff",
    hex_type_string_fg="#d7ba7d",
    hex_type_bytes_fg="#ce9178",
    hex_selection_bg="#3b4252",
    hex_cursor_bg="#b36b00",
    hex_selected_fg="#ffffff",
    diff_changed_fg="#ffb86c",
    diff_changed_punct="#8b7355",
    inspector_label="#8892a0",
    inspector_value="#ffffff",
    inspector_dim="#6b7280",
    inspector_warning="#ff5555",
    inspector_header="#4c75c6",
    inspector_accent="#5ea1ff",
    freq_low_fg="#a0a0a0",
    freq_mid_fg="#ffaa00",
    freq_high_fg="#ff5555",
    search_banner_bg="#10b981",
    search_banner_fg="#ffffff",
    search_hit_fg="#10b981",
    search_payload_bg="#1e3a5f",  # Soft blue background for payload regions
    search_inspector_bg="#065f46",
    search_inspector_fg="#ffffff",
    viz_selected="#ffffff",
    viz_unselected_dim="#6b7280",
    viz_pattern_a="#5ea1ff",
    viz_pattern_b="#4c75c6",
)

DIM = Palette(
    footer_bg="#2b2b2b",
    footer_fg="#cccccc",
    accent="#a0a0a0",
    accent_dim="#888888",
    focus_border="#bbbbbb",
    panel_border="#444444",
    byte_cursor_bg="#555555",
    byte_cursor_fg="#ffffff",
    shortcut_fg="#000000",
    shortcut_bg="#a0a0a0",
    unmapped_fg="#888888",
    unmapped_bg="#1a1a1a",
    parsed_name="#e0e0e0",
    parsed_value="#f0f0f0",
    parsed_index="#a0a0a0",
    parsed_offset="#777777",
    parsed_type="#888888",
    parsed_punct="#666666",
    parsed_error="#ff6666",
    minimap_mapped="#a0a0a0",
    minimap_unmapped="#1a1a1a",
    minimap_viewport="#555555",
    minimap_cursor="#bbbbbb",
    hex_unmapped_fg="#666666",
    hex_type_int_fg="#cccccc",
    hex_type_float_fg="#cccccc",
    hex_type_string_fg="#bbbbbb",
    hex_type_bytes_fg="#aaaaaa",
    hex_selection_bg="#303030",
    hex_cursor_bg="#7a7a7a",
    hex_selected_fg="#000000",
    diff_changed_fg="#e6b673",
    diff_changed_punct="#6e5c47",
    inspector_label="#777777",
    inspector_value="#f0f0f0",
    inspector_dim="#666666",
    inspector_warning="#ff6666",
    inspector_header="#888888",
    inspector_accent="#a0a0a0",
    freq_low_fg="#999999",
    freq_mid_fg="#bbbb00",
    freq_high_fg="#ff6666",
    search_banner_bg="#009955",
    search_banner_fg="#ffffff",
    search_hit_fg="#00bb66",
    search_payload_bg="#2a3a4a",  # Soft blue background for payload regions (dim theme)
    search_inspector_bg="#005533",
    search_inspector_fg="#ffffff",
    viz_selected="#f0f0f0",
    viz_unselected_dim="#666666",
    viz_pattern_a="#a0a0a0",
    viz_pattern_b="#888888",
)

HIGH_CONTRAST = Palette(
    footer_bg="#000000",
    footer_fg="#ffffff",
    accent="#00ffff",
    accent_dim="#00aaaa",
    focus_border="#ffff00",
    panel_border="#888888",
    byte_cursor_bg="#ff00ff",
    byte_cursor_fg="#000000",
    shortcut_fg="#000000",
    shortcut_bg="#ffff00",
    unmapped_fg="#888888",
    unmapped_bg="#000000",
    parsed_name="#ffffff",
    parsed_value="#ffffff",
    parsed_index="#00ffff",
    parsed_offset="#aaaaaa",
    parsed_type="#00aaaa",
    parsed_punct="#888888",
    parsed_error="#ff6666",
    minimap_mapped="#00ffff",
    minimap_unmapped="#000000",
    minimap_viewport="#00aaaa",
    minimap_cursor="#ffff00",
    hex_unmapped_fg="#888888",
    hex_type_int_fg="#00ffff",
    hex_type_float_fg="#00ffff",
    hex_type_string_fg="#ffff00",
    hex_type_bytes_fg="#ff00ff",
    hex_selection_bg="#333333",
    hex_cursor_bg="#888800",
    hex_selected_fg="#000000",
    diff_changed_fg="#ffb000",
    diff_changed_punct="#aa7700",
    inspector_label="#aaaaaa",
    inspector_value="#ffffff",
    inspector_dim="#888888",
    inspector_warning="#ff6666",
    inspector_header="#00aaaa",
    inspector_accent="#00ffff",
    freq_low_fg="#aaaaaa",
    freq_mid_fg="#ffff00",
    freq_high_fg="#ff0000",
    search_banner_bg="#00ff00",
    search_banner_fg="#000000",
    search_hit_fg="#00ff00",
    search_payload_bg="#003366",  # Soft blue background for payload regions (high contrast)
    search_inspector_bg="#008800",
    search_inspector_fg="#ffffff",
    viz_selected="#ffffff",
    viz_unselected_dim="#888888",
    viz_pattern_a="#00ffff",
    viz_pattern_b="#00aaaa",
)

# Selected palette for now
PALETTE = DEFAULT
