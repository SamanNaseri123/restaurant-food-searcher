"""Fetch pages from the Wayback Machine (Internet Archive) as a fallback
for bot-blocked sites.

Free API, no auth needed. Returns archived HTML snapshots.
"""
import logging

import httpx

logger = logging.getLogger(__name__)

_WAYBACK_API = "https://archive.org/wayback/available"


async def fetch_from_wayback(url: str) -> str | None:
    """Try to fetch an archived version of a URL from the Wayback Machine.

    Returns HTML content or None if no snapshot exists.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Check if a snapshot exists
            resp = await client.get(_WAYBACK_API, params={"url": url})
            resp.raise_for_status()
            data = resp.json()

            snapshot = data.get("archived_snapshots", {}).get("closest")
            if not snapshot or not snapshot.get("available"):
                logger.info(f"No Wayback snapshot for {url}")
                return None

            archive_url = snapshot["url"]
            # Prefer raw HTML (id_ suffix gives original content)
            archive_url = archive_url.replace("/http", "id_/http", 1)

            logger.info(f"Found Wayback snapshot: {archive_url}")

            # Fetch the archived page
            resp = await client.get(archive_url, follow_redirects=True)
            resp.raise_for_status()
            return resp.text

    except Exception as e:
        logger.warning(f"Wayback fetch failed for {url}: {e}")
        return None
