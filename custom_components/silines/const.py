"""Constants for the Silines integration."""

from homeassistant.const import Platform

DOMAIN = "silines"

DEFAULT_IP = "192.168.1.20"
DEFAULT_PORT = 80
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_UPDATE_INTERVAL = 10
DEFAULT_API_TIMEOUT = 3

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.TEXT
]
