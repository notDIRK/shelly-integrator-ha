"""Shelly Cloud API layer.

This module handles all network communication with Shelly Cloud:
- Authentication (JWT token management)
- WebSocket connections
- HTTP API calls
"""
from .auth import ShellyAuth
from .websocket import ShellyWebSocket

__all__ = ["ShellyAuth", "ShellyWebSocket"]
