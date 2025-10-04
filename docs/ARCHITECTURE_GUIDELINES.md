# WhisperBridge Architecture Guidelines

## Overview
WhisperBridge is a desktop OCR and translation application built with PySide6/Qt. This document outlines the project structure and key architectural principles to maintain code quality and consistency.

## Project Structure

### Core Layers
```
src/whisperbridge/
├── core/           # Core managers, config, API clients
├── services/       # Business logic services (singletons)
├── ui_qt/         # Qt UI components and workers
├── providers/     # External API adapters
├── utils/         # Utility functions
└── models/        # Data models (if needed)
```

### Key Directories
- **core/**: Singleton managers (API, config, keyboard, logger, settings)
- **services/**: Business logic services orchestrated by Qt app
- **ui_qt/**: Qt widgets, windows, workers (background tasks)
- **providers/**: API provider adapters (Google, OpenAI)
- **utils/**: Pure functions, helpers, no state

## Architectural Principles

### 1. Separation of Concerns
- **UI Layer** (`ui_qt/`): Only UI logic, no business rules
- **Service Layer** (`services/`): All business logic, data operations
- **Core Layer** (`core/`): Infrastructure, configuration, external APIs
- **Utils** (`utils/`): Stateless helpers, pure functions

### 2. Threading Model
- **Main Thread**: Qt UI only - no blocking operations
- **Worker Threads**: Heavy tasks via `QThread` + `QObject` workers
- **Workers**: Located in `ui_qt/workers.py`, emit signals back to main thread
- **Worker Factory**: Use `QtApp.create_and_run_worker` for creating and managing worker threads. All workers should emit `finished` for results and `error` for failures to ensure consistent error handling.
- **Never**: Block UI thread with I/O, network, or CPU-intensive tasks

### 3. Configuration Management
- **Centralized**: `config_service` singleton manages all settings
- **Observer Pattern**: Notify components of setting changes
- **Caching**: Built-in caching with TTL in `ConfigService`
- **Persistence**: `settings_manager` handles file I/O

### 4. Service Design
- **Singletons**: Services are global singletons (get_*_service())
- **Dependencies**: Services inject dependencies, not import directly
- **Async Operations**: Use workers for background tasks, not async/await
- **Error Handling**: Services handle errors, emit appropriate signals

### 5. UI Architecture
- **Coordinator Pattern**: `app.py` orchestrates UI lifecycle
- **Delegation**: UI components delegate to `UIService`
- **Signals/Slots**: All communication between threads/components
- **No Direct Coupling**: UI widgets don't import services directly

## Development Guidelines

### Code Organization
- **One Responsibility**: Each module/class has single purpose
- **Import Order**: Standard library → Third-party → Local (core → services → ui)
- **Naming**: snake_case for modules/functions, PascalCase for classes
- **Docstrings**: All public methods documented with type hints

### Threading Rules
- **Qt Main Thread Only**: UI updates, widget manipulation
- **Worker Threads**: I/O, network, CPU-heavy tasks
- **Signal Communication**: Workers emit signals, main thread handles results
- **No Shared State**: Avoid mutable shared state between threads

### Error Handling
- **Graceful Degradation**: App continues working if non-critical services fail
- **User Feedback**: Show errors via notifications/tray, not exceptions
- **Logging**: All errors logged with context, not exposed to user
- **Recovery**: Implement retry logic for transient failures

### Testing Strategy
- **Unit Tests**: Pure functions, utilities, isolated logic
- **Integration Tests**: Service interactions, API calls
- **UI Tests**: Critical user flows (if automated)
- **Manual Testing**: UI/UX, hotkeys, system integration

### Adding New Features
- **Follow Structure**: Place code in appropriate layer/directory
- **Use Patterns**: Observer for config, workers for async tasks
- **Document**: Update this file if introducing new patterns
- **Test**: Add tests before merging, ensure no regressions

### Configuration Changes
- **Schema First**: Update `core/config.py` Settings model
- **Migration**: Handle backward compatibility in settings_manager
- **Observers**: Add observers if components need to react
- **Validation**: Validate settings on load/save

This architecture ensures maintainable, testable, and performant code. When in doubt, follow existing patterns in the codebase.