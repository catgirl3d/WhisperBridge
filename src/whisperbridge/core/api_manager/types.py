"""
Type definitions for the API Manager package.

This module contains core data types used across the API manager:
- ModelSource: Sources for model listings
"""

from enum import Enum


class ModelSource(str, Enum):
    """Sources for model listings."""

    CACHE = "cache"
    API = "api"
    API_TEMP_KEY = "api_temp_key"
    UNCONFIGURED = "unconfigured"
    FALLBACK = "fallback"
    ERROR = "error"


__all__ = ["ModelSource"]
