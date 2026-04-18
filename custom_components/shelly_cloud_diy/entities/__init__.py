"""Entity layer for Shelly Cloud DIY.

This module contains:
- Base entity class with shared logic
- Entity descriptions for sensors/binary sensors
- Entity factory functions
"""
from .base import ShellyBaseEntity
from .descriptions import (
    BlockSensorDescription,
    RpcSensorDescription,
    BlockBinarySensorDescription,
    RpcBinarySensorDescription,
    BLOCK_SENSORS,
    RPC_SENSORS,
    BLOCK_BINARY_SENSORS,
    RPC_BINARY_SENSORS,
    get_model_name,
)

__all__ = [
    "ShellyBaseEntity",
    "BlockSensorDescription",
    "RpcSensorDescription",
    "BlockBinarySensorDescription",
    "RpcBinarySensorDescription",
    "BLOCK_SENSORS",
    "RPC_SENSORS",
    "BLOCK_BINARY_SENSORS",
    "RPC_BINARY_SENSORS",
    "get_model_name",
]
