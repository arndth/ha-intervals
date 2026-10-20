import { overviewModel } from './overview.js';
import { esc, fmt, table, vo2Chart } from './charts.js';
import { routeGraphic } from './route-map.js';
import { weekProgress, weeklyBars, monthlyCombo, consistency } from './overview-charts.js';

/** Read-only dashboard. Caller wires data-detail, data-tab and data-streets. */
export function renderOverview(data, tile, {route=null, streets=false, palette}={}) {
  const o=overviewModel(data), p=palette || {planActual:'#2a78d6',planGhost:'#86b6ef',fatigue:'#eb6834',grid:'#dde1e5',baseline:'#aeb7bf'};
  const km=(v)=>`${fmt.n(v)} km`, date=(s)=>esc(fmt.day(s));
  const gps=route?.id===String(o.last?.id) ? route : null;
  const map=gps?.points?.length>=2 ? routeGraphic(gps.points,streets) : '';
  const last=o.last ? `<span class="dash-kicker">Letzter Lauf · ${date(o.last.day)}</span>
       <h2>${esc(o.last.name||'Lauf')}</h2>
       <div class="dash-run-metrics"><strong>${esc(km(o.last.km))}</strong><span>${esc(fmt.hms(o.last.seconds))}<small>Bewegungszeit</small></span><span>${esc(fmt.pace(o.last.pace_s_km))} /km<small>Ø Pace</small></span><span>${esc(o.last.hr_avg??'—')} bpm<small>Ø Herzfrequenz</small></span></div>
       <button class="dash-link" data-detail="${esc(o.last.id)}">Splits & Laufdetails →</button>`
    : `<span class="dash-kicker">Letzter Lauf</span><h2>Noch kein Lauf erfasst</h2><p>Im geladenen Zeitraum stehen keine Laufaktivitäten.</p>`;
  const mapState=map ? `<div class="dash-map-canvas">${map}</div>` :
    `<div class="dash-map-empty">${gps?.loading?'GPS-Strecke wird geladen …':esc(gps?.error||'Keine GPS-Strecke verfügbar · die Laufdaten bleiben sichtbar.')}</div>`;
  const mapControl=map ? `<div class="dash-map-options">${streets ? `<span>Straßenkarte: © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap-Mitwirkende</a></span>` : `<span>Private GPS-Skizze · keine Kartenanfrage an Dritte</span>`}
    <button data-streets="${streets?'off':'on'}">${streets?'Straßenkarte ausblenden':'Straßenkarte laden'}</button></div>` : '';
  const next=o.next ? `<span class="dash-kicker">${o.next.tag===o.today?'Heute geplant · Status prüfen':'Nächste Einheit'}</span>
      <h3>${esc(o.next.name||'Lauf')}</h3><p><b>${date(o.next.tag)}</b> · ${o.next.km?esc(km(o.next.km)):'Distanz offen'}</p>
      <button class="dash-link" data-tab="plan">Gesamten Plan ansehen →</button>` :
      `<span class="dash-kicker">Nächste Einheit</span><h3>Keine geplant</h3><p>Kein künftiger Lauf im geladenen Plan.</p>`;
  const weekPercent=o.planKm>0?Math.round(o.current.km/o.planKm*100):null;
  const weekBadge=weekPercent!=null?`<span class="dash-badge">${weekPercent}% des Wochenumfangs erfasst</span>`:'';
  const days=['Mo','Di','Mi','Do','Fr','Sa','So'].map((label,i)=>{
    const at=new Date(`${o.weekStart}T00:00:00Z`);at.setUTCDate(at.getUTCDate()+i);
    const day=at.toISOString().slice(0,10),plan=o.currentPlan.filter(x=>x.tag===day),done=(data.trainings||[]).filter(x=>x.day===day);
    return `<div class="dash-day ${day===o.today?'is-today':''}"><span class="dash-day-name">${label}<small>${date(day)}</small></span><span class="dash-day-body">${plan.length?plan.map(x=>`<span>${esc(x.name||'Lauf')}${x.km?` · ${esc(km(x.km))}`:''}</span>`).join(''):'<span class="dash-muted">Kein Lauf geplant</span>'}
      ${done.map(x=>`<button class="dash-done" data-detail="${esc(x.id)}">● Erfasst: ${esc(km(x.km))} · ${esc(fmt.pace(x.pace_s_km))}/km</button>`).join('')}</span></div>`;
  }).join('');
  const weeks=o.previous.map(w=>[`${fmt.day(w.start)}–${fmt.day(w.end)}`,String(w.count),fmt.n(w.km),fmt.hms(w.seconds),String(w.load),fmt.n(w.longest)]);
  const months=o.months.map(m=>[`${m.month}${m.partial?' *':''}`,String(m.count),fmt.n(m.km),fmt.hms(m.seconds),String(m.load)]);
  const vo2=(data.vo2max?.verlauf||[]).filter(v=>v.day>=o.since&&v.day<=o.today);
  const vo2graph=vo2Chart(vo2,p);
  const fourSummary=`${o.fourWeeks.count} Läufe · ${km(o.fourWeeks.km)} · ${fmt.hms(o.fourWeeks.seconds)} Bewegungszeit`;
  return `<div class="dash-shell">
    <div class="dash-intro"><div><span class="dash-kicker">DEIN LAUF-COCKPIT · ${date(o.today)}</span><h2>Der Überblick.</h2><p>Training, Strecke und Entwicklung — ohne Leistungswerte zu erfinden.</p></div><span class="dash-mark" aria-hidden="true">↗</span></div>
    <div class="dash-lead">
      <section class="dash-route" aria-label="Letztes Training und GPS-Strecke"><div class="dash-route-info">${last}</div>${mapState}${mapControl}</section>
      <aside class="dash-stack">
        <section class="dash-panel dash-week-snapshot"><span class="dash-kicker">DIESE WOCHE · ${date(o.weekStart)}–${date(o.weekEnd)}</span>
          <div class="dash-snapshot-value">${esc(fmt.n(o.current.km))}<span>km erfasst</span></div>
          <div class="dash-progress"><span style="width:${Math.min(100,Math.max(0,weekPercent||0))}%"></span></div>
          <p>${o.planCount?`${o.planCount} Läufe · ${esc(km(o.planKm))} geplant`:'Kein Wochenplan geladen'}${weekPercent!=null?` · ${weekPercent}% erfasst`:''}</p>
          <div class="dash-snapshot-sub"><span>${o.current.count} Läufe</span><span>${esc(fmt.hms(o.current.seconds))} bewegt</span><span>Last ${o.current.load}</span></div>
          <small>Umfang ist keine Aussage über Erholung oder Planerfüllung.</small>
        </section>
        <section class="dash-panel dash-next">${next}</section>
      </aside>
    </div>
    <div class="dash-section-head"><div><span class="dash-kicker">01 / AKTUELLE WOCHE</span><h2>Rhythmus & Fortschritt</h2></div>${weekBadge}</div>
    <div class="dash-grid"><section class="dash-panel"><h3>Wochenfortschritt</h3><p class="dash-caption">Kumulierte Kilometer · durchgezogen erfasst, gestrichelt geplant. Die Woche läuft noch.</p>
      <div class="dash-chart">${weekProgress(o,data,p)}</div><div class="dash-legend"><span><i style="background:${p.planActual}"></i> Erfasst</span><span><i style="background:${p.planGhost}"></i> Plan</span></div>
      <p class="dash-note">${o.current.count?`${o.current.count} Läufe · längster ${esc(km(o.current.longest))} · Last ${o.current.load}`:'Noch kein Lauf in dieser Woche erfasst.'}</p></section>
      <section class="dash-panel"><h3>Wochenkalender</h3><p class="dash-caption">Geplant und aufgezeichnet bleiben getrennt.</p><div class="dash-days">${days}</div></section></div>
    <div class="dash-section-head"><div><span class="dash-kicker">02 / VERLAUF</span><h2>Vier abgeschlossene Wochen</h2></div></div>
    <section class="dash-panel"><div class="dash-panel-head"><p class="dash-caption">${esc(fourSummary)}. Orange: laufende, unvollständige Woche. Keine Einträge ≠ Trainingspause.</p></div>
      <div class="dash-chart">${weeklyBars(o,p)}</div><div class="tablewrap">${table(['Woche','Läufe','km','Zeit','Last','Längster km'],weeks)}</div></section>
    <div class="dash-section-head"><div><span class="dash-kicker">03 / LANGZEIT</span><h2>Sechs Monate im Blick</h2></div><span class="dash-badge">${date(o.since)}–${date(o.today)}</span></div>
    <div class="dash-grid"><section class="dash-panel"><h3>Distanz & Häufigkeit</h3><p class="dash-caption">${o.sixMonths.count} erfasste Läufe · ${esc(km(o.sixMonths.km))}. Balken = km, Linie = Läufe; getrennte Skalen.</p>
      <div class="dash-chart">${monthlyCombo(o.months,p)}</div><div class="dash-legend"><span><i style="background:${p.planActual}"></i> km</span><span><i style="background:${p.fatigue}"></i> Läufe</span></div>
      <div class="tablewrap">${table(['Monat','Läufe','km','Zeit','Last'],months)}</div><p class="dash-caption">* Randmonate sind Teilmonate.</p></section>
      <section class="dash-panel"><h3>Konstanz</h3><p class="dash-caption">Jedes Feld ein Kalendertag; dunkler = mehr erfasste Laufkilometer.</p><div class="dash-heat">${consistency(o,data)}</div>
      <div class="dash-heat-legend"><span>Kein Eintrag</span><i></i><i></i><i></i><span>≥ 15 km</span></div>
      <p class="dash-note">${o.limitedHistory?'Der Datenabruf deckt den Zeitraum nicht vollständig ab.':'Nur lokal verfügbare Aktivitäten; andere Quellen können fehlen.'} Kein Eintrag ist kein belegter Ruhetag.</p>
      <div class="dash-mini"><h3>VO₂max-Schätzung</h3><p class="dash-caption">Persönliche Aktivitätsschätzungen, keine Labormessung · ${vo2.length} Läufe mit Wert.</p>
      ${vo2.length?`<div class="dash-chart">${vo2graph.svg}</div>`:'<p class="dash-muted">Keine belastbare Schätzung vorhanden.</p>'}</div></section></div>
  </div>`;
}
