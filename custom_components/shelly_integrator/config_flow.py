"""Config flow for Shelly Integrator."""
from __future__ import annotations

import logging
import secrets
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url

from .const import (
    DOMAIN,
    API_GET_TOKEN,
    INTEGRATOR_TAG,
    CONF_INTEGRATOR_TOKEN,
    CONF_LOCAL_GATEWAY_URL,
    CONF_WEBHOOK_ID,
    SHELLY_CONSENT_URL,
)
from .core.consent import build_consent_url
from .utils import validate_gateway_url

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_INTEGRATOR_TOKEN): str,
        vol.Optional(CONF_LOCAL_GATEWAY_URL): str,
    }
)


class ShellyIntegratorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shelly Integrator."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._token: str | None = None
        self._gateway_url: str | None = None
        self._webhook_id: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ShellyIntegratorOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - token input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_INTEGRATOR_TOKEN]

            # Validate optional gateway URL before hitting the network
            raw_gw = user_input.get(CONF_LOCAL_GATEWAY_URL)
            safe_gw: str | None = None
            if raw_gw:
                try:
                    safe_gw = validate_gateway_url(raw_gw)
                except ValueError:
                    errors[CONF_LOCAL_GATEWAY_URL] = "invalid_gateway_url"

            if not errors:
                # Validate credentials by trying to get JWT
                try:
                    session = async_get_clientsession(self.hass)
                    async with session.post(
                        API_GET_TOKEN,
                        data={"itg": INTEGRATOR_TAG, "token": token},
                    ) as response:
                        data = await response.json()

                        if not data.get("isok"):
                            errors["base"] = "invalid_auth"
                        else:
                            # Only allow one instance of this integration
                            await self.async_set_unique_id(INTEGRATOR_TAG)
                            self._abort_if_unique_id_configured()

                            # Store token + validated gateway URL + fresh
                            # per-install webhook id, then proceed to consent.
                            self._token = token
                            self._gateway_url = safe_gw
                            self._webhook_id = secrets.token_urlsafe(16)
                            return await self.async_step_consent()

                except aiohttp.ClientError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_consent(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the consent step - show link to grant device access."""
        if user_input is not None:
            # User clicked submit, create the entry
            # Store gateway URL in options if provided (from step 1)
            options = {}
            if self._gateway_url:
                options[CONF_LOCAL_GATEWAY_URL] = self._gateway_url

            return self.async_create_entry(
                title="Shelly Integrator",
                data={
                    CONF_INTEGRATOR_TOKEN: self._token,
                    CONF_WEBHOOK_ID: self._webhook_id,
                },
                options=options,
            )

        # Build consent URL
        consent_url = self._build_consent_url()

        return self.async_show_form(
            step_id="consent",
            data_schema=vol.Schema({}),
            description_placeholders={"consent_url": consent_url},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        # Reuse the entry's stored webhook id so the consent URL rendered
        # here matches the endpoint the running integration listens on.
        if entry:
            self._webhook_id = entry.data.get(CONF_WEBHOOK_ID)

        if user_input is not None:
            token = user_input[CONF_INTEGRATOR_TOKEN]

            # Validate optional gateway URL first
            raw_gw = user_input.get(CONF_LOCAL_GATEWAY_URL, "")
            safe_gw = ""
            if raw_gw:
                try:
                    safe_gw = validate_gateway_url(raw_gw)
                except ValueError:
                    errors[CONF_LOCAL_GATEWAY_URL] = "invalid_gateway_url"

            if not errors:
                # Validate token
                try:
                    session = async_get_clientsession(self.hass)
                    async with session.post(
                        API_GET_TOKEN,
                        data={"itg": INTEGRATOR_TAG, "token": token},
                    ) as response:
                        data = await response.json()

                        if not data.get("isok"):
                            errors["base"] = "invalid_auth"
                        else:
                            # Preserve the per-install webhook_id across
                            # reconfigure — rotating it silently would
                            # break the Shelly Cloud consent callback.
                            existing_webhook_id = (
                                entry.data.get(CONF_WEBHOOK_ID)
                                if entry else None
                            )
                            new_data = {CONF_INTEGRATOR_TOKEN: token}
                            if existing_webhook_id:
                                new_data[CONF_WEBHOOK_ID] = existing_webhook_id
                            new_options = {CONF_LOCAL_GATEWAY_URL: safe_gw}
                            self.hass.config_entries.async_update_entry(
                                entry, data=new_data, options=new_options
                            )
                            await self.hass.config_entries.async_reload(entry.entry_id)
                            return self.async_abort(reason="reconfigure_successful")

                except aiohttp.ClientError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

        # Get current values
        current_token = entry.data.get(CONF_INTEGRATOR_TOKEN, "") if entry else ""
        current_gateway = entry.options.get(CONF_LOCAL_GATEWAY_URL, "") if entry else ""

        # Build consent URL
        consent_url = self._build_consent_url()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_INTEGRATOR_TOKEN, default=current_token): str,
                vol.Optional(CONF_LOCAL_GATEWAY_URL, default=current_gateway): str,
            }),
            errors=errors,
            description_placeholders={"consent_url": consent_url},
        )

    def _build_consent_url(self) -> str:
        """Build the Shelly consent URL using this flow's webhook id."""
        return _safe_build_consent_url(self.hass, self._webhook_id)


class ShellyIntegratorOptionsFlow(OptionsFlow):
    """Handle options flow for Shelly Integrator."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate optional gateway URL
            raw_gw = user_input.get(CONF_LOCAL_GATEWAY_URL, "")
            safe_gw = ""
            if raw_gw:
                try:
                    safe_gw = validate_gateway_url(raw_gw)
                except ValueError:
                    errors[CONF_LOCAL_GATEWAY_URL] = "invalid_gateway_url"

            # If token is provided, validate it
            new_token = user_input.get(CONF_INTEGRATOR_TOKEN)
            if not errors and new_token:
                try:
                    session = async_get_clientsession(self.hass)
                    async with session.post(
                        API_GET_TOKEN,
                        data={"itg": INTEGRATOR_TAG, "token": new_token},
                    ) as response:
                        data = await response.json()
                        if not data.get("isok"):
                            errors["base"] = "invalid_auth"
                except aiohttp.ClientError:
                    errors["base"] = "cannot_connect"

            if not errors:
                # Update token in data if changed
                if new_token:
                    new_data = {**self.config_entry.data, CONF_INTEGRATOR_TOKEN: new_token}
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=new_data
                    )

                # Save options (validated gateway URL)
                options = {CONF_LOCAL_GATEWAY_URL: safe_gw}
                return self.async_create_entry(title="", data=options)

        # Build consent URL
        consent_url = self._build_consent_url()
        
        # Get current values
        current_gateway = self.config_entry.options.get(CONF_LOCAL_GATEWAY_URL, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_INTEGRATOR_TOKEN,
                    description={"suggested_value": ""},
                ): str,
                vol.Optional(
                    CONF_LOCAL_GATEWAY_URL,
                    default=current_gateway,
                ): str,
            }),
            errors=errors,
            description_placeholders={"consent_url": consent_url},
        )

    def _build_consent_url(self) -> str:
        """Build the Shelly consent URL using the entry's webhook id."""
        webhook_id = self.config_entry.data.get(CONF_WEBHOOK_ID)
        return _safe_build_consent_url(self.hass, webhook_id)


def _safe_build_consent_url(hass, webhook_id: str | None) -> str:
    """Build consent URL with fallback on error.

    ``webhook_id`` is the per-install randomised identifier. If missing
    (e.g. a race during initial setup) we fall back to the generic
    integrator landing page so the user still sees a useful link.
    """
    if not webhook_id:
        return f"{SHELLY_CONSENT_URL}?itg={INTEGRATOR_TAG}"
    try:
        ha_url = get_url(hass, prefer_external=True)
        return build_consent_url(INTEGRATOR_TAG, ha_url, webhook_id)
    except Exception as err:
        _LOGGER.warning("Could not build consent URL: %s", err)
        return f"{SHELLY_CONSENT_URL}?itg={INTEGRATOR_TAG}"
