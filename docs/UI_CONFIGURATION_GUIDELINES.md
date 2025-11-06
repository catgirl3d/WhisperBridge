# UI Configuration Guidelines

## Overview
This document defines the standard approach for UI widget configuration in WhisperBridge to ensure consistency, maintainability, and scalability.

## Configuration Principles

### 1. Centralized Configuration
- All widget configuration is centralized in CONFIG dictionaries; visual styles live in QSS
- Use consistent naming pattern: `{WIDGET_TYPE}_CONFIG`
- Place configurations at class level (not inside methods)
- Include size and any widget-specific properties (no inline CSS in Python)
- Add objectName for widgets that need styling/testing
- Follow DRY principle - avoid hardcoded values

Key Principles:
1. Centralized Configuration: All CONFIG dictionaries live at class level; visual appearance is defined in QSS
2. Explicit Mapping: Use explicit button-to-config mappings, not dynamic key generation
3. Unified Factory: Single _create_widget_from_config method for all widgets
4. ObjectName Usage: Set objectName for all testable/stylable widgets
5. Separation of Concerns: Python handles logic/state, QSS handles appearance

### 2. Standard Configuration Structure
Each CONFIG dictionary should include:
```python
WIDGET_TYPE_CONFIG = {
    'property_name': {
        'size': (width, height),           # Optional for fixed-size widgets
        'icon_size': (width, height),      # Optional for icon widgets
        'object_name': 'widgetName',       # Optional for testable/stylable widgets
        'text': 'Default text',            # Optional for text widgets
        'tooltip': 'Help text',            # Optional for interactive widgets
        # Note: the project's factory applies the common keys above.
        # The codebase does not automatically apply a 'properties' mapping
        # (dynamic properties must be set explicitly or the factory extended).
        # Add widget-specific properties as needed.
    }
}
```

### 3. Naming Conventions
- Use snake_case for configuration keys
- Use descriptive names: `mode_combo`, `style_combo`, `close_button`
- Group related configurations: `INFO_WIDGET_CONFIG`, `FOOTER_WIDGET_CONFIG`

### 4. Implementation Pattern

#### 4.1 Standard Widget Factory Method
```python
def _create_widget_from_config(self, widget_type: str, config_key: str, widget_class, **kwargs):
    """Generic widget factory using configuration dictionaries.

    Current implementation (see `src/whisperbridge/ui_qt/overlay_ui_builder.py`)
    applies a fixed set of common keys from the configuration:
    - size, object_name, width, icon_size, text, tooltip

    If you need dynamic properties applied from configs (e.g. 'properties'),
    extend this method to iterate and call `widget.setProperty(...)`.
    """
    config_maps = {
        'info': self.INFO_WIDGET_CONFIG,
        'language': self.LANGUAGE_WIDGET_CONFIG,
        'footer': self.FOOTER_WIDGET_CONFIG,
        'label': self.LABEL_CONFIG
    }

    config = config_maps[widget_type][config_key]
    widget = widget_class(**kwargs)

    # Apply common configuration properties supported by the factory
    if hasattr(widget, 'setFixedSize') and 'size' in config:
        widget.setFixedSize(*config['size'])
    if hasattr(widget, 'setObjectName') and 'object_name' in config:
        widget.setObjectName(config['object_name'])
    if hasattr(widget, 'setFixedWidth') and 'width' in config:
        widget.setFixedWidth(config['width'])
    if hasattr(widget, 'setIconSize') and 'icon_size' in config:
        widget.setIconSize(QSize(*config['icon_size']))
    if hasattr(widget, 'setText') and 'text' in config:
        widget.setText(config['text'])
    if hasattr(widget, 'setToolTip') and 'tooltip' in config:
        widget.setToolTip(config['tooltip'])

    return widget, config
```

