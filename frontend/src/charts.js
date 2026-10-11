/**
 * Diagramme als reines SVG — keine Bibliothek.
 *
 * Grundregeln, die überall gelten: dünne Marken (Linien 2 px, Balken ≤ 24 px),
 * zurückgenommenes Gitter aus durchgezogenen Haarlinien, 2-px-Spalt in
 * Flächenfarbe zwischen berührenden Balken statt Rahmen, nur Endpunkte und
 * Extremwerte direkt beschriftet, Text nie in Serienfarbe. Zu jedem Diagramm
 * gehört eine Tabelle — ein Tooltip darf nie der einzige Weg zu einem Wert
 * sein.
 */

export const fmt = {
  n: (v, d = 1) =>
    v === null || v === undefined || Number.isNaN(v)
      ? "—"
      : v.toLocaleString("de-DE", {
          minimumFractionDigits: d,
          maximumFractionDigits: d,
        }),
  pace: (s) =>
    !s || !Number.isFinite(s)
      ? "—"
      : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`,
  hms: (s) => {
    if (!s) return "—";
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = Math.round(s % 60);
    return h
      ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`
      : `${m}:${String(r).padStart(2, "0")}`;
  },
  date: (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    const MON = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
    return `${d.getDate()}. ${MON[d.getMonth()]}`;
  },
  day: (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    const DOW = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
    return `${DOW[d.getDay()]} ${d.getDate()}.${d.getMonth() + 1}.`;
  },
};

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );

const path = (pts) =>
  pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

/** Balken mit abgerundetem Datenende, eckig an der Grundlinie. */
function bar(x, yTop, w, yBase, fill, r = 4) {
  const h = yBase - yTop;
  const rr = Math.min(r, h, w / 2);
  return (
    `<path d="M${x} ${yBase} L${x} ${yTop + rr} Q${x} ${yTop} ${x + rr} ${yTop}` +
    ` L${x + w - rr} ${yTop} Q${x + w} ${yTop} ${x + w} ${yTop + rr}` +
    ` L${x + w} ${yBase} Z" fill="${fill}"/>`
  );
}

/* ── Trainingslast und Form ────────────────────────────────────────────── */

