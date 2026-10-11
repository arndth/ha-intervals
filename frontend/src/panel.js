/**
 * Seitenleisten-Panel „Laufen".
 *
 * Home Assistant übergibt dem Element `hass`, `narrow` und `panel`. Weil es
 * ein Custom Element ist und kein iframe, erbt es damit die Anmeldung des
 * Nutzers — es braucht keinen eigenen Token.
 *
 * Alle Daten kommen über Services der Integration. Dieselben Services, die
 * auch ein externer Agent über die REST-API aufruft; eine zweite,
 * bevorzugte Schnittstelle fürs Frontend gibt es bewusst nicht.
 */

import { CSS_TOKENS, detectMode, palette, phaseColor } from "./theme.js";
import {
  esc,
  fmt,
  formMeter,
  formStatus,
  loadChart,
  table,
  vo2Chart,
  volumeChart,
  zonesChart,
} from "./charts.js";

const VIEWS = [
  { id: "form", label: "Form" },
  { id: "plan", label: "Trainingsplan" },
  { id: "best", label: "Bestzeiten" },
  { id: "runs", label: "Trainings" },
];

const RANGES = [30, 60, 91];

function an_text(a) {
  return a.prose || a.verdict?.prosa || "Analyse ohne Text.";
}

const ART = {
  ruhe: "Ruhe",
  locker: "Locker",
  qualitaet: "Qualität",
  longrun: "Longrun",
};

class HaIntervalsPanel extends HTMLElement {
  constructor() {
    super();
    this._view = "form";
    this._days = 91;
    this._data = null;
    this._error = null;
    this._busy = false;
    this._open = new Set(); // aufgeklappte Tabellen
    this._moving = null; // Einheit im Verschieben-Dialog
    this._detail = null; // geöffnetes Training
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }
  get hass() {
    return this._hass;
  }

  set narrow(v) {
    this._narrow = v;
  }

  /* ── Dienste ─────────────────────────────────────────────────────────── */

  /** Letztes Argument ist returnResponse — dieselbe strukturierte Antwort,
   *  die ein Agent über `?return_response` bekommt. */
  _call(service, data = {}) {
    return this._hass.callService(
      "ha_intervals",
      service,
      data,
      undefined,
      false,
      true
    );
  }

  async _load() {
    this._busy = true;
    this._render();
    try {
      const res = await this._call("daten_abfragen", { tage: this._days });
      this._data = res?.response ?? null;
      this._error = null;
    } catch (err) {
      this._error = String(err?.message || err);
    }
    this._busy = false;
    this._render();
  }

  async _sync() {
    this._busy = true;
    this._render();
    try {
      await this._call("sync");
      await this._load();
    } catch (err) {
      this._error = String(err?.message || err);
      this._busy = false;
      this._render();
    }
  }

  async _openDetail(id) {
    this._detail = { id, loading: true, data: null };
    this._render();
    try {
      const res = await this._call("training_details", { activity_id: id });
      this._detail = { id, loading: false, data: res?.response ?? null };
    } catch (err) {
      this._detail = { id, loading: false, error: String(err?.message || err) };
    }
    this._render();
  }

  async _move(eventId, ziel, modus) {
    try {
      const res = await this._call("verschieben", {
        event_id: eventId,
        ziel,
        modus,
      });
      const r = res?.response;
      if (r && !r.ok) {
        // Abgelehnt: Konflikt und Alternativen anzeigen, statt still zu scheitern
        this._moving = { ...this._moving, result: r };
        this._render();
        return r;
      }
      this._moving = null;
      await this._load();
      return r;
    } catch (err) {
      this._moving = { ...this._moving, result: { ok: false, fehler: String(err?.message || err) } };
      this._render();
    }
  }

  /* ── Darstellung ─────────────────────────────────────────────────────── */