#### 4.2 Explicit Button Mapping (no inline styles)
```python
def apply_button_style(self, button: QPushButton, compact: bool):
    """Apply styling to a button based on compact/full mode using configuration dictionaries.

    The implementation in `overlay_ui_builder.py`:
    - Uses an explicit mapping from known button instances to `BUTTON_STYLES`
    - Falls back to `default_compact` / `default_full` for other buttons
    - Uses `_make_icon_from_spec` to build QIcons for configured assets/qtawesome specs
    - Sets dynamic properties `mode` (and ensures `utility` exists) so QSS can select styles
    - Performs a style refresh after property changes
    """
    mode = 'compact' if compact else 'full'

    # Explicit mapping of buttons to their style configurations
    button_configs = {
        self.translate_btn: {
            'compact': self.BUTTON_STYLES['translate_compact'],
            'full': self.BUTTON_STYLES['translate_full']
        },
        self.reader_mode_btn: {
            'compact': self.BUTTON_STYLES['reader_compact'],
            'full': self.BUTTON_STYLES['reader_full']
        }
    }

    # Get the specific config for the button and mode (fallback to defaults)
    config = button_configs.get(button, {}).get(mode)
    if not config:
        config = self.BUTTON_STYLES[f'default_{mode}']

    config = config.copy()  # avoid mutating class-level dicts

    # Button-specific icon selection (examples)
    if button == self.reader_mode_btn:
        config['icon'] = self._make_icon_from_spec(self.ICONS_CONFIG['reader']['full' if mode == 'full' else 'compact'])
    elif button == self.translate_btn:
        config['icon'] = self._make_icon_from_spec(self.ICONS_CONFIG['translate']['all'])

    # Apply size, text and icon if provided by config
    if 'text' in config and config['text'] is not None:
        button.setText(config['text'])
    if 'tooltip' in config and config['tooltip']:
        button.setToolTip(config['tooltip'])
    if 'size' in config:
        button.setFixedSize(*config['size'])
    if 'icon_size' in config:
        button.setIconSize(QSize(*config['icon_size']))
    if config.get('icon') is not None:
        button.setIcon(config['icon'])

    # Set dynamic properties for QSS to consume
    try:
        button.setProperty("mode", mode)
        if button.property("utility") is None:
            button.setProperty("utility", False)

        # Force style refresh so QSS reacts to the new properties
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()
    except Exception:
        # Do not break UI on styling errors
        pass
```

#### 4.3 Disabled State Via QSS
```python
def apply_disabled_translate_visuals(self, button: QPushButton, reason_msg: str, compact: bool) -> None:
    """Apply strong disabled visuals for the Translate/Style button.

    Implementation note:
    The codebase uses a logical-disabled approach (keeps the widget enabled
    to preserve certain cursor/hover behaviors) — it sets a dynamic property
    `logically_disabled` and updates `mode` and icon metadata for QSS to style.
    """
    if not button:
        return

    try:
        # Logical disabled state (do not call setEnabled(False) to preserve cursor events)
        button.setProperty("logically_disabled", True)
        button.setCursor(Qt.CursorShape.ForbiddenCursor)
        button.setToolTip(reason_msg or self.DEFAULT_DISABLED_TOOLTIP)

        # Map compact/full to the DISABLED_STYLES and set the mode property
        config = self.DISABLED_STYLES['compact' if compact else 'full']
        mode = 'compact' if compact else 'full'
        button.setProperty("mode", mode)

        # Apply lock/disabled icon from ICONS_CONFIG using icon_key
        icon_key = config.get('icon_key')
        if icon_key:
            icon_spec = self.ICONS_CONFIG.get('translate_disabled', {}).get(icon_key)
            if icon_spec:
                button.setIcon(self._make_icon_from_spec(icon_spec))

        # Force style refresh
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()
    except Exception as e:
        logger.debug(f"Failed to apply disabled translate visuals: {e}")
```

### Dynamic properties catalog
- The codebase uses a small, well-defined set of dynamic properties (set via `setProperty`) that QSS and code rely on:
  - `mode` (string) — "compact" | "full": controls compact/full visual variants (buttons, panels).
  - `utility` (bool) — true/false: marks small utility buttons so QSS can style them differently from large action buttons.
  - `logically_disabled` (bool) — true/false: indicates a logical disabled state (used instead of `setEnabled(False)` to preserve cursor/hover behaviour).
  - `status` (string) — e.g., "success", "error", "warning": used on status labels to select colour/indicator variants.
