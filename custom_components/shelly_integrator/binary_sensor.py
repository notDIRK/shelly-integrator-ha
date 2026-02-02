"""Binary sensor platform for Shelly Integrator.

Based on official Home Assistant Shelly integration patterns.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShellyIntegratorCoordinator, SIGNAL_NEW_DEVICE
from .entity_descriptions import (
    BLOCK_BINARY_SENSORS,
    RPC_BINARY_SENSORS,
    BlockBinarySensorDescription,
    RpcBinarySensorDescription,
    get_model_name,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Shelly Integrator binary sensors."""
    coordinator: ShellyIntegratorCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which entities have been created (by unique_id)
    created_entities: set[str] = set()

    def _create_binary_sensors(device_id: str) -> list[BinarySensorEntity]:
        """Create binary sensor entities for a device based on its status."""
        entities: list[BinarySensorEntity] = []
        device_data = coordinator.devices.get(device_id, {})
        status = device_data.get("status", {})
        
        if not status:
            _LOGGER.debug("No status data for device %s", device_id)
            return entities

        # Detect device generation based on status keys
        is_gen2 = any(
            re.match(r"switch:\d+|light:\d+|cover:\d+|input:\d+", key)
            for key in status.keys()
        )

        if is_gen2:
            entities.extend(_create_rpc_binary_sensors(device_id, status, created_entities, coordinator))
        else:
            entities.extend(_create_block_binary_sensors(device_id, status, created_entities, coordinator))

        if entities:
            _LOGGER.info("Creating %d binary sensor entities for device %s", len(entities), device_id)

        return entities

    @callback
    def async_add_device(device_id: str) -> None:
        """Add entities for a newly discovered device."""
        entities = _create_binary_sensors(device_id)
        if entities:
            async_add_entities(entities)

    # Add existing devices
    entities: list[BinarySensorEntity] = []
    for device_id in list(coordinator.devices.keys()):
        entities.extend(_create_binary_sensors(device_id))

    if entities:
        async_add_entities(entities)

    # Listen for new devices
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, async_add_device)
    )


def _create_block_binary_sensors(
    device_id: str,
    status: dict[str, Any],
    created_entities: set[str],
    coordinator: ShellyIntegratorCoordinator,
) -> list[BinarySensorEntity]:
    """Create Gen1 Block binary sensors from status."""
    entities: list[BinarySensorEntity] = []

    # Inputs
    inputs = status.get("inputs", [])
    for idx, inp in enumerate(inputs):
        if "input" in inp:
            desc = BLOCK_BINARY_SENSORS.get("input")
            if desc:
                unique_id = f"{device_id}_input_{idx}"
                if unique_id not in created_entities:
                    created_entities.add(unique_id)
                    entities.append(BlockBinarySensor(
                        coordinator, device_id, desc, idx, "inputs", "input"
                    ))

    # Motion (Shelly Motion)
    if "motion" in status:
        desc = BLOCK_BINARY_SENSORS.get("motion")
        if desc:
            unique_id = f"{device_id}_motion"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(BlockBinarySensor(
                    coordinator, device_id, desc, 0, None, "motion"
                ))

    # Door/Window sensor
    sensor = status.get("sensor", {})
    if sensor and "state" in sensor:
        desc = BLOCK_BINARY_SENSORS.get("sensor_state")
        if desc:
            unique_id = f"{device_id}_door"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(BlockBinarySensor(
                    coordinator, device_id, desc, 0, "sensor", "state"
                ))

    # Flood sensor
    if "flood" in status:
        desc = BLOCK_BINARY_SENSORS.get("flood")
        if desc:
            unique_id = f"{device_id}_flood"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(BlockBinarySensor(
                    coordinator, device_id, desc, 0, None, "flood"
                ))

    # Smoke sensor
    if "smoke" in status:
        desc = BLOCK_BINARY_SENSORS.get("smoke")
        if desc:
            unique_id = f"{device_id}_smoke"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(BlockBinarySensor(
                    coordinator, device_id, desc, 0, None, "smoke"
                ))

    # Gas alarm (binary version)
    gas_sensor = status.get("gas_sensor", {})
    if gas_sensor and "alarm_state" in gas_sensor:
        desc = BLOCK_BINARY_SENSORS.get("gas_alarm")
        if desc:
            unique_id = f"{device_id}_gas_alarm_binary"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(BlockBinarySensor(
                    coordinator, device_id, desc, 0, "gas_sensor", "alarm_state"
                ))

    # Overtemperature
    if "overtemperature" in status:
        desc = BLOCK_BINARY_SENSORS.get("overtemperature")
        if desc:
            unique_id = f"{device_id}_overtemperature"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(BlockBinarySensor(
                    coordinator, device_id, desc, 0, None, "overtemperature"
                ))

    # Overpower (check in relays)
    relays = status.get("relays", [])
    for idx, relay in enumerate(relays):
        if "overpower" in relay:
            desc = BLOCK_BINARY_SENSORS.get("overpower")
            if desc:
                unique_id = f"{device_id}_overpower_{idx}"
                if unique_id not in created_entities:
                    created_entities.add(unique_id)
                    entities.append(BlockBinarySensor(
                        coordinator, device_id, desc, idx, "relays", "overpower"
                    ))

    # Vibration
    if "vibration" in status:
        desc = BLOCK_BINARY_SENSORS.get("vibration")
        if desc:
            unique_id = f"{device_id}_vibration"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(BlockBinarySensor(
                    coordinator, device_id, desc, 0, None, "vibration"
                ))

    return entities


