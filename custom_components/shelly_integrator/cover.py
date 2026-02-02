"""Cover platform for Shelly Integrator.

Based on official Home Assistant Shelly integration patterns.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShellyIntegratorCoordinator, SIGNAL_NEW_DEVICE
from .entity_descriptions import get_model_name

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Shelly Integrator covers."""
    coordinator: ShellyIntegratorCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which entities have been created (by unique_id)
    created_entities: set[str] = set()

    def _create_covers(device_id: str) -> list[CoverEntity]:
        """Create cover entities for a device based on its status."""
        entities: list[CoverEntity] = []
        device_data = coordinator.devices.get(device_id, {})
        status = device_data.get("status", {})
        
        if not status:
            _LOGGER.debug("No status data for device %s", device_id)
            return entities

        # Gen1: rollers array
        rollers = status.get("rollers", [])
        for idx, _ in enumerate(rollers):
            unique_id = f"{device_id}_cover_{idx}"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(ShellyCover(
                    coordinator, device_id, idx, f"rollers.{idx}", is_gen2=False
                ))

        # Gen2: cover:N pattern
        for key in status:
            if match := re.match(r"cover:(\d+)", key):
                idx = int(match.group(1))
                unique_id = f"{device_id}_cover_{idx}"
                if unique_id not in created_entities:
                    created_entities.add(unique_id)
                    entities.append(ShellyCover(
                        coordinator, device_id, idx, key, is_gen2=True
                    ))

        if entities:
            _LOGGER.info("Creating %d cover entities for device %s", len(entities), device_id)

        return entities

    @callback
    def async_add_device(device_id: str) -> None:
        """Add entities for a newly discovered device."""
        entities = _create_covers(device_id)
        if entities:
            async_add_entities(entities)

    # Add existing devices
    entities: list[CoverEntity] = []
    for device_id in list(coordinator.devices.keys()):
        entities.extend(_create_covers(device_id))

    if entities:
        async_add_entities(entities)

    # Listen for new devices
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, async_add_device)
    )


class ShellyCover(CoordinatorEntity[ShellyIntegratorCoordinator], CoverEntity):
    """Shelly cover entity."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self,
        coordinator: ShellyIntegratorCoordinator,
        device_id: str,
        channel: int,
        key: str,
        is_gen2: bool,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._channel = channel
        self._key = key
        self._is_gen2 = is_gen2

        self._attr_unique_id = f"{device_id}_cover_{channel}"
        self._attr_name = "Cover" if channel == 0 else f"Cover {channel + 1}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        device_data = self.coordinator.devices.get(self._device_id, {})
        device_code = device_data.get("device_code", "")
        status = device_data.get("status", {})
        
        name = device_data.get("name")
        if not name:
            if self._is_gen2:
                sys_info = status.get("sys", {}).get("device", {})
                name = sys_info.get("name")
            else:
                getinfo = status.get("getinfo", {}).get("fw_info", {})
                name = getinfo.get("device")
        if not name:
            name = get_model_name(device_code) if device_code else f"Shelly {self._device_id[-6:]}"

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=name,
            manufacturer="Shelly",
            model=get_model_name(device_code) if device_code else "Unknown",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        device = self.coordinator.devices.get(self._device_id, {})
        return device.get("online", False)

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover (0-100, 100 is fully open)."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        if self._is_gen2:
            cover_data = status.get(self._key, {})
            return cover_data.get("current_pos")
        else:
            rollers = status.get("rollers", [])
            if len(rollers) > self._channel:
                return rollers[self._channel].get("current_pos")

        return None

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        if position is not None:
            return position == 0
        return None

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        if self._is_gen2:
            cover_data = status.get(self._key, {})
            return cover_data.get("state") == "opening"
        else:
            rollers = status.get("rollers", [])
            if len(rollers) > self._channel:
                return rollers[self._channel].get("state") == "open"
        return False

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        if self._is_gen2:
            cover_data = status.get(self._key, {})
            return cover_data.get("state") == "closing"
        else:
            rollers = status.get("rollers", [])
            if len(rollers) > self._channel:
                return rollers[self._channel].get("state") == "close"
        return False

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.coordinator.send_command(
            device_id=self._device_id,
            cmd="roller",
            channel=self._channel,
            action="open",
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.coordinator.send_command(
            device_id=self._device_id,
            cmd="roller",
            channel=self._channel,
            action="close",
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.coordinator.send_command(
            device_id=self._device_id,
            cmd="roller",
            channel=self._channel,
            action="stop",
        )

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get("position")
        if position is not None:
            await self.coordinator.send_command(
                device_id=self._device_id,
                cmd="roller",
                channel=self._channel,
                action="to_pos",
                params={"pos": position},
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
