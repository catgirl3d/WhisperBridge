"""
Version helpers for WhisperBridge.

Provides a single function get_version() that returns the installed package version.
Prefers importlib.metadata, falls back to setuptools-scm write_to file, else '0.0.0+local'.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Final

DEFAULT_VERSION: Final[str] = "0.0.0+local"


def get_version() -> str:
    """
    Resolve the application version.

    Priority:
    1) Installed package metadata (importlib.metadata)
    2) setuptools-scm write_to artifact (whisperbridge/_version.py)
    3) Fallback to "0.0.0+local"
    """
    # 1) Try installed package metadata
    try:
        return pkg_version("whisperbridge")
    except PackageNotFoundError:
        pass
    except Exception:
        # metadata subsystem failed; continue to fallbacks
        pass

    # 2) Try setuptools-scm write_to artifact if present
    try:
        from whisperbridge._version import version as scm_version  # type: ignore

        if isinstance(scm_version, str) and scm_version:
            return scm_version
    except Exception:
        pass

    # 3) Fallback
    return DEFAULT_VERSION


__all__ = ["get_version", "DEFAULT_VERSION"]