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
            # Step 0: Parse mentions from caption
            text, attributes = self._parse_mentions(caption)
            
            if media_paths:
                return self._post_with_images(text, attributes, media_paths)
            return self._post_text(text, attributes)
        except Exception as exc:
            logger.error("LinkedIn publish failed: %s", exc)
            return PublishResult(
                platform=self.platform_name,
                success=False,
                error=str(exc),
            )

    def _post_text(self, text: str, attributes: List[dict] = None) -> PublishResult:
        """Create a text-only post."""
        share_content = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE",
        }
        if attributes:
            share_content["shareCommentary"]["attributes"] = attributes

        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": share_content
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        resp = requests.post(f"{LINKEDIN_API_BASE}/ugcPosts", headers=self._headers, json=payload, timeout=30)
        resp.raise_for_status()
        return self._format_result(resp.json())

    def _post_with_images(self, text: str, attributes: List[dict], paths: List[str]) -> PublishResult:
        """Handle the 3-step handshake to upload multiple images and post."""
        from pathlib import Path
        media_urns = []
        for path in paths:
            # Resolve relative paths
            abs_path = Path(path)
            if not abs_path.is_absolute():
                abs_path = Path.cwd() / path

            # Check if file exists
            if not abs_path.exists():
                logger.warning(f"Media file not found: {abs_path}. Skipping.")
                continue

            # Step 1: Register Upload
            register_payload = {
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": self.person_urn,
                    "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]
                }
            }
            reg_resp = requests.post(f"{LINKEDIN_API_BASE}/assets?action=registerUpload", headers=self._headers, json=register_payload).json()
            upload_url = reg_resp['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
            asset_urn = reg_resp['value']['asset']

            # Step 2: Upload Binary
            with open(abs_path, 'rb') as f:
                requests.put(upload_url, data=f)
            
            media_urns.append(asset_urn)
            logger.info(f"Uploaded image: {abs_path} -> {asset_urn}")

        if not media_urns and paths:
            return PublishResult(success=False, platform="LinkedIn", error="Failed to upload any images.")

        # Step 3: Create UGC Post with all assets
        media_content = []
        for urn in media_urns:
            media_content.append({
                "status": "READY",
                "media": urn,
                "title": {"text": "MCP-LiteLabs Walkthrough"}
            })

        share_content = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "IMAGE",
            "media": media_content
        }
        if attributes:
            share_content["shareCommentary"]["attributes"] = attributes

        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": share_content
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

    def _parse_mentions(self, text: str) -> tuple[str, List[dict]]:
        """
        Parses custom mention syntax @[urn:li:person:XXXX:0] or @[urn:li:organization:XXXX:0]
        and returns the cleaned text plus the attributes array for LinkedIn's API.
        
        Syntax: @[URN:INDEX]
        Example: "Built by @[urn:li:person:123:0]" -> "Built by Mohammad Hussain"
        Note: We currently don't know the 'name' from just the URN, so the mention
        will show the URN in the 'text' if not replaced. 
        Actually, LinkedIn's UGC API expects the URN to be IN THE TEXT where the mention is.
        Wait, no. The text should have the *display name*, and attributes point to the index.
        """
        import re
        attributes = []
        
        # This regex looks for @[urn:li:XXX:YYY:0]
        # We'll replace it with a placeholder or just use the URN as text for now
        # Actually, for the best look, we should probably just leave the URN in the text
        # and LinkedIn will often resolve it, but the PROFESSIONAL way is:
        # Text: "Built by Mohammad Hussain"
        # Attribute: { start: 9, length: 16, value: "urn:li:person:XXX" }
        
        # For simplicity, let's keep the URN in the text but format it as requested
        # Actually, the user's screenshot showed @[urn:li:person:pjK3tcVg0K:0]
        # Let's replace the whole @[...] with just... what? 
        # If we don't know the name, we'll just use the URN.
        
        pattern = r"@\[(urn:li:(person|organization):[\w-]+):0\]"
        
        def replace_mention(match):
            urn = match.group(1)
            start_index = match.start()
            
            # Determine display text
            display_text = "Mohammad Hussain" if "person:pjK3tcVg0K" in urn else "A Generative Slice" if "organization:107795425" in urn else urn
            
            # LinkedIn requires specific object types based on URN type
            if "person" in urn:
                attr_value = {"com.linkedin.common.MemberUrn": urn}
            else:
                attr_value = {"com.linkedin.common.CompanyUrn": urn}

            attributes.append({
                "start": start_index,
                "length": len(display_text),
                "value": attr_value
            })
            return display_text

        cleaned_text = re.sub(pattern, replace_mention, text)
        return cleaned_text, attributes
