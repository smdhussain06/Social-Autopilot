"""
AI Caption Enhancer using Google Gemini 1.5 Flash.

Takes raw captions and makes them smarter, faster, and more charismatic
with platform-specific tone adjustments.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Platform tone profiles ──
PLATFORM_TONES = {
    "linkedin": (
        "Professional yet bold. Use strong hooks, thought-leadership language, "
        "and a compelling call-to-action. Keep it concise but authoritative. "
        "No emojis overload — one or two max. End with a question to spark engagement."
    ),
    "youtube": (
        "High-energy and scroll-stopping. Write like a viral Shorts caption — "
        "short, punchy, curiosity-driven. Use 1-2 emojis. "
        "Front-load the hook in the first 5 words."
    ),
    "instagram": (
        "Trendy, relatable, and visually expressive. Use 2-4 relevant emojis. "
        "Write in a conversational tone that feels authentic. "
        "Include a soft CTA like 'Save this' or 'Tag someone who needs this'."
    ),
}

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def _build_prompt(caption: str, platform: str, hashtags: list[str]) -> str:
    """Construct the Gemini prompt for caption enhancement."""
    tone = PLATFORM_TONES.get(platform, PLATFORM_TONES["instagram"])
    hashtag_str = " ".join(hashtags) if hashtags else ""

    return (
        f"You are an elite social media copywriter. "
        f"Rewrite the following caption for {platform.upper()} to make it "
        f"sound smarter, faster, and more charismatic.\n\n"
        f"TONE GUIDELINES:\n{tone}\n\n"
        f"ORIGINAL CAPTION:\n\"{caption}\"\n\n"
        f"HASHTAGS TO INCLUDE:\n{hashtag_str}\n\n"
        f"RULES:\n"
        f"- Return ONLY the enhanced caption text (no explanations).\n"
        f"- Weave the hashtags naturally at the end.\n"
        f"- Keep it under 280 characters for YouTube, under 2200 for others.\n"
        f"- Preserve the core message and intent.\n"
    )


def enhance_caption(
    caption: str,
    platform: str,
    hashtags: list[str] | None = None,
    api_key: str = "",
) -> str:
    """
    Enhance a caption using Gemini 1.5 Flash.

    Returns the enhanced caption, or the original if enhancement fails.
    """
    if not api_key:
        logger.warning("No Gemini API key — returning original caption.")
        return _append_hashtags(caption, hashtags)

    hashtags = hashtags or []
    prompt = _build_prompt(caption, platform, hashtags)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)

            enhanced = response.text.strip()
            if enhanced:
                logger.info(
                    "Caption enhanced for %s (attempt %d/%d).",
                    platform,
                    attempt,
                    MAX_RETRIES,
                )
                return enhanced

        except Exception as exc:
            logger.warning(
                "Gemini enhancement attempt %d/%d failed: %s",
                attempt,
                MAX_RETRIES,
                exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    logger.error("All Gemini enhancement attempts failed — using original caption.")
    return _append_hashtags(caption, hashtags)


def _append_hashtags(caption: str, hashtags: Optional[list[str]]) -> str:
    """Append hashtags to a caption if they aren't already present."""
    if not hashtags:
        return caption
    tag_str = " ".join(hashtags)
    if tag_str in caption:
        return caption
    return f"{caption}\n\n{tag_str}"
