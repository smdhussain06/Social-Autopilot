"""
Data source module.

Supports two content backends:
  1. Google Sheets (primary) — reads from a structured spreadsheet
  2. JSON Manifest (fallback) — reads from a local JSON file

Each source returns a list of ContentItem dicts for today's scheduled posts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Content item type ──
ContentItem = dict[str, Any]
# Expected keys: date, caption, video_url, hashtags, platforms


def _parse_date(value: str) -> Optional[datetime]:
    """Try to parse a date string in common formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _normalize_item(raw: dict) -> ContentItem:
    """Normalize a raw row/dict into a standard ContentItem."""
    hashtags = raw.get("hashtags", [])
    if isinstance(hashtags, str):
        hashtags = [h.strip() for h in hashtags.replace(",", " ").split() if h.strip()]

    platforms = raw.get("platforms", [])
    if isinstance(platforms, str):
        platforms = [p.strip().lower() for p in platforms.split(",") if p.strip()]

    return {
        "date": raw.get("date", ""),
        "caption": raw.get("caption", ""),
        "video_url": raw.get("video_url", ""),
        "hashtags": hashtags,
        "platforms": platforms,
    }


# ─────────────────────────────────────────────
# Google Sheets Source
# ─────────────────────────────────────────────

class GoogleSheetsSource:
    """Reads content rows from a Google Sheet via service account auth."""

    def __init__(self, credentials_dict: dict, sheet_id: str) -> None:
        self.credentials_dict = credentials_dict
        self.sheet_id = sheet_id

    def fetch_all(self) -> list[ContentItem]:
        """Fetch all rows from the first worksheet."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ]
            creds = Credentials.from_service_account_info(
                self.credentials_dict, scopes=scopes
            )
            client = gspread.authorize(creds)
            sheet = client.open_by_key(self.sheet_id)
            worksheet = sheet.sheet1
            records = worksheet.get_all_records()

            items = [_normalize_item(row) for row in records]
            logger.info(
                "Fetched %d content items from Google Sheet '%s'.",
                len(items),
                sheet.title,
            )
            return items

        except Exception as exc:
            logger.error("Google Sheets fetch failed: %s", exc)
            raise

    def fetch_today(self) -> list[ContentItem]:
        """Return only items scheduled for today (UTC)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_items = self.fetch_all()
        return [
            item
            for item in all_items
            if _parse_date(item.get("date", ""))
            and _parse_date(item["date"]).strftime("%Y-%m-%d") == today
        ]


# ─────────────────────────────────────────────
# JSON Manifest Source
# ─────────────────────────────────────────────

class JsonManifestSource:
    """Reads content from a local JSON manifest file."""

    def __init__(self, path: str | Path = "content_manifest.json") -> None:
        self.path = Path(path)

    def fetch_all(self) -> list[ContentItem]:
        """Load all entries from the JSON file."""
        if not self.path.exists():
            logger.warning("JSON manifest not found at %s", self.path)
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = [_normalize_item(entry) for entry in data]
            logger.info(
                "Loaded %d content items from JSON manifest '%s'.",
                len(items),
                self.path.name,
            )
            return items
        except Exception as exc:
            logger.error("JSON manifest read failed: %s", exc)
            raise

    def fetch_today(self) -> list[ContentItem]:
        """Return only items scheduled for today (UTC)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_items = self.fetch_all()
        return [
            item
            for item in all_items
            if _parse_date(item.get("date", ""))
            and _parse_date(item["date"]).strftime("%Y-%m-%d") == today
        ]


# ─────────────────────────────────────────────
# Smart loader
# ─────────────────────────────────────────────

def get_todays_content(
    sheets_credentials: Optional[dict] = None,
    sheet_id: str = "",
    manifest_path: str = "content_manifest.json",
) -> list[ContentItem]:
    """
    Fetch today's content items.

    Strategy:
      1. Try Google Sheets if credentials are available.
      2. Fall back to the local JSON manifest.
      3. If neither has today's content, return an empty list.
    """
    items: list[ContentItem] = []

    # Primary: Google Sheets
    if sheets_credentials and sheet_id:
        try:
            source = GoogleSheetsSource(sheets_credentials, sheet_id)
            items = source.fetch_today()
            if items:
                logger.info("Using %d item(s) from Google Sheets.", len(items))
                return items
            logger.info("No items for today in Google Sheets — trying JSON fallback.")
        except Exception:
            logger.warning("Sheets failed — falling back to JSON manifest.")

    # Fallback: JSON manifest
    try:
        source = JsonManifestSource(manifest_path)
        items = source.fetch_today()
        if items:
            logger.info("Using %d item(s) from JSON manifest.", len(items))
            return items
    except Exception:
        logger.warning("JSON manifest fallback also failed.")

    logger.warning("No content items found for today.")
    return []
