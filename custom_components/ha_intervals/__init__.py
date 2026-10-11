"""Intervals.icu Laufplan — Einstieg, Services, Panel.

Die Integration ist **agentneutral**: sie kennt Hermes nicht und ruft ihn
nicht auf. Stattdessen bietet sie zwei Schnittstellen, die jeder Agent über
die normale Home-Assistant-API benutzen kann:

  Services  — aufrufbar per REST (`POST /api/services/ha_intervals/<name>`)
              oder WebSocket. Services mit Antwort liefern strukturierte
              Daten zurück, wenn `?return_response` gesetzt ist.

  Events    — auf dem HA-Bus. Ein Agent abonniert sie per WebSocket
              (`subscribe_events`), oder eine HA-Automation hängt sich daran
              und ruft den Agenten per `rest_command` auf.

Damit bleibt die Kopplung bei null: Agent austauschen heißt Automation
ändern, nicht Integration anfassen.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IntervalsAuthError, IntervalsClient, IntervalsConnectionError
from .const import (
    CONF_API_KEY,
    CONF_ATHLETE_ID,
    CONF_RACE_DATE,
    DOMAIN,
    EVENT_PLAN_CHANGED,
    EVENT_PLAN_CONFLICT,
    MOVE_MODES,
    PANEL_COMPONENT,
    PANEL_STATIC_PATH,
    PANEL_URL_PATH,
    SERVICE_ANALYSE,
    SERVICE_BUILD_PLAN,
    SERVICE_DETAIL,
    SERVICE_GET_DATA,
    SERVICE_GET_PLAN,
    SERVICE_MOVE,
    SERVICE_REPLAN,
    SERVICE_SYNC,
)
from .coordinator import IntervalsCoordinator
from .planner import plan_move
from .store import IntervalsStore
from .util import to_iso

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]

# ── Service-Schemata ─────────────────────────────────────────────────────

MOVE_SCHEMA = vol.Schema(
    {
        vol.Required("event_id"): cv.string,
        # "morgen" / "uebermorgen" / ein ISO-Datum
        vol.Required("ziel"): cv.string,
        vol.Optional("modus", default="tauschen"): vol.In(MOVE_MODES),
        vol.Optional("entry_id"): cv.string,
    }
)

REPLAN_SCHEMA = vol.Schema(
    {
        vol.Optional("ab_datum"): cv.string,
        vol.Optional("grund", default=""): cv.string,
        vol.Optional("entry_id"): cv.string,
    }
)

DETAIL_SCHEMA = vol.Schema(
    {
        vol.Required("activity_id"): cv.string,
        vol.Optional("entry_id"): cv.string,
    }
)

ANALYSE_SCHEMA = vol.Schema(
    {
        vol.Optional("activity_id"): cv.string,
        vol.Optional("entry_id"): cv.string,
    }
)

SIMPLE_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})

BUILD_PLAN_SCHEMA = vol.Schema(
    {
        # Vorgabe ist der Trockenlauf. Ein Dienst, der beim ersten Aufruf
        # ungefragt 39 Termine in einen fremden Kalender schreibt, wäre eine
        # unangenehme Überraschung.
        vol.Optional("trocken", default=True): cv.boolean,
        vol.Optional("ziel_pace"): cv.string,
        # Ohne Angabe wird der heutige Stand aus den Läufen der letzten
        # 120 Tage geschätzt.
        vol.Optional("start_pace"): cv.string,
        vol.Optional("locker_pace"): cv.string,
        vol.Optional("basis_km"): vol.Coerce(float),
        vol.Optional("entry_id"): cv.string,
    }
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("tage", default=91): vol.All(
            vol.Coerce(int), vol.Range(min=7, max=365)
        ),
        vol.Optional("entry_id"): cv.string,
    }
)


def _parse_target(value: str) -> date:
    """`morgen`, `uebermorgen`, `heute` oder ein ISO-Datum."""
    today = date.today()
    key = value.strip().lower()
    if key in ("heute", "today"):
        return today
    if key in ("morgen", "tomorrow"):
        return today + timedelta(days=1)
    if key in ("uebermorgen", "übermorgen"):
        return today + timedelta(days=2)
    try:
        return date.fromisoformat(value)
    except ValueError as err:
        raise HomeAssistantError(
            f"'{value}' ist kein Datum. Erlaubt: heute, morgen, uebermorgen "
            "oder JJJJ-MM-TT."
        ) from err


# ── Einstieg ─────────────────────────────────────────────────────────────


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eine Athleten-Konfiguration einrichten."""
    client = IntervalsClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data[CONF_ATHLETE_ID],
    )

    try:
        await client.async_validate()
    except IntervalsAuthError as err:
        # Schlüssel zurückgezogen oder geändert: HA fragt den Nutzer neu.
        raise ConfigEntryAuthFailed(str(err)) from err
    except IntervalsConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    # Altlasten geradeziehen: v0.1.0 hat jede Zeichenkette als Renndatum
    # angenommen. Einmal beim Start normalisieren, damit bestehende
    # Einrichtungen nach dem Update ohne Zutun funktionieren.
    roh = entry.data.get(CONF_RACE_DATE)
    iso = to_iso(roh)
    if roh and iso and roh != iso:
        _LOGGER.info("Renndatum %s auf %s normalisiert", roh, iso)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_RACE_DATE: iso}
        )
    elif roh and not iso:
        _LOGGER.warning(
            "Renndatum %r ist unlesbar und wird ignoriert. In den Optionen "
            "der Integration neu setzen.", roh
        )

    store = IntervalsStore(hass, entry.entry_id)
    await store.async_init()

    coordinator = IntervalsCoordinator(hass, entry, client, store)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_panel(hass)
    _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        coordinator: IntervalsCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.store.async_close()
        if not hass.data[DOMAIN]:
            for svc in (
                SERVICE_SYNC,
                SERVICE_MOVE,
                SERVICE_REPLAN,
                SERVICE_ANALYSE,
                SERVICE_GET_PLAN,
                SERVICE_BUILD_PLAN,
    SERVICE_DETAIL,
    SERVICE_GET_DATA,
            ):
                hass.services.async_remove(DOMAIN, svc)
    return ok


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ── Panel ────────────────────────────────────────────────────────────────


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Das gebaute React-Bundle als Seitenleisten-Panel anmelden.

    Als Custom Element, nicht als iframe: nur so bekommt die Seite das
    `hass`-Objekt übergeben und erbt damit die Anmeldung des Nutzers. Ein
    iframe müsste sich separat ausweisen — und dann läge wieder irgendwo ein
    langlebiger Token herum.
    """
    if hass.data.get(f"{DOMAIN}_panel_registered"):
        return

    panel_dir = Path(__file__).parent / "panel"
    bundle = panel_dir / f"{PANEL_COMPONENT}.js"
    if not bundle.exists():
        _LOGGER.warning(
            "Panel-Bundle fehlt (%s). Die Integration läuft, aber die "
            "Seitenleiste bleibt leer. Bei einer HACS-Installation sollte das "
            "nicht vorkommen — bei einer Kopie aus dem Quellcode muss "
            "'npm run build' im Ordner frontend/ gelaufen sein.",
            bundle,
        )
        return

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_PATH, str(panel_dir), False)]
        )

        from homeassistant.components import panel_custom

        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_COMPONENT,
            module_url=f"{PANEL_STATIC_PATH}/{PANEL_COMPONENT}.js",
            sidebar_title="Laufen",
            sidebar_icon="mdi:run-fast",
            require_admin=False,
        )
        hass.data[f"{DOMAIN}_panel_registered"] = True
    except Exception:  # noqa: BLE001
        # Die Panel-API hat sich in HA schon mehrfach geändert. Wenn sie
        # bricht, soll die Integration trotzdem laufen — Sensoren, Services
        # und Events sind davon unabhängig.
        _LOGGER.exception(
            "Panel konnte nicht angemeldet werden. Sensoren und Services "
            "laufen weiter."
        )


# ── Services ─────────────────────────────────────────────────────────────


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> IntervalsCoordinator:
    """Den Koordinator wählen. Bei nur einem Athleten ist `entry_id` optional."""
    entries: dict[str, IntervalsCoordinator] = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("Keine eingerichtete Intervals.icu-Konfiguration.")
    entry_id = call.data.get("entry_id")
    if entry_id:
        if entry_id not in entries:
            raise HomeAssistantError(f"Unbekannte entry_id: {entry_id}")
        return entries[entry_id]
    if len(entries) > 1:
        raise HomeAssistantError(
            "Mehrere Athleten eingerichtet — 'entry_id' angeben."
        )
    return next(iter(entries.values()))


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SYNC):
        return

    async def _sync(call: ServiceCall) -> ServiceResponse:
        c = _coordinator(hass, call)
        await c.async_request_refresh()
        return {"stand": c.data.get("stand") if c.data else None}

    async def _move(call: ServiceCall) -> ServiceResponse:
        """Eine Einheit verschieben, tauschen oder streichen.

        Antwortet strukturiert — auch bei Ablehnung, samt zulässiger
        Alternativen. Ein Agent kann daraus unmittelbar den nächsten Zug
        wählen, ohne raten zu müssen.
        """
        c = _coordinator(hass, call)
        target = _parse_target(call.data["ziel"])
        mode = call.data["modus"]
        event_id = str(call.data["event_id"])

        plan = c.planned_sessions()
        race = c.entry.data.get(CONF_RACE_DATE)
        result = plan_move(
            plan,
            event_id,
            target,
            mode,
            target_week_load=c.target_week_load(target),
            race_date=date.fromisoformat(race) if race else None,
        )

        payload: dict = {
            "ok": result.ok,
            "modus": mode,
            "ziel": target.isoformat(),
            "hinweise": result.notes,
            "umplanung_noetig": result.needs_replan,
            "aenderungen": [
                {
                    "event_id": ch.event_id,
                    "aktion": ch.action,
                    "neuer_tag": ch.new_day.isoformat() if ch.new_day else None,
                }
                for ch in result.changes
            ],
            "konflikte": [
                {"regel": v.rule, "text": v.message} for v in result.violations
            ],
            "alternativen": [
                {
                    "modus": a.mode,
                    "ziel": a.target_day.isoformat(),
                    "text": a.label,
                }
                for a in result.alternatives
            ],
        }

        if not result.ok:
            hass.bus.async_fire(EVENT_PLAN_CONFLICT, payload)
            return payload

        await c.async_apply_changes(result.changes)
        hass.bus.async_fire(EVENT_PLAN_CHANGED, payload)
        return payload

    async def _replan(call: ServiceCall) -> ServiceResponse:
        c = _coordinator(hass, call)
        ab = call.data.get("ab_datum")
        return await c.async_replan(
            date.fromisoformat(ab) if ab else date.today(),
            call.data.get("grund", ""),
        )

    async def _analyse(call: ServiceCall) -> ServiceResponse:
        c = _coordinator(hass, call)
        return await c.async_analyse(call.data.get("activity_id"))

    async def _get_plan(call: ServiceCall) -> ServiceResponse:
        """Den Plan auslesen — der Lesezugriff für einen externen Agenten."""
        c = _coordinator(hass, call)
        return {
            "renntag": c.race_date.isoformat() if c.race_date else None,
            "einheiten": [
                {
                    "event_id": s.event_id,
                    "tag": s.day.isoformat(),
                    "art": s.kind,
                    "name": s.name,
                    "last": s.load,
                    "km": s.km,
                    "beschreibung": s.description,
                }
                for s in c.planned_sessions()
            ],
        }

    async def _get_data(call: ServiceCall) -> ServiceResponse:
        """Alles, was das Dashboard zeigt — in einem Aufruf.

        Dieselbe Quelle, aus der auch ein externer Agent liest. Es gibt
        bewusst keine zweite, bevorzugte Schnittstelle fürs Frontend.
        """
        c = _coordinator(hass, call)
        return await c.async_panel_data(call.data.get("tage", 91))

    async def _build_plan(call: ServiceCall) -> ServiceResponse:
        c = _coordinator(hass, call)
        roh = call.data.get("ziel_pace")
        if roh:
            try:
                m, sek = str(roh).split(":")
                pace = int(m) * 60 + int(sek)
            except ValueError:
                raise HomeAssistantError(
                    f"'{roh}' ist keine Pace. Erwartet wird MM:SS, etwa 5:00."
                ) from None
        else:
            pace = 300
        start = call.data.get("start_pace")
        start_s = None
        if start:
            try:
                m, sek = str(start).split(":")
                start_s = int(m) * 60 + int(sek)
            except ValueError:
                raise HomeAssistantError(
                    f"'{start}' ist keine Pace. Erwartet wird MM:SS."
                ) from None
        locker = call.data.get("locker_pace")
        locker_s = None
        if locker:
            try:
                m, sek = str(locker).split(":")
                locker_s = int(m) * 60 + int(sek)
            except ValueError:
                raise HomeAssistantError(
                    f"'{locker}' ist keine Pace. Erwartet wird MM:SS."
                ) from None
        result = await c.async_build_plan(
            call.data.get("trocken", True),
            pace,
            start_s,
            locker_s,
            call.data.get("basis_km"),
        )
        if result.get("ok") and not result.get("trocken"):
            hass.bus.async_fire(EVENT_PLAN_CHANGED, {
                "quelle": "plan_erstellen",
                "geschrieben": result.get("geschrieben"),
                "ersetzt": result.get("ersetzt"),
            })
        return result

    async def _detail(call: ServiceCall) -> ServiceResponse:
        c = _coordinator(hass, call)
        return await c.async_activity_detail(str(call.data["activity_id"]))

    for name, handler, schema in (
        (SERVICE_SYNC, _sync, SIMPLE_SCHEMA),
        (SERVICE_DETAIL, _detail, DETAIL_SCHEMA),
        (SERVICE_BUILD_PLAN, _build_plan, BUILD_PLAN_SCHEMA),
        (SERVICE_GET_DATA, _get_data, DATA_SCHEMA),
        (SERVICE_MOVE, _move, MOVE_SCHEMA),
        (SERVICE_REPLAN, _replan, REPLAN_SCHEMA),
        (SERVICE_ANALYSE, _analyse, ANALYSE_SCHEMA),
        (SERVICE_GET_PLAN, _get_plan, SIMPLE_SCHEMA),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