  _render() {
    if (!this.shadowRoot) return;
    const p = palette(detectMode(this));
    const d = this._data;

    const tabs = VIEWS.map(
      (v) =>
        `<button class="tab ${v.id === this._view ? "on" : ""}" data-tab="${v.id}">${v.label}</button>`
    ).join("");

    const ranges = RANGES.map(
      (r) =>
        `<button class="seg ${r === this._days ? "on" : ""}" data-range="${r}">${r} Tage</button>`
    ).join("");

    let body;
    if (this._error) {
      body = `<div class="card err"><b>Daten konnten nicht geladen werden.</b><br>${esc(this._error)}</div>`;
    } else if (!d) {
      body = this._busy
        ? this._skeleton(4)
        : `<div class="card empty"><b>Noch keine Daten</b>
             <p class="hint">Einmal „Abrufen" drücken — danach stehen Form, Plan und Trainings hier.</p></div>`;
    } else {
      body =
        this._view === "form"
          ? this._viewForm(d, p)
          : this._view === "plan"
          ? this._viewPlan(d, p)
          : this._view === "best"
          ? this._viewBest(d, p)
          : this._viewRuns(d);
    }

    this.shadowRoot.innerHTML = `<style>${this._css()}</style>
      <header>
        <div class="brand">
          <div class="eyebrow">intervals.icu${d?.stand ? " · Stand " + esc(fmt.day(d.stand)) : ""}</div>
          <h1>Laufen</h1>
          ${d?.renntag ? `<div class="sub">Wettkampf am ${esc(fmt.day(d.renntag))}</div>` : ""}
        </div>
        ${
          d?.tage_bis_rennen != null
            ? `<div class="cd"><span class="n">${d.tage_bis_rennen}</span><span class="u">Tage</span></div>`
            : ""
        }
      </header>
      ${this._progress(d, p)}
      <nav>${tabs}<span class="spacer"></span>
        <button class="ghost" data-act="sync" ${this._busy ? "disabled" : ""}>${this._busy ? "…" : "Abrufen"}</button>
      </nav>
      ${this._view === "form" || this._view === "runs" ? `<div class="filter"><span class="eyebrow">Zeitraum</span>${ranges}</div>` : ""}
      ${body}
      ${this._moving ? this._moveDialog() : ""}
      ${this._detail ? this._detailSheet(p) : ""}`;

    this._wire();
  }

  /** Schmales Band: wie weit ist der Plan? Eine Zahl allein beantwortet
   *  "noch 91 Tage" — das Band beantwortet "wo im Aufbau stehe ich". */
  _progress(d, p) {
    const plan = d?.plan || [];
    if (!plan.length || d?.tage_bis_rennen == null) return "";
    const heute = new Date().toISOString().slice(0, 10);
    const erledigt = plan.filter((s) => s.tag < heute).length;
    const pct = Math.round((erledigt / plan.length) * 100);
    const aktuell = plan.find((s) => s.tag >= heute);
    return `<div class="progress">
      <div class="track"><span style="width:${pct}%;background:${p.fitness}"></span></div>
      <div class="meta">
        <span>${erledigt} von ${plan.length} Einheiten</span>
        ${aktuell ? `<span>Als Nächstes: ${esc(aktuell.name)} am ${esc(fmt.day(aktuell.tag))}</span>` : ""}
      </div>
    </div>`;
  }

  _skeleton(n = 3) {
    return `<div class="card">${Array.from({ length: n })
      .map((_, i) => `<div class="sk" style="width:${[70, 92, 55][i % 3]}%"></div>`)
      .join("")}</div>`;
  }

  _badge(text, color) {
    return `<span class="badge" style="--c:${color}">${esc(text)}</span>`;
  }

  _wire() {
    const r = this.shadowRoot;
    r.querySelectorAll("[data-tab]").forEach((b) =>
      b.addEventListener("click", () => {
        this._view = b.dataset.tab;
        this._render();
      })
    );
    r.querySelectorAll("[data-range]").forEach((b) =>
      b.addEventListener("click", () => {
        this._days = +b.dataset.range;
        this._load();
      })
    );
    r.querySelectorAll('[data-act="sync"]').forEach((b) =>
      b.addEventListener("click", () => this._sync())
    );
    r.querySelectorAll("[data-table]").forEach((b) =>
      b.addEventListener("click", () => {
        const k = b.dataset.table;
        this._open.has(k) ? this._open.delete(k) : this._open.add(k);
        this._render();
      })
    );
    r.querySelectorAll("[data-move]").forEach((b) =>
      b.addEventListener("click", () => {
        const s = (this._data.plan || []).find((x) => x.event_id === b.dataset.move);
        this._moving = { session: s, result: null };
        this._render();
      })
    );
    r.querySelectorAll("[data-do]").forEach((b) =>
      b.addEventListener("click", () =>
        this._move(b.dataset.id, b.dataset.ziel, b.dataset.do)
      )
    );
    r.querySelectorAll("[data-detail]").forEach((row) =>
      row.addEventListener("click", () => this._openDetail(row.dataset.detail))
    );
    r.querySelectorAll('[data-act="close"]').forEach((b) =>
      b.addEventListener("click", () => {
        this._moving = null;
        this._detail = null;
        this._render();
      })
    );
  }

  /* ── Ansicht: Form ───────────────────────────────────────────────────── */

