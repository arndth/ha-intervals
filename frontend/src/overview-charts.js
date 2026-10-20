import {esc, fmt} from './charts.js';

const N = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
const xy = (points) => points.map(([x,y],i)=>`${i?'L':'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
const wrap = (body, label, w=680, h=230) => `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">${body}</svg>`;

export function weekProgress(o, data, p) {
  const W=680,H=240,L=40,R=28,T=23,B=33;
  const dates=Array.from({length:7},(_,i)=>{
    const d=new Date(`${o.weekStart}T00:00:00Z`);d.setUTCDate(d.getUTCDate()+i);return d.toISOString().slice(0,10);
  });
  const cumulative=(items,field,dateKey)=>{
    let sum=0;return [[L,T+0],...dates.map((day,i)=>{
      sum+=items.filter(x=>x[dateKey]===day).reduce((a,x)=>a+N(x[field]),0);
      return [L+(W-L-R)*i/6,sum];
    })];
  };
  const actual=(data.trainings||[]).filter(x=>x.day>=o.weekStart&&x.day<=o.today);
  const planned=cumulative(o.currentPlan,'km','tag'), completed=cumulative(actual,'km','day');
  const max=Math.max(5,Math.ceil(Math.max(o.planKm,o.current.km)/5)*5);
  const y=(v)=>T+(H-T-B)*(1-v/max);
  const x=(i)=>L+(W-L-R)*i/6;
  const planPath=xy(planned.slice(1).map(([x,v])=>[x,y(v)]));
  const end=dates.filter(d=>d<=o.today).length-1;
  const actualPts=completed.slice(1,Math.max(0,end)+2).map(([x,v])=>[x,y(v)]);
  let h='';
  for(let i=0;i<=4;i++) {const v=max*i/4;h+=`<line x1="${L}" y1="${y(v)}" x2="${W-R}" y2="${y(v)}" stroke="${p.grid}"/><text x="${L-8}" y="${y(v)+4}" text-anchor="end" fill="var(--ink-3)" font-size="10">${fmt.n(v,0)}</text>`;}
  h+=`<path d="${planPath}" fill="none" stroke="${p.planGhost}" stroke-width="3" stroke-dasharray="6 5"/>`;
  if(actualPts.length){const path=xy(actualPts),last=actualPts[actualPts.length-1];h+=`<path d="${path} L${last[0]} ${y(0)} L${L} ${y(0)} Z" fill="${p.planActual}" opacity=".11"/><path d="${path}" fill="none" stroke="${p.planActual}" stroke-width="3.5" stroke-linejoin="round"/><circle cx="${last[0]}" cy="${last[1]}" r="5" fill="${p.planActual}" stroke="var(--surface)" stroke-width="2"/>`;}
  ['Mo','Di','Mi','Do','Fr','Sa','So'].forEach((d,i)=>h+=`<text x="${x(i)}" y="${H-9}" text-anchor="middle" fill="var(--ink-3)" font-size="11">${d}</text>`);
  return wrap(h,`Kumulierte Kilometer dieser Woche: ${fmt.n(o.current.km)} erfasst, ${fmt.n(o.planKm)} geplant.`,W,H);
}

export function weeklyBars(o,p) {
  const weeks=[...o.previous,{...o.current,start:o.weekStart,partial:true}];
  const W=680,H=184,L=20,R=18,T=18,B=37,base=H-B;
  const max=Math.max(5,...weeks.map(x=>x.km));
  const width=(W-L-R)/weeks.length;
  let h=`<line x1="${L}" y1="${base}" x2="${W-R}" y2="${base}" stroke="${p.baseline}"/>`;
  weeks.forEach((w,i)=>{
    const x=L+width*i+width*.25,bw=width*.5,height=(w.km/max)*(base-T);
    h+=`<rect x="${x}" y="${base-height}" width="${bw}" height="${height}" rx="6" fill="${i===4?p.fatigue:p.planActual}" opacity="${w.km?1:.2}"/>`;
    h+=`<text x="${x+bw/2}" y="${Math.max(13,base-height-7)}" text-anchor="middle" fill="var(--ink)" font-size="11" font-weight="600">${fmt.n(w.km,0)}</text>`;
    h+=`<text x="${x+bw/2}" y="${H-15}" text-anchor="middle" fill="var(--ink-3)" font-size="10">${i===4?'Laufend':esc(fmt.date(w.start))}</text>`;
  });
  return wrap(h,`Erfasste Wochenkilometer der letzten vier abgeschlossenen Wochen und der laufenden Teilwoche.`,W,H);
}

export function monthlyCombo(months,p) {
  const W=680,H=230,L=24,R=22,T=25,base=H-45,plot=base-T;
  const maxKm=Math.max(5,...months.map(m=>m.km)), maxRuns=Math.max(1,...months.map(m=>m.count));
  const band=(W-L-R)/months.length;
  let h=`<line x1="${L}" y1="${base}" x2="${W-R}" y2="${base}" stroke="${p.baseline}"/>`;
  const pts=[];
  months.forEach((m,i)=>{
    const x=L+band*i+band/2,bw=Math.min(35,band*.4),barH=N(m.km)/maxKm*plot;
    h+=`<rect x="${x-bw/2}" y="${base-barH}" width="${bw}" height="${barH}" rx="5" fill="${p.planActual}" opacity=".7"/>`;
    h+=`<text x="${x}" y="${H-15}" text-anchor="middle" fill="var(--ink-3)" font-size="10">${esc(m.month.slice(5))}${m.partial?'*':''}</text>`;
    pts.push([x,base-N(m.count)/maxRuns*plot]);
  });
  if(pts.length){h+=`<path d="${xy(pts)}" fill="none" stroke="${p.fatigue}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
    for(const [x,y] of pts)h+=`<circle cx="${x}" cy="${y}" r="4" fill="${p.fatigue}" stroke="var(--surface)" stroke-width="1.5"/>`;}
  h+=`<text x="${L}" y="14" fill="var(--ink-3)" font-size="10">km bis ${fmt.n(maxKm,0)} · Läufe bis ${maxRuns} (eigene Skalen)</text>`;
  return wrap(h,'Monatsdistanz als Balken und Laufanzahl als Linie mit getrennten Skalen. Details in Tabelle.',W,H);
}

export function consistency(o,data) {
  const start=new Date(`${o.since}T00:00:00Z`),end=new Date(`${o.today}T00:00:00Z`);
  const aligned=new Date(start);aligned.setUTCDate(aligned.getUTCDate()-(aligned.getUTCDay()+6)%7);
  const days=Math.round((end-aligned)/86400000)+1;
  const cols=Math.ceil(days/7),cell=14,gap=4,W=cols*(cell+gap)+10,H=7*(cell+gap)+19;
  const perDay=new Map();for(const run of data.trainings||[])perDay.set(run.day,(perDay.get(run.day)||0)+N(run.km));
  let body='';
  for(let i=0;i<days;i++){
    const date=new Date(aligned);date.setUTCDate(date.getUTCDate()+i);
    const label=date.toISOString().slice(0,10);
    const v=perDay.get(label)||0;
    const fill=label<o.since?'var(--rule)':v>=15?'#f04d3c':v>=8?'#fa8555':v>0?'#fbb78c':'var(--rule)';
    body+=`<rect x="${(Math.floor(i/7)*(cell+gap)+4)}" y="${(i%7)*(cell+gap)+5}" width="${cell}" height="${cell}" rx="3" fill="${fill}" opacity="${label < o.since ? 0.3 : 1}"><title>${label}: ${fmt.n(v)} km erfasst</title></rect>`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Erfasste Lauftage der letzten sechs Monate, Farbintensität nach Kilometerzahl">${body}</svg>`;
}
