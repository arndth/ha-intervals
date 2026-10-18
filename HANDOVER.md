# Übergabe

Alles, was ein Agent oder ein Mensch braucht, um dieses Projekt zu
übernehmen. Stand: **18.10.2026, v0.4.3**.

---

## 1. Worum es geht

Eine Home-Assistant-Integration, die Laufdaten aus intervals.icu holt, einen
periodisierten Trainingsplan rechnet und zurückschreibt, Läufe auswertet und
ein eigenes Dashboard in die Seitenleiste stellt.

**Der tragende Grundsatz: intervals.icu ist die Wahrheit.** Der Plan wird
dorthin geschrieben, nicht nur hier angezeigt — von dort synchronisiert er
auf die Uhr. Lokal liegt nur, was intervals.icu nicht kennt: KI-Analysen,
Planbegründungen und ein Cache, damit das Panel sofort rendert und auch dann
funktioniert, wenn intervals.icu gerade weg ist.

**Zweiter Grundsatz: die Integration ist agentneutral.** Sie kennt weder
Hermes noch n8n noch TrainingPeaks. Sie bietet Services und Events über die
normale HA-API; wer sie benutzt, ist ihr gleichgültig. Agent austauschen
heißt: Automation ändern, Integration unberührt lassen.

---

## 2. Wo was läuft

| Teil | Ort |
|---|---|
| Integration | HA unter `192.168.1.69:8123`, Domain `ha_intervals` |
| Quellcode | `github.com/arndth/ha-intervals`, lokal `~/Documents/Claude/HomeAssistant/ha-intervals` |
| Installation | HACS als benutzerdefiniertes Repository |
| Lokale Ablage | `/config/ha_intervals/<entry_id>.db` (SQLite) |
| Panel | Seitenleiste „Laufen", Pfad `/laufen` |
| Datenquelle | intervals.icu, Athlet `i243228` |
| Uploadweg | HealthFit (iOS) → intervals.icu, **nicht** über Strava |
| n8n | Proxmox-LXC, `http://192.168.1.140:5678` |

---

## 3. Die Schnittstelle für Hermes

Das ist der Teil, der zählt. Alle Services liefern strukturierte Antworten,
wenn `?return_response` gesetzt ist.

```bash
curl -X POST "http://192.168.1.69:8123/api/services/ha_intervals/<name>?return_response" \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d '{...}'
```

### Lesen

| Service | Zweck |
|---|---|
| `daten_abfragen` | **Alles in einem Aufruf**: Verlauf, Wochen, Trainings, Plan, Bestzeiten, VO2max, Analysen. Parameter `tage` (7–365, Vorgabe 91). |
| `plan_abfragen` | nur die geplanten Einheiten |
| `training_details` | ein Lauf: Eckdaten, Kilometer-Splits, Zonen, geplante Einheit, Analyse. Parameter `activity_id`. |

### Schreiben

| Service | Zweck |
|---|---|
| `sync` | sofort von intervals.icu holen |
| `plan_erstellen` | 13-Wochen-Plan rechnen und schreiben. `trocken` (Vorgabe **true**), `ziel_pace`, `start_pace`, `locker_pace`, `basis_km` |
| `verschieben` | `event_id`, `ziel` (heute/morgen/JJJJ-MM-TT), `modus` (tauschen/schieben/streichen) |
| `plan_exportieren` | Einheiten an einen Webhook schicken. `von`, `bis`, `trocken` |
| `analysieren` | einen Lauf von Claude bewerten lassen. `activity_id` optional |
| `umplanen` | **noch nicht implementiert**, gibt `ok: false` zurück |

### Die wichtigste Antwortform

`verschieben` liefert bei Ablehnung den Konflikt **und die zulässigen
Alternativen**. Ein Agent kann daraus unmittelbar den nächsten Zug wählen,
ohne zu raten:

```json
{
  "ok": false,
  "konflikte": [{"regel": "qualitaet_vor_longrun",
                 "text": "Harte Einheit am Sa direkt vor dem Longrun."}],
  "alternativen": [{"modus": "tauschen", "ziel": "2026-10-14", "text": "Mit Mi tauschen"},
                   {"modus": "streichen", "ziel": "2026-10-13", "text": "Einheit streichen"}],
  "umplanung_noetig": false
}
```

### Events auf dem HA-Bus

Abonnierbar per WebSocket (`subscribe_events`) oder über eine Automation.

