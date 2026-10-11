"""VO2max-Schätzung nach dem Verfahren von Runalyze.

Der Gedanke: aus der Durchschnitts-Herzfrequenz eines Laufs lässt sich
ableiten, welchen Anteil der maximalen Sauerstoffaufnahme der Läufer dabei
abgerufen hat. Rechnet man die tatsächlich gelaufene Geschwindigkeit auf
100 % hoch und setzt sie in die ACSM-Gleichung für Laufökonomie ein, kommt
eine VO2max-Schätzung heraus.

    1. speedAchieved   = distance_m × 60 / duration_s            [m/min]
    2. %VO2max_fromHR  = e^((avgHR/HRmax − 1.00466) / 0.68725)
    3. speedAt100%     = speedAchieved / %VO2max_fromHR
    4. VO2max_raw      = −4.6 + 0.182253·s + 0.000104·s²
    5. VO2max          = VO2max_raw × Korrekturfaktor

Grenzen, die man kennen sollte:

* Die Schätzung steht und fällt mit der **HFmax**. Ein um 5 Schläge zu
  niedrig angesetzter Wert hebt das Ergebnis um gut 2 Punkte. Deshalb wird
  sie hier nicht geraten: fehlt sie, wird nichts gerechnet.
* Sie gilt für **gleichmäßige Läufe**. Intervalle, Bergläufe und sehr kurze
  Einheiten liefern Unsinn, weil die mittlere Herzfrequenz dort nicht zur
  mittleren Geschwindigkeit passt. Darum die Mindestfilter unten.
* Der Korrekturfaktor ist Runalyzes persönliche Kalibrierung gegen echte
  Labormessungen. Ohne eigene Messung bleibt er bei 1,0 — dann ist der Wert
  als *Verlauf* aussagekräftig, nicht als Absolutwert.
"""

from __future__ import annotations

import math

# Unterhalb dieser Werte ist die Schätzung nicht belastbar.
MIN_KM = 2.0
MIN_SECONDS = 600          # 10 Minuten
MIN_HR_FRACTION = 0.65     # unter 65 % der HFmax wird die Umkehrfunktion wild
MAX_HR_FRACTION = 1.02     # darüber liegt vermutlich ein Messfehler vor

# Plausibilitätsfenster für das Ergebnis. Wer außerhalb liegt, hat eher ein
# Datenproblem als eine Weltklasseausdauer.
MIN_VO2 = 15.0
MAX_VO2 = 90.0


def estimate(
    km: float | None,
    seconds: float | None,
    hr_avg: float | None,
    hr_max: float | None,
    correction: float = 1.0,
) -> float | None:
    """VO2max in ml/kg/min, oder `None` wenn der Lauf nicht taugt.

    Gibt bewusst `None` statt einer Zahl zurück, wenn die Voraussetzungen
    fehlen. Ein geschätzter Wert ohne Grundlage wäre schlimmer als keiner —
    er sähe genauso aus wie ein echter.
    """
    if not km or not seconds or not hr_avg or not hr_max:
        return None
    if km < MIN_KM or seconds < MIN_SECONDS:
        return None

    anteil = hr_avg / hr_max
    if not (MIN_HR_FRACTION <= anteil <= MAX_HR_FRACTION):
        return None

    speed = km * 1000 * 60 / seconds                      # m/min
    pct = math.exp((anteil - 1.00466) / 0.68725)
    if pct <= 0:
        return None

    speed_100 = speed / pct
    roh = -4.6 + 0.182253 * speed_100 + 0.000104 * speed_100**2
    wert = roh * (correction or 1.0)

    if not (MIN_VO2 <= wert <= MAX_VO2):
        return None
    return round(wert, 1)


def series(aktivitaeten: list[dict], hr_max: float | None, correction: float = 1.0) -> list[dict]:
    """Verlauf über eine Liste von Aktivitäten, älteste zuerst.

    Läufe ohne belastbare Schätzung fallen heraus statt als Lücke zu
    erscheinen — eine unterbrochene Kurve suggeriert einen Einbruch, den es
    nicht gab.
    """
    out: list[dict] = []
    for a in sorted(aktivitaeten, key=lambda x: x.get("day") or ""):
        v = estimate(
            a.get("km"), a.get("seconds"), a.get("hr_avg"), hr_max, correction
        )
        if v is not None:
            out.append({"day": a.get("day"), "vo2max": v, "activity_id": a.get("id")})
    return out


def rolling_best(verlauf: list[dict], fenster: int = 42) -> float | None:
    """Bester Wert der letzten `fenster` Einträge.

    Runalyze zeigt einen geglätteten Wert; der beste aus einem Fenster ist
    robuster gegen einzelne schlechte Tage als der Mittelwert und schwankt
    weniger als der letzte Einzelwert.
    """
    if not verlauf:
        return None
    return max(x["vo2max"] for x in verlauf[-fenster:])
