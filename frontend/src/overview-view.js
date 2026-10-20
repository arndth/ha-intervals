import { overviewModel } from "./overview.js";
import { esc, fmt, table } from "./charts.js";

/** Read-only dashboard HTML. Caller wires data-detail and data-tab buttons. */
export function renderOverview(data, tile) {
  const o = overviewModel(data);
  const km = (v) => `${fmt.n(v)} km`;
  const day = (s) => esc(fmt.day(s));
  const last = o.last
    ? `<div class="eyebrow">${day(o.last.day)} · Aufgezeichnet</div>
       <h3>${esc(o.last.name || "Lauf")}</h3>
       <div class="overview-stats"><b>${esc(km(o.last.km))}</b><span>${esc(fmt.hms(o.last.seconds))} Bewegungszeit</span>
         <span>${esc(fmt.pace(o.last.pace_s_km))} /km</span></div>
       <p class="hint">Ø HF ${esc(o.last.hr_avg ?? "—")} · Last ${esc(o.last.load ?? "—")}</p>
       <button class="ghost sm" data-detail="${esc(o.last.id)}">Splits & Details</button>`
    : `<p class="hint">Im geladenen Zeitraum ist kein Lauf erfasst.</p>`;
  const next = o.next
    ? `<div class="eyebrow">${day(o.next.tag)} · ${o.next.tag === o.today ? "Heute geplant (Status prüfen)" : "Geplant"}</div>
       <h3>${esc(o.next.name || "Training")}</h3>
       <div class="overview-stats"><b>${o.next.km ? esc(km(o.next.km)) : "Distanz offen"}</b>
         <span>${esc(o.next.art || "Lauf")}</span></div>
       ${o.next.beschreibung ? `<p class="hint overview-desc">${esc(o.next.beschreibung.replace(/\[HA-LAUFPLAN\].*$/ms, "").trim())}</p>` : ""}
       <button class="ghost sm" data-tab="plan">Zum Trainingsplan</button>`
    : `<p class="hint">Kein kommendes Lauftraining im geladenen Plan.</p>`;
  const days = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const week = days.map((label, i) => {
    const at = new Date(`${o.weekStart}T00:00:00Z`);
    at.setUTCDate(at.getUTCDate() + i);
    const date = at.toISOString().slice(0, 10);
    const plan = o.currentPlan.filter((x) => x.tag === date);
    const done = (data.trainings || []).filter((x) => x.day === date);
    return `<div class="overview-day ${date === o.today ? "today" : ""}">
      <span class="daylabel">${label}<small>${day(date)}</small></span>
      <span class="daycontent">${plan.length ? plan.map((x) => `<span>${esc(x.name || "Lauf")}${x.km ? ` · ${esc(km(x.km))}` : ""}</span>`).join("") : `<span class="muted">Kein Lauf geplant</span>`}
        ${done.map((x) => `<button data-detail="${esc(x.id)}" class="done">Erfasst: ${esc(km(x.km))} · ${esc(fmt.pace(x.pace_s_km))} /km</button>`).join("")}</span>
    </div>`;
  }).join("");
  const weeks = o.previous.map((w) => [
    `${fmt.day(w.start)}–${fmt.day(w.end)}`, String(w.count), fmt.n(w.km),
    fmt.hms(w.seconds), String(w.load), fmt.n(w.longest),
  ]);
  const months = o.months.map((m) => [
    `${m.month}${m.partial ? " *" : ""}`, String(m.count), fmt.n(m.km),
    fmt.hms(m.seconds), String(m.load),
  ]);
  return `<p class="hint lead">Stand ${day(o.today)} · Daten aus der lokalen intervals.icu-Ablage. „Erfasst“ ist nicht automatisch „Plan erfüllt“.</p>
    <section class="card overview-week">
      <div class="head"><h2>Aktuelle Woche · ${day(o.weekStart)}–${day(o.weekEnd)}</h2><span class="eyebrow">Montag–Sonntag</span></div>
      <div class="tiles overview-tiles">
        ${tile("Erfasst bis heute", fmt.n(o.current.km), "km", `${o.current.count} Läufe · ${fmt.hms(o.current.seconds)} Bewegungszeit`)}
        ${tile("Wochenplan", o.planCount ? fmt.n(o.planKm) : "—", o.planCount ? "km" : "", `${o.planCount} geplante Läufe`)}
        ${tile("Erfasste Last", String(o.current.load), "", "Keine Trainingsbereitschaft")}
      </div>
      <div class="overview-days">${week}</div>
    </section>
    <div class="grid2">
      <section class="card"><div class="head"><h2>Letztes Training</h2></div>${last}</section>
      <section class="card"><div class="head"><h2>Nächstes Training</h2></div>${next}</section>
    </div>
    <section class="card"><div class="head"><h2>Zusammenfassung dieser Woche</h2></div>
      <p class="prose">${o.current.count ? `${o.current.count} erfasste Läufe, ${esc(km(o.current.km))}, ${esc(fmt.hms(o.current.seconds))} Bewegungszeit, längster Lauf ${esc(km(o.current.longest))} und Last ${o.current.load}.` : "Noch kein Lauf in dieser Woche erfasst."}
        ${o.planCount ? ` Im Plan: ${o.planCount} Läufe mit zusammen ${esc(km(o.planKm))}.` : " Kein Laufplan für diese Woche geladen."}
        Die laufende Woche ist noch nicht abgeschlossen; Umfang allein bewertet weder Intensität noch Erholung.</p>
    </section>
    <section class="card"><div class="head"><h2>Letzte 4 abgeschlossene Wochen</h2></div>
      <p class="hint">${o.fourWeeks.count} erfasste Läufe · ${esc(km(o.fourWeeks.km))} · ${esc(fmt.hms(o.fourWeeks.seconds))} Bewegungszeit · Last ${o.fourWeeks.load}. Wochen ohne Eintrag bedeuten nicht zwingend Trainingspause.</p>
      <div class="tablewrap">${table(["Woche", "Läufe", "km", "Zeit", "Last", "Längster km"], weeks)}</div>
    </section>
    <section class="card"><div class="head"><h2>Letzte 6 Monate · ${day(o.since)} bis ${day(o.today)}</h2></div>
      <p class="hint">${o.sixMonths.count} erfasste Läufe · ${esc(km(o.sixMonths.km))} · ${esc(fmt.hms(o.sixMonths.seconds))} Bewegungszeit · Last ${o.sixMonths.load}. Rollierender Zeitraum; Randmonate sind Teilmonate (*). ${o.limitedHistory ? "Der Datenabruf deckt den Zeitraum nicht vollständig ab." : "Nur lokal erfasste Laufaktivitäten; nicht importierte Quellen können fehlen."}</p>
      <div class="tablewrap">${table(["Monat", "Läufe", "km", "Zeit", "Last"], months)}</div>
    </section>`;
}
