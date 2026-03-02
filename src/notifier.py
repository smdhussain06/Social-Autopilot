"""
Failsafe notification module.

Sends formatted alerts to Discord and/or Slack webhooks
when posts fail or when the daily run completes.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class Level(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# ── Color mapping for Discord embeds ──
_DISCORD_COLORS = {
    Level.INFO: 0x2ECC71,      # Green
    Level.WARNING: 0xF39C12,   # Orange
    Level.ERROR: 0xE74C3C,     # Red
}

_LEVEL_EMOJI = {
    Level.INFO: "✅",
    Level.WARNING: "⚠️",
    Level.ERROR: "🚨",
}


def send_alert(
    message: str,
    level: Level = Level.INFO,
    discord_url: str = "",
    slack_url: str = "",
    platform: str = "",
    error: Optional[Exception] = None,
) -> None:
    """
    Send a formatted alert to Discord and/or Slack.

    Args:
        message: Human-readable alert message.
        level: Severity level (INFO, WARNING, ERROR).
        discord_url: Discord webhook URL.
        slack_url: Slack incoming webhook URL.
        platform: Which social platform this relates to.
        error: Optional exception for traceback inclusion.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    emoji = _LEVEL_EMOJI.get(level, "ℹ️")

    # Build error details
    error_detail = ""
    if error:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        error_detail = "".join(tb)[-500:]  # Last 500 chars of traceback

    if discord_url:
        _send_discord(discord_url, message, level, timestamp, emoji, platform, error_detail)

    if slack_url:
        _send_slack(slack_url, message, level, timestamp, emoji, platform, error_detail)

    if not discord_url and not slack_url:
        logger.warning("No webhook URLs configured — alert not sent: %s", message)


def _send_discord(
    url: str,
    message: str,
    level: Level,
    timestamp: str,
    emoji: str,
    platform: str,
    error_detail: str,
) -> None:
    """Send a rich embed to a Discord webhook."""
    embed = {
        "title": f"{emoji}  Social Media Bot — {level.value}",
        "description": message,
        "color": _DISCORD_COLORS.get(level, 0x95A5A6),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": [],
        "footer": {"text": "Social Media Automation Engine"},
    }

    if platform:
        embed["fields"].append({"name": "Platform", "value": platform, "inline": True})

    embed["fields"].append({"name": "Timestamp", "value": timestamp, "inline": True})

    if error_detail:
        embed["fields"].append({
            "name": "Error Traceback",
            "value": f"```\n{error_detail}\n```",
            "inline": False,
        })

    payload = {"embeds": [embed]}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Discord alert sent (%s).", level.value)
    except Exception as exc:
        logger.error("Failed to send Discord alert: %s", exc)


def _send_slack(
    url: str,
    message: str,
    level: Level,
    timestamp: str,
    emoji: str,
    platform: str,
    error_detail: str,
) -> None:
    """Send a formatted message to a Slack incoming webhook."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Social Media Bot — {level.value}",
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": message},
        },
    ]

    context_elements = [
        {"type": "mrkdwn", "text": f"*Time:* {timestamp}"},
    ]
    if platform:
        context_elements.append({"type": "mrkdwn", "text": f"*Platform:* {platform}"})

    blocks.append({"type": "context", "elements": context_elements})

    if error_detail:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{error_detail}```"},
        })

    payload = {"blocks": blocks}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Slack alert sent (%s).", level.value)
    except Exception as exc:
        logger.error("Failed to send Slack alert: %s", exc)


def send_summary(
    results: dict[str, bool],
    discord_url: str = "",
    slack_url: str = "",
) -> None:
    """
    Send a daily summary of publish results.

    Args:
        results: Map of platform -> success (True/False).
    """
    total = len(results)
    success = sum(1 for v in results.values() if v)
    failed = total - success

    status = "All Clear" if failed == 0 else f"{failed}/{total} Failed"
    level = Level.INFO if failed == 0 else Level.ERROR

    lines = [f"**Daily Publish Summary — {status}**\n"]
    for platform, ok in results.items():
        icon = "✅" if ok else "❌"
        lines.append(f"{icon}  **{platform}**")

    message = "\n".join(lines)
    send_alert(message, level=level, discord_url=discord_url, slack_url=slack_url)
