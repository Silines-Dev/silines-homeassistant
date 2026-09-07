"""Silines integration lifecycle and DataUpdateCoordinator implementation."""

import asyncio
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, PLATFORMS, DEFAULT_API_TIMEOUT
from .models import SilinesDeviceState, StandardRelay
import logging

_LOGGER = logging.getLogger(__name__)


type SilinesConfigEntry = ConfigEntry["SilinesCoordinator"]


async def async_setup_entry(hass: HomeAssistant, entry: SilinesConfigEntry) -> bool:
    """Set up Silines integration from a config entry."""

    cache_key = f"silines_cache_{entry.data['ip']}_{entry.data['port']}"
    initial_data = hass.data.pop(cache_key, None)

    coordinator = SilinesCoordinator(hass, entry, initial_data=initial_data)
    entry.runtime_data = coordinator

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SilinesConfigEntry) -> bool:
    """Unload a config entry."""
    entry.runtime_data.cancel_background_tasks()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

class SilinesHttpClient:
    """Transport layer: Handles raw HTTP network operations only."""

    class SilinesHttpClientException(Exception):
        pass

    def __init__(self, session: aiohttp.ClientSession, config_entry: SilinesConfigEntry) -> None:
        """Initialize the raw HTTP transport client."""
        self._session = session
        self._config_entry = config_entry
        self.api_timeout = float(config_entry.data.get("api_timeout", DEFAULT_API_TIMEOUT))

    def get_url(self, url_path: str) -> str:
        """Dynamically build the absolute URL endpoint path."""
        ip = self._config_entry.data["ip"]
        port = self._config_entry.data["port"]
        return f"http://{ip}:{port}{url_path}"

    @property
    def auth(self) -> aiohttp.BasicAuth:
        """Dynamically construct credentials payload supporting runtime authorization updates."""
        return aiohttp.BasicAuth(
            self._config_entry.data["username"], self._config_entry.data["password"]
        )

    async def get_json(self, url_path: str) -> dict[str, Any]:
        """Execute atomic HTTP GET operation and return raw JSON dictionary."""
        data_url = self.get_url(url_path)
        try:
            async with asyncio.timeout(self.api_timeout + 2):
                async with self._session.get(
                    data_url, auth=self.auth, timeout=aiohttp.ClientTimeout(total=self.api_timeout)
                ) as response:
                    if response.status in (401, 403):
                        raise SilinesHttpClient.SilinesHttpClientException(
                            f"Authentication failed for Silines device at {self._config_entry.data['ip']}:{self._config_entry.data['port']}: HTTP {response.status}"
                        )
                    if response.status != 200:
                        raise SilinesHttpClient.SilinesHttpClientException(f"HTTP Error {response.status}: {response.reason}")
                    raw_json = await response.json(content_type=None)
                    if not isinstance(raw_json, dict):
                        raise SilinesHttpClient.SilinesHttpClientException("Response is not a valid JSON dictionary")
                    return raw_json
        except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise SilinesHttpClient.SilinesHttpClientException(f"Connection error: {err}") from err
        except (ValueError, TypeError) as err:
            raise SilinesHttpClient.SilinesHttpClientException(f"Data format corruption or invalid types received: {err}") from err
        except Exception as err:
            raise SilinesHttpClient.SilinesHttpClientException(f"Unexpected exception: {err}") from err

    async def send_post(self, url_path: str, data: dict[str, Any], command_name: str) -> str | None:
        """Execute atomic HTTP POST operation to submit CGI payload controls."""
        post_url = self.get_url(url_path)
        try:
            async with asyncio.timeout(self.api_timeout + 2):
                async with self._session.post(
                    post_url, data=data, auth=self.auth, timeout=aiohttp.ClientTimeout(total=self.api_timeout)
                ) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Failed to execute command '%s' on Silines controller %s, status code: %s",command_name,self._config_entry.data["ip"],response.status,)
                        raise SilinesHttpClient.SilinesHttpClientException(f"HTTP Error {response.status}: {response.reason}")
                    return await response.text()
        except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise SilinesHttpClient.SilinesHttpClientException(f"Connection error: {err}") from err
        except Exception as err:
            raise SilinesHttpClient.SilinesHttpClientException(f"Unexpected exception: {err}") from err

class SilinesCoordinator(DataUpdateCoordinator[SilinesDeviceState]):
    """Network/Logical layer: Processes business logic and manages Home Assistant state/exceptions."""

    config_entry: SilinesConfigEntry
    http_client: SilinesHttpClient

    def __init__(self, hass: HomeAssistant, entry: SilinesConfigEntry, initial_data: dict[str, Any] | None = None) -> None:
        """Initialize Silines coordinator caching hardware credentials."""
        self.config_entry = entry
        
        session = async_get_clientsession(hass)
        self.http_client = SilinesHttpClient(session, entry)
        
        self.registered_sensor_uids: set[tuple[str, str]] = set()
        self.pulse_durations: dict[int, int] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._initial_data = initial_data
        self.relay_switches: dict[int, Any] = {}
        self.switch_lock: dict[str, list[int]] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=f"Silines {entry.unique_id}",
            update_interval=timedelta(seconds=entry.data.get("update_interval", 10)),
            config_entry=entry
        )

    def cancel_background_tasks(self) -> None:
        """Cancel all pending pulse refresh tasks during integration unload."""
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

    async def _async_update_data(self) -> SilinesDeviceState:
        """Fetch regular status data updates from main.json API endpoint."""
        if self._initial_data is not None:
            raw_json = self._initial_data
            self._initial_data = None
            return SilinesDeviceState(raw_json, self.config_entry.unique_id)

        for id in self.switch_lock:
            self.switch_lock[id][0] = 1
       
        try:
            raw_json = await self.http_client.get_json("/api/main.json")
            return SilinesDeviceState(raw_json, self.config_entry.unique_id)
        except Exception as err:
            for id in self.switch_lock: self.switch_lock[id][0] = 0
            raise UpdateFailed(err) from err

    def set_sheduled_refresh(self, delay_sec: float, debug_name: str | None) -> None:
        async def refresh(delay_seconds: float) -> None:
            await asyncio.sleep(delay_seconds)
            try:
                await self.async_refresh()
            except Exception as err:
                _LOGGER.debug("Silent background pulse refresh skipped: %s", err)
        task = self.hass.async_create_background_task(refresh(delay_sec), name=debug_name)
        self._background_tasks.add(task)
        task.add_done_callback(lambda t, *_: self._background_tasks.discard(t))
