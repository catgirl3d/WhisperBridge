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
        'size': (width, height),           # Required for fixed-size widgets
        'icon_size': (width, height),      # Required for icon widgets
        'object_name': 'widgetName',       # Required for testable/stylable widgets
        'text': 'Default text',            # Optional for text widgets
        'tooltip': 'Help text',            # Optional for interactive widgets
        # Optional dynamic properties for QSS selectors
        # 'properties': {'mode': 'compact'}
        # Add widget-specific properties as needed
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
    """Generic widget factory using configuration dictionaries."""
    config_maps = {
        'info': self.INFO_WIDGET_CONFIG,
        'language': self.LANGUAGE_WIDGET_CONFIG,
        'footer': self.FOOTER_WIDGET_CONFIG
    }
    
    config = config_maps[widget_type][config_key]
    widget = widget_class(**kwargs)
    
    # Apply common configuration properties
    if hasattr(widget, 'setFixedSize') and 'size' in config:
        widget.setFixedSize(*config['size'])
    if hasattr(widget, 'setObjectName') and 'object_name' in config:
        widget.setObjectName(config['object_name'])
    if hasattr(widget, 'setFixedWidth') and 'width' in config:
        widget.setFixedWidth(config['width'])
    if 'properties' in config:
        for k, v in config['properties'].items():
            widget.setProperty(k, v)
    if hasattr(widget, 'setIconSize') and 'icon_size' in config:
        widget.setIconSize(QSize(*config['icon_size']))
    
    return widget, config
```

#### 4.2 Explicit Button Mapping (no inline styles)
```python
def apply_button_style(self, button: QPushButton, compact: bool):
    """Apply per-mode configuration (size/text/icon) and expose mode to QSS."""
    mode = 'compact' if compact else 'full'
    
    # Explicit mapping of buttons to their configurations
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
    
    config = button_configs.get(button, {}).get(mode) or self.BUTTON_STYLES[f'default_{mode}']
    config = config.copy()
    
    # Button-specific customizations
    if button == self.translate_btn and mode == 'full':
        config['text'] = getattr(self, '_translate_original_text', '  Translate')
    elif button == self.reader_mode_btn:
        if mode == 'full':
            config['text'] = getattr(self, '_reader_original_text', 'Reader')
            config['icon'] = self.icon_book_black
        else:
            config['icon'] = self.icon_book_white
    
    # Apply configuration
    button.setText(config['text'])
    button.setFixedSize(*config['size'])
    button.setIconSize(QSize(*config['icon_size']))
    if config.get('icon') is not None:
        button.setIcon(config['icon'])
    
    # Expose mode to QSS (style.qss uses selectors like QPushButton#translateBtn[mode="compact"])
    button.setProperty('mode', mode)
    button.style().unpolish(button); button.style().polish(button)
```

#### 4.3 Disabled State Via QSS
```python
def apply_disabled_translate_visuals(self, button: QPushButton, reason_msg: str, compact: bool) -> None:
    """Apply disabled state; visuals are handled by QSS via :disabled and [mode] selectors."""
    if not button:
        return
    
    try:
        button.setEnabled(False)
        button.setCursor(Qt.CursorShape.ForbiddenCursor)
        button.setToolTip(reason_msg or self.DEFAULT_DISABLED_TOOLTIP)
        
        # Keep mode property for QSS to select the proper visuals
        button.setProperty('mode', 'compact' if compact else 'full')
        button.style().unpolish(button); button.style().polish(button)
        
        # Optional: set icon explicitly if your QSS doesn't handle icons
        if compact:
            button.setIcon(self.icon_translate_disabled_compact)
        else:
            button.setIcon(self.icon_translate_disabled_full)
    except Exception as e:
        logger.debug(f"Failed to apply disabled translate visuals: {e}")
```

### 5. Styling Best Practices
- Centralize styles in QSS files: use `src/whisperbridge/assets/style.qss` for all visual styling
- Target widgets by objectName: use `objectName` for specific widget styling
- Avoid inline styles: do not call `setStyleSheet()` in Python code for visual styling
- Use CSS selectors and dynamic properties: leverage Qt selectors (e.g., `QPushButton#id[mode="compact"]`)
- Separate concerns: Python handles logic/state, QSS handles appearance

## Existing Configurations

### Current Standard Configurations
- `DISABLED_STYLES` - Disabled-state configuration (e.g., icons, flags), visuals in QSS
- `LANGUAGE_WIDGET_CONFIG` - Language selection widgets
- `FOOTER_WIDGET_CONFIG` - Footer widgets
- `BUTTON_STYLES` - Button configuration (size/text/icon) by type and mode; visuals in QSS
- `INFO_WIDGET_CONFIG` - Info row widgets
- `TEXT_EDIT_CONFIG` - Text edit widgets
- `WINDOW_CONFIG` - Window sizing and layout properties
- `TOP_BUTTONS_CONFIG` - Top-right control button configurations
- `RESIZE_CONFIG` - Window resize behavior settings
- `MINIBAR_WINDOW_CONFIG` - MiniBar window sizing and layout
- `MINIBAR_BUTTON_CONFIG` - MiniBar button configurations
- `READER_WINDOW_CONFIG` - Reader window sizing and font settings
- `READER_BUTTON_CONFIG` - Reader window button configurations

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