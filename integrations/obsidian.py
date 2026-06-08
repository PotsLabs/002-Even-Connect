"""
Obsidian integration — fetch notes/media and send to G1 glasses.

This module shows how external data sources (Obsidian vault) can be connected
to the glasses via the protocol layer.

Architecture:
  Obsidian (local vault / REST API)
    ↓ fetch note/image
  obsidian.py (this file) — format & prepare
    ↓ calls
  protocol.connect — send to glasses (text, images, etc.)
    ↓ via
  protocol.bmp — encode images
  protocol.commands — build packets

Usage:
    from integrations.obsidian import sync_note, send_obsidian_image
    from protocol.connect import GlassesManager

    manager = GlassesManager()
    await manager.scan_and_connect(timeout=12)

    # Send note as text
    await sync_note(manager, "/path/to/vault", "My Note")

    # Send image from attachments
    await send_obsidian_image(manager, "/path/to/image.png", stereo=True)

    await manager.disconnect_all()
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx

from protocol.connect import (
    GlassesManager,
    send_text,
    send_bmp_to_glass,
    stereo_pair,
)
from protocol.bmp import to_bmp_bytes, build_frames, build_crc_cmd

logger = logging.getLogger(__name__)


# ── Obsidian Vault Access ──────────────────────────────────────────────────────

class ObsidianVault:
    """Access local Obsidian vault or remote API."""

    def __init__(self, vault_path: Optional[str] = None, api_url: Optional[str] = None, api_token: Optional[str] = None):
        """
        Initialize vault access.

        Args:
            vault_path: Path to local .obsidian folder (for direct file access)
            api_url: Remote Obsidian REST API endpoint (e.g., http://localhost:27124)
            api_token: API token for remote access
        """
        self.vault_path = Path(vault_path) if vault_path else None
        self.api_url = api_url
        self.api_token = api_token
        self.http_client = httpx.AsyncClient(timeout=10.0) if api_url else None

    async def fetch_note(self, note_name: str) -> str:
        """
        Fetch markdown note content.

        Args:
            note_name: Note name or path (e.g., "Daily Notes/2026-06-09")

        Returns:
            Markdown content as string
        """
        if self.api_url:
            return await self._fetch_note_api(note_name)
        elif self.vault_path:
            return self._fetch_note_local(note_name)
        else:
            raise ValueError("No vault path or API URL configured")

    async def _fetch_note_api(self, note_name: str) -> str:
        """Fetch via Obsidian REST API (requires plugin)."""
        try:
            url = urljoin(self.api_url, f"/api/vault/query/search")
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            resp = await self.http_client.get(url, params={"query": note_name}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data:
                return data[0].get("content", "")
            return f"Note '{note_name}' not found"
        except Exception as e:
            logger.error(f"Obsidian API fetch failed: {e}")
            return f"Error fetching note: {e}"

    def _fetch_note_local(self, note_name: str) -> str:
        """Fetch from local vault directory."""
        try:
            note_path = self.vault_path.parent / f"{note_name}.md"
            if not note_path.exists():
                note_path = self.vault_path.parent / note_name / "index.md"

            if note_path.exists():
                with open(note_path, "r", encoding="utf-8") as f:
                    return f.read()
            return f"Note '{note_name}' not found at {note_path}"
        except Exception as e:
            logger.error(f"Local vault fetch failed: {e}")
            return f"Error reading note: {e}"

    async def fetch_attachment(self, attachment_name: str) -> bytes:
        """
        Fetch attachment (image, file) from vault.

        Args:
            attachment_name: Filename (e.g., "screenshot.png")

        Returns:
            File bytes
        """
        if self.vault_path:
            return self._fetch_attachment_local(attachment_name)
        else:
            raise ValueError("Attachment fetch only supported for local vaults")

    def _fetch_attachment_local(self, attachment_name: str) -> bytes:
        """Fetch attachment from local attachments folder."""
        try:
            attach_path = self.vault_path.parent / "attachments" / attachment_name
            if attach_path.exists():
                with open(attach_path, "rb") as f:
                    return f.read()
            raise FileNotFoundError(f"Attachment not found: {attach_path}")
        except Exception as e:
            logger.error(f"Attachment fetch failed: {e}")
            raise

    async def close(self):
        """Close HTTP client."""
        if self.http_client:
            await self.http_client.aclose()


# ── Markdown → Display Conversion ──────────────────────────────────────────────

def format_markdown_for_display(markdown: str, max_lines: int = 20) -> str:
    """
    Convert Obsidian markdown to plain text suitable for glasses display.

    - Remove markdown syntax (# ** [] etc.)
    - Limit to max_lines
    - Preserve line breaks for readability
    """
    lines = markdown.split("\n")

    cleaned = []
    for line in lines[:max_lines]:
        # Remove markdown headings
        line = line.lstrip("#").strip()
        # Remove bold/italic
        line = line.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
        # Remove links but keep text
        import re

        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        # Remove code blocks
        line = line.replace("`", "").replace("```", "")

        if line:
            cleaned.append(line)

    return "\n".join(cleaned)


# ── Send to Glasses ────────────────────────────────────────────────────────────

async def sync_note(
    manager: GlassesManager,
    vault_path: str,
    note_name: str,
    api_url: Optional[str] = None,
) -> bool:
    """
    Fetch note from Obsidian and send to glasses as text.

    Args:
        manager: GlassesManager instance (must be connected)
        vault_path: Path to Obsidian vault folder
        note_name: Name of note to fetch
        api_url: Optional Obsidian REST API URL

    Returns:
        True if sent successfully, False otherwise
    """
    if not manager.left_glass and not manager.right_glass:
        logger.error("Not connected to glasses")
        return False

    try:
        vault = ObsidianVault(vault_path=vault_path, api_url=api_url)
        content = await vault.fetch_note(note_name)
        await vault.close()

        # Format for display
        display_text = format_markdown_for_display(content)

        # Send via protocol
        await send_text(manager, display_text)
        logger.info(f"Sent note '{note_name}' to glasses")
        return True

    except Exception as e:
        logger.error(f"Failed to sync note: {e}")
        return False


async def send_obsidian_image(
    manager: GlassesManager,
    vault_path: str,
    image_name: str,
    stereo: bool = True,
    max_disparity: int = 10,
) -> tuple[bool, bool]:
    """
    Fetch image from Obsidian attachments and send to glasses.

    Args:
        manager: GlassesManager instance (must be connected)
        vault_path: Path to Obsidian vault folder
        image_name: Attachment filename
        stereo: If True, create stereo pair; if False, send to both as-is
        max_disparity: Max pixel shift for stereo depth

    Returns:
        (left_ok, right_ok) — success for each glass
    """
    if not manager.left_glass and not manager.right_glass:
        logger.error("Not connected to glasses")
        return (False, False)

    try:
        vault = ObsidianVault(vault_path=vault_path)
        image_bytes = await vault.fetch_attachment(image_name)
        await vault.close()

        if stereo:
            # Create stereo pair from single image
            # z=0.5 means mid-range depth
            left_bmp, right_bmp = stereo_pair([(image_bytes, 0.5)], max_disparity=max_disparity)
        else:
            # Send same image to both
            left_bmp = right_bmp = to_bmp_bytes(image_bytes, invert=True)

        # Send via protocol
        left_ok = await send_bmp_to_glass(manager.left_glass, left_bmp)
        right_ok = await send_bmp_to_glass(manager.right_glass, right_bmp)

        logger.info(f"Sent image '{image_name}' to glasses (L:{left_ok}, R:{right_ok})")
        return (left_ok, right_ok)

    except Exception as e:
        logger.error(f"Failed to send image: {e}")
        return (False, False)


# ── Periodic Sync (Background Task) ────────────────────────────────────────────

async def sync_daily_note(
    manager: GlassesManager,
    vault_path: str,
    interval_seconds: int = 3600,
    api_url: Optional[str] = None,
) -> None:
    """
    Periodically fetch and send today's daily note to glasses.

    Args:
        manager: GlassesManager instance
        vault_path: Path to vault
        interval_seconds: How often to sync (default 1 hour)
        api_url: Optional REST API URL
    """
    from datetime import datetime

    while True:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            daily_path = f"Daily Notes/{today}"

            ok = await sync_note(manager, vault_path, daily_path, api_url)
            if ok:
                logger.info(f"Daily sync successful at {datetime.now()}")
            else:
                logger.warning(f"Daily sync failed at {datetime.now()}")

        except Exception as e:
            logger.error(f"Daily sync error: {e}")

        await asyncio.sleep(interval_seconds)


# ── Example: Full Workflow ─────────────────────────────────────────────────────

async def example_workflow():
    """Example of using Obsidian integration with protocol."""
    from protocol.connect import GlassesManager

    manager = GlassesManager()

    # Connect to glasses
    logger.info("Connecting to glasses...")
    if not await manager.scan_and_connect(timeout=12):
        logger.error("Failed to connect")
        return

    await manager.sync_time()
    logger.info("Connected!")

    # Send a note
    logger.info("Fetching note from Obsidian...")
    await sync_note(
        manager,
        vault_path="/Users/pots/Obsidian/MyVault",
        note_name="Inbox/Quick Capture",
    )

    # Send an image
    logger.info("Fetching image from Obsidian...")
    await send_obsidian_image(
        manager,
        vault_path="/Users/pots/Obsidian/MyVault",
        image_name="screenshot.png",
        stereo=True,
    )

    # Cleanup
    await manager.disconnect_all()
    logger.info("Done!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_workflow())
