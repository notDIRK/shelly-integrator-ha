"""Sensor platform for Shelly Integrator.

Based on official Home Assistant Shelly integration patterns.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShellyIntegratorCoordinator, SIGNAL_NEW_DEVICE
from .entity_descriptions import (
    BLOCK_SENSORS,
    RPC_SENSORS,
    BlockSensorDescription,
    RpcSensorDescription,
    get_model_name,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Shelly Integrator sensors."""
    coordinator: ShellyIntegratorCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which sensor entities have been created (by unique_id)
    created_sensors: set[str] = set()

    def _create_sensors(device_id: str) -> list[SensorEntity]:
        """Create sensor entities for a device based on its status."""
        entities: list[SensorEntity] = []
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
            entities.extend(_create_rpc_sensors(device_id, status, created_sensors, coordinator))
        else:
            entities.extend(_create_block_sensors(device_id, status, created_sensors, coordinator))

        if entities:
            _LOGGER.info("Creating %d sensor entities for device %s", len(entities), device_id)

        return entities

    @callback
    def async_add_device(device_id: str) -> None:
        """Add entities for a newly discovered device."""
        entities = _create_sensors(device_id)
        if entities:
            async_add_entities(entities)

    # Add existing devices
    entities: list[SensorEntity] = []
    for device_id in list(coordinator.devices.keys()):
        entities.extend(_create_sensors(device_id))

    if entities:
        async_add_entities(entities)

    # Listen for new devices
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, async_add_device)
    )


def _create_block_sensors(
    device_id: str,
    status: dict[str, Any],
    created_sensors: set[str],
    coordinator: ShellyIntegratorCoordinator,
) -> list[SensorEntity]:
    """Create Gen1 Block sensors from status."""
    entities: list[SensorEntity] = []

    # Map status keys to block/attribute format
    # Gen1 status has: emeters[], relays[], meters[], gas_sensor{}, etc.
    
    # Emeters (Shelly EM, 3EM)
    emeters = status.get("emeters", [])
    for idx, emeter in enumerate(emeters):
        for attr in ["power", "voltage", "current", "pf", "reactive"]:
            if attr in emeter:
                key = ("emeter", attr if attr != "pf" else "powerFactor")
                if key in BLOCK_SENSORS:
                    desc = BLOCK_SENSORS[key]
                    unique_id = f"{device_id}_{desc.key}_{idx}"
                    if unique_id not in created_sensors:
                        created_sensors.add(unique_id)
                        entities.append(BlockSensor(
                            coordinator, device_id, desc, idx, "emeters", attr
                        ))
        # Energy
        if "total" in emeter:
            key = ("emeter", "energy")
            if key in BLOCK_SENSORS:
                desc = BLOCK_SENSORS[key]
                unique_id = f"{device_id}_{desc.key}_{idx}"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(BlockSensor(
                        coordinator, device_id, desc, idx, "emeters", "total"
                    ))
        # Energy returned
        if "total_returned" in emeter:
            key = ("emeter", "energyReturned")
            if key in BLOCK_SENSORS:
                desc = BLOCK_SENSORS[key]
                unique_id = f"{device_id}_{desc.key}_ret_{idx}"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(BlockSensor(
                        coordinator, device_id, desc, idx, "emeters", "total_returned"
                    ))

    # Meters (Shelly 1PM, etc.)
    meters = status.get("meters", [])
    for idx, meter in enumerate(meters):
        if "power" in meter:
            key = ("relay", "power")
            if key in BLOCK_SENSORS:
                desc = BLOCK_SENSORS[key]
                unique_id = f"{device_id}_meter_power_{idx}"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(BlockSensor(
                        coordinator, device_id, desc, idx, "meters", "power"
                    ))
        if "total" in meter:
            key = ("relay", "energy")
            if key in BLOCK_SENSORS:
                desc = BLOCK_SENSORS[key]
                unique_id = f"{device_id}_meter_energy_{idx}"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(BlockSensor(
                        coordinator, device_id, desc, idx, "meters", "total"
                    ))

    # Gas sensor (Shelly Gas)
    gas_sensor = status.get("gas_sensor", {})
    if gas_sensor:
        # Sensor operation state
        if "sensor_state" in gas_sensor:
            key = ("sensor", "sensorOp")
            if key in BLOCK_SENSORS:
                desc = BLOCK_SENSORS[key]
                unique_id = f"{device_id}_gas_sensor_state"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(BlockSensor(
                        coordinator, device_id, desc, 0, "gas_sensor", "sensor_state"
                    ))
        # Alarm state
        if "alarm_state" in gas_sensor:
            key = ("sensor", "gas")
            if key in BLOCK_SENSORS:
                desc = BLOCK_SENSORS[key]
                unique_id = f"{device_id}_gas_alarm_state"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(BlockSensor(
                        coordinator, device_id, desc, 0, "gas_sensor", "alarm_state"
                    ))
        # Self test
        if "self_test_state" in gas_sensor:
            key = ("sensor", "selfTest")
            if key in BLOCK_SENSORS:
                desc = BLOCK_SENSORS[key]
                unique_id = f"{device_id}_gas_self_test"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(BlockSensor(
                        coordinator, device_id, desc, 0, "gas_sensor", "self_test_state"
                    ))

    # Gas concentration
    concentration = status.get("concentration", {})
    if concentration and concentration.get("is_valid"):
        key = ("sensor", "concentration")
        if key in BLOCK_SENSORS:
            desc = BLOCK_SENSORS[key]
            unique_id = f"{device_id}_gas_concentration"
            if unique_id not in created_sensors:
                created_sensors.add(unique_id)
                entities.append(BlockSensor(
                    coordinator, device_id, desc, 0, "concentration", "ppm"
                ))

    # Temperature (various devices)
    temp = status.get("tmp", {}) or status.get("temperature", {})
    if temp and "tC" in temp:
        key = ("sensor", "temp")
        if key in BLOCK_SENSORS:
            desc = BLOCK_SENSORS[key]
            unique_id = f"{device_id}_temperature"
            if unique_id not in created_sensors:
                created_sensors.add(unique_id)
                entities.append(BlockSensor(
                    coordinator, device_id, desc, 0, "tmp" if "tmp" in status else "temperature", "tC"
                ))

    # Humidity (Shelly H&T)
    hum = status.get("hum", {})
    if hum and "value" in hum:
        key = ("sensor", "humidity")
        if key in BLOCK_SENSORS:
            desc = BLOCK_SENSORS[key]
            unique_id = f"{device_id}_humidity"
            if unique_id not in created_sensors:
                created_sensors.add(unique_id)
                entities.append(BlockSensor(
                    coordinator, device_id, desc, 0, "hum", "value"
                ))

    # Battery
    bat = status.get("bat", {})
    if bat and "value" in bat:
        key = ("device", "battery")
        if key in BLOCK_SENSORS:
            desc = BLOCK_SENSORS[key]
            unique_id = f"{device_id}_battery"
            if unique_id not in created_sensors:
                created_sensors.add(unique_id)
                entities.append(BlockSensor(
                    coordinator, device_id, desc, 0, "bat", "value"
                ))

    # Illuminance (Shelly Motion)
    lux = status.get("lux", {})
    if lux and "value" in lux:
        key = ("sensor", "luminosity")
        if key in BLOCK_SENSORS:
            desc = BLOCK_SENSORS[key]
            unique_id = f"{device_id}_illuminance"
            if unique_id not in created_sensors:
                created_sensors.add(unique_id)
                entities.append(BlockSensor(
                    coordinator, device_id, desc, 0, "lux", "value"
                ))

    return entities


