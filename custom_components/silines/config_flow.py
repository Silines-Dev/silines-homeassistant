"""Config flow for Silines integration."""

from __future__ import annotations
import asyncio
import logging
from typing import Any
from uuid import uuid4
import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from .const import (
    DEFAULT_IP,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_API_TIMEOUT,
    DEFAULT_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SilinesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Silines integration via Basic Auth."""

    VERSION = 1

    def _get_schema(self, defaults: dict[str, Any], is_reconfigure: bool = False) -> vol.Schema:
        """Return the data schema with dynamic defaults. Separates user flow from reconfigure."""
        return vol.Schema(
            {
                vol.Required("ip", default=defaults.get("ip", DEFAULT_IP)): str,
                vol.Required("port", default=defaults.get("port", DEFAULT_PORT)): int,
                vol.Required("username", default=defaults.get("username", DEFAULT_USERNAME)): str,
                vol.Required(
                    "password", default=defaults.get("password", DEFAULT_PASSWORD)
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    "update_interval",
                    default=defaults.get("update_interval", DEFAULT_UPDATE_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    "api_timeout",
                    default=defaults.get("api_timeout", DEFAULT_API_TIMEOUT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=30,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where the user enters device details."""
        errors: dict[str, str] = {}
        if user_input is not None:

            if user_input["api_timeout"] >= user_input["update_interval"]:
                errors["base"] = "timeout_greater_than_interval"
            else:
                existing_entries = self.hass.config_entries.async_entries(DOMAIN)
                for entry in existing_entries:
                    if entry.data.get("ip") == user_input["ip"] and entry.data.get("port") == user_input["port"]:
                        return self.async_abort(reason="already_configured")

            device_model, valied_json, error_code = await self._test_connection(
                user_input["ip"],
                user_input["port"],
                user_input["username"],
                user_input["password"],
                user_input["api_timeout"]
            )
            if error_code:
                errors["base"] = error_code
            else:
                cache_key = f"silines_cache_{user_input['ip']}_{user_input['port']}"
                self.hass.data[cache_key] = valied_json
                dev_reg = dr.async_get(self.hass)
                silines_devices_total = sum(
                    1 for device in dev_reg.devices.values()
                    if device.manufacturer == "silines"
                )
                instance_counter = silines_devices_total + 1
                
                random_token = uuid4().hex
                final_unique_id = f"silines_{random_token}_{instance_counter}"

                await self.async_set_unique_id(final_unique_id)
                self._abort_if_unique_id_configured()

                display_name = device_model if device_model != "Device" else f"Silines Device {instance_counter}"

                return self.async_create_entry(
                    title=display_name,
                    data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self._get_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of network parameters seamlessly."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            current_update_interval = entry.data.get("update_interval", DEFAULT_UPDATE_INTERVAL)
            if user_input["api_timeout"] >= current_update_interval:
                errors["base"] = "timeout_greater_than_interval"
            else:
                existing_entries = self.hass.config_entries.async_entries(DOMAIN)
                for e in existing_entries:
                    if e.entry_id != entry.entry_id:
                        if e.data.get("ip") == user_input["ip"] and e.data.get("port") == user_input["port"]:
                            return self.async_abort(reason="already_configured")

                device_model, valied_json, error_code = await self._test_connection(
                    user_input["ip"],
                    user_input["port"],
                    user_input["username"],
                    user_input["password"],
                    user_input["api_timeout"]
                )
                if error_code:
                    errors["base"] = error_code
                else:
                    cache_key = f"silines_cache_{user_input['ip']}_{user_input['port']}"
                    self.hass.data[cache_key] = valied_json
                    return self.async_update_reload_and_abort(
                        entry,
                        title=f"Silines {device_model}" if device_model != "Device" else entry.title,
                        data={**entry.data, **user_input}
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._get_schema(user_input or dict(entry.data)),
            errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication if credentials expire or change."""
        return await self.async_step_reconfigure()

    async def _test_connection(
        self, ip: str, port: int, username: str, password: str, api_timeout: float
    ) -> tuple[str | None, dict[str, Any] | None, str | None]:
        """Test API authentication and connection validity."""
        get_url = f"http://{ip}:{port}"
        session = async_get_clientsession(self.hass)
        auth = aiohttp.BasicAuth(username, password)
        data_url = f"{get_url}/api/main.json"

        try:
            async with asyncio.timeout(api_timeout + 2):
                async with session.get(
                    data_url, auth=auth, timeout=aiohttp.ClientTimeout(total=api_timeout) 
                ) as response:
                    if response.status == 200:
                        valied_json = await response.json(content_type=None)
                        return valied_json.get("DEV_N", "Device"), valied_json, None

                    if response.status in (401, 403):
                        return None, None, "invalid_auth"

                    return None, None, "cannot_connect"

        except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError) as e:
            _LOGGER.warning("Network error with Silines at %s: %s", ip, str(e))
            return None, None, "cannot_connect"
        except (ValueError, TypeError, aiohttp.ContentTypeError) as e:
            _LOGGER.error("Invalid response from Silines at %s: %s", ip, str(e))
            return None, None, "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception during Silines validation at %s", ip)
            return None, None, "unknown"
