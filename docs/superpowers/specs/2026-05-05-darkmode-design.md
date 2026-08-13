# Dark Mode Design — recordGUI

**Date:** 2026-05-05  
**Status:** Approved

---

## Overview

Add a light/dark mode toggle to the recordGUI PyQt6 application. The user can switch themes at any time via a toolbar button; the preference persists across restarts via `config.json`.

---

## Architecture

### New file: `gui/theme.py`

Contains two complete QSS stylesheet strings and a single public function:

```python
LIGHT_THEME: str   # existing stylesheet content
DARK_THEME: str    # new dark stylesheet

def apply_theme(app: QApplication, is_dark: bool) -> None:
    app.setStyleSheet(DARK_THEME if is_dark else LIGHT_THEME)
```

No other public API. Dialogs and widgets do not import this module directly.

### Modified: `gui/mainGUI.py`

1. **Startup**: after `app = QApplication(...)`, read `cfg.get("darkMode", False)` and call `apply_theme(app, is_dark)`.
2. **Toolbar button**: added at the right end of the toolbar using existing `createToolbarButton()`.
   - Label: `"🌙 다크"` when in light mode, `"☀️ 라이트"` when in dark mode.
   - Click handler: flip `_is_dark` flag → `apply_theme(app, _is_dark)` → `saveConfig({"darkMode": _is_dark})`.
3. **Remove**: the existing `app.setStyleSheet(""" ... """)` block at the bottom of the file.

### Modified: `gui/add_channel_dialog.py` and `gui/edit_channel_dialog.py`

Remove local `self.setStyleSheet(...)` calls. The disabled-widget styles (`QLineEdit:disabled`, `QComboBox:disabled`, `QLabel#InfoHint:disabled`) move into the global theme strings in `theme.py`.

---

## Color Palette

### Light Theme (unchanged from current)

| Role | Value |
|------|-------|
| Background | `#f6f7fb` |
| Widget surface | `#ffffff` |
| Border | `#e5eaf3` |
| Text | `#111827` |
| Subtle text / InfoHint | `#64748b` |
| Accent (scrollbar, focus) | `#c7d2fe` |
| Disabled background | `#f2f2f2` |
| Disabled text | `#888888` |

### Dark Theme (Gray Dark)

| Role | Value |
|------|-------|
| Background | `#111827` |
| Widget surface | `#1f2937` |
| Border | `#374151` |
| Text | `#f9fafb` |
| Subtle text / InfoHint | `#9ca3af` |
| Accent (scrollbar, focus) | `#a5b4fc` |
| Disabled background | `#374151` |
| Disabled text | `#6b7280` |

---

## Data Flow

```
App start
  → loadConfig() → cfg["darkMode"] (default: False)
  → apply_theme(app, is_dark)

Toolbar toggle click
  → flip _is_dark
  → apply_theme(app, _is_dark)          # instant visual update
  → saveConfig({..., "darkMode": _is_dark})  # persists across restarts
```

---

## Scope

**In scope:**
- `gui/theme.py` (new)
- `gui/mainGUI.py` — toolbar button, startup theme load, remove old setStyleSheet
- `gui/add_channel_dialog.py` — remove local setStyleSheet
- `gui/edit_channel_dialog.py` — remove local setStyleSheet

**Out of scope:**
- OS dark mode auto-detection
- Per-dialog theme overrides
- Animated theme transitions
