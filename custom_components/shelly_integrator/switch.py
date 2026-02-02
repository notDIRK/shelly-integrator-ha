"""Switch platform for Shelly Integrator.

Based on official Home Assistant Shelly integration patterns.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Shelly Integrator switches."""
    coordinator: ShellyIntegratorCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which entities have been created (by unique_id)
    created_entities: set[str] = set()

    def _create_switches(device_id: str) -> list[SwitchEntity]:
        """Create switch entities for a device based on its status."""
        entities: list[SwitchEntity] = []
        device_data = coordinator.devices.get(device_id, {})
        status = device_data.get("status", {})
        
        if not status:
            _LOGGER.debug("No status data for device %s", device_id)
            return entities

        # Gen1: relays array
        relays = status.get("relays", [])
        for idx, _ in enumerate(relays):
            unique_id = f"{device_id}_switch_{idx}"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(ShellySwitch(
                    coordinator, device_id, idx, f"relays.{idx}", is_gen2=False
                ))

        # Gen2: switch:N pattern
        for key in status:
            if match := re.match(r"switch:(\d+)", key):
                idx = int(match.group(1))
                unique_id = f"{device_id}_switch_{idx}"
                if unique_id not in created_entities:
                    created_entities.add(unique_id)
                    entities.append(ShellySwitch(
                        coordinator, device_id, idx, key, is_gen2=True
                    ))

        if entities:
            _LOGGER.info("Creating %d switch entities for device %s", len(entities), device_id)

        return entities

    @callback
    def async_add_device(device_id: str) -> None:
        """Add entities for a newly discovered device."""
        entities = _create_switches(device_id)
        if entities:
            async_add_entities(entities)

    # Add existing devices
    entities: list[SwitchEntity] = []
    for device_id in list(coordinator.devices.keys()):
        entities.extend(_create_switches(device_id))

    if entities:
        async_add_entities(entities)

    # Listen for new devices
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, async_add_device)
    )


class ShellySwitch(CoordinatorEntity[ShellyIntegratorCoordinator], SwitchEntity):
    """Shelly switch entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ShellyIntegratorCoordinator,
        device_id: str,
        channel: int,
        key: str,
        is_gen2: bool,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._channel = channel
        self._key = key
        self._is_gen2 = is_gen2

        self._attr_unique_id = f"{device_id}_switch_{channel}"
        self._attr_name = "Switch" if channel == 0 else f"Switch {channel + 1}"

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
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        if self._is_gen2:
            switch_data = status.get(self._key, {})
            return switch_data.get("output", False)
        else:
            relays = status.get("relays", [])
            if len(relays) > self._channel:
                return relays[self._channel].get("ison", False)

        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        device = self.coordinator.devices.get(self._device_id, {})
        return device.get("online", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.send_command(
            device_id=self._device_id,
            cmd="relay",
            channel=self._channel,
            action="on",
        )
        self._update_local_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.send_command(
            device_id=self._device_id,
            cmd="relay",
            channel=self._channel,
            action="off",
        )
        self._update_local_state(False)

    def _update_local_state(self, is_on: bool) -> None:
        """Update local state optimistically."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        if self._is_gen2:
            if self._key in status:
                status[self._key]["output"] = is_on
        else:
            relays = status.get("relays", [])
            if len(relays) > self._channel:
                relays[self._channel]["ison"] = is_on

        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
