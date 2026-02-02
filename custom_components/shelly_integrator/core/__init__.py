"""Core business logic layer.

This module contains domain logic for:
- Device management and discovery
- Command building
- Consent URL handling
"""
from .devices import DeviceRegistry, Device
from .consent import build_consent_url, parse_webhook_payload

__all__ = [
    "DeviceRegistry",
    "Device",
    "build_consent_url",
    "parse_webhook_payload",
]
