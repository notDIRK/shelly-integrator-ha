"""Device management for Shelly Integrator.

Handles device discovery, state management, and status parsing.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass
class Device:
    """Represents a Shelly device."""

    device_id: str
    host: str | None = None
    name: str | None = None
    device_type: str | None = None
    device_code: str | None = None
    access_groups: str = "00"
    online: bool = False
    status: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def is_gen2(self) -> bool:
        """Check if device is Gen2/Gen3 (RPC-based)."""
        return any(
            re.match(r"switch:\d+|light:\d+|cover:\d+|input:\d+", key)
            for key in self.status.keys()
        )

    @property
    def hostname(self) -> str | None:
        """Get device hostname from status or name."""
        if self.is_gen2:
            sys_info = self.status.get("sys", {}).get("device", {})
            return sys_info.get("name")
        else:
            getinfo = self.status.get("getinfo", {}).get("fw_info", {})
            return getinfo.get("device") or self.name

    def to_dict(self) -> dict[str, Any]:
        """Convert device to dictionary (for backward compatibility)."""
        return {
            "name": self.name,
            "device_type": self.device_type,
            "device_code": self.device_code,
            "access_groups": self.access_groups,
            "online": self.online,
            "status": self.status,
            "settings": self.settings,
        }


class DeviceRegistry:
    """Registry for managing discovered devices."""

    def __init__(self) -> None:
        """Initialize device registry."""
        self._devices: dict[str, Device] = {}
        self._host_map: dict[str, str] = {}  # device_id -> host

    @property
    def devices(self) -> dict[str, Device]:
        """Return all devices."""
        return self._devices

    @property
    def devices_dict(self) -> dict[str, dict[str, Any]]:
        """Return devices as dict of dicts (backward compatibility)."""
        return {did: dev.to_dict() for did, dev in self._devices.items()}

    def get(self, device_id: str) -> Device | None:
        """Get device by ID."""
        return self._devices.get(device_id)

    def get_host(self, device_id: str) -> str | None:
        """Get host for device."""
        device = self._devices.get(device_id)
        return device.host if device else None

    def get_devices_for_host(self, host: str) -> list[str]:
        """Get all device IDs for a specific host."""
        return [
            did for did, dev in self._devices.items()
            if dev.host == host
        ]

    def add_or_update(
        self,
        device_id: str,
        host: str | None = None,
        name: str | None = None,
        device_type: str | None = None,
        device_code: str | None = None,
        access_groups: str | None = None,
        online: bool | None = None,
        status: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> tuple[Device, bool]:
        """Add or update a device.

        Returns:
            Tuple of (device, is_new)
        """
        is_new = device_id not in self._devices

        if is_new:
            device = Device(device_id=device_id)
            self._devices[device_id] = device
        else:
            device = self._devices[device_id]

        # Update fields if provided
        if host is not None:
            device.host = host
        if name is not None:
            device.name = name
        if device_type is not None:
            device.device_type = device_type
        if device_code is not None:
            device.device_code = device_code
        if access_groups is not None:
            device.access_groups = access_groups
        if online is not None:
            device.online = online
        if status is not None:
            device.status = status
        if settings is not None:
            device.settings = settings

        if is_new:
            _LOGGER.info("New device registered: %s", device_id)
        else:
            _LOGGER.debug("Device updated: %s", device_id)

        return device, is_new

    def remove(self, device_id: str) -> Device | None:
        """Remove a device from registry."""
        device = self._devices.pop(device_id, None)
        if device:
            _LOGGER.info("Device removed: %s", device_id)
        return device

    def exists(self, device_id: str) -> bool:
        """Check if device exists."""
        return device_id in self._devices


def extract_name_from_status(status: dict[str, Any], is_gen2: bool) -> str | None:
    """Extract device name from status data.

    Args:
        status: Device status dictionary
        is_gen2: Whether device is Gen2/Gen3

    Returns:
        Device name or None
    """
    if is_gen2:
        sys_info = status.get("sys", {}).get("device", {})
        return sys_info.get("name")
    else:
        getinfo = status.get("getinfo", {}).get("fw_info", {})
        return getinfo.get("device")


def extract_name_from_settings(settings: dict[str, Any]) -> str | None:
    """Extract device name from settings data.

    Args:
        settings: Device settings dictionary

    Returns:
        Device name or None
    """
    # Gen2: name in settings root
    name = settings.get("name")
    if name:
        return name

    # Gen1: name in device section
    device_section = settings.get("device", {})
    return device_section.get("hostname")


def is_gen2_status(status: dict[str, Any]) -> bool:
    """Check if status is from a Gen2/Gen3 device."""
    return any(
        re.match(r"switch:\d+|light:\d+|cover:\d+|input:\d+", key)
        for key in status.keys()
    )