export function loadChart(verlauf, p) {
  if (!verlauf?.length) return leer("Noch keine Wellness-Daten von intervals.icu.");

  const W = 1000, L = 46, R = 58, T = 28, LOAD = 210, GAP = 30, FORM = 66;
  const yBot = T + LOAD, fTop = yBot + GAP, fBot = fTop + FORM;
  const axisY = fBot + 16, H = axisY + 10;
  const plotW = W - L - R;

  const d = verlauf.filter((r) => r.ctl != null);
  if (!d.length) return leer("Keine auswertbaren Werte im Zeitraum.");

  const maxY = Math.ceil(Math.max(...d.map((r) => Math.max(r.ctl, r.atl || 0))) / 10) * 10 + 10;
  const x = (i) => L + (d.length === 1 ? plotW / 2 : (i / (d.length - 1)) * plotW);
  const y = (v) => yBot - (v / maxY) * LOAD;
  const fMax = Math.max(5, Math.ceil(Math.max(...d.map((r) => Math.abs(r.form ?? 0))) / 5) * 5);
  const fy = (v) => (fTop + fBot) / 2 - (v / fMax) * (FORM / 2);

  let h = "";
  for (let v = 0; v <= maxY; v += 10) {
    h += `<line x1="${L}" y1="${y(v)}" x2="${L + plotW}" y2="${y(v)}" stroke="${p.grid}" stroke-width="1"/>`;
    h += `<text x="${L - 9}" y="${y(v) + 3.5}" font-family="${MONO}" font-size="10.5" text-anchor="end" fill="var(--ink-3)" style="font-variant-numeric:tabular-nums">${v}</text>`;
  }
  h += `<text x="${L}" y="${T - 11}" font-family="${MONO}" font-size="9.5" letter-spacing="0.8" fill="var(--ink-3)">LAST · CTL UND ATL</text>`;

  const ctl = d.map((r, i) => [x(i), y(r.ctl)]);
  h += `<path d="${path(ctl)} L${x(d.length - 1)} ${yBot} L${L} ${yBot} Z" fill="${p.fitness}" opacity="0.10"/>`;
  h += `<path d="${path(ctl)}" fill="none" stroke="${p.fitness}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;

  const atl = d.filter((r) => r.atl != null).map((r, i) => [x(i), y(r.atl)]);
  if (atl.length) {
    h += `<path d="${path(atl)}" fill="none" stroke="${p.fatigue}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  }

  const last = d[d.length - 1];
  const le = ctl[ctl.length - 1];
  const ae = atl.length ? atl[atl.length - 1] : null;
  // Kollisionsschutz: laufen die Endwerte zusammen, werden die Beschriftungen
  // auseinandergezogen statt übereinander gestapelt.
  let ly = le[1], ay = ae ? ae[1] : 0;
  if (ae && Math.abs(ly - ay) < 15) {
    const m = (ly + ay) / 2;
    ly = m - 8;
    ay = m + 8;
  }
  if (ae) {
    h += `<circle cx="${ae[0]}" cy="${ae[1]}" r="4.5" fill="${p.fatigue}" stroke="var(--surface)" stroke-width="2"/>`;
    h += `<text x="${ae[0] + 9}" y="${ay + 3.5}" font-family="${MONO}" font-size="11.5" font-weight="600" fill="var(--ink)" style="font-variant-numeric:tabular-nums">${fmt.n(last.atl)}</text>`;
  }
  h += `<circle cx="${le[0]}" cy="${le[1]}" r="4.5" fill="${p.fitness}" stroke="var(--surface)" stroke-width="2"/>`;
  h += `<text x="${le[0] + 9}" y="${ly + 3.5}" font-family="${MONO}" font-size="11.5" font-weight="600" fill="var(--ink)" style="font-variant-numeric:tabular-nums">${fmt.n(last.ctl)}</text>`;

  // Formband auf derselben Zeitachse
  const bw = Math.max(1.5, Math.min(9, plotW / d.length - 2));
  d.forEach((r, i) => {
    const v = r.form ?? 0;
    const top = v >= 0 ? fy(v) : fy(0);
    const hh = Math.max(Math.abs(fy(v) - fy(0)), 0.8);
    h += `<rect x="${(x(i) - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${hh.toFixed(1)}" fill="${v >= 0 ? p.formPos : p.formNeg}" opacity="0.85"/>`;
  });
  h += `<line x1="${L}" y1="${fy(0)}" x2="${L + plotW}" y2="${fy(0)}" stroke="${p.baseline}" stroke-width="1"/>`;
  h += `<text x="${L - 9}" y="${fy(0) + 3.5}" font-family="${MONO}" font-size="10.5" text-anchor="end" fill="var(--ink-3)">0</text>`;
  h += `<text x="${L}" y="${fTop - 9}" font-family="${MONO}" font-size="9.5" letter-spacing="0.8" fill="var(--ink-3)">FORM · CTL − ATL</text>`;

  const ticks = [];
  d.forEach((r, i) => {
    if (new Date(r.day).getDate() === 1 || i === 0 || i === d.length - 1) ticks.push([i, r.day]);
  });
  h += `<line x1="${L}" y1="${fBot + 1}" x2="${L + plotW}" y2="${fBot + 1}" stroke="${p.baseline}" stroke-width="1"/>`;
  ticks.forEach(([i, day], n) => {
    const anchor = n === 0 ? "start" : n === ticks.length - 1 ? "end" : "middle";
    h += `<text x="${x(i)}" y="${axisY}" font-family="${MONO}" font-size="10.5" text-anchor="${anchor}" fill="var(--ink-3)">${esc(fmt.date(day))}</text>`;
  });

  return {
    svg: `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Trainingslast über ${d.length} Tage. Fitness zuletzt ${fmt.n(last.ctl)}, Ermüdung ${fmt.n(last.atl)}, Form ${fmt.n(last.form)}.">${h}</svg>`,
    minWidth: 820,
    table: table(
      ["Tag", "Fitness", "Ermüdung", "Form"],
      d.slice().reverse().map((r) => [fmt.day(r.day), fmt.n(r.ctl), fmt.n(r.atl), fmt.n(r.form)])
    ),
  };
}

/* ── Wochenumfang: Soll gegen Ist ──────────────────────────────────────── */

