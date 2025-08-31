# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure setup
- Basic package organization with modular architecture
- Configuration management with Pydantic settings
- Environment variable support with .env files
- Comprehensive dependency management
- Development and production requirement files
- Modern Python packaging with pyproject.toml
- Logging system with Loguru
- Core application framework

### Changed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- N/A

## [1.0.0] - 2025-01-01

### Added
- Desktop application for quick text translation
- OCR functionality with EasyOCR and Tesseract fallback
- GPT API integration for translations
- Global hotkey support (Ctrl+Shift+T)
- Interactive screen capture interface
- Overlay windows for displaying results
- System tray integration
- Settings management with secure API key storage
- Multi-language support for OCR and translation
- Caching system for improved performance
- Comprehensive error handling and logging
- Cross-platform compatibility (Windows, macOS, Linux)

### Changed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- Secure API key storage using system keyring
- Input validation for all user inputs
- Safe handling of sensitive configuration data

## [0.1.0] - 2024-12-01

### Added
- Project initialization
- Basic architecture design
- Initial documentation
- Development environment setup

---

## Types of changes
- `Added` for new features
- `Changed` for changes in existing functionality
- `Deprecated` for soon-to-be removed features
- `Removed` for now removed features
- `Fixed` for any bug fixes
- `Security` in case of vulnerabilities

## Versioning
This project uses [Semantic Versioning](https://semver.org/).

Given a version number MAJOR.MINOR.PATCH, increment the:

- MAJOR version when you make incompatible API changes
- MINOR version when you add functionality in a backwards compatible manner
- PATCH version when you make backwards compatible bug fixes

Additional labels for pre-release and build metadata are available as extensions to the MAJOR.MINOR.PATCH format.