| Event | Wann | Nutzlast |
|---|---|---|
| `ha_intervals_training_neu` | neue Aktivität aufgetaucht | `activity_id`, `name`, `km`, `last`, `tag` |
| `ha_intervals_plan_geaendert` | Zug nach intervals.icu geschrieben | `aenderungen`, bei `plan_erstellen` auch `geschrieben`/`ersetzt` |
| `ha_intervals_plan_konflikt` | Zug abgelehnt | `konflikte`, `alternativen` |
| `ha_intervals_analyse_fertig` | Analyse liegt vor | `activity_id` plus Urteil |

### Entitäten

```
sensor.fitness              CTL, 42-Tage-Mittel
sensor.ermudung             ATL, 7-Tage-Mittel
sensor.form                 CTL − ATL
sensor.wochenkilometer      nur Läufe, Woche ab Montag
sensor.tage_bis_zum_rennen
sensor.naechste_einheit     Name; Attribute: event_id, tag, art, last, km, beschreibung
sensor.vo2max               bester Wert aus 90 Tagen
calendar.trainingsplan      geplante Einheiten als Ganztagestermine
```

Alle Sensoren mit `state_class` haben HAs Langzeitstatistik — unbegrenzter
Verlauf ohne InfluxDB.

---

## 4. Aufbau

```
custom_components/ha_intervals/
  planner.py       Regelwerk fürs Verschieben — rein, ohne HA-Importe
  planbuilder.py   Plangenerator — rein, ohne HA-Importe
  vo2max.py        VO2max-Schätzung — rein, ohne HA-Importe
  util.py          Datumsparser, Syntax-Extraktion — rein
  api.py           intervals.icu-Client
  coordinator.py   Abruf, Rückschreiben, Aggregate — die einzige dicke Stelle
  store.py         SQLite
  analysis.py      Claude-Aufrufe, Splits
  config_flow.py · sensor.py · calendar.py · services.yaml
  panel/           gebautes Frontend-Bundle (erzeugt die GitHub-Action)
frontend/
  src/theme.js     Tokens, Hell/Dunkel-Erkennung, geprüfte Palette
  src/charts.js    Diagramme als reines SVG, ohne Bibliothek
  src/panel.js     Custom Element, vier Ansichten
  dev.html         Prüfstand mit nachgebildeten Dienstantworten
tests/             60 Tests, laufen ohne Home Assistant
```

**Die reinen Module sind die Sollbruchstelle.** `planner`, `planbuilder`,
`vo2max` und `util` importieren nichts aus `homeassistant` und sind
vollständig getestet. Wer Logik ergänzt, gehört dorthin, nicht in den
Koordinator.

---

## 5. Entscheidungen und ihre Gründe

Wer etwas davon umdrehen will, sollte den Grund kennen.

**Verschieben ist ein Regelwerk, keine KI.** Ein Training auf morgen zu
schieben ist eine Datumsänderung mit fünf Randbedingungen. Ein Regelwerk
antwortet sofort, kostet nichts, liefert bei gleicher Eingabe dieselbe
Antwort und lässt sich testen. Ein Modell wird erst befragt, wenn **kein**
zulässiger Einzelzug mehr existiert — dann ist es eine Trainingsfrage.

Die fünf Regeln: keine zwei Qualitätseinheiten hintereinander · keine
Qualität direkt vor dem Longrun · mindestens ein Ruhetag pro Woche ·
Wochenlast innerhalb ±10 % · in der Rennwoche wird nur gestrichen.

**Streichen wird nie abgelehnt.** Wer sagt „ich schaffe das heute nicht",
trainiert auch bei einem Nein nicht; eine Ablehnung entkoppelte den Plan nur
von der Wirklichkeit. Stattdessen wird der Lastverlust gemeldet.

**Plan neu schreiben fasst nur die Zukunft an.** Sonst wäre nicht mehr
unterscheidbar, was geplant war und was gelaufen ist — der Unterschied
zwischen „Plan anpassen" und „Geschichte umschreiben".

**SQLite, nicht InfluxDB.** Läufe sind Ereignisse mit Attributen, keine
gleichmäßig gesampelten Messreihen. Eine Datei, keine Dependency, vom
HA-Backup mitgenommen.

**Das Panel ist ein Custom Element, kein iframe.** Nur so bekommt es das
`hass`-Objekt und erbt die Anmeldung. Ein iframe bräuchte einen eigenen
langlebigen Token.