def _create_rpc_binary_sensors(
    device_id: str,
    status: dict[str, Any],
    created_entities: set[str],
    coordinator: ShellyIntegratorCoordinator,
) -> list[BinarySensorEntity]:
    """Create Gen2/Gen3 RPC binary sensors from status."""
    entities: list[BinarySensorEntity] = []

    # Inputs (input:N)
    for key in status:
        if match := re.match(r"input:(\d+)", key):
            idx = int(match.group(1))
            input_data = status[key]
            if "state" in input_data:
                desc = RPC_BINARY_SENSORS.get("input")
                if desc:
                    unique_id = f"{device_id}_input_{idx}"
                    if unique_id not in created_entities:
                        created_entities.add(unique_id)
                        entities.append(RpcBinarySensor(
                            coordinator, device_id, desc, idx, key, "state"
                        ))

    # Cloud connectivity
    cloud = status.get("cloud", {})
    if "connected" in cloud:
        desc = RPC_BINARY_SENSORS.get("cloud")
        if desc:
            unique_id = f"{device_id}_cloud"
            if unique_id not in created_entities:
                created_entities.add(unique_id)
                entities.append(RpcBinarySensor(
                    coordinator, device_id, desc, 0, "cloud", "connected"
                ))

    return entities


class BlockBinarySensor(CoordinatorEntity[ShellyIntegratorCoordinator], BinarySensorEntity):
    """Shelly Gen1 Block binary sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ShellyIntegratorCoordinator,
        device_id: str,
        description: BlockBinarySensorDescription,
        channel: int,
        status_key: str | None,
        attr_key: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._description = description
        self._channel = channel
        self._status_key = status_key
        self._attr_key = attr_key

        self._attr_unique_id = f"{device_id}_{description.key}_{channel}"

        # Add channel suffix if multiple channels
        name = description.name or "Binary Sensor"
        if channel > 0:
            name = f"{name} {channel + 1}"
        self._attr_name = name

        if description.device_class:
            self._attr_device_class = description.device_class
        if description.entity_category:
            self._attr_entity_category = description.entity_category
        if description.icon:
            self._attr_icon = description.icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        device_data = self.coordinator.devices.get(self._device_id, {})
        device_code = device_data.get("device_code", "")
        
        name = device_data.get("name")
        if not name:
            status = device_data.get("status", {})
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        # Direct status key (no container)
        if self._status_key is None:
            value = status.get(self._attr_key)
        else:
            container = status.get(self._status_key)
            if container is None:
                return None
            # Handle arrays
            if isinstance(container, list):
                if self._channel >= len(container):
                    return None
                container = container[self._channel]
            value = container.get(self._attr_key) if isinstance(container, dict) else None

        if value is None:
            return None

        # Apply transformation if defined
        if self._description.value_fn:
            return self._description.value_fn(value)

        # Default boolean conversion
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value > 0
        if isinstance(value, str):
            return value.lower() in ("true", "on", "1", "open")

        return None


class RpcBinarySensor(CoordinatorEntity[ShellyIntegratorCoordinator], BinarySensorEntity):
    """Shelly Gen2/Gen3 RPC binary sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ShellyIntegratorCoordinator,
        device_id: str,
        description: RpcBinarySensorDescription,
        channel: int,
        component_key: str,
        attr_key: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._description = description
        self._channel = channel
        self._component_key = component_key
        self._attr_key = attr_key

        self._attr_unique_id = f"{device_id}_{component_key}_{attr_key}"

        # Add channel suffix if multiple channels
        name = description.name or "Binary Sensor"
        if channel > 0:
            name = f"{name} {channel + 1}"
        self._attr_name = name

        if description.device_class:
            self._attr_device_class = description.device_class
        if description.entity_category:
            self._attr_entity_category = description.entity_category

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        device_data = self.coordinator.devices.get(self._device_id, {})
        device_code = device_data.get("device_code", "")
        status = device_data.get("status", {})
        
        name = device_data.get("name")
        if not name:
            sys_info = status.get("sys", {}).get("device", {})
            name = sys_info.get("name")
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        component = status.get(self._component_key)
        if component is None:
            return None

        value = component.get(self._attr_key)

        if value is None:
            return None

        # Default boolean conversion
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value > 0

        return None
