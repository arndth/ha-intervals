"""Dünner Client für die intervals.icu-REST-API.

Auth ist HTTP Basic mit dem Benutzernamen `API_KEY` — wörtlich, nicht als
Platzhalter — und dem persönlichen Schlüssel als Passwort.

Limits laut Anbieter: 5000 Aufrufe/Tag, 2500 je 15 Minuten, 10/s je IP.
Beim Standardintervall von 20 Minuten liegen wir bei rund 200/Tag.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import aiohttp

from .const import API_BASE, API_USER

_LOGGER = logging.getLogger(__name__)


class IntervalsAuthError(Exception):
    """Schlüssel oder Athlete-ID werden abgelehnt."""


class IntervalsConnectionError(Exception):
    """intervals.icu nicht erreichbar oder antwortet mit 5xx."""


class IntervalsClient:
    """Aufrufe gegen intervals.icu. Nutzt die geteilte Session von HA."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        athlete_id: str,
    ) -> None:
        self._session = session
        self._auth = aiohttp.BasicAuth(API_USER, api_key)
        self.athlete_id = athlete_id

    # ── intern ───────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        url = f"{API_BASE}{path}"
        try:
            async with self._session.request(
                method,
                url,
                auth=self._auth,
                params=params,
                json=json,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403):
                    raise IntervalsAuthError(f"{resp.status} auf {path}")
                if resp.status == 404:
                    # Ein fehlendes Event ist kein Verbindungsfehler, sondern
                    # ein normaler Zustand — etwa wenn der Agent zweimal löscht.
                    return None
                if resp.status >= 500:
                    raise IntervalsConnectionError(f"{resp.status} auf {path}")
                resp.raise_for_status()
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except aiohttp.ClientError as err:
            raise IntervalsConnectionError(str(err)) from err

    # ── Lesen ────────────────────────────────────────────────────────────

    async def async_get_activities(self, oldest: date, newest: date) -> list[dict]:
        """Aktivitäten im Zeitraum. Hinweis des Anbieters: aus Strava
        importierte Daten gibt die API nicht heraus."""
        return (
            await self._request(
                "GET",
                f"/athlete/{self.athlete_id}/activities",
                params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
            )
            or []
        )

    async def async_get_wellness(self, oldest: date, newest: date) -> list[dict]:
        """Tageswerte: ctl, atl, rampRate, hrv, restingHR, weight, sleep."""
        return (
            await self._request(
                "GET",
                f"/athlete/{self.athlete_id}/wellness",
                params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
            )
            or []
        )

    async def async_get_events(self, oldest: date, newest: date) -> list[dict]:
        """Kalendereinträge — die geplanten Einheiten."""
        return (
            await self._request(
                "GET",
                f"/athlete/{self.athlete_id}/events",
                params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
            )
            or []
        )

    async def async_get_streams(
        self, activity_id: str, types: list[str] | None = None
    ) -> dict[str, list]:
        """Zeitreihen einer Aktivität.

        Rückgabe als Dict nach Typ, damit die Auswertung nicht auf die
        Reihenfolge der Liste angewiesen ist.
        """
        types = types or [
            "time",
            "distance",
            "heartrate",
            "velocity_smooth",
            "altitude",
            "cadence",
        ]
        raw = await self._request(
            "GET",
            f"/activity/{activity_id}/streams",
            params={"types": ",".join(types)},
        )
        if not raw:
            return {}
        return {s["type"]: s.get("data", []) for s in raw if "type" in s}

    # ── Schreiben ────────────────────────────────────────────────────────

    async def async_create_event(self, payload: dict) -> dict | None:
        return await self._request(
            "POST", f"/athlete/{self.athlete_id}/events", json=payload
        )

    async def async_update_event(self, event_id: str | int, payload: dict) -> dict | None:
        return await self._request(
            "PUT", f"/athlete/{self.athlete_id}/events/{event_id}", json=payload
        )

    async def async_delete_event(self, event_id: str | int) -> None:
        await self._request("DELETE", f"/athlete/{self.athlete_id}/events/{event_id}")

    # ── Prüfung beim Einrichten ──────────────────────────────────────────

    async def async_validate(self) -> None:
        """Wirft IntervalsAuthError bzw. IntervalsConnectionError.

        Ein billiger Aufruf genügt: ein Tag Wellness statt der ganzen Historie.
        """
        today = date.today()
        await self._request(
            "GET",
            f"/athlete/{self.athlete_id}/wellness",
            params={"oldest": today.isoformat(), "newest": today.isoformat()},
        )