export function volumeChart(wochen, p) {
  if (!wochen?.length) return leer("Noch keine Läufe im Zeitraum.");

  const W = 520, H = 248, L = 36, R = 10, T = 26, B = 34;
  const plotW = W - L - R, plotH = H - T - B;
  const maxY = Math.max(10, Math.ceil(Math.max(...wochen.map((w) => Math.max(w.km, w.soll_km || 0))) / 10) * 10);
  const band = plotW / wochen.length;
  const bw = Math.min(11, (band - 8) / 2);
  const y = (v) => T + plotH - (v / maxY) * plotH;

  let h = "";
  for (let v = 0; v <= maxY; v += 10) {
    h += `<line x1="${L}" y1="${y(v)}" x2="${L + plotW}" y2="${y(v)}" stroke="${p.grid}" stroke-width="1"/>`;
    h += `<text x="${L - 7}" y="${y(v) + 3.5}" font-family="${MONO}" font-size="10" text-anchor="end" fill="var(--ink-3)" style="font-variant-numeric:tabular-nums">${v}</text>`;
  }
  h += `<text x="${L}" y="${T - 10}" font-family="${MONO}" font-size="9" letter-spacing="0.7" fill="var(--ink-3)">KILOMETER</text>`;

  wochen.forEach((w, i) => {
    const c = L + band * i + band / 2;
    // 2-px-Spalt zwischen den Säulen, kein Rahmen
    if (w.soll_km) h += bar(c - bw - 1, y(w.soll_km), bw, T + plotH, p.planGhost);
    h += bar(c + 1, y(w.km), bw, T + plotH, p.planActual);
    if (i === wochen.length - 1) {
      h += `<text x="${c + 1 + bw}" y="${y(w.km) - 7}" font-family="${MONO}" font-size="10.5" font-weight="600" text-anchor="end" fill="var(--ink)">${Math.round(w.km)}</text>`;
    }
    if (i % 2 === 0 || i === wochen.length - 1) {
      h += `<text x="${c}" y="${H - 12}" font-family="${MONO}" font-size="9.5" text-anchor="middle" fill="var(--ink-3)">${esc(fmt.date(w.start))}</text>`;
    }
  });
  h += `<line x1="${L}" y1="${T + plotH}" x2="${L + plotW}" y2="${T + plotH}" stroke="${p.baseline}" stroke-width="1"/>`;

  return {
    svg: `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wochenumfang Soll gegen Ist über ${wochen.length} Wochen.">${h}</svg>`,
    minWidth: 420,
    legend: [
      { color: p.planGhost, label: "Soll", block: true },
      { color: p.planActual, label: "Ist", block: true },
    ],
    table: table(
      ["Woche ab", "Soll", "Ist", "Last"],
      wochen.slice().reverse().map((w) => [
        fmt.date(w.start),
        w.soll_km ? fmt.n(w.soll_km, 0) : "—",
        fmt.n(w.km),
        String(w.last),
      ])
    ),
  };
}

/* ── Zeit in den Herzfrequenzzonen ─────────────────────────────────────── */

export function zonesChart(wochen, p) {
  const mit = (wochen || []).filter((w) => (w.zonen || []).some((z) => z > 0));
  if (!mit.length) {
    return leer(
      "Keine Zonenzeiten vorhanden. intervals.icu liefert sie nur für Läufe mit Herzfrequenz."
    );
  }

  const W = 520, H = 248, L = 36, R = 10, T = 26, B = 34;
  const plotW = W - L - R, plotH = H - T - B;
  const totals = mit.map((w) => w.zonen.reduce((a, b) => a + b, 0));
  const maxY = Math.max(60, Math.ceil(Math.max(...totals) / 60) * 60);
  const band = plotW / mit.length;
  const bw = Math.min(20, band - 9);
  const y = (v) => T + plotH - (v / maxY) * plotH;

  let h = "";
  for (let v = 0; v <= maxY; v += 60) {
    h += `<line x1="${L}" y1="${y(v)}" x2="${L + plotW}" y2="${y(v)}" stroke="${p.grid}" stroke-width="1"/>`;
    h += `<text x="${L - 7}" y="${y(v) + 3.5}" font-family="${MONO}" font-size="10" text-anchor="end" fill="var(--ink-3)" style="font-variant-numeric:tabular-nums">${v / 60} h</text>`;
  }

  mit.forEach((w, i) => {
    const x0 = L + band * i + (band - bw) / 2;
    let acc = 0;
    w.zonen.forEach((v, z) => {
      if (v <= 0) return;
      const yTop = y(acc + v), yBase = y(acc);
      const oben = w.zonen.slice(z + 1).every((q) => q <= 0);
      // 2-px-Spalt zwischen den Segmenten — die Fläche trennt, nicht ein Rahmen
      const hh = Math.max(yBase - yTop - 2, 0.8);
      h += oben
        ? bar(x0, yTop, bw, yTop + hh, p.zones[z])
        : `<rect x="${x0}" y="${yTop.toFixed(1)}" width="${bw}" height="${hh.toFixed(1)}" fill="${p.zones[z]}"/>`;
      acc += v;
    });
    if (i % 2 === 0 || i === mit.length - 1) {
      h += `<text x="${x0 + bw / 2}" y="${H - 12}" font-family="${MONO}" font-size="9.5" text-anchor="middle" fill="var(--ink-3)">${esc(fmt.date(w.start))}</text>`;
    }
  });
  h += `<line x1="${L}" y1="${T + plotH}" x2="${L + plotW}" y2="${T + plotH}" stroke="${p.baseline}" stroke-width="1"/>`;

  return {
    svg: `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Zeit in den Herzfrequenzzonen je Woche.">${h}</svg>`,
    minWidth: 420,
    legend: p.zones.map((c, i) => ({ color: c, label: `Z${i + 1}`, block: true })),
    table: table(
      ["Woche ab", "Z1", "Z2", "Z3", "Z4", "Z5", "Σ min"],
      mit.slice().reverse().map((w) => [
        fmt.date(w.start),
        ...w.zonen.map(String),
        String(w.zonen.reduce((a, b) => a + b, 0)),
      ])
    ),
  };
}

