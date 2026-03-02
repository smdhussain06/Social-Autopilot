"""
Instagram Publisher.

Two modes:
  1. Direct — Instagram Graph API container → publish flow
  2. Buffer — Buffer Publish API

Auto-selects based on available credentials and INSTAGRAM_MODE env var.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .base import Publisher, PublishResult

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
BUFFER_API_BASE = "https://api.bufferapp.com/1"


class InstagramPublisher(Publisher):
    """Publish to Instagram via Graph API or Buffer."""

    def __init__(
        self,
        access_token: str = "",
        account_id: str = "",
        mode: str = "graph",
        buffer_profile_id: str = "",
    ) -> None:
        self.access_token = access_token
        self.account_id = account_id
        self.mode = mode.lower()
        self.buffer_profile_id = buffer_profile_id

    @property
    def platform_name(self) -> str:
        return "Instagram"

    def is_enabled(self) -> bool:
        if self.mode == "buffer":
            return bool(self.access_token and self.buffer_profile_id)
        return bool(self.access_token and self.account_id)

    def publish(self, content: dict[str, Any]) -> PublishResult:
        """Route to the appropriate publish method based on mode."""
        try:
            if self.mode == "buffer":
                return self._publish_via_buffer(content)
            return self._publish_via_graph(content)
        except Exception as exc:
            logger.error("Instagram publish failed: %s", exc)
            return PublishResult(
                platform=self.platform_name,
                success=False,
                error=str(exc),
            )

    # ─────────────────────────────────────────
    # Instagram Graph API (Direct)
    # ─────────────────────────────────────────

    def _publish_via_graph(self, content: dict[str, Any]) -> PublishResult:
        """
        Publish via Instagram Graph API.

        Flow:
          1. Create a media container (REELS for video, IMAGE for photo)
          2. Wait for container to be ready
          3. Publish the container
        """
        caption = content.get("caption", "")
        video_url = content.get("video_url", "")

        if video_url:
            return self._graph_publish_reel(caption, video_url)
        else:
            logger.warning("Instagram Graph API requires media — no video URL provided.")
            return PublishResult(
                platform=self.platform_name,
                success=False,
                error="Instagram requires a video or image URL for Graph API posting.",
            )

    def _graph_publish_reel(self, caption: str, video_url: str) -> PublishResult:
        """Create and publish a Reel (vertical video)."""

        # Step 1: Create container
        container_resp = requests.post(
            f"{GRAPH_API_BASE}/{self.account_id}/media",
            params={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json().get("id")

        if not container_id:
            raise RuntimeError("Instagram did not return a container ID.")

        logger.info("Instagram container created: %s", container_id)

        # Step 2: Wait for container to be ready (poll status)
        self._wait_for_container(container_id)

        # Step 3: Publish
        publish_resp = requests.post(
            f"{GRAPH_API_BASE}/{self.account_id}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        publish_resp.raise_for_status()
        data = publish_resp.json()
        post_id = data.get("id", "")

        logger.info("Instagram Reel published: %s", post_id)
        return PublishResult(
            platform=self.platform_name,
            success=True,
            post_id=post_id,
            post_url=f"https://www.instagram.com/reel/{post_id}/",
            raw_response=data,
        )

    def _wait_for_container(
        self, container_id: str, max_attempts: int = 30, delay: int = 5
    ) -> None:
        """Poll the container status until it's ready or times out."""
        for attempt in range(1, max_attempts + 1):
            resp = requests.get(
                f"{GRAPH_API_BASE}/{container_id}",
                params={
                    "fields": "status_code",
                    "access_token": self.access_token,
                },
                timeout=15,
            )
            resp.raise_for_status()
            status = resp.json().get("status_code", "")

            if status == "FINISHED":
                logger.info("Container %s ready (attempt %d).", container_id, attempt)
                return
            elif status == "ERROR":
                raise RuntimeError(
                    f"Instagram container {container_id} entered ERROR state."
                )

            logger.debug(
                "Container %s status: %s (attempt %d/%d)",
                container_id,
                status,
                attempt,
                max_attempts,
            )
            time.sleep(delay)

        raise TimeoutError(
            f"Instagram container {container_id} not ready after {max_attempts * delay}s."
        )

    # ─────────────────────────────────────────
    # Buffer API
    # ─────────────────────────────────────────

    def _publish_via_buffer(self, content: dict[str, Any]) -> PublishResult:
        """Publish via Buffer's Publish API."""
        caption = content.get("caption", "")
        video_url = content.get("video_url", "")

        media = []
        if video_url:
            media.append({"link": video_url, "type": "video"})

        payload = {
            "text": caption,
            "profile_ids": [self.buffer_profile_id],
            "now": True,
        }
        if media:
            payload["media"] = media[0]

        resp = requests.post(
            f"{BUFFER_API_BASE}/updates/create.json",
            params={"access_token": self.access_token},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        update_id = ""
        if "updates" in data and data["updates"]:
            update_id = data["updates"][0].get("id", "")

        success = data.get("success", False)
        logger.info("Buffer publish result: success=%s, id=%s", success, update_id)

        return PublishResult(
            platform=f"{self.platform_name} (Buffer)",
            success=success,
            post_id=update_id,
            raw_response=data,
        )