  _viewForm(d, p) {
    const letzte = (d.verlauf || []).filter((r) => r.ctl != null).slice(-1)[0] || {};
    const st = formStatus(letzte.form);
    const woche = (d.wochen || []).slice(-1)[0];

    const load = loadChart(d.verlauf, p);
    const vol = volumeChart(d.wochen, p);
    const zon = zonesChart(d.wochen, p);
    const an = (d.analysen || [])[0];

    return `
      <section class="card hero">
        <div>
          <span class="pill ${st.tone}">${esc(st.label)}</span>
          <span class="big" style="color:${letzte.form >= 0 ? p.formPos : p.formNeg}">${fmt.n(letzte.form)}</span>
          <div class="eyebrow">Form = Fitness − Ermüdung</div>
        </div>
        <div>
          <div class="eyebrow" style="margin-bottom:8px">Formfenster</div>
          <div class="scroll" style="--mw:360px">${formMeter(letzte.form, p)}</div>
          <div class="bands">
            <span style="flex:10">überlastet</span><span style="flex:15">aufbauend</span
            ><span style="flex:10">neutral</span><span style="flex:20">frisch</span>
          </div>
        </div>
      </section>

      <div class="tiles">
        ${this._tile("Fitness · CTL", fmt.n(letzte.ctl), "", "42-Tage-Mittel", p.fitness)}
        ${this._tile("Ermüdung · ATL", fmt.n(letzte.atl), "", "7-Tage-Mittel", p.fatigue)}
        ${this._tile(
          "Diese Woche",
          woche ? fmt.n(woche.km) : "—",
          woche?.soll_km ? `/ ${fmt.n(woche.soll_km, 0)} km` : "km",
          woche?.soll_km ? `${Math.round((woche.km / woche.soll_km) * 100)} % vom Soll` : null
        )}
        ${
          d.vo2max?.aktuell
            ? this._tile("VO2max", fmt.n(d.vo2max.aktuell), "ml/kg/min",
                `bester aus 42 Läufen · HFmax ${d.vo2max.hr_max}`, p.fitness)
            : this._tile("VO2max", "—", "", "HFmax in den Optionen setzen")
        }
        ${this._tile(
          "Geplant",
          String((d.plan || []).length),
          "Einheiten",
          d.tage_bis_rennen != null ? `bis zum ${fmt.day(d.renntag)}` : null
        )}
      </div>

      ${this._chartCard("last", "Trainingslast und Form", "Fitness ist der 42-Tage-, Ermüdung der 7-Tage-Mittelwert der Tageslast.", load, [
        { color: p.fitness, label: "Fitness (CTL)" },
        { color: p.fatigue, label: "Ermüdung (ATL)" },
      ])}

      <div class="grid2">
        ${this._chartCard("vol", "Wochenumfang", "Soll aus dem Plan, Ist aus den hochgeladenen Läufen.", vol, vol.legend)}
        ${this._chartCard("zon", "Zeit in den Herzfrequenzzonen", "Minuten pro Woche, Z1 hell bis Z5 dunkel.", zon, zon.legend)}
      </div>

      ${
        an
          ? `<section class="card">
               <div class="head"><h2>Analyse des letzten Laufs</h2><span class="eyebrow">${esc(an.model || "")}</span></div>
               <p class="prose">${esc(an.prose || "—")}</p>
               ${an.verdict?.empfehlung_naechste_woche ? `<p class="prose"><b>Nächste Woche:</b> ${esc(an.verdict.empfehlung_naechste_woche)}</p>` : ""}
             </section>`
          : `<section class="card"><p class="hint">Noch keine Analyse. Service <code>ha_intervals.analysieren</code> aufrufen — dafür muss ein Anthropic-Schlüssel hinterlegt sein.</p></section>`
      }`;
  }

  /* ── Ansicht: Trainingsplan ──────────────────────────────────────────── */

  _viewPlan(d, p) {
    const heute = new Date().toISOString().slice(0, 10);
    const kommend = (d.plan || []).filter((s) => s.tag >= heute).slice(0, 24);
    if (!kommend.length) {
      return `<section class="card empty"><b>Kein Plan hinterlegt</b>
        <p class="hint">Mit <code>ha_intervals.plan_erstellen</code> einen Plan rechnen
        und nach intervals.icu schreiben.</p></section>`;
    }

    // Nach Kalenderwoche gruppieren: eine Liste von 24 Zeilen liest sich
    // nicht, eine Woche als Block schon.
    const wochen = new Map();
    for (const s of kommend) {
      const d0 = new Date(s.tag);
      const mo = new Date(d0);
      mo.setDate(d0.getDate() - ((d0.getDay() + 6) % 7));
      const k = mo.toISOString().slice(0, 10);
      if (!wochen.has(k)) wochen.set(k, []);
      wochen.get(k).push(s);
    }

    const bloecke = [...wochen.entries()].map(([start, ss]) => {
      const km = ss.reduce((a, x) => a + (x.km || 0), 0);
      const phase = this._phaseOf(ss[0]);
      const rows = ss.map((s) => `
        <div class="planrow ${s.art === "ruhe" ? "rest" : ""}">
          <span class="day">${esc(fmt.day(s.tag))}</span>
          <span class="dot" style="background:${this._artColor(s.art, p)}"></span>
          <span class="what">
            <span class="kind">${esc(s.name || ART[s.art] || s.art)}</span>
            ${s.beschreibung ? `<span class="detail">${esc((s.beschreibung || "").split("\n")[0])}</span>` : ""}
          </span>
          <span class="load">${s.last || "—"}</span>
          ${s.art === "ruhe"
            ? `<span class="spacerbtn"></span>`
            : `<button class="ghost sm" data-move="${esc(s.event_id)}">Verschieben</button>`}
        </div>`).join("");
      return `<section class="card">
        <div class="head">
          <h2>Woche ab ${esc(fmt.date(start))}</h2>
          <span class="right">
            ${phase ? this._badge(phase, phaseColor(phase, p)) : ""}
            <span class="eyebrow">${fmt.n(km, 1)} km</span>
          </span>
        </div>
        <div class="plan">${rows}</div>
      </section>`;
    });

    return `<p class="hint lead">Änderungen gehen nach intervals.icu und von dort auf die Uhr.</p>`
      + bloecke.join("");
  }

