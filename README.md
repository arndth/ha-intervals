# Intervals.icu Laufplan

Home-Assistant-Integration, die Laufdaten aus [intervals.icu](https://intervals.icu)
holt, einen Trainingsplan verwaltet und ein eigenes Dashboard in die
Seitenleiste stellt.

**intervals.icu bleibt die Wahrheit.** Der Plan wird dorthin geschrieben, nicht
nur hier angezeigt — von dort synchronisiert er auf die Uhr. Lokal liegt nur,
was intervals.icu nicht kennt: KI-Analysen, Planbegründungen, Pace-Dauer-Kurven
und ein Cache, damit das Panel sofort rendert.

---

## Installation

1. **HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories**
   URL dieses Repos eintragen, Kategorie **Integration**.
2. **Herunterladen**, danach Home Assistant **neu starten**.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Intervals.icu"**
   API-Schlüssel (intervals.icu → Einstellungen → Developer) und Athlete-ID
   eintragen, dann Renndatum und Distanz.
4. **„Laufen"** erscheint in der Seitenleiste.

Renndatum, Distanz, Zielzeit, Abrufintervall und der optionale
Anthropic-Schlüssel lassen sich jederzeit unter **Konfigurieren** ändern.
Ohne Anthropic-Schlüssel läuft alles außer der KI-Analyse; ohne Renndatum
alles außer Plan und Countdown.

### Aktualisieren

`git tag v0.2.0 && git push --tags` → die GitHub-Action baut das Paket,
HACS meldet das Update, ein Klick, Neustart.

---

## Schnittstelle für eigene Agenten

Die Integration ruft **keinen** Agenten auf und kennt keinen. Sie bietet
stattdessen zwei Wege, die jedes Werkzeug über die normale HA-API erreicht.

### Services

Alle liefern strukturierte Antworten, wenn `?return_response` gesetzt ist.

```bash
curl -X POST "http://192.168.1.69:8123/api/services/ha_intervals/verschieben?return_response" \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{"event_id":"12345","ziel":"morgen","modus":"tauschen"}'
```

| Service | Zweck |
|---|---|
| `ha_intervals.daten_abfragen` | alles, was das Dashboard zeigt, in einem Aufruf |
| `ha_intervals.plan_abfragen` | nur die geplanten Einheiten |
| `ha_intervals.verschieben` | verschieben / tauschen / streichen |
| `ha_intervals.sync` | sofort von intervals.icu holen |
| `ha_intervals.analysieren` | einen Lauf bewerten lassen |
| `ha_intervals.plan_erstellen` | 13-Wochen-Plan rechnen und schreiben (Trockenlauf ist Vorgabe) |
| `ha_intervals.training_details` | Eckdaten, Splits, Zonen und Analyse eines Laufs |
| `ha_intervals.plan_exportieren` | geplante Einheiten an einen Webhook schicken |
| `ha_intervals.umplanen` | Restwoche neu planen *(noch nicht fertig)* |

Antwort von `verschieben` bei einer Ablehnung — die `alternativen` sind
zulässige Einzelzüge, ein Agent kann daraus direkt den nächsten wählen:

```json
{
  "ok": false,
  "konflikte": [
    {"regel": "qualitaet_vor_longrun",
     "text": "Harte Einheit am Sa direkt vor dem Longrun."}
  ],
  "alternativen": [
    {"modus": "tauschen", "ziel": "2026-10-14", "text": "Mit Mi tauschen"},
    {"modus": "streichen", "ziel": "2026-10-13", "text": "Einheit streichen"}
  ],
  "umplanung_noetig": false
}
```

### Events auf dem HA-Bus

| Event | Wann |
|---|---|
| `ha_intervals_training_neu` | eine neue Aktivität ist aufgetaucht |
| `ha_intervals_plan_geaendert` | ein Zug wurde nach intervals.icu geschrieben |
| `ha_intervals_plan_konflikt` | ein Zug wurde abgelehnt |
| `ha_intervals_analyse_fertig` | eine Analyse liegt vor |

Ein Agent abonniert sie per WebSocket (`subscribe_events`) — oder eine
Automation hängt sich daran und ruft ihn auf:

```yaml
automation:
  - alias: Neues Training an den Agenten melden
    triggers:
      - trigger: event
        event_type: ha_intervals_training_neu
    actions:
      - action: rest_command.agent_benachrichtigen
        data:
          payload: "{{ trigger.event.data | to_json }}"
```

Agent austauschen heißt damit: Automation ändern. Die Integration bleibt
unberührt.

---

## Strukturierte Workouts und Export

Jede geplante Einheit trägt neben der Prosa auch die **intervals.icu-Workout-
Schreibweise**:

```
- 2km Z2 Pace

5x
- 1km Z5 Pace
- 0.4km Z1 Pace

- 1.5km Z2 Pace
```

intervals.icu baut daraus einen strukturierten Workout — die Uhr zählt die
Intervalle dann selbst herunter, statt nur einen Text anzuzeigen. Beide
Parser (intervals.icu wie der n8n-Konverter) lesen ausschließlich Zeilen mit
`-` oder `5x` und übergehen Prosa und Markierung.

Drei Eigenheiten der Schreibweise, aus dem Parser gelesen und nicht geraten:

- **`m` heißt Minuten, nicht Meter.** 400 m Trabpause ist `0.4km`.
- Eine **Leerzeile beendet** einen Wiederholungsblock. Ohne sie wird das
  Auslaufen mit hineingezogen.
- Der **erste Schritt legt den Zieltyp fest** — deshalb trägt jede erste
  Zeile `Pace`.

`plan_exportieren` schickt die Einheiten an eine in den Optionen hinterlegte
Webhook-Adresse, je Einheit ein Aufruf mit `athleteid`, `title`,
`description` (die Schreibweise) und `workoutday`. Das passt auf den
n8n-Sub-Workflow „Send to TrainingPeaks"; die Integration selbst kennt weder
n8n noch TrainingPeaks.

## Das Regelwerk

Verschieben ist **kein** KI-Aufruf. Es ist eine Datumsänderung mit fünf
Randbedingungen, und die prüft `planner.py` — sofort, kostenlos,
deterministisch und testbar:

1. Keine zwei Qualitätseinheiten an aufeinanderfolgenden Tagen
2. Keine Qualitätseinheit direkt vor dem Longrun
3. Mindestens ein Ruhetag pro Woche
4. Wochenlast innerhalb ±10 % des Plans
5. In der Rennwoche wird nur gestrichen, nie verschoben

**Streichen wird nie abgelehnt.** Wer sagt „ich schaffe das heute nicht",
trainiert auch dann nicht, wenn das Regelwerk Nein sagt — eine Ablehnung würde
den Plan nur von der Wirklichkeit entkoppeln. Stattdessen meldet der Service
den Verlust und setzt bei Bedarf `umplanung_noetig`.

Ein Modell wird erst befragt, wenn **kein** zulässiger Zug mehr existiert.
Dann ist es eine Trainingsfrage, und die gehört dorthin.

```bash
python3 tests/test_planner.py      # läuft ohne Home Assistant
```

---

## Entwicklung

```
custom_components/ha_intervals/
  planner.py      Regelwerk — rein, ohne HA-Importe, vollständig getestet
  api.py          intervals.icu-Client
  coordinator.py  Abruf, Rückschreiben, Aggregate fürs Panel
  store.py        SQLite unter /config/ha_intervals/
  analysis.py     Claude-Aufrufe
  panel/          gebautes Frontend-Bundle (von der Action erzeugt)
frontend/
  src/theme.js    Tokens; Hell/Dunkel wird an der Kartenfläche gemessen
  src/charts.js   Diagramme als reines SVG, ohne Bibliothek
  src/panel.js    das Custom Element mit den vier Ansichten
  dev.html        Prüfstand mit nachgebildeten Dienstantworten
```

### Panel entwickeln ohne Home Assistant

`dev.html` bildet `hass.callService` nach und liefert dieselbe Nutzlast wie
`daten_abfragen`. Damit lässt sich jede Ansicht ansehen, ohne ein Paket zu
schnüren und HA neu zu starten. ES-Module brauchen HTTP — `file://` scheitert
an CORS:

```bash
cd frontend && npm install && npm run build
cd .. && python3 -m http.server 8777
# http://127.0.0.1:8777/frontend/dev.html
#   ?theme=dark                              dunkles Theme
#   ?view=plan&move=1001&try=tauschen        Konfliktdialog
```

Das Panel ist ein Custom Element, kein iframe: nur so bekommt es das
`hass`-Objekt und erbt die Anmeldung des Nutzers. Ein iframe bräuchte einen
eigenen langlebigen Token.

## Stand

| | |
|---|---|
| Abruf, Speicherung, Sensoren, Kalender | fertig |
| Regelwerk fürs Verschieben | fertig, 12 Tests |
| Services und Events | fertig |
| Panel: Form, Trainingsplan, Bestzeiten, Trainings | fertig, hell und dunkel geprüft |
| Detailseite je Training mit Kilometer-Splits | fertig |
| Strukturierte Workouts (intervals.icu-Schreibweise) | fertig, gegen den n8n-Konverter geprüft |
| Export an einen Webhook | fertig |
| Plangenerator mit Tempoprogression | fertig, 16 Tests |
| Verschieben aus dem Panel samt Konfliktanzeige | fertig |
| KI-Einzelanalyse | fertig, ungetestet gegen die echte API |
| Wochen-Umplanung (reagiert auf tatsächliches Training) | noch nicht implementiert |
| Pace-Dauer-Kurve (echte Bestzeiten aus Streams) | noch nicht implementiert |
