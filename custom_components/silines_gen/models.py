"""Standard Data Models and State Maps for all Silines devices."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StandardSensor:
    """Sensor model mapping raw attributes to a typed metric."""
    id: str
    value: float | None
    valid: bool
    sensor_type: str
    name: str


@dataclass(frozen=True)
class StandardRelay:
    """Relay model matching standard hardware channels."""
    id: int
    name: str
    is_on: bool
    available: bool


@dataclass(frozen=True)
class StandardInput:
    """Binary input model matching discrete hardware channels."""
    id: int
    name: str
    is_on: bool
    valid: bool


class SilinesDeviceState:
    """Universal state registry structuring response vectors into typed dictionaries."""

    def __init__(self, raw_data: dict[str, Any], entry_unique_id: str) -> None:
        """Initialize device data maps directly from raw dictionaries."""
        self.device_name: str = str(raw_data.get("DEV_N", "Silines Device")).strip()
        self.reboot_active: bool = bool(raw_data.get("REBOOT", False))
        self.device_prefix: str = entry_unique_id

        self.sensor_map: dict[tuple[str, str], StandardSensor] = {}
        self.relay_map: dict[int, StandardRelay] = {}
        self.input_map: dict[int, StandardInput] = {}
        self.srs_htr_map: dict[str, bool] = {}

        self._parse_relays(raw_data.get("REL", []))
        self._parse_inputs(raw_data.get("INP", []))
        self._parse_sensors(raw_data.get("SENS", []))
        self._parse_external_srs(raw_data.get("SRS", []))

    def _parse_relays(self, rel_list: list[Any] | None) -> None:
        """Parse relay telemetry supporting both nested lists and flat bool vectors."""
        if not isinstance(rel_list, list):
            return

        for idx, item in enumerate(rel_list):
            relay_id = idx + 1
            name = ""
            is_on = bool(item)
            available = True

            if isinstance(item, (list, tuple)) and len(item) >= 2:
                name = str(item[0]).strip()
                is_on = bool(item[1])
                available = bool(item[2]) if len(item) > 3 else True

            self.relay_map[relay_id] = StandardRelay(
                id=relay_id,
                name=name if name else f"Relay {relay_id}",
                is_on=is_on,
                available=available,
            )

    def _parse_inputs(self, inp_list: list[Any] | None) -> None:
        """Parse tri-state discrete input arrays handling line fault conditions."""
        if not isinstance(inp_list, list):
            return

        for idx, item in enumerate(inp_list):
            input_id = idx + 1
            friendly_name = f"Input {input_id}"
            raw_status = item

            if isinstance(item, (list, tuple)) and len(item) > 0:
                raw_status = item[0]
                if len(item) >= 2 and str(item[1]).strip():
                    friendly_name = str(item[1]).strip()

            try:
                status_int = int(raw_status)
                is_on = status_int == 1
                is_valid = status_int != 2
            except (ValueError, TypeError):
                is_on = False
                is_valid = False

            self.input_map[input_id] = StandardInput(
                id=input_id, name=friendly_name, is_on=is_on, valid=is_valid
            )

    def _add_metric(
        self,
        item: dict[str, Any],
        raw_key: str,
        hardware_id: str,
        sensor_type: str,
        friendly_name: str,
        is_valid: bool,
    ) -> None:
        """Isolate floating point parsing and dictionary assembly to completely eliminate duplication."""
        if raw_key not in item or item.get(raw_key) is None:
            return

        try:
            val = float(item[raw_key])
            metric_valid = is_valid
        except (ValueError, TypeError):
            val = None
            metric_valid = False

        self.sensor_map[(hardware_id, sensor_type)] = StandardSensor(
            id=hardware_id,
            value=val,
            valid=metric_valid,
            sensor_type=sensor_type,
            name=friendly_name,
        )

    def _parse_sensors(self, sens_list: list[Any] | None) -> None:
        """Deconstruct combined hardware SENS objects into isolated map keys."""
        if not isinstance(sens_list, list):
            return

        for idx, item in enumerate(sens_list):
            if not isinstance(item, dict):
                continue

            is_valid = item.get("S") is True or item.get("S") == 1
            raw_name = str(item.get("N", "")).strip()
            friendly_name = raw_name if raw_name else f"Sensor {idx + 1}"

            hardware_id = f"SOC_{idx}"
            self._add_metric(item, "T", hardware_id, "TEMP", friendly_name, is_valid)
            self._add_metric(item, "H", hardware_id, "HUM", friendly_name, is_valid)

    def _parse_external_srs(self, srs_data: Any) -> None:
        """Deconstruct external modular bus payloads normalizing nested data contexts."""
        if isinstance(srs_data, list):
            raw_list = srs_data
        elif isinstance(srs_data, dict):
            raw_list = srs_data.get("DATA", []) or srs_data.get("SENS", [])
        else:
            return

        if not isinstance(raw_list, list):
            return

        for item in raw_list:
            if not isinstance(item, dict):
                continue

            raw_name = str(item.get("N") or item.get("id", "")).strip()
            hardware_id = raw_name.upper()
            if item.get("id"):
                hardware_id = str(item.get("id")).strip().upper()

            if not hardware_id:
                continue

            friendly_name = raw_name if raw_name else hardware_id

            if "HTR" in item:
                self.srs_htr_map[hardware_id] = bool(item.get("HTR", False))

            is_valid = item.get("S") is True or item.get("S") == 1

            self._add_metric(item, "T", hardware_id, "TEMP", friendly_name, is_valid)
            self._add_metric(item, "H", hardware_id, "HUM", friendly_name, is_valid)