  /** Phase steht in der Markierung der Beschreibung. */
  _phaseOf(s) {
    const m = /phase=([^\s]+)/.exec(s.beschreibung || "");
    return m ? m[1].replace(/_/g, " ") : null;
  }

  _artColor(art, p) {
    return art === "qualitaet" ? p.fatigue
      : art === "longrun" ? p.fitness
      : art === "ruhe" ? p.grid
      : p.zones[1];
  }

  _moveDialog() {
    const { session: s, result: r } = this._moving;
    if (!s) return "";
    const btn = (ziel, modus, label) =>
      `<button class="ghost" data-do="${modus}" data-ziel="${ziel}" data-id="${esc(s.event_id)}">${esc(label)}</button>`;

    let out = `<div class="sheet"><div class="card">
      <div class="head"><h2>${esc(s.name || s.art)}</h2>
        <button class="ghost sm" data-act="close">Schließen</button></div>
      <p class="hint">${esc(fmt.day(s.tag))}${s.beschreibung ? " · " + esc(s.beschreibung) : ""}</p>
      <div class="row">
        ${btn("morgen", "tauschen", "Mit morgen tauschen")}
        ${btn("morgen", "schieben", "Auf morgen schieben")}
        ${btn(s.tag, "streichen", "Streichen")}
      </div>`;

    if (r && !r.ok) {
      out += `<div class="callout">
        <b>Geht so nicht.</b>
        <ul>${(r.konflikte || []).map((k) => `<li>${esc(k.text)}</li>`).join("")}</ul>
        ${
          (r.alternativen || []).length
            ? `<p class="hint">Zulässig wäre:</p><div class="row">${r.alternativen
                .map((a) => btn(a.ziel, a.modus, a.text))
                .join("")}</div>`
            : `<p class="hint">Kein zulässiger Einzelzug mehr — hier hilft nur eine Umplanung.</p>`
        }
        ${r.fehler ? `<p class="hint">${esc(r.fehler)}</p>` : ""}
      </div>`;
    }
    if (r && r.ok && r.hinweise?.length) {
      out += `<div class="callout"><b>Übernommen.</b><ul>${r.hinweise
        .map((h) => `<li>${esc(h)}</li>`)
        .join("")}</ul></div>`;
    }
    return out + "</div></div>";
  }

  /* ── Ansicht: Bestzeiten ─────────────────────────────────────────────── */

  _viewBest(d, p) {
    const v = d.vo2max || {};
    const chart = vo2Chart(v.verlauf, p);
    const offen = this._open.has("vo2");
    const vo2 = `<section class="card">
      <div class="head">
        <h2>VO2max</h2>
        ${chart.table ? `<button class="ghost sm" data-table="vo2">${offen ? "Diagramm" : "Tabelle"}</button>` : ""}
      </div>
      <p class="hint">
        Geschätzt nach dem Verfahren von Runalyze: aus der Herzfrequenz wird
        abgeleitet, welchen Anteil der VO2max ein Lauf abgerufen hat, und die
        Geschwindigkeit auf 100 % hochgerechnet.
        ${v.hr_max ? `HFmax ${v.hr_max}.` : "Ohne HFmax wird nichts gerechnet."}
        ${v.korrektur && v.korrektur !== 1
          ? ` Korrektur ×${fmt.n(v.korrektur, 2)}.`
          : " Unkalibriert — der Verlauf zählt, nicht der Absolutwert."}
      </p>
      ${offen && chart.table
        ? `<div class="tablewrap">${chart.table}</div>`
        : `<div class="scroll" style="--mw:${chart.minWidth}px">${chart.svg}</div>`}
    </section>`;

    const b = d.bestzeiten || [];
    if (!b.length) {
      return vo2 + `<section class="card empty"><b>Keine Distanzklassen belegt</b>
        <p class="hint">Sobald Läufe nahe 5, 10 oder 13 km vorliegen, stehen hier
        die schnellsten je Klasse.</p></section>`;
    }
    return vo2 + `<section class="card">
      <div class="head"><h2>Schnellste Läufe je Distanz</h2></div>
      <p class="hint">
        Gesamtschnitt eines Laufs, <b>nicht</b> das schnellste Teilstück darin.
        Eine echte Bestzeitenkurve braucht die Auswertung der Streams — die ist
        noch nicht gebaut.
      </p>
      <div class="tablewrap">${table(
        ["Distanz", "Zeit", "Pace", "Tag", "Lauf", "Läufe in der Klasse"],
        b.map((e) => [
          `${fmt.n(e.distanz_km, e.distanz_km % 1 ? 2 : 0)} km`,
          fmt.hms(e.sekunden),
          fmt.pace(e.pace_s_km) + " /km",
          fmt.day(e.tag),
          e.name || "—",
          String(e.anzahl_laeufe),
        ])
      )}</div>
    </section>`;
  }

