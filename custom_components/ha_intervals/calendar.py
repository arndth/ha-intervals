"""Die geplanten Einheiten als HA-Kalender.

Damit stehen sie in jeder Kalenderkarte und sind für Automationen über
`calendar.get_events` erreichbar — auch für einen externen Agenten.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IntervalsCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    add([TrainingCalendar(hass.data[DOMAIN][entry.entry_id])])


class TrainingCalendar(CoordinatorEntity[IntervalsCoordinator], CalendarEntity):
    _attr_has_entity_name = True
    _attr_name = "Trainingsplan"
    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator: IntervalsCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_plan"

    def _as_event(self, s) -> CalendarEvent:
        return CalendarEvent(
            start=s.day,
            end=s.day + timedelta(days=1),  # Ganztagestermin
            summary=s.name or s.kind,
            description=s.description,
            uid=s.event_id,
        )

    @property
    def event(self) -> CalendarEvent | None:
        heute = date.today()
        kommend = [s for s in self.coordinator.planned_sessions() if s.day >= heute]
        return self._as_event(kommend[0]) if kommend else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        a, b = start_date.date(), end_date.date()
        return [
            self._as_event(s)
            for s in self.coordinator.planned_sessions()
            if a <= s.day <= b
        ]