def _create_rpc_sensors(
    device_id: str,
    status: dict[str, Any],
    created_sensors: set[str],
    coordinator: ShellyIntegratorCoordinator,
) -> list[SensorEntity]:
    """Create Gen2/Gen3 RPC sensors from status."""
    entities: list[SensorEntity] = []

    # Find all switch:N components
    for key in status:
        if match := re.match(r"(switch|light|cover):(\d+)", key):
            component = match.group(1)
            idx = int(match.group(2))
            component_data = status[key]

            # Power
            if "apower" in component_data:
                desc = RPC_SENSORS.get("switch_power")
                if desc:
                    unique_id = f"{device_id}_{component}_{idx}_power"
                    if unique_id not in created_sensors:
                        created_sensors.add(unique_id)
                        entities.append(RpcSensor(
                            coordinator, device_id, desc, idx, key, "apower"
                        ))

            # Voltage
            if "voltage" in component_data:
                desc = RPC_SENSORS.get("switch_voltage")
                if desc:
                    unique_id = f"{device_id}_{component}_{idx}_voltage"
                    if unique_id not in created_sensors:
                        created_sensors.add(unique_id)
                        entities.append(RpcSensor(
                            coordinator, device_id, desc, idx, key, "voltage"
                        ))

            # Current
            if "current" in component_data:
                desc = RPC_SENSORS.get("switch_current")
                if desc:
                    unique_id = f"{device_id}_{component}_{idx}_current"
                    if unique_id not in created_sensors:
                        created_sensors.add(unique_id)
                        entities.append(RpcSensor(
                            coordinator, device_id, desc, idx, key, "current"
                        ))

            # Energy
            if "aenergy" in component_data:
                desc = RPC_SENSORS.get("switch_energy")
                if desc:
                    unique_id = f"{device_id}_{component}_{idx}_energy"
                    if unique_id not in created_sensors:
                        created_sensors.add(unique_id)
                        entities.append(RpcSensor(
                            coordinator, device_id, desc, idx, key, "aenergy"
                        ))

            # Temperature
            if "temperature" in component_data:
                desc = RPC_SENSORS.get("switch_temperature")
                if desc:
                    unique_id = f"{device_id}_{component}_{idx}_temp"
                    if unique_id not in created_sensors:
                        created_sensors.add(unique_id)
                        entities.append(RpcSensor(
                            coordinator, device_id, desc, idx, key, "temperature"
                        ))

    # Temperature components (temperature:N)
    for key in status:
        if match := re.match(r"temperature:(\d+)", key):
            idx = int(match.group(1))
            desc = RPC_SENSORS.get("temperature")
            if desc:
                unique_id = f"{device_id}_temperature_{idx}"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(RpcSensor(
                        coordinator, device_id, desc, idx, key, "tC"
                    ))

    # Humidity components (humidity:N)
    for key in status:
        if match := re.match(r"humidity:(\d+)", key):
            idx = int(match.group(1))
            desc = RPC_SENSORS.get("humidity")
            if desc:
                unique_id = f"{device_id}_humidity_{idx}"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(RpcSensor(
                        coordinator, device_id, desc, idx, key, "rh"
                    ))

    # Illuminance (illuminance:N)
    for key in status:
        if match := re.match(r"illuminance:(\d+)", key):
            idx = int(match.group(1))
            desc = RPC_SENSORS.get("illuminance")
            if desc:
                unique_id = f"{device_id}_illuminance_{idx}"
                if unique_id not in created_sensors:
                    created_sensors.add(unique_id)
                    entities.append(RpcSensor(
                        coordinator, device_id, desc, idx, key, "lux"
                    ))

    return entities


