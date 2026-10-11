"""Konstanten der Integration.

Die Event-Namen hier sind die öffentliche Schnittstelle nach außen: ein
Agent (Hermes, Node-RED, n8n) abonniert sie über die HA-WebSocket-API
(`subscribe_events`) oder eine HA-Automation hängt sich daran. Deshalb
werden sie behandelt wie ein API-Vertrag — umbenennen heißt brechen.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ha_intervals"
PANEL_URL_PATH: Final = "laufen"
PANEL_STATIC_PATH: Final = "/ha_intervals_panel"
PANEL_COMPONENT: Final = "ha-intervals-panel"

API_BASE: Final = "https://intervals.icu/api/v1"
API_USER: Final = "API_KEY"  # intervals.icu erwartet diesen String wörtlich als Benutzername

# ── Konfiguration ────────────────────────────────────────────────────────
CONF_API_KEY: Final = "api_key"
CONF_ATHLETE_ID: Final = "athlete_id"
CONF_RACE_DATE: Final = "race_date"
CONF_RACE_DISTANCE: Final = "race_distance_km"
CONF_RACE_GOAL: Final = "race_goal_seconds"
CONF_SCAN_INTERVAL: Final = "scan_interval_minutes"
CONF_ANTHROPIC_KEY: Final = "anthropic_api_key"
CONF_MODEL: Final = "analysis_model"

DEFAULT_SCAN_INTERVAL: Final = 20
DEFAULT_MODEL: Final = "claude-opus-5"
HISTORY_DAYS: Final = 180

# ── Services ─────────────────────────────────────────────────────────────
SERVICE_SYNC: Final = "sync"
SERVICE_MOVE: Final = "verschieben"
SERVICE_REPLAN: Final = "umplanen"
SERVICE_ANALYSE: Final = "analysieren"
SERVICE_GET_PLAN: Final = "plan_abfragen"
SERVICE_GET_DATA: Final = "daten_abfragen"
SERVICE_BUILD_PLAN: Final = "plan_erstellen"
SERVICE_DETAIL: Final = "training_details"

# ── Events auf dem HA-Bus ────────────────────────────────────────────────
EVENT_NEW_ACTIVITY: Final = f"{DOMAIN}_training_neu"
EVENT_PLAN_CHANGED: Final = f"{DOMAIN}_plan_geaendert"
EVENT_PLAN_CONFLICT: Final = f"{DOMAIN}_plan_konflikt"
EVENT_ANALYSIS_READY: Final = f"{DOMAIN}_analyse_fertig"

# Markierung in der Beschreibung jedes erzeugten Eintrags. Daran erkennt die
# Integration beim erneuten Erstellen ihre eigenen Einträge und räumt sie weg,
# statt den Kalender zu verdoppeln. Von Hand angelegte Einheiten bleiben
# unberührt — sie tragen die Markierung nicht.
#
# Die Markierung trägt die Metadaten mit, statt sie später aus dem Text zu
# erraten: Art, Kilometer, Woche, Phase. Das Raten war nicht nur ungenau,
# sondern falsch — die alte Markierung "[ha_intervals]" enthält die
# Zeichenfolge "interval", und der Klassifizierer hat daraufhin jede Einheit
# als Qualitätstraining eingestuft, auch "Locker 5 km".
PLAN_MARKER: Final = "[HA-LAUFPLAN]"
LEGACY_MARKERS: Final = ("[ha_intervals]",)

# ── Trainingsarten ───────────────────────────────────────────────────────
# "Qualität" heißt: zehrt so, dass am Folgetag nichts Hartes mehr geht.
KIND_REST: Final = "ruhe"
KIND_EASY: Final = "locker"
KIND_QUALITY: Final = "qualitaet"
KIND_LONG: Final = "longrun"

QUALITY_KINDS: Final = frozenset({KIND_QUALITY, KIND_LONG})

# ── Modi für das Verschieben ─────────────────────────────────────────────
MODE_SWAP: Final = "tauschen"
MODE_PUSH: Final = "schieben"
MODE_DROP: Final = "streichen"

MOVE_MODES: Final = (MODE_SWAP, MODE_PUSH, MODE_DROP)

# Grenzen des Regelwerks
MAX_WEEK_LOAD_DRIFT: Final = 0.10  # ±10 % Wochenlast
MIN_REST_DAYS_PER_WEEK: Final = 1
RACE_WEEK_DAYS: Final = 7  # in der Rennwoche wird nur gestrichen, nie verschoben
