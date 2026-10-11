"""Einrichtung über die Oberfläche: Schlüssel, Athlet, Wettkampf."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IntervalsAuthError, IntervalsClient, IntervalsConnectionError
from .const import (
    CONF_ANTHROPIC_KEY,
    CONF_API_KEY,
    CONF_ATHLETE_ID,
    CONF_MODEL,
    CONF_RACE_DATE,
    CONF_RACE_DISTANCE,
    CONF_RACE_GOAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

STEP_USER = vol.Schema(
    {vol.Required(CONF_API_KEY): str, vol.Required(CONF_ATHLETE_ID): str}
)

STEP_RACE = vol.Schema(
    {
        vol.Required(CONF_RACE_DATE): str,
        vol.Required(CONF_RACE_DISTANCE, default=13.0): vol.Coerce(float),
        vol.Optional(CONF_RACE_GOAL, default=0): vol.Coerce(int),
    }
)


class IntervalsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            athlete = user_input[CONF_ATHLETE_ID].strip()
            # intervals.icu schreibt die ID mit führendem i — beide Formen zulassen.
            if athlete.isdigit():
                athlete = f"i{athlete}"
            await self.async_set_unique_id(athlete)
            self._abort_if_unique_id_configured()

            client = IntervalsClient(
                async_get_clientsession(self.hass),
                user_input[CONF_API_KEY].strip(),
                athlete,
            )
            try:
                await client.async_validate()
            except IntervalsAuthError:
                errors["base"] = "auth"
            except IntervalsConnectionError:
                errors["base"] = "connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                self._data = {
                    CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                    CONF_ATHLETE_ID: athlete,
                }
                return await self.async_step_race()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER, errors=errors
        )

    async def async_step_race(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=f"Intervals.icu {self._data[CONF_ATHLETE_ID]}", data=self._data
            )
        return self.async_show_form(step_id="race", data_schema=STEP_RACE)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return IntervalsOptionsFlow()


class IntervalsOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=720)),
                    vol.Optional(
                        CONF_ANTHROPIC_KEY, default=o.get(CONF_ANTHROPIC_KEY, "")
                    ): str,
                    vol.Optional(
                        CONF_MODEL, default=o.get(CONF_MODEL, DEFAULT_MODEL)
                    ): str,
                }
            ),
        )