**Chrome aus HA-Variablen, Serienfarben fest.** Das Panel soll aussehen wie
der Rest der Installation; die Kurvenfarben sind dagegen gegen Kontrast,
Lightness-Band und Farbsinnstörungen geprüft und dürfen nicht nach Theme
wandern. Welche Variante gilt, wird an der Helligkeit der Kartenfläche
**gemessen**, nicht geraten. Es wird keine Schrift nachgeladen.

**Tempovorgaben kommen aus zwei Quellen.** Harte Einheiten vom Ziel, lockere
vom gewohnten Dauerlauftempo. Beides aus dem Ziel abzuleiten erzeugte
6:21/km als „locker" bei einem Läufer, der seine Dauerläufe um 5:24/km läuft
— eine Vorgabe, die man ignoriert.

---

## 6. Fallen, die dieses Projekt schon getreten hat

Jede davon hat Zeit gekostet. Sie stehen hier, damit es nicht noch einmal
passiert.

**Der eigene Marker vergiftete den Klassifizierer.** Die Planmarkierung hieß
`[ha_intervals]` — und enthält die Zeichenfolge `interval`. Der
Klassifizierer suchte genau danach und stufte *jede* Einheit als
Qualitätstraining ein, auch „Locker 5 km". Damit hätte das Regelwerk fast
jede Verschiebung abgelehnt. Seitdem: Marker heißt `[HA-LAUFPLAN]`, trägt
die Metadaten selbst, und `classify()` entfernt Klammertext vor dem
Abgleich.

**`vol.Any` wird zur Konstanten.** `vol.Any("", vol.All(Coerce(int), Range))`
sollte „leer oder eine Zahl" heißen. HA kann das nicht auf ein Bedienelement
abbilden und rendert das Feld als `type: constant` — sichtbar, aber nicht
ausfüllbar, ohne jede Fehlermeldung. Für optionale Zahlen einen
`NumberSelector` nehmen.
→ **Die Form eines Formulars entsteht in HA, nicht im Quelltext.** Prüfen
lässt sie sich, indem man den Options-Flow über die REST-API startet und
`data_schema` liest.

**Zwei Datenklassen, ein Datenfluss.** `PlannedSession` bekam ein Feld
`syntax`, `Session` nicht — der Koordinator baut beide aus denselben Spalten.
Die Integration kam gar nicht mehr hoch. Die Tests erreichten den
Koordinator nicht, weil er `homeassistant` importiert; genau in dieser Naht
saß der Fehler. `tests/test_signaturen.py` prüft das jetzt statisch.

**Gleicher Klassenname, zwei Begriffe.** `.note` gab es als Hinweisblock im
Dialog (mit `border-top`) und als Zusatzzeile in den Kacheln. Der Rahmen
schlug überall durch.

**`m` heißt Minuten.** In der intervals.icu-Workout-Schreibweise ist `400m`
= 400 Minuten. Eine 400-m-Trabpause schreibt man `0.4km`. Dazu: eine
Leerzeile beendet den Wiederholungsblock, und der erste Schritt legt den
Zieltyp für den ganzen Workout fest.

**Die API gibt bei geplanten Terminen kein `distance` zurück.** Deshalb
tragen die Marker die Kilometer selbst.

**intervals.icu liefert keine Strava-Daten über die API.** Hier irrelevant,
weil HealthFit direkt hochlädt — bei einer anderen Quelle wäre es die erste
Verdächtige, wenn nichts ankommt.

**Submaximale Läufe sind keine Wettkämpfe.** Eine Riegel-Hochrechnung aus
Läufen bei HF 155–160 hat die Leistungsfähigkeit deutlich unterschätzt und
zu einer falschen Einschätzung geführt. Vor jeder Prognose prüfen, ob der
Bezugslauf überhaupt eine Maximalleistung war.

---

## 7. Aktueller Zustand

**Athlet:** `i243228` · HFmax **190** · VO2max-Korrektur **1,05**
(Runalyze-kalibriert; mit 183 und 1,0 lägen die Werte rund 5,5 Punkte
niedriger — bei Vergleichen mit Garmin dieselbe HFmax verwenden).

**Wettkampf:** 13,0 km am **So 10.01.2027**, Zieltempo **4:30/km** (58:30).

