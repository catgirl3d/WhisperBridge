"""
Type definitions for the API Manager package.

This module contains core data types used across the API manager:
- ModelSource: Sources for model listings
- APIUsage: API usage statistics
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ModelSource(str, Enum):
    """Sources for model listings."""

    CACHE = "cache"
    API = "api"
    API_TEMP_KEY = "api_temp_key"
    UNCONFIGURED = "unconfigured"
    FALLBACK = "fallback"
    ERROR = "error"


@dataclass
class APIUsage:
    """API usage statistics."""

    requests_count: int = 0
    tokens_used: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_request_time: Optional[datetime] = None
    rate_limit_hits: int = 0


__all__ = [
    "ModelSource",
    "APIUsage",
]
