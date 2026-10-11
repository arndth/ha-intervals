"""Sensoren. Mit state_class bekommen sie HAs Langzeitstatistik gratis —
dafür braucht es weder InfluxDB noch Grafana."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IntervalsCoordinator

DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="ctl", name="Fitness", icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="atl", name="Ermüdung", icon="mdi:battery-charging-low",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="form", name="Form", icon="mdi:speedometer",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="wochen_km", name="Wochenkilometer", icon="mdi:map-marker-distance",
        native_unit_of_measurement="km", state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tage_bis_rennen", name="Tage bis zum Rennen", icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="naechste_einheit", name="Nächste Einheit", icon="mdi:run",
    ),
    SensorEntityDescription(
        key="vo2max", name="VO2max", icon="mdi:lungs",
        native_unit_of_measurement="ml/kg/min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coordinator: IntervalsCoordinator = hass.data[DOMAIN][entry.entry_id]
    add(IntervalsSensor(coordinator, d) for d in DESCRIPTIONS)


class IntervalsSensor(CoordinatorEntity[IntervalsCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: IntervalsCoordinator, description: SensorEntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def native_value(self):
        key = self.entity_description.key
        data = self.coordinator.data or {}

        if key == "vo2max":
            return data.get("vo2max")

        if key in ("ctl", "atl", "form"):
            v = data.get(key)
            return round(v, 1) if v is not None else None

        if key == "tage_bis_rennen":
            r = self.coordinator.race_date
            return (r - date.today()).days if r else None

        if key == "wochen_km":
            return data.get("wochen_km")

        if key == "naechste_einheit":
            heute = date.today()
            kommend = [s for s in self.coordinator.planned_sessions() if s.day >= heute]
            return kommend[0].name if kommend else "—"

        return None

    @property
    def extra_state_attributes(self):
        if self.entity_description.key != "naechste_einheit":
            return None
        heute = date.today()
        kommend = [s for s in self.coordinator.planned_sessions() if s.day >= heute]
        if not kommend:
            return None
        s = kommend[0]
        return {
            "event_id": s.event_id,
            "tag": s.day.isoformat(),
            "art": s.kind,
            "last": s.load,
            "km": s.km,
            "beschreibung": s.description,
        }