/* ── VO2max-Verlauf ────────────────────────────────────────────────────── */

export function vo2Chart(verlauf, p) {
  if (!verlauf?.length) {
    return leer(
      "Keine VO2max-Werte. Dafür braucht es die maximale Herzfrequenz in den " +
        "Optionen und gleichmäßige Läufe ab 2 km."
    );
  }

  const W = 1000, L = 52, R = 56, T = 28, B = 34, H = 240;
  const plotW = W - L - R, plotH = H - T - B;
  const vals = verlauf.map((x) => x.vo2max);
  const lo = Math.floor((Math.min(...vals) - 1) / 2) * 2;
  const hi = Math.ceil((Math.max(...vals) + 1) / 2) * 2;
  const y = (v) => T + plotH - ((v - lo) / (hi - lo || 1)) * plotH;
  const x = (i) =>
    L + (verlauf.length === 1 ? plotW / 2 : (i / (verlauf.length - 1)) * plotW);

  let h = "";
  for (let v = lo; v <= hi; v += 2) {
    h += `<line x1="${L}" y1="${y(v)}" x2="${L + plotW}" y2="${y(v)}" stroke="${p.grid}" stroke-width="1"/>`;
    h += `<text x="${L - 9}" y="${y(v) + 3.5}" font-family="${MONO}" font-size="10.5" text-anchor="end" fill="var(--ink-3)" style="font-variant-numeric:tabular-nums">${v}</text>`;
  }
  h += `<text x="${L}" y="${T - 11}" font-family="${MONO}" font-size="9.5" letter-spacing="0.8" fill="var(--ink-3)">ML/KG/MIN</text>`;

  const pts = verlauf.map((r, i) => [x(i), y(r.vo2max)]);
  h += `<path d="${path(pts)}" fill="none" stroke="${p.fitness}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;

  // Nur Bestwert und Endpunkt werden beschriftet — eine Zahl an jedem Punkt
  // liest niemand.
  const besterI = vals.indexOf(Math.max(...vals));
  pts.forEach((q, i) => {
    const betont = i === pts.length - 1 || i === besterI;
    h += `<circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="${betont ? 4.5 : 2.6}" fill="${p.fitness}" stroke="var(--surface)" stroke-width="${betont ? 2 : 1}"/>`;
  });
  const last = pts[pts.length - 1];
  h += `<text x="${last[0] + 10}" y="${last[1] + 4}" font-family="${MONO}" font-size="12" font-weight="600" fill="var(--ink)">${fmt.n(vals[vals.length - 1])}</text>`;
  if (besterI !== vals.length - 1) {
    h += `<text x="${pts[besterI][0]}" y="${pts[besterI][1] - 11}" font-family="${MONO}" font-size="10.5" text-anchor="middle" fill="var(--ink-3)">${fmt.n(vals[besterI])}</text>`;
  }

  const schritt = Math.max(1, Math.round(verlauf.length / 6));
  const letzter = verlauf.length - 1;
  verlauf.forEach((r, i) => {
    // Der letzte Tick wird immer gesetzt; ein gestufter zu dicht davor
    // würde mit ihm überlappen ("5. Ok11. Okt").
    const zuNah = letzter - i < schritt * 0.75;
    if ((i % schritt === 0 && !zuNah) || i === letzter) {
      h += `<text x="${x(i)}" y="${H - 12}" font-family="${MONO}" font-size="10.5" text-anchor="middle" fill="var(--ink-3)">${esc(fmt.date(r.day))}</text>`;
    }
  });
  h += `<line x1="${L}" y1="${T + plotH}" x2="${L + plotW}" y2="${T + plotH}" stroke="${p.baseline}" stroke-width="1"/>`;

  return {
    svg: `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="VO2max-Verlauf über ${verlauf.length} Läufe, zuletzt ${fmt.n(vals[vals.length - 1])} ml/kg/min.">${h}</svg>`,
    minWidth: 700,
    table: table(
      ["Tag", "VO2max"],
      verlauf.slice().reverse().map((r) => [fmt.day(r.day), fmt.n(r.vo2max)])
    ),
  };
}


/* ── Hilfsbausteine ────────────────────────────────────────────────────── */

export function table(head, rows) {
  return (
    "<table><thead><tr>" +
    head.map((h) => `<th>${esc(h)}</th>`).join("") +
    "</tr></thead><tbody>" +
    rows
      .map((r) => "<tr>" + r.map((c) => `<td>${esc(c)}</td>`).join("") + "</tr>")
      .join("") +
    "</tbody></table>"
  );
}

function leer(text) {
  return { empty: true, svg: `<p class="hint">${esc(text)}</p>`, minWidth: 0 };
}

/** Formfenster −30…+25 mit markiertem Rennbereich. */
export function formMeter(wert, p) {
  const W = 600, H = 54, L = 2, R = 2, lo = -30, hi = 25;
  const x = (t) => L + ((t - lo) / (hi - lo)) * (W - L - R);
  const yT = 20, hT = 12;
  const v = Math.max(lo, Math.min(hi, wert ?? 0));
  const col = v >= 0 ? p.formPos : p.formNeg;

  let h = `<rect x="${L}" y="${yT}" width="${W - L - R}" height="${hT}" rx="6" fill="${p.grid}"/>`;
  [-20, -5, 5].forEach((t) => {
    h += `<line x1="${x(t)}" y1="${yT + hT}" x2="${x(t)}" y2="${yT + hT + 4}" stroke="${p.baseline}" stroke-width="1"/>`;
  });
  h += `<rect x="${x(5)}" y="${yT}" width="${x(15) - x(5)}" height="${hT}" fill="${p.status.good}" opacity="0.18"/>`;
  h += `<text x="${(x(5) + x(15)) / 2}" y="12" font-family="${MONO}" font-size="9.5" letter-spacing="0.9" text-anchor="middle" fill="var(--ink-3)">RENNWOCHE</text>`;
  h += `<rect x="${Math.min(x(0), x(v))}" y="${yT}" width="${Math.abs(x(v) - x(0))}" height="${hT}" fill="${col}"/>`;
  h += `<line x1="${x(0)}" y1="${yT - 4}" x2="${x(0)}" y2="${yT + hT + 4}" stroke="var(--ink)" stroke-width="1.5"/>`;
  h += `<circle cx="${x(v)}" cy="${yT + hT / 2}" r="6" fill="${col}" stroke="var(--surface)" stroke-width="2"/>`;
  h += `<text x="${L}" y="${yT + hT + 17}" font-family="${MONO}" font-size="10" fill="var(--ink-3)">−30</text>`;
  h += `<text x="${x(0)}" y="${yT + hT + 17}" font-family="${MONO}" font-size="10" text-anchor="middle" fill="var(--ink-3)">0</text>`;
  h += `<text x="${W - R}" y="${yT + hT + 17}" font-family="${MONO}" font-size="10" text-anchor="end" fill="var(--ink-3)">+25</text>`;

  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Formfenster von minus 30 bis plus 25, aktuell ${fmt.n(wert)}.">${h}</svg>`;
}

export function formStatus(v) {
  if (v == null) return { label: "unbekannt", tone: "neutral" };
  if (v > 12) return { label: "frisch", tone: "good" };
  if (v >= -5) return { label: "neutral", tone: "neutral" };
  if (v >= -20) return { label: "produktiver Aufbau", tone: "neutral" };
  return { label: "überlastet", tone: "critical" };
}