class BlockSensor(CoordinatorEntity[ShellyIntegratorCoordinator], SensorEntity):
    """Shelly Gen1 Block sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ShellyIntegratorCoordinator,
        device_id: str,
        description: BlockSensorDescription,
        channel: int,
        status_key: str,
        attr_key: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._description = description
        self._channel = channel
        self._status_key = status_key
        self._attr_key = attr_key

        self._attr_unique_id = f"{device_id}_{description.key}_{channel}"
        
        # Add channel suffix if multiple channels
        name = description.name or "Sensor"
        if channel > 0:
            name = f"{name} {channel + 1}"
        self._attr_name = name

        if description.device_class:
            self._attr_device_class = description.device_class
        if description.state_class:
            self._attr_state_class = description.state_class
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        if description.entity_category:
            self._attr_entity_category = description.entity_category
        if description.icon:
            self._attr_icon = description.icon
        if description.suggested_display_precision is not None:
            self._attr_suggested_display_precision = description.suggested_display_precision

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
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        # Navigate to the value
        container = status.get(self._status_key)
        if container is None:
            return None

        # Handle arrays (emeters, meters, etc.)
        if isinstance(container, list):
            if self._channel >= len(container):
                return None
            container = container[self._channel]

        value = container.get(self._attr_key) if isinstance(container, dict) else None

        # Apply transformation if defined
        if value is not None and self._description.value_fn:
            value = self._description.value_fn(value)

        return value


class RpcSensor(CoordinatorEntity[ShellyIntegratorCoordinator], SensorEntity):
    """Shelly Gen2/Gen3 RPC sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ShellyIntegratorCoordinator,
        device_id: str,
        description: RpcSensorDescription,
        channel: int,
        component_key: str,
        attr_key: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._description = description
        self._channel = channel
        self._component_key = component_key
        self._attr_key = attr_key

        self._attr_unique_id = f"{device_id}_{component_key}_{attr_key}"

        # Add channel suffix if multiple channels
        name = description.name or "Sensor"
        if channel > 0:
            name = f"{name} {channel + 1}"
        self._attr_name = name

        if description.device_class:
            self._attr_device_class = description.device_class
        if description.state_class:
            self._attr_state_class = description.state_class
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        if description.entity_category:
            self._attr_entity_category = description.entity_category
        if description.icon:
            self._attr_icon = description.icon
        if description.suggested_display_precision is not None:
            self._attr_suggested_display_precision = description.suggested_display_precision

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
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        device = self.coordinator.devices.get(self._device_id, {})
        status = device.get("status", {})

        component = status.get(self._component_key)
        if component is None:
            return None

        value = component.get(self._attr_key)

        # Apply transformation if defined
        if value is not None and self._description.value_fn:
            value = self._description.value_fn(value)

        return value