  /* ── Ansicht: Trainings ──────────────────────────────────────────────── */

  _viewRuns(d) {
    const t = d.trainings || [];
    if (!t.length) {
      return `<section class="card"><p class="hint">Keine Aktivitäten im Zeitraum.</p></section>`;
    }
    const analysen = new Map((d.analysen || []).map((a) => [String(a.activity_id), a]));
    return `<section class="card">
      <div class="head"><h2>Trainings</h2><span class="eyebrow">${t.length} Einträge</span></div>
      <p class="hint">Zeile anklicken für Splits und Details.</p>
      <div class="tablewrap"><table>
        <thead><tr>${["Tag","Lauf","km","Zeit","Pace","HF","Last","Analyse"]
          .map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
        <tbody>${t.map((a) => `<tr class="click" data-detail="${esc(a.id)}">
          <td>${esc(fmt.day(a.day))}</td><td>${esc(a.name || "—")}</td>
          <td>${esc(fmt.n(a.km))}</td><td>${esc(fmt.hms(a.seconds))}</td>
          <td>${esc(fmt.pace(a.pace_s_km))} /km</td>
          <td>${esc(a.hr_avg ? String(a.hr_avg) : "—")}</td>
          <td>${esc(String(a.load ?? "—"))}</td>
          <td>${analysen.has(String(a.id)) ? "ja" : "—"}</td></tr>`).join("")}
        </tbody></table></div>
    </section>`;
  }

  /* ── Detailseite eines Trainings ─────────────────────────────────────── */

  _detailSheet(p) {
    const d = this._detail;
    const head = (titel) => `<div class="head"><h2>${esc(titel)}</h2>
      <button class="ghost sm" data-act="close">Schließen</button></div>`;

    if (d.loading) return `<div class="sheet"><div class="card">${head("Lade …")}</div></div>`;
    if (d.error || !d.data?.ok) {
      return `<div class="sheet"><div class="card">${head("Nicht ladbar")}
        <p class="hint">${esc(d.error || d.data?.grund || "Unbekannter Fehler")}</p></div></div>`;
    }

    const x = d.data;
    const t = x.training || {};
    const k = x.kennzahlen || {};
    const sp = x.splits || [];

    // Splits als Balken: die schnellste Pace ist der Bezug, langsamere Zeilen
    // werden entsprechend länger. Ein eigenes Diagramm wäre hier Overhead —
    // die Tabelle *ist* die Darstellung.
    const paces = sp.map((s) => s.pace_s_km).filter(Boolean);
    const best = paces.length ? Math.min(...paces) : 0;
    const worst = paces.length ? Math.max(...paces) : 1;
    const breite = (v) => (worst === best ? 100 : 30 + (70 * (worst - v)) / (worst - best));

    const splitRows = sp.map((s) => `<tr>
        <td>${s.teil ? esc(fmt.n(s.km, 2)) : s.km}</td>
        <td>${esc(fmt.pace(s.pace_s_km))}</td>
        <td>${esc(fmt.hms(s.sekunden))}</td>
        <td>${esc(s.hf ? String(s.hf) : "—")}</td>
        <td class="barcell"><span class="bar" style="width:${breite(s.pace_s_km).toFixed(0)}%;
          background:${s.teil ? p.planGhost : p.fitness}"></span></td>
      </tr>`).join("");

    const zonen = (x.zonen_minuten || []).some((z) => z > 0)
      ? `<div class="legend">${(x.zonen_minuten || []).map((m, i) =>
          `<span><i class="blk" style="background:${p.zones[i]}"></i>Z${i + 1} ${m} min</span>`
        ).join("")}</div>`
      : "";

    const plan = x.geplant_war
      ? `<p class="prose"><b>Geplant war:</b> ${esc(x.geplant_war.name || "")} — ${esc(x.geplant_war.description || "")}</p>`
      : "";

    const an = x.analyse
      ? `<p class="prose">${esc(an_text(x.analyse))}</p>`
      : `<p class="hint">Keine Analyse zu diesem Lauf.</p>`;

    return `<div class="sheet"><div class="card wide">
      ${head(t.name || "Training")}
      <p class="hint">${esc(fmt.day(t.day))} · ${esc(t.kind || "")}</p>
      <div class="verdict">
        <div><span class="k">Distanz</span><span class="v">${esc(fmt.n(t.km))} km</span></div>
        <div><span class="k">Zeit</span><span class="v">${esc(fmt.hms(t.seconds))}</span></div>
        <div><span class="k">Pace</span><span class="v">${esc(fmt.pace(t.pace_s_km))}</span></div>
        <div><span class="k">HF ø</span><span class="v">${esc(t.hr_avg || "—")}</span></div>
        <div><span class="k">Last</span><span class="v">${esc(t.load ?? "—")}</span></div>
        ${t.vo2max
          ? `<div><span class="k">VO2max</span><span class="v">${esc(fmt.n(t.vo2max))}</span></div>`
          : ""}
        ${k.entkopplung_prozent !== undefined
          ? `<div><span class="k">Entkopplung</span><span class="v">${esc(fmt.n(k.entkopplung_prozent))} %</span></div>`
          : ""}
      </div>
      ${zonen}
      ${plan}
      ${an}
      ${sp.length
        ? `<div class="tablewrap"><table>
             <thead><tr><th>km</th><th>Pace</th><th>Zeit</th><th>HF</th><th></th></tr></thead>
             <tbody>${splitRows}</tbody></table></div>`
        : `<p class="hint">${esc(x.hinweis || "Keine Streams vorhanden — ohne sie gibt es keine Splits.")}</p>`}
    </div></div>`;
  }