- Implementation notes:
  - Properties are applied in code via `widget.setProperty(...)` (see `src/whisperbridge/ui_qt/overlay_ui_builder.py:524` and nearby).
  - QSS selectors should reference these properties, for example:
    - QPushButton[mode="compact"] { ... }
    - QLabel[status="error"] { color: #d32f2f; }
  - If you add new dynamic properties, add them to this catalog and document where they are set.
  
### 5. Styling Best Practices
- Centralize styles in QSS files: use `src/whisperbridge/assets/style.qss` for all visual styling
- Target widgets by objectName: use `objectName` for specific widget styling
- Avoid inline styles: do not call `setStyleSheet()` in Python code for visual styling
- Use CSS selectors and dynamic properties: leverage Qt selectors (e.g., `QPushButton#id[mode="compact"]`)
- Separate concerns: Python handles logic/state, QSS handles appearance

## Existing Configurations

### Current Standard Configurations
- `TRANSLATOR_DIALOG_CONFIG` - Translator settings dialog configuration
- `DISABLED_STYLES` - Disabled-state metadata (icon keys); visuals handled by QSS
- `ICONS_CONFIG` - Centralized icon configuration (qtawesome specs or asset paths)
- `LANGUAGE_WIDGET_CONFIG` - Language selection widget configs (size/icon_size/object_name)
- `FOOTER_WIDGET_CONFIG` - Footer widgets configuration (status label, close button)
- `BUTTON_STYLES` - Button configuration (size/text/icon_size/tooltip) by type and mode
- `INFO_WIDGET_CONFIG` - Info-row widgets (mode/style combos, labels, auto-swap checkbox)
- `TEXT_EDIT_CONFIG` - Text edit widget configuration (object_name)
- `LABEL_CONFIG` - Label widget configuration (object_name/text)
- `LAYOUT_CONFIG` (PanelWidget) - Panel layout spacing and dimensions
- `LAYOUT_CONFIG` (OverlayUIBuilder) - Main overlay layout margins and spacers

Component-specific configurations present in other UI modules (keep these in their module files and reference them here):
- `READER_WINDOW_CONFIG` - Reader window sizing and font settings (see [`src/whisperbridge/ui_qt/reader_window.py:36`](src/whisperbridge/ui_qt/reader_window.py:36))
- `READER_BUTTON_CONFIG` - Reader window button configurations (font controls, increase/decrease) (see [`src/whisperbridge/ui_qt/reader_window.py:46`](src/whisperbridge/ui_qt/reader_window.py:46))
- `READER_LABEL_CONFIG` - Reader window label configurations (text display) (see [`src/whisperbridge/ui_qt/reader_window.py:65`](src/whisperbridge/ui_qt/reader_window.py:65))

- `MINIBAR_WINDOW_CONFIG` - MiniBar window sizing and layout properties (see [`src/whisperbridge/ui_qt/minibar_overlay.py:31`](src/whisperbridge/ui_qt/minibar_overlay.py:31))
- `MINIBAR_BUTTON_CONFIG` - MiniBar button configurations (expand/close) (see [`src/whisperbridge/ui_qt/minibar_overlay.py:39`](src/whisperbridge/ui_qt/minibar_overlay.py:39))
- `MINIBAR_LABEL_CONFIG` - MiniBar label configurations (title) (see [`src/whisperbridge/ui_qt/minibar_overlay.py:58`](src/whisperbridge/ui_qt/minibar_overlay.py:58))

## Adding New Configurations

When adding new widget types:

1. Create CONFIG dictionary following the standard structure
2. Add to class level - place after existing configs
3. Create factory method - `_create_widget_type()`
4. Update documentation - add to this file
5. Add tests - ensure configuration works correctly

## Code Review Checklist

When reviewing UI code, check for:
- [ ] No hardcoded sizes/styles in Python (styles belong to QSS)
- [ ] All configs follow naming pattern
- [ ] Factory methods use configs
- [ ] objectName set for testable widgets
- [ ] Consistent error handling
- [ ] Proper documentation

## Examples

### Good Example
```python
BUTTON_CONFIG = {
    'primary': {
        'size': (120, 28),
        'object_name': 'primaryButton',
        'text': 'Primary Action'
    }
}

def _create_primary_button(self) -> QPushButton:
    config = self.BUTTON_CONFIG['primary']
    btn = QPushButton(config['text'])
    btn.setFixedSize(*config['size'])
    btn.setObjectName(config['object_name'])
    return btn
```

```css
/* In style.qss */
QPushButton#primaryButton {
    background-color: #4CAF50;
    color: white;
    border: none;
}
QPushButton#primaryButton:hover {
    background-color: #45a049;
}
```

### Bad Example
```python
def _create_primary_button(self) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(120, 28)  # Hardcoded!
    btn.setStyleSheet("QPushButton { background-color: #4CAF50; }")  # Inline styling in Python - not allowed
    # Missing objectName!
    return btn
```

### Reader Window Example
```python
# Configuration dictionaries
READER_WINDOW_CONFIG = {
    'minimum_size': (500, 400),
    'default_font_size': 14,
    'font_family': "Arial",
    'font_size_min': 8,
    'font_size_max': 32,
    'font_size_step': 2,
}

READER_BUTTON_CONFIG = {
    'font_controls': {
        'size': (32, 32),
        'icon_size': (16, 16),
        'icon_color': "black",
    },
    'decrease': {
        'icon': "fa5s.minus",
        'tooltip': "Decrease font size",
        'object_name': "decreaseFontBtn",
    }
}

# Factory method using config
def _create_decrease_button(self) -> QPushButton:
    config = READER_BUTTON_CONFIG['decrease']
    btn_config = READER_BUTTON_CONFIG['font_controls']
    btn = QPushButton(self)
    btn.setObjectName(config['object_name'])
    btn.setFixedSize(*btn_config['size'])
    btn.setIcon(qta.icon(config['icon'], color=btn_config['icon_color']))
    btn.setIconSize(QSize(*btn_config['icon_size']))
    btn.setToolTip(config['tooltip'])
    return btn

# Font size control using config
def _decrease_font_size(self):
    if self._current_font_size > READER_WINDOW_CONFIG['font_size_min']:
        self._current_font_size -= READER_WINDOW_CONFIG['font_size_step']
        self._update_font_size()
```

### MiniBar Overlay Example
```python
# Configuration dictionaries
MINIBAR_WINDOW_CONFIG = {
    'fixed_height': 28,
    'minimum_width': 190,
    'layout_margins': (10, 0, 4, 0),
    'layout_spacing': 2,
    'title_font': ("Arial", 10, QFont.Weight.Bold),
}

MINIBAR_BUTTON_CONFIG = {
    'expand': {
        'size': (22, 22),
        'icon': "fa5s.expand-alt",
        'fallback_icon': "fa5s.chevron-up",
        'fallback_text': "Expand",
        'icon_color': "black",
        'object_name': "expandBtnMini",
    },
    'close': {
        'size': (22, 22),
        'icon': "fa5s.times",
        'fallback_text': "X",
        'icon_color': "black",
        'object_name': "closeBtnMini",
    }
}

MINIBAR_LABEL_CONFIG = {
    'title': {
        'object_name': "titleLabelMini",
        'font': ("Arial", 10, QFont.Weight.Bold),
    }
}

# Unified widget factory method
def _create_widget_from_config(self, widget_type: str, config_key: str, widget_class, **kwargs):
    """Generic factory method to create widgets from configuration dictionaries."""
    config_maps = {
        'button': MINIBAR_BUTTON_CONFIG,
        'label': MINIBAR_LABEL_CONFIG
    }
    
    config = config_maps[widget_type][config_key]
    widget = widget_class(**kwargs)
    
    # Apply common configuration properties
    if 'object_name' in config:
        widget.setObjectName(config['object_name'])
    if 'size' in config:
        widget.setFixedSize(*config['size'])
    if 'font' in config:
        widget.setFont(QFont(*config['font']))
        
    return widget, config

# Factory methods using the unified approach
def _create_expand_button(self) -> QPushButton:
    """Create the expand button using configuration."""
    btn, config = self._create_widget_from_config('button', 'expand', QPushButton)
    
    # Apply button-specific configuration
    try:
        btn.setIcon(qta.icon(config['icon'], color=config['icon_color']))
    except Exception:
        try:
            btn.setIcon(qta.icon(config['fallback_icon'], color=config['icon_color']))
        except Exception:
            btn.setText(config['fallback_text'])
    
    btn.clicked.connect(self._handle_expand_clicked)
    return btn

def _create_title_label(self) -> QLabel:
    """Create the title label using configuration."""
    label, _ = self._create_widget_from_config('label', 'title', QLabel)
    return label

# Styling is handled in style.qss using objectName selectors:
# QPushButton#expandBtnMini { ... }
# QPushButton#closeBtnMini { ... }
# QLabel#titleLabelMini { ... }
```

## Integration with Memory Bank

Update `.kilocode/rules/memory-bank/architecture.md`:
```markdown
UI Configuration Standards
- All UI configurations follow centralized approach documented in docs/UI_CONFIGURATION_GUIDELINES.md
- Widget styles use CONFIG dictionaries with consistent naming
- Factory methods follow standardized patterns