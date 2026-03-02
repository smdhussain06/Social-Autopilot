#!/usr/bin/env python3
"""
Social Media Automation Engine — Main Orchestrator.

Entry point for the GitHub Actions CRON job.
Coordinates: config → data source → AI enhancement → publishing → notifications.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from src.config import Config, load_config
from src.data_source import get_todays_content
from src.ai_enhancer import enhance_caption
from src.notifier import Level, send_alert, send_summary
from src.publishers.base import PublishResult
from src.publishers.linkedin import LinkedInPublisher
from src.publishers.youtube import YouTubePublisher
from src.publishers.instagram import InstagramPublisher


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s │ %(levelname)-7s │ %(name)-20s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def build_publishers(cfg: Config) -> list[Any]:
    """Instantiate all enabled publishers."""
    publishers = []

    if cfg.linkedin_enabled:
        publishers.append(
            LinkedInPublisher(
                access_token=cfg.linkedin_access_token,
                person_urn=cfg.linkedin_organization_urn or cfg.linkedin_person_urn,
            )
        )

    if cfg.youtube_enabled:
        publishers.append(
            YouTubePublisher(
                client_config=cfg.youtube_client_config,
                refresh_token=cfg.youtube_refresh_token,
            )
        )

    if cfg.instagram_enabled:
        publishers.append(
            InstagramPublisher(
                access_token=cfg.instagram_access_token,
                account_id=cfg.instagram_account_id,
                mode=cfg.instagram_mode,
                buffer_profile_id=cfg.buffer_profile_id,
            )
        )

    return publishers


def process_content_item(
    item: dict[str, Any],
    publishers: list[Any],
    cfg: Config,
) -> dict[str, bool]:
    """
    Process a single content item through the pipeline:
      1. Enhance caption per platform
      2. Publish to each target platform
      3. Send failsafe alerts on errors

    Returns a dict of platform → success.
    """
    logger = logging.getLogger("orchestrator")
    results: dict[str, bool] = {}
    target_platforms = item.get("platforms", [])

    for publisher in publishers:
        platform_key = publisher.platform_name.lower()

        # Skip if this content isn't targeted for this platform
        if target_platforms and platform_key not in target_platforms:
            logger.info("Skipping %s — not in target platforms.", publisher.platform_name)
            continue

        # ── AI Enhancement ──
        enhanced_caption = item.get("caption", "")
        if cfg.gemini_api_key:
            try:
                enhanced_caption = enhance_caption(
                    caption=item.get("caption", ""),
                    platform=platform_key,
                    hashtags=item.get("hashtags", []),
                    api_key=cfg.gemini_api_key,
                )
                logger.info(
                    "Caption enhanced for %s: '%s' → '%s'",
                    publisher.platform_name,
                    item.get("caption", "")[:50],
                    enhanced_caption[:50],
                )
            except Exception as exc:
                logger.warning(
                    "AI enhancement failed for %s — using original: %s",
                    publisher.platform_name,
                    exc,
                )

        # ── Publish ──
        enhanced_item = {**item, "caption": enhanced_caption}

        if cfg.dry_run:
            logger.info(
                "[DRY RUN] Would publish to %s: %s",
                publisher.platform_name,
                enhanced_caption[:80],
            )
            results[publisher.platform_name] = True
            continue

        try:
            result: PublishResult = publisher.publish(enhanced_item)
            results[publisher.platform_name] = result.success
            logger.info(str(result))

            if not result.success:
                send_alert(
                    message=f"Failed to publish to **{publisher.platform_name}**.\n"
                    f"Error: {result.error}",
                    level=Level.ERROR,
                    discord_url=cfg.discord_webhook_url,
                    slack_url=cfg.slack_webhook_url,
                    platform=publisher.platform_name,
                )
        except Exception as exc:
            results[publisher.platform_name] = False
            logger.error("%s publish error: %s", publisher.platform_name, exc)
            send_alert(
                message=f"**{publisher.platform_name}** publish crashed.\n"
                f"Error: `{exc}`",
                level=Level.ERROR,
                discord_url=cfg.discord_webhook_url,
                slack_url=cfg.slack_webhook_url,
                platform=publisher.platform_name,
                error=exc,
            )

    return results


def main() -> None:
    """Main entry point."""
    cfg = load_config()
    setup_logging(cfg.log_level)
    logger = logging.getLogger("orchestrator")

    logger.info("=" * 60)
    logger.info("  Social Media Automation Engine — Starting")
    logger.info("  Dry Run: %s", cfg.dry_run)
    logger.info("=" * 60)

    # ── Fetch content ──
    try:
        content_items = get_todays_content(
            sheets_credentials=cfg.google_sheets_credentials,
            sheet_id=cfg.google_sheet_id,
        )
    except Exception as exc:
        logger.error("Content fetch failed: %s", exc)
        send_alert(
            message=f"Content fetch failed.\nError: `{exc}`",
            level=Level.ERROR,
            discord_url=cfg.discord_webhook_url,
            slack_url=cfg.slack_webhook_url,
        )
        sys.exit(1)

    if not content_items:
        logger.info("No content scheduled for today. Exiting cleanly.")
        send_alert(
            message="No content scheduled for today. Nothing to publish.",
            level=Level.INFO,
            discord_url=cfg.discord_webhook_url,
            slack_url=cfg.slack_webhook_url,
        )
        return

    logger.info("Found %d content item(s) for today.", len(content_items))

    # ── Build publishers ──
    publishers = build_publishers(cfg)
    if not publishers:
        logger.error("No publishers available. Exiting.")
        sys.exit(1)

    # ── Process each content item ──
    all_results: dict[str, bool] = {}
    for i, item in enumerate(content_items, 1):
        logger.info("─── Processing item %d/%d ───", i, len(content_items))
        item_results = process_content_item(item, publishers, cfg)
        all_results.update(item_results)

    # ── Summary ──
    logger.info("=" * 60)
    logger.info("  Results Summary")
    for platform, success in all_results.items():
        icon = "✅" if success else "❌"
        logger.info("  %s  %s", icon, platform)
    logger.info("=" * 60)

    send_summary(
        results=all_results,
        discord_url=cfg.discord_webhook_url,
        slack_url=cfg.slack_webhook_url,
    )

    # Exit with error if ALL platforms failed
    if all_results and not any(all_results.values()):
        logger.error("All platforms failed. Exiting with error.")
        sys.exit(1)


if __name__ == "__main__":
    main()