  /* ── Bausteine ───────────────────────────────────────────────────────── */

  _tile(label, value, unit, note, color) {
    return `<div class="tile">
      <span class="eyebrow">${esc(label)}</span>
      <div class="row base">
        <span class="v"${color ? ` style="color:${color}"` : ""}>${esc(value)}</span>
        ${unit ? `<span class="unit">${esc(unit)}</span>` : ""}
      </div>
      ${note ? `<span class="note">${esc(note)}</span>` : ""}
    </div>`;
  }

  _chartCard(key, title, sub, chart, legend) {
    const open = this._open.has(key);
    return `<section class="card">
      <div class="head"><h2>${esc(title)}</h2>
        ${chart.table ? `<button class="ghost sm" data-table="${key}">${open ? "Diagramm" : "Tabelle"}</button>` : ""}
      </div>
      ${sub ? `<p class="hint">${esc(sub)}</p>` : ""}
      ${
        open && chart.table
          ? `<div class="tablewrap">${chart.table}</div>`
          : `<div class="scroll" style="--mw:${chart.minWidth}px">${chart.svg}</div>
             ${
               legend?.length
                 ? `<div class="legend">${legend
                     .map(
                       (l) =>
                         `<span><i class="${l.block ? "blk" : ""}" style="background:${l.color}"></i>${esc(l.label)}</span>`
                     )
                     .join("")}</div>`
                 : ""
             }`
      }
    </section>`;
  }

