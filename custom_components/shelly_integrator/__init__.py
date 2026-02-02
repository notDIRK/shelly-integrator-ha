"""Shelly Integrator integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote_plus

import aiohttp
from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url
from homeassistant.components.webhook import (
    async_register as webhook_register,
    async_unregister as webhook_unregister,
)
from homeassistant.components.persistent_notification import (
    async_create as notify_create,
    async_dismiss as notify_dismiss,
)

from .const import (
    DOMAIN,
    PLATFORMS,
    API_GET_TOKEN,
    INTEGRATOR_TAG,
    CONF_INTEGRATOR_TOKEN,
    WEBHOOK_ID,
    SHELLY_CONSENT_URL,
)
from .coordinator import ShellyIntegratorCoordinator

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_ID = f"{DOMAIN}_setup"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shelly Integrator from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    token = entry.data[CONF_INTEGRATOR_TOKEN]

    session = async_get_clientsession(hass)

    # Get JWT token
    try:
        jwt_token = await get_jwt_token(session, INTEGRATOR_TAG, token)
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to get JWT token: {err}") from err

    # Create coordinator
    coordinator = ShellyIntegratorCoordinator(
        hass=hass,
        session=session,
        tag=INTEGRATOR_TAG,
        token=token,
        jwt_token=jwt_token,
    )

    # Start WebSocket connection
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register webhook for user consent callback
    webhook_id = WEBHOOK_ID
    webhook_register(
        hass,
        DOMAIN,
        "Shelly Integrator Callback",
        webhook_id,
        lambda hass, webhook_id, request: handle_webhook(hass, entry.entry_id, request),
    )

    # Auto-connect to default EU server (devices will appear when they send updates)
    # This ensures stateless operation - no need to save server info
    default_server = "shelly-187-eu.shelly.cloud"
    _LOGGER.info("Auto-connecting to default server: %s", default_server)
    await coordinator.connect_to_host(default_server)

    # Store webhook ID for unload
    hass.data[DOMAIN][f"{entry.entry_id}_webhook"] = webhook_id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Create persistent notification with consent URL
    await _create_consent_notification(hass, webhook_id)

    return True


async def _create_consent_notification(hass: HomeAssistant, webhook_id: str) -> None:
    """Create a persistent notification with the device consent URL."""
    try:
        # Get the external URL of Home Assistant
        ha_url = get_url(hass, prefer_external=True)
        webhook_url = f"{ha_url}/api/webhook/{webhook_id}"
        encoded_callback = quote_plus(webhook_url)

        consent_url = f"{SHELLY_CONSENT_URL}?itg={INTEGRATOR_TAG}&cb={encoded_callback}"

        message = (
            "## Add Your Shelly Devices\n\n"
            "To connect your Shelly devices, click the link below to grant access:\n\n"
            f"**[Grant Device Access]({consent_url})**\n\n"
            "You will be asked to log into your Shelly Cloud account and select "
            "which devices to share with Home Assistant.\n\n"
            "---\n"
            "*This notification will remain until you dismiss it. "
            "You can use the link again anytime to add more devices.*"
        )

        notify_create(
            hass,
            message=message,
            title="Shelly Integrator Setup",
            notification_id=NOTIFICATION_ID,
        )

        _LOGGER.info("Consent URL: %s", consent_url)

    except Exception as err:
        _LOGGER.warning("Could not create consent notification: %s", err)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: ShellyIntegratorCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Dismiss notification
    notify_dismiss(hass, NOTIFICATION_ID)

    # Unregister webhook
    webhook_id = hass.data[DOMAIN].pop(f"{entry.entry_id}_webhook", None)
    if webhook_id:
        webhook_unregister(hass, webhook_id)

    # Close WebSocket connection
    await coordinator.async_close()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def handle_webhook(
    hass: HomeAssistant, entry_id: str, request: web.Request
) -> web.Response:
    """Handle webhook callback from Shelly Cloud user consent.
    
    Shelly Cloud sends ONE request PER DEVICE with format:
    {
        "userId": 123,
        "deviceId": "abc123",
        "deviceType": "SHPLG-1",
        "deviceCode": "shellyplug",
        "accessGroups": "01",
        "action": "add" | "remove",
        "host": "shelly-187-eu.shelly.cloud",
        "name": ["Device Name"]
    }
    """
    try:
        data = await request.json()
        _LOGGER.info("Webhook received from Shelly Cloud: %s", data)

        coordinator: ShellyIntegratorCoordinator = hass.data[DOMAIN].get(entry_id)
        if not coordinator:
            _LOGGER.error("Coordinator not found for entry %s", entry_id)
            return web.Response(status=404)

        # Extract device info from Shelly's callback format
        device_id = data.get("deviceId")
        host = data.get("host")
        action = data.get("action", "add")
        device_name = data.get("name", [])
        device_type = data.get("deviceType")
        device_code = data.get("deviceCode")

        if not device_id:
            _LOGGER.error("Missing deviceId in webhook data: %s", data)
            return web.Response(status=400)

        if action == "add":
            _LOGGER.info(
                "Device granted: id=%s, host=%s, type=%s, code=%s, name=%s",
                device_id, host, device_type, device_code, device_name
            )

            # Store device info in coordinator
            if host:
                coordinator._device_host_map[device_id] = host
            
            # Pre-populate device with name from Shelly Cloud
            if device_id not in coordinator.devices:
                coordinator.devices[device_id] = {}
            
            if device_name:
                coordinator.devices[device_id]["name"] = device_name[0]
            if device_type:
                coordinator.devices[device_id]["device_type"] = device_type
            if device_code:
                coordinator.devices[device_id]["device_code"] = device_code

            # Connect to the host if not already connected
            if host and host not in coordinator.hosts:
                _LOGGER.info("Connecting to new host: %s", host)
                await coordinator.connect_to_host(host)

            # Show notification
            name_str = device_name[0] if device_name else device_id
            notify_create(
                hass,
                message=f"Device '{name_str}' added from Shelly Cloud.",
                title="Shelly Device Added",
                notification_id=f"{DOMAIN}_device_added",
            )

        elif action == "remove":
            _LOGGER.info("Device removed: id=%s", device_id)
            coordinator._device_host_map.pop(device_id, None)
            coordinator.devices.pop(device_id, None)

        return web.Response(text="OK", status=200)

    except Exception as err:
        _LOGGER.error("Webhook error: %s", err)
        return web.Response(status=500)


async def get_jwt_token(
    session: aiohttp.ClientSession,
    tag: str,
    token: str,
) -> str:
    """Get JWT token from Shelly Cloud API."""
    async with session.post(
        API_GET_TOKEN,
        data={"itg": tag, "token": token},
    ) as response:
        response.raise_for_status()
        data = await response.json()

        if not data.get("isok"):
            raise ValueError(f"API error: {data}")

        return data["data"]
