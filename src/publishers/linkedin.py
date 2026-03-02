import logging
import time
from typing import Any, List
import requests
from .base import Publisher, PublishResult

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"

class LinkedInPublisher(Publisher):
    """Publish posts to a LinkedIn personal profile with multi-image support."""

    def __init__(self, access_token: str, person_urn: str) -> None:
        self.access_token = access_token
        self.person_urn = person_urn
        self._headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    @property
    def platform_name(self) -> str:
        return "LinkedIn"

    def is_enabled(self) -> bool:
        return bool(self.access_token and self.person_urn)

    def publish(self, content: dict[str, Any]) -> PublishResult:
        """
        Create a LinkedIn UGC post with text and multiple images.
        """
        caption = content.get("caption", "")
        media_paths = content.get("media_paths", [])

        try:
            if media_paths:
                return self._post_with_images(caption, media_paths)
            return self._post_text(caption)
        except Exception as exc:
            logger.error("LinkedIn publish failed: %s", exc)
            return PublishResult(
                platform=self.platform_name,
                success=False,
                error=str(exc),
            )

    def _post_text(self, text: str) -> PublishResult:
        """Create a text-only post."""
        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        resp = requests.post(f"{LINKEDIN_API_BASE}/ugcPosts", headers=self._headers, json=payload, timeout=30)
        resp.raise_for_status()
        return self._format_result(resp.json())

    def _post_with_images(self, text: str, paths: List[str]) -> PublishResult:
        """Handle the 3-step handshake to upload multiple images and post."""
            asset_urn = reg_resp['value']['asset']

            # Step 2: Upload Binary
            with open(path, 'rb') as f:
                requests.put(upload_url, headers={"Authorization": f"Bearer {self.access_token}"}, data=f)
            
            media_urns.append(asset_urn)
            logger.info(f"Uploaded image: {path} -> {asset_urn}")

        # Step 3: Create UGC Post with all assets
        media_content = []
        for urn in media_urns:
            media_content.append({
                "status": "READY",
                "media": urn,
                "title": {"text": "MCP-LiteLabs Walkthrough"}
            })

        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": media_content
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        resp = requests.post(f"{LINKEDIN_API_BASE}/ugcPosts", headers=self._headers, json=payload, timeout=30)
        resp.raise_for_status()
        return self._format_result(resp.json())

    def _format_result(self, data: dict) -> PublishResult:
        post_id = data.get("id", "")
        return PublishResult(
            platform=self.platform_name,
            success=True,
            post_id=post_id,
            post_url=f"https://www.linkedin.com/feed/update/{post_id}/",
            raw_response=data
        )
