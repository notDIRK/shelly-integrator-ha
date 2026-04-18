"""HTTP utilities for Shelly Cloud DIY.

Contains async HTTP request helpers.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from urllib.parse import urlparse

import aiohttp

_LOGGER = logging.getLogger(__name__)


def validate_gateway_url(raw: str) -> str:
    """Normalise and validate a user-supplied local gateway URL.

    Rejects non-http(s) schemes and loopback targets so an operator cannot
    accidentally point the integration at the HA host itself (SSRF guard).
    Returns the URL with any trailing slash trimmed.

    Raises:
        ValueError: if the URL fails any check. Message is user-facing.
    """
    if not raw or not raw.strip():
        raise ValueError("empty")
    parsed = urlparse(raw.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("invalid_scheme")
    if not parsed.hostname:
        raise ValueError("invalid_host")
    host = parsed.hostname.lower()
    if host in ("localhost", "ip6-localhost", "ip6-loopback"):
        raise ValueError("loopback_blocked")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_unspecified:
            raise ValueError("loopback_blocked")
    except ValueError as err:
        # Not an IP literal — only re-raise our own signal.
        if str(err) in ("loopback_blocked",):
            raise
    return raw.strip().rstrip("/")


async def fetch_csv_from_gateway(
    gateway_url: str,
    hostname: str,
    channel: int,
    session: aiohttp.ClientSession | None = None,
    timeout: int = 120,
) -> str | None:
    """Fetch CSV data from a Shelly EM device via gateway.

    Args:
        gateway_url: Base gateway URL (e.g., https://example.com/sensor)
        hostname: Device hostname (e.g., shellyem-48E729689B2B)
        channel: Channel number (0 or 1)
        session: aiohttp session to reuse (recommended).
                 Falls back to creating a temporary session if None.
        timeout: Request timeout in seconds

    Returns:
        Raw CSV data string, or None on failure
    """
    try:
        safe_base = validate_gateway_url(gateway_url)
    except ValueError as err:
        _LOGGER.warning("Refusing unsafe gateway URL %r: %s", gateway_url, err)
        return None

    url = f"{safe_base}/{hostname}/emeter/{channel}/em_data.csv"

    _LOGGER.debug("Fetching CSV from %s", url)

    try:
        if session is not None:
            return await _fetch(session, url, timeout)

        # Fallback: create a temporary session (not recommended)
        async with aiohttp.ClientSession() as temp_session:
            return await _fetch(temp_session, url, timeout)

    except asyncio.TimeoutError:
        _LOGGER.warning("Timeout fetching %s", url)
    except aiohttp.ClientError as err:
        _LOGGER.warning("Network error fetching %s: %s", url, err)
    except Exception as err:
        _LOGGER.exception("Unexpected error fetching %s: %s", url, err)

    return None


async def _fetch(
    session: aiohttp.ClientSession, url: str, timeout: int
) -> str | None:
    """Perform the actual HTTP GET."""
    async with session.get(
        url, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as response:
        if response.status != 200:
            _LOGGER.warning(
                "Failed to fetch %s: HTTP %d", url, response.status
            )
            return None
        return await response.text()
