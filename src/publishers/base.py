"""
Abstract base class for all platform publishers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of a publish operation."""

    platform: str
    success: bool
    post_url: str = ""
    post_id: str = ""
    error: Optional[str] = None
    raw_response: Optional[dict] = None

    def __str__(self) -> str:
        status = "✅ SUCCESS" if self.success else "❌ FAILED"
        url_info = f" → {self.post_url}" if self.post_url else ""
        err_info = f" | Error: {self.error}" if self.error else ""
        return f"[{self.platform}] {status}{url_info}{err_info}"


class Publisher(ABC):
    """Abstract publisher that all platform publishers must implement."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g., 'linkedin')."""
        ...

    @abstractmethod
    def publish(self, content: dict[str, Any]) -> PublishResult:
        """
        Publish content to the platform.

        Args:
            content: A ContentItem dict with keys:
                - caption: Enhanced caption text
                - video_url: URL to the video (may be empty)
                - hashtags: List of hashtag strings
                - platforms: List of target platform names

        Returns:
            PublishResult with success status and metadata.
        """
        ...

    def is_enabled(self) -> bool:
        """Check if this publisher has the required credentials."""
        return True
