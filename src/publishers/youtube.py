"""
YouTube Shorts Publisher.

Uploads short-form vertical video via YouTube Data API v3
using OAuth2 refresh token flow for authentication.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Optional

import requests

from .base import Publisher, PublishResult

logger = logging.getLogger(__name__)

YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubePublisher(Publisher):
    """Upload YouTube Shorts via the Data API v3."""

    def __init__(
        self,
        client_config: Optional[dict] = None,
        refresh_token: str = "",
    ) -> None:
        self.client_config = client_config or {}
        self.refresh_token = refresh_token
        self._access_token: str = ""

    @property
    def platform_name(self) -> str:
        return "YouTube"

    def is_enabled(self) -> bool:
        return bool(self.client_config and self.refresh_token)

    def _get_access_token(self) -> str:
        """Exchange refresh token for a fresh access token."""
        if self._access_token:
            return self._access_token

        installed = self.client_config.get("installed") or self.client_config.get("web", {})
        client_id = installed.get("client_id", "")
        client_secret = installed.get("client_secret", "")

        if not client_id or not client_secret:
            raise ValueError("YouTube client_id or client_secret missing from config.")

        resp = requests.post(
            YOUTUBE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        logger.info("YouTube access token refreshed.")
        return self._access_token

    def publish(self, content: dict[str, Any]) -> PublishResult:
        """
        Upload a video as a YouTube Short.

        Steps:
          1. Download video from URL to a temp file
          2. Refresh OAuth2 access token
          3. Upload via resumable upload endpoint
        """
        caption = content.get("caption", "")
        video_url = content.get("video_url", "")
        hashtags = content.get("hashtags", [])

        if not video_url:
            logger.warning("No video URL for YouTube — skipping.")
            return PublishResult(
                platform=self.platform_name,
                success=False,
                error="No video URL provided.",
            )

        try:
            # Download video
            video_path = self._download_video(video_url)

            # Get access token
            access_token = self._get_access_token()

            # Build metadata
            tags = [h.lstrip("#") for h in hashtags]
            title = caption[:100] if caption else "New Short"
            description = f"{caption}\n\n#Shorts {' '.join(hashtags)}"

            # Upload
            result = self._upload_video(
                access_token, video_path, title, description, tags
            )

            # Cleanup
            if os.path.exists(video_path):
                os.remove(video_path)

            return result

        except Exception as exc:
            logger.error("YouTube publish failed: %s", exc)
            return PublishResult(
                platform=self.platform_name,
                success=False,
                error=str(exc),
            )

    def _download_video(self, url: str) -> str:
        """Download a video to a temporary file."""
        logger.info("Downloading video from %s", url)
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()

        suffix = ".mp4"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp.close()

        file_size = os.path.getsize(tmp.name)
        logger.info("Video downloaded: %s (%.1f MB)", tmp.name, file_size / 1e6)
        return tmp.name

    def _upload_video(
        self,
        access_token: str,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
    ) -> PublishResult:
        """Upload video using the YouTube Data API v3 resumable upload."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
                "shorts": {"shortsVideoStatus": "SHORT"},
            },
        }

        # Step 1: Initiate resumable upload
        init_resp = requests.post(
            YOUTUBE_UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers=headers,
            json=metadata,
            timeout=30,
        )
        init_resp.raise_for_status()
        upload_url = init_resp.headers.get("Location")

        if not upload_url:
            raise RuntimeError("YouTube did not return a resumable upload URL.")

        # Step 2: Upload the video binary
        file_size = os.path.getsize(video_path)
        with open(video_path, "rb") as f:
            upload_resp = requests.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size),
                },
                data=f,
                timeout=600,
            )
        upload_resp.raise_for_status()
        data = upload_resp.json()

        video_id = data.get("id", "")
        post_url = f"https://youtube.com/shorts/{video_id}" if video_id else ""

        logger.info("YouTube Short uploaded: %s", post_url)
        return PublishResult(
            platform=self.platform_name,
            success=True,
            post_id=video_id,
            post_url=post_url,
            raw_response=data,
        )