  _css() {
    return `
    :host { ${CSS_TOKENS}
      display:block; padding:20px 22px 64px; font-family:var(--sans);
      color:var(--ink); background:var(--plane); min-height:100%; font-size:15px;
      line-height:1.5; }
    * { box-sizing:border-box; }

    /* ── Kopf ── */
    header { display:flex; justify-content:space-between; align-items:flex-end;
      gap:20px; flex-wrap:wrap; padding-bottom:14px; }
    h1 { margin:3px 0 0; font-size:28px; font-weight:680; letter-spacing:-0.025em; }
    .brand .sub { color:var(--ink-2); font-size:13.5px; margin-top:3px; }
    .eyebrow, .cd .u { font-family:var(--mono); font-size:10.5px; letter-spacing:0.13em;
      text-transform:uppercase; color:var(--ink-3); }
    .cd { text-align:right; }
    .cd .n { font-size:38px; font-weight:680; display:block; line-height:1;
      letter-spacing:-0.035em; color:var(--accent); }

    /* ── Fortschrittsband ── */
    .progress { margin:2px 0 18px; }
    .progress .track { height:5px; border-radius:3px; background:var(--rule);
      overflow:hidden; }
    .progress .track span { display:block; height:100%; border-radius:3px; }
    .progress .meta { display:flex; justify-content:space-between; gap:12px;
      flex-wrap:wrap; margin-top:7px; font-family:var(--mono); font-size:11px;
      color:var(--ink-3); }

    /* ── Navigation ── */
    nav { display:flex; gap:2px; align-items:center; border-bottom:1px solid var(--rule);
      margin-bottom:18px; flex-wrap:wrap; }
    nav .spacer { flex:1; }
    button { font:inherit; cursor:pointer; }
    .tab { appearance:none; border:0; background:transparent; padding:11px 15px;
      font-size:14px; color:var(--ink-2); border-bottom:2px solid transparent;
      border-radius:var(--radius-sm) var(--radius-sm) 0 0; }
    .tab:hover { color:var(--ink); background:var(--surface); }
    .tab.on { color:var(--accent); border-bottom-color:var(--accent); font-weight:600; }

    .ghost { appearance:none; background:var(--surface); border:1px solid var(--rule);
      border-radius:var(--radius-sm); color:var(--ink-2); font-family:var(--mono);
      font-size:11px; letter-spacing:0.06em; text-transform:uppercase;
      padding:6px 12px; transition:none; }
    .ghost:hover { color:var(--ink); border-color:var(--ink-3); }
    .ghost[disabled] { opacity:0.45; cursor:default; }
    .ghost.sm { padding:4px 10px; font-size:10px; }

    .filter { display:flex; gap:8px; align-items:center; margin-bottom:16px;
      flex-wrap:wrap; }
    .seg { appearance:none; border:1px solid var(--rule); background:var(--surface);
      border-radius:var(--radius-sm); padding:6px 13px; font-family:var(--mono);
      font-size:11.5px; color:var(--ink-2); }
    .seg:hover { color:var(--ink); }
    .seg.on { background:var(--accent); color:#fff; border-color:var(--accent);
      font-weight:600; }

    /* ── Karten ── */
    .card { background:var(--surface); border:1px solid var(--rule);
      border-radius:var(--radius); padding:var(--pad); margin-bottom:var(--gap);
      min-width:0; }
    .card.err { color:var(--error-color, #d03b3b); }
    .card.empty { text-align:center; padding:34px 20px; }
    .card.empty b { display:block; margin-bottom:6px; }
    .head { display:flex; justify-content:space-between; align-items:center;
      gap:12px; flex-wrap:wrap; margin-bottom:4px; }
    .head .right { display:inline-flex; align-items:center; gap:10px; }
    h2 { margin:0; font-size:15.5px; font-weight:620; letter-spacing:-0.01em; }
    .hint { color:var(--ink-2); font-size:13px; margin:0 0 14px; max-width:68ch; }
    .hint.lead { margin:-4px 0 14px; }
    .prose { color:var(--ink-2); font-size:13.5px; line-height:1.62; margin:0 0 10px;
      max-width:64ch; }
    .prose b { color:var(--ink); }
    code { font-family:var(--mono); font-size:12px; background:var(--plane);
      padding:1px 5px; border-radius:4px; }

    .badge { display:inline-flex; align-items:center; font-family:var(--mono);
      font-size:10px; letter-spacing:0.09em; text-transform:uppercase;
      padding:3px 9px; border-radius:999px; color:var(--c);
      border:1px solid color-mix(in srgb, var(--c) 40%, transparent);
      background:color-mix(in srgb, var(--c) 12%, transparent); }

    .sk { height:13px; border-radius:6px; background:var(--rule); margin:11px 0; }

    /* ── Hero ── */
    .hero { display:grid; grid-template-columns:minmax(180px,250px) 1fr; gap:30px;
      align-items:center; }
    .big { font-size:58px; font-weight:680; line-height:1; letter-spacing:-0.045em;
      display:block; margin:10px 0 7px; }
    .pill { display:inline-flex; font-family:var(--mono); font-size:10.5px;
      letter-spacing:0.1em; text-transform:uppercase; padding:4px 10px;
      border-radius:999px; border:1px solid var(--rule); background:var(--plane); }
    .pill.good { color:#0ca30c; } .pill.critical { color:#d03b3b; }
    .bands { display:flex; font-family:var(--mono); font-size:10px;
      letter-spacing:0.08em; text-transform:uppercase; color:var(--ink-3);
      margin-top:7px; }
    .bands span { text-align:center; }
    .bands span:first-child { text-align:left; }
    .bands span:last-child { text-align:right; }

    /* ── Kacheln ── */
    .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(176px,1fr));
      gap:var(--gap); margin-bottom:var(--gap); }
    .tiles > * { min-width:0; }
    .tile { background:var(--surface); border:1px solid var(--rule);
      border-radius:var(--radius); padding:16px 18px 15px; }
    .tile .v { font-size:30px; font-weight:650; letter-spacing:-0.035em; }
    .tile .unit { font-family:var(--mono); font-size:11.5px; color:var(--ink-3); }
    .tile .note { display:block; margin-top:7px; font-family:var(--mono);
      font-size:10.5px; color:var(--ink-3); letter-spacing:0.03em; }
    .row { display:flex; gap:8px; flex-wrap:wrap; }
    .row.base { align-items:baseline; margin-top:7px; }

    .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:var(--gap); }
    .grid2 > * { min-width:0; }
    @media (max-width:900px) { .grid2 { grid-template-columns:1fr; }
      .hero { grid-template-columns:1fr; gap:20px; } }

    /* ── Diagramme ── */
    .scroll { overflow-x:auto; max-width:100%; }
    .scroll svg { display:block; width:100%; min-width:var(--mw,0); height:auto; }
    .legend { display:flex; gap:16px; flex-wrap:wrap; margin-top:12px;
      font-size:12.5px; color:var(--ink-2); }
    .legend span { display:inline-flex; align-items:center; gap:6px; }
    .legend i { width:14px; height:3px; border-radius:2px; display:inline-block; }
    .legend i.blk { width:11px; height:11px; border-radius:3px; }

    /* ── Tabellen ── */
    .tablewrap { overflow-x:auto; margin-top:12px; }
    table { border-collapse:collapse; width:100%; font-size:12.5px; }
    th, td { text-align:right; padding:8px 11px; border-bottom:1px solid var(--rule);
      font-family:var(--mono); font-variant-numeric:tabular-nums; white-space:nowrap; }
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align:left; }
    th { font-size:10px; letter-spacing:0.1em; text-transform:uppercase;
      color:var(--ink-3); font-weight:500; }
    tbody tr:last-child td { border-bottom:0; }
    tr.click { cursor:pointer; }
    tr.click:hover td { background:var(--plane); }

    /* ── Plan ── */
    .plan { display:flex; flex-direction:column; margin-top:6px; }
    .planrow { display:grid; grid-template-columns:72px 8px 1fr auto auto; gap:12px;
      align-items:center; padding:11px 0; border-bottom:1px solid var(--rule); }
    .planrow:last-child { border-bottom:0; }
    .planrow .day { font-family:var(--mono); font-size:11px; color:var(--ink-3);
      text-transform:uppercase; letter-spacing:0.05em; }
    .planrow .dot { width:8px; height:8px; border-radius:50%; }
    .planrow .kind { font-size:13.5px; font-weight:600; }
    .planrow .detail { display:block; color:var(--ink-2); font-size:12.5px;
      margin-top:2px; overflow:hidden; text-overflow:ellipsis; }
    .planrow .load { font-family:var(--mono); font-size:12px; color:var(--ink-2); }
    .planrow.rest .kind { color:var(--ink-3); font-weight:500; }
    /* Ein Ruhetag lässt sich nicht verschieben — statt eines toten Knopfes
       bleibt die Spalte leer, damit die Zeilen trotzdem fluchten. */
    .spacerbtn { display:inline-block; width:104px; }
    @media (max-width:620px) { .planrow { grid-template-columns:64px 8px 1fr auto; }
      .planrow .load { display:none; } }

    /* ── Dialoge ── */
    .sheet { position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:9;
      display:flex; align-items:center; justify-content:center; padding:20px; }
    .sheet .card { max-width:540px; width:100%; margin:0; max-height:86vh;
      overflow:auto; }
    .sheet .card.wide { max-width:700px; }
    /* Hinweisblock im Dialog. Hieß früher .note und kollidierte damit mit
       der Zusatzzeile in den Kacheln — gleicher Klassenname, zwei Begriffe,
       und der border-top schlug in die Kacheln durch. */
    .callout { border-top:1px solid var(--rule); margin-top:14px; padding-top:13px;
      font-size:13px; }
    .callout ul { margin:7px 0 11px; padding-left:18px; color:var(--ink-2); }
    .barcell { width:38%; padding-right:0; }
    .bar { display:block; height:7px; border-radius:3px; }
    .verdict { display:grid; grid-template-columns:repeat(auto-fit,minmax(100px,1fr));
      gap:1px; background:var(--rule); border:1px solid var(--rule);
      border-radius:var(--radius-sm); overflow:hidden; margin:14px 0; }
    .verdict > div { background:var(--surface); padding:10px 12px; }
    .verdict .k { display:block; font-family:var(--mono); font-size:9.5px;
      letter-spacing:0.1em; text-transform:uppercase; color:var(--ink-3); }
    .verdict .v { font-family:var(--mono); font-size:14px; font-weight:600;
      font-variant-numeric:tabular-nums; }

    @media (prefers-reduced-motion:reduce) { * { animation:none !important;
      transition:none !important; } }
    `;
  }
}

if (!customElements.get("ha-intervals-panel")) {
  customElements.define("ha-intervals-panel", HaIntervalsPanel);
}
