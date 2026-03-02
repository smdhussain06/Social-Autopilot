"""
Centralized configuration loader.

All secrets and config values are pulled from environment variables
(injected by GitHub Actions Secrets). No hardcoding — ever.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Immutable configuration loaded from environment variables."""

    # ── Google Sheets ──
    google_sheet_id: str = ""
    google_sheets_credentials_b64: str = ""

    # ── Gemini AI ──
    gemini_api_key: str = ""

    # ── LinkedIn ──
    linkedin_access_token: str = ""
    linkedin_person_urn: str = ""
    linkedin_organization_urn: str = ""

    # ── YouTube ──
    youtube_client_secret_b64: str = ""
    youtube_refresh_token: str = ""

    # ── Instagram ──
    instagram_access_token: str = ""
    instagram_account_id: str = ""
    instagram_mode: str = "graph"  # "graph" or "buffer"
    buffer_profile_id: str = ""

    # ── Notifications ──
    discord_webhook_url: str = ""
    slack_webhook_url: str = ""

    # ── Runtime ──
    dry_run: bool = False
    log_level: str = "INFO"

    # ── Derived (populated post-init) ──
    _google_sheets_credentials: Optional[dict] = field(
        default=None, repr=False, compare=False
    )
    _youtube_client_config: Optional[dict] = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # Decode base64 credentials if present
        if self.google_sheets_credentials_b64:
            try:
                decoded = base64.b64decode(self.google_sheets_credentials_b64)
                object.__setattr__(
                    self, "_google_sheets_credentials", json.loads(decoded)
                )
            except Exception as exc:
                logger.warning("Failed to decode Google Sheets credentials: %s", exc)

        if self.youtube_client_secret_b64:
            try:
                decoded = base64.b64decode(self.youtube_client_secret_b64)
                object.__setattr__(
                    self, "_youtube_client_config", json.loads(decoded)
                )
            except Exception as exc:
                logger.warning("Failed to decode YouTube client secret: %s", exc)

    @property
    def google_sheets_credentials(self) -> Optional[dict]:
        return self._google_sheets_credentials

    @property
    def youtube_client_config(self) -> Optional[dict]:
        return self._youtube_client_config

    # ── Platform availability checks ──
    @property
    def linkedin_enabled(self) -> bool:
        return bool(self.linkedin_access_token and (self.linkedin_person_urn or self.linkedin_organization_urn))

    @property
    def youtube_enabled(self) -> bool:
        return bool(self.youtube_client_secret_b64 and self.youtube_refresh_token)

    @property
    def instagram_enabled(self) -> bool:
        return bool(self.instagram_access_token and self.instagram_account_id)

    @property
    def sheets_enabled(self) -> bool:
        return bool(self.google_sheets_credentials_b64 and self.google_sheet_id)

    @property
    def notifications_enabled(self) -> bool:
        return bool(self.discord_webhook_url or self.slack_webhook_url)


def load_config() -> Config:
    """Build a Config from current environment variables."""

    cfg = Config(
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
        google_sheets_credentials_b64=os.getenv("GOOGLE_SHEETS_CREDENTIALS", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        linkedin_access_token=os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
        linkedin_person_urn=os.getenv("LINKEDIN_PERSON_URN", ""),
        linkedin_organization_urn=os.getenv("LINKEDIN_ORGANIZATION_URN", ""),
        youtube_client_secret_b64=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        youtube_refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
        instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        instagram_account_id=os.getenv("INSTAGRAM_ACCOUNT_ID", ""),
        instagram_mode=os.getenv("INSTAGRAM_MODE", "graph").lower(),
        buffer_profile_id=os.getenv("BUFFER_PROFILE_ID", ""),
        discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL", ""),
        dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )

    # ── Validate critical secrets ──
    if not cfg.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — AI enhancement will be skipped.")

    if not cfg.notifications_enabled:
        logger.warning(
            "No webhook URLs configured — failsafe notifications are disabled."
        )

    enabled = []
    if cfg.linkedin_enabled:
        enabled.append("LinkedIn")
    if cfg.youtube_enabled:
        enabled.append("YouTube")
    if cfg.instagram_enabled:
        enabled.append("Instagram")

    if not enabled:
        logger.error("No publishing platforms configured. Check your secrets.")
        sys.exit(1)

    logger.info("Platforms enabled: %s", ", ".join(enabled))
    return cfg