**Plan:** 39 Einheiten, geschrieben am 14.10. mit `ziel_pace 4:30` und
`basis_km 10`. Drei Einheiten pro Woche (Di Qualität, Do locker, So lang),
Wochenumfang 17 · 28 · 33 · 26 · 36 · 38 · 42 · 32 · 44 · 44 · 44 · 38 · 28 km.
Lockeres Tempo 5:29–5:54/km.

**Gelaufen (Woche 1 vollständig):**

| Tag | Einheit | km | Pace | HF | VO2max |
|---|---|---:|---|---:|---:|
| 13.10. | Locker 5 km | 5,0 | 4:53 | 163 | 50,6 |
| 15.10. | Locker 7 km | 6,6 | 5:10 | 159 | 49,0 |
| 18.10. | Dauerlauf 10 km | 10,0 | 5:01 | 159 | 50,9 |

Fitness 9,5 · Ermüdung 16,2 · Form −6,7 · Woche 21,6 km.

**Beobachtung für den Nachfolger:** alle drei Einheiten wurden deutlich
schneller gelaufen als vorgegeben (5:01 statt 5:29–5:49 beim Longrun). Wenn
sich das hält, ist entweder der Startwert zu niedrig angesetzt oder die
Vorgaben werden ohnehin ignoriert — beides einen Blick wert, bevor die
Qualitätsphase ab Woche 5 beginnt.

---

## 8. Betrieb

**Installieren:** HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories
→ `https://github.com/arndth/ha-intervals`, Kategorie *Integration* →
herunterladen → HA neu starten → Integration hinzufügen.

**Aktualisieren:** `git tag vX.Y.Z && git push --tags`. Die GitHub-Action
baut das Frontend-Bundle, schreibt die Version aus dem Tag ins Manifest,
lässt die Tests laufen und hängt `ha_intervals.zip` ans Release. HACS meldet
sich, ein Klick, Neustart.

**Neustart ist bei Codeänderungen Pflicht** — Python hält importierte Module
im Speicher, „Integration neu laden" lädt nur den Config-Entry. Nur
Optionsänderungen wirken ohne Neustart. Also lieber größere Releases.

**Frontend entwickeln ohne HA:**

```bash
cd frontend && npm install && npm run build
cd .. && python3 -m http.server 8777
# http://127.0.0.1:8777/frontend/dev.html
#   ?theme=dark · ?view=plan · ?view=best · ?detail=9000
```

ES-Module brauchen HTTP; über `file://` scheitern sie an CORS.

**Tests:** `for t in tests/test_*.py; do python3 $t; done` — 60 Tests in sechs Dateien, ohne
Home Assistant, ohne Netz.

---

## 9. Offen

| Punkt | Lage |
|---|---|
| **`umplanen`** | Nicht implementiert. Die Ebene, die auf *tatsächliches* Training reagiert statt auf eine Anweisung zu warten. Der Entwurf sah vor, dass Claude Vorschläge macht, die erst durchs Regelwerk und an einem Menschen vorbei müssen. |
| **Pace-Dauer-Kurve** | Nicht implementiert. „Bestzeiten" zeigt heute Gesamtschnitte je Distanzklasse und sagt das auch; echte Bestzeiten brauchen die Auswertung der Streams. |
| **KI-Analyse** | Geschrieben, nie gegen die echte API gelaufen — es ist kein Anthropic-Schlüssel hinterlegt. |
| **TrainingPeaks-Export** | Dienst und Workout-Syntax stehen und sind gegen den n8n-Konverter geprüft. Es fehlen: Webhook-Knoten in n8n, Webhook-Adresse und Athleten-ID in den Optionen. |
| **TrainingPeaks-Cookie** | Steht im n8n-Workflow im Klartext und gehört in die Credential-Verwaltung. Es läuft regelmäßig ab. |
| **Zonentabelle im Konverter** | Setzt die Einheit auf `Pace`, zieht die Prozentwerte aber aus der Power-Tabelle. Für intervals.icu folgenlos, für TrainingPeaks beim ersten Workout zu prüfen. |
| **VO2max-Fenster** | `sensor.vo2max` nimmt den besten Wert aus 90 Tagen, `daten_abfragen` aus dem angefragten Zeitraum. Gleicher Name, zwei Fenster — vereinheitlichen. |
| **Bens Innentemperatur** | `cca_sync.py` im Nachbarprojekt nutzt für Bens West-Fenster Idas Sensor. Nicht Teil dieses Projekts, aber im selben Arbeitsordner notiert. |
