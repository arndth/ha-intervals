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

import { CSS_TOKENS, detectMode, palette } from "./theme.js";
import {
  esc,
  fmt,
  formMeter,
  formStatus,
  loadChart,
  table,
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
      body = `<div class="card"><p class="hint">${this._busy ? "Lade …" : "Keine Daten."}</p></div>`;
    } else {
      body =
        this._view === "form"
          ? this._viewForm(d, p)
          : this._view === "plan"
          ? this._viewPlan(d)
          : this._view === "best"
          ? this._viewBest(d)
          : this._viewRuns(d);
    }

    this.shadowRoot.innerHTML = `<style>${this._css()}</style>
      <header>
        <div>
          <div class="eyebrow">intervals.icu${d?.stand ? " · Stand " + esc(fmt.day(d.stand)) : ""}</div>
          <h1>Laufen</h1>
        </div>
        ${
          d?.tage_bis_rennen != null
            ? `<div class="cd"><span class="n">${d.tage_bis_rennen}</span><span class="u">Tage bis zum Rennen</span></div>`
            : ""
        }
      </header>
      <nav>${tabs}<span class="spacer"></span>
        <button class="ghost" data-act="sync" ${this._busy ? "disabled" : ""}>${this._busy ? "…" : "Abrufen"}</button>
      </nav>
      ${this._view === "form" || this._view === "runs" ? `<div class="filter"><span class="eyebrow">Zeitraum</span>${ranges}</div>` : ""}
      ${body}
      ${this._moving ? this._moveDialog() : ""}`;

    this._wire();
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
    r.querySelectorAll('[data-act="close"]').forEach((b) =>
      b.addEventListener("click", () => {
        this._moving = null;
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
        ${this._tile("Fitness · CTL", fmt.n(letzte.ctl), "")}
        ${this._tile("Ermüdung · ATL", fmt.n(letzte.atl), "")}
        ${this._tile("Diese Woche", woche ? fmt.n(woche.km) : "—", woche?.soll_km ? `/ ${fmt.n(woche.soll_km, 0)} km` : "km")}
        ${this._tile("Geplante Einheiten", String((d.plan || []).length), "")}
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

  _viewPlan(d) {
    const heute = new Date().toISOString().slice(0, 10);
    const kommend = (d.plan || []).filter((s) => s.tag >= heute).slice(0, 21);
    if (!kommend.length) {
      return `<section class="card"><p class="hint">Keine geplanten Einheiten in intervals.icu.</p></section>`;
    }

    const rows = kommend
      .map(
        (s) => `
      <div class="planrow ${s.art === "ruhe" ? "rest" : ""}">
        <span class="day">${esc(fmt.day(s.tag))}</span>
        <span class="what">
          <span class="kind">${esc(s.name || ART[s.art] || s.art)}</span>
          ${s.beschreibung ? `<span class="detail">${esc(s.beschreibung)}</span>` : ""}
        </span>
        <span class="load">${s.last || "—"}</span>
        <button class="ghost sm" data-move="${esc(s.event_id)}">Verschieben</button>
      </div>`
      )
      .join("");

    return `<section class="card">
      <div class="head"><h2>Kommende Einheiten</h2>
        <span class="eyebrow">${kommend.length} Einträge</span></div>
      <p class="hint">Änderungen gehen nach intervals.icu und von dort auf die Uhr.</p>
      <div class="plan">${rows}</div>
    </section>`;
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
      out += `<div class="note">
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
      out += `<div class="note"><b>Übernommen.</b><ul>${r.hinweise
        .map((h) => `<li>${esc(h)}</li>`)
        .join("")}</ul></div>`;
    }
    return out + "</div></div>";
  }

  /* ── Ansicht: Bestzeiten ─────────────────────────────────────────────── */

  _viewBest(d) {
    const b = d.bestzeiten || [];
    if (!b.length) {
      return `<section class="card"><p class="hint">Noch keine Läufe, die einer Distanzklasse zugeordnet werden konnten.</p></section>`;
    }
    return `<section class="card">
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
      <div class="tablewrap">${table(
        ["Tag", "Lauf", "km", "Zeit", "Pace", "HF", "Last", "Analyse"],
        t.map((a) => [
          fmt.day(a.day),
          a.name || "—",
          fmt.n(a.km),
          fmt.hms(a.seconds),
          fmt.pace(a.pace_s_km) + " /km",
          a.hr_avg ? String(a.hr_avg) : "—",
          String(a.load ?? "—"),
          analysen.has(String(a.id)) ? "ja" : "—",
        ])
      )}</div>
    </section>`;
  }

  /* ── Bausteine ───────────────────────────────────────────────────────── */

  _tile(label, value, unit) {
    return `<div class="tile"><span class="eyebrow">${esc(label)}</span>
      <div class="row base"><span class="v">${esc(value)}</span>${unit ? `<span class="unit">${esc(unit)}</span>` : ""}</div></div>`;
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
      display:block; padding:16px 20px 56px; font-family:var(--sans);
      color:var(--ink); background:var(--plane); min-height:100%; font-size:15px; }
    * { box-sizing:border-box; }
    h1 { margin:2px 0 0; font-size:26px; font-weight:650; letter-spacing:-0.02em; }
    h2 { margin:0; font-size:15px; font-weight:600; }
    header { display:flex; justify-content:space-between; align-items:flex-end;
      gap:20px; flex-wrap:wrap; padding-bottom:12px; }
    .cd { text-align:right; }
    .cd .n { font-family:var(--mono); font-size:30px; font-weight:600; display:block;
      line-height:1; letter-spacing:-0.02em; }
    .cd .u, .eyebrow { font-family:var(--mono); font-size:10.5px; letter-spacing:0.12em;
      text-transform:uppercase; color:var(--ink-3); }
    nav { display:flex; gap:4px; align-items:center; border-bottom:1px solid var(--rule);
      margin-bottom:16px; flex-wrap:wrap; }
    nav .spacer { flex:1; }
    button { font:inherit; cursor:pointer; }
    .tab { appearance:none; border:0; background:transparent; padding:10px 14px;
      font-size:14px; color:var(--ink-2); border-bottom:2px solid transparent; }
    .tab.on { color:var(--accent); border-bottom-color:var(--accent); font-weight:600; }
    .ghost { appearance:none; background:transparent; border:1px solid var(--rule);
      border-radius:7px; color:var(--ink-2); font-family:var(--mono); font-size:11px;
      letter-spacing:0.06em; text-transform:uppercase; padding:5px 11px; }
    .ghost:hover { color:var(--ink); }
    .ghost[disabled] { opacity:0.5; cursor:default; }
    .ghost.sm { padding:3px 9px; font-size:10px; }
    .filter { display:flex; gap:8px; align-items:center; margin-bottom:14px; flex-wrap:wrap; }
    .seg { appearance:none; border:1px solid var(--rule); background:transparent;
      border-radius:7px; padding:5px 11px; font-family:var(--mono); font-size:11.5px;
      color:var(--ink-2); }
    .seg.on { background:var(--accent); color:#fff; border-color:var(--accent); font-weight:600; }
    .card { background:var(--surface); border:1px solid var(--rule);
      border-radius:var(--radius); padding:16px 18px 18px; margin-bottom:16px; min-width:0; }
    .card.err { color:var(--error-color, #d03b3b); }
    .head { display:flex; justify-content:space-between; align-items:center;
      gap:12px; flex-wrap:wrap; margin-bottom:6px; }
    .hint { color:var(--ink-2); font-size:13px; margin:0 0 12px; max-width:68ch; }
    .prose { color:var(--ink-2); font-size:13.5px; line-height:1.62; margin:0 0 10px; max-width:64ch; }
    .prose b { color:var(--ink); }
    code { font-family:var(--mono); font-size:12px; }
    .hero { display:grid; grid-template-columns:minmax(170px,230px) 1fr; gap:28px; align-items:center; }
    .big { font-size:52px; font-weight:650; line-height:1; letter-spacing:-0.04em;
      display:block; margin:8px 0 6px; }
    .pill { display:inline-block; font-family:var(--mono); font-size:10.5px;
      letter-spacing:0.1em; text-transform:uppercase; padding:3px 9px; border-radius:999px;
      border:1px solid var(--rule); }
    .pill.good { color:#0ca30c; } .pill.critical { color:#d03b3b; }
    .bands { display:flex; font-family:var(--mono); font-size:10px; letter-spacing:0.08em;
      text-transform:uppercase; color:var(--ink-3); margin-top:6px; }
    .bands span { text-align:center; }
    .bands span:first-child { text-align:left; } .bands span:last-child { text-align:right; }
    .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
      gap:12px; margin-bottom:16px; }
    .tiles > * { min-width:0; }
    .tile { background:var(--surface); border:1px solid var(--rule);
      border-radius:var(--radius); padding:13px 15px; }
    .tile .v { font-size:26px; font-weight:620; letter-spacing:-0.03em; }
    .tile .unit { font-family:var(--mono); font-size:11px; color:var(--ink-3); }
    .row { display:flex; gap:8px; flex-wrap:wrap; }
    .row.base { align-items:baseline; margin-top:5px; }
    .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    .grid2 > * { min-width:0; }
    @media (max-width:880px) { .grid2 { grid-template-columns:1fr; }
      .hero { grid-template-columns:1fr; gap:18px; } }
    .scroll { overflow-x:auto; max-width:100%; }
    .scroll svg { display:block; width:100%; min-width:var(--mw,0); height:auto; }
    .legend { display:flex; gap:16px; flex-wrap:wrap; margin-top:10px;
      font-size:12.5px; color:var(--ink-2); }
    .legend span { display:inline-flex; align-items:center; gap:6px; }
    .legend i { width:14px; height:3px; border-radius:2px; display:inline-block; }
    .legend i.blk { width:11px; height:11px; border-radius:3px; }
    .tablewrap { overflow-x:auto; margin-top:10px; }
    table { border-collapse:collapse; width:100%; font-size:12.5px; }
    th, td { text-align:right; padding:6px 10px; border-bottom:1px solid var(--rule);
      font-family:var(--mono); font-variant-numeric:tabular-nums; white-space:nowrap; }
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align:left; }
    th { font-size:10px; letter-spacing:0.1em; text-transform:uppercase;
      color:var(--ink-3); font-weight:500; }
    tbody tr:last-child td { border-bottom:0; }
    .plan { display:flex; flex-direction:column; }
    .planrow { display:grid; grid-template-columns:70px 1fr auto auto; gap:12px;
      align-items:center; padding:10px 0; border-bottom:1px solid var(--rule); }
    .planrow:last-child { border-bottom:0; }
    .planrow .day { font-family:var(--mono); font-size:11px; color:var(--ink-3);
      text-transform:uppercase; letter-spacing:0.05em; }
    .planrow .kind { font-size:13.5px; font-weight:600; }
    .planrow .detail { display:block; color:var(--ink-2); font-size:12.5px; margin-top:1px; }
    .planrow .load { font-family:var(--mono); font-size:12px; color:var(--ink-2); }
    .planrow.rest .kind { color:var(--ink-3); font-weight:500; }
    @media (max-width:560px) { .planrow { grid-template-columns:62px 1fr auto; }
      .planrow .load { display:none; } }
    .sheet { position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:9;
      display:flex; align-items:center; justify-content:center; padding:20px; }
    .sheet .card { max-width:520px; width:100%; margin:0; max-height:80vh; overflow:auto; }
    .note { border-top:1px solid var(--rule); margin-top:14px; padding-top:12px; font-size:13px; }
    .note ul { margin:6px 0 10px; padding-left:18px; color:var(--ink-2); }
    @media (prefers-reduced-motion:reduce) { * { animation:none !important; transition:none !important; } }
    `;
  }
}

if (!customElements.get("ha-intervals-panel")) {
  customElements.define("ha-intervals-panel", HaIntervalsPanel);
}
