export const OVERVIEW_CSS = `
.dash-shell { --dash-coral:#f16a49; --dash-mint:#55d6bb; --dash-ink:#112f3b; max-width:1480px; margin:0 auto; }
.dash-shell .dash-kicker { color:var(--dash-coral); font:700 10px/1.4 var(--mono); letter-spacing:.15em; text-transform:uppercase; }
.dash-intro { display:flex; align-items:center; justify-content:space-between; margin:6px 0 24px; }
.dash-intro h2 { font-size:clamp(28px,4vw,45px); font-weight:730; letter-spacing:-.055em; line-height:1.08; margin:6px 0 7px; }
.dash-intro p { color:var(--ink-2); margin:0; font-size:14px; }
.dash-mark { display:grid; place-items:center; width:55px; height:55px; border-radius:18px; background:color-mix(in srgb,var(--accent) 12%,var(--surface)); color:var(--accent); font-size:31px; }
.dash-lead { display:grid; grid-template-columns:minmax(0,1.65fr) minmax(275px,.8fr); gap:16px; margin-bottom:32px; }
.dash-route { position:relative; isolation:isolate; min-height:478px; border-radius:22px; overflow:hidden; background:radial-gradient(ellipse at 70% 70%,#284a56 0,#153543 48%,#0e2834 100%); color:#f5fafb; box-shadow:0 20px 46px rgba(6,36,49,.15); }
.dash-route:after { content:''; position:absolute; inset:0; z-index:-1; background:linear-gradient(115deg,rgba(7,28,37,.78),transparent 64%); pointer-events:none; }
.dash-route-info { position:relative; z-index:2; padding:27px 28px 14px; }
.dash-route-info h2 { font-size:clamp(24px,3vw,36px); letter-spacing:-.04em; margin:7px 0 12px; color:#fff; }
.dash-run-metrics { display:flex; gap:16px 27px; flex-wrap:wrap; align-items:baseline; color:#f8fafa; font:600 15px var(--mono); }
.dash-run-metrics strong { font:700 clamp(27px,3vw,36px)/1 var(--sans); color:#fff; letter-spacing:-.04em; }
.dash-run-metrics small { display:block; margin-top:4px; color:#bdd3d9; font:10px var(--mono); }
.dash-link { border:0; background:transparent; padding:8px 0; margin-top:6px; color:var(--dash-coral); font:650 12px var(--sans); cursor:pointer; text-align:left; }
.dash-route .dash-link { color:#ffb48f; }
.dash-link:hover, .dash-map-options button:hover, .dash-done:hover { text-decoration:underline; }
.dash-map-canvas { position:absolute; inset:163px -10px 37px; z-index:0; }
.dash-map-canvas svg { width:100%; height:100%; color:#c9f2ee; display:block; }
.dash-map-empty { position:absolute; inset:210px 20px 55px; display:grid; place-items:center; border:1px dashed rgba(255,255,255,.18); border-radius:15px; color:#b9d2d5; text-align:center; font-size:13px; padding:24px; }
.dash-map-options { position:absolute; z-index:3; bottom:0; inset-inline:0; min-height:40px; display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 16px; background:rgba(7,23,30,.83); color:#c8d7d8; font-size:10px; }
.dash-map-options a { color:#d6eded; text-decoration:underline; }
.dash-map-options button { background:none; border:0; color:#ffd4bd; font:600 11px var(--sans); cursor:pointer; white-space:nowrap; }
.dash-stack { display:grid; grid-template-rows:1fr auto; gap:16px; }
.dash-shell .dash-panel { border:1px solid var(--rule); border-radius:20px; background:var(--surface); padding:21px 23px; min-width:0; box-shadow:0 9px 23px rgba(8,32,49,.035); }
.dash-shell .dash-panel h3 { font-size:17px; font-weight:670; margin:3px 0 7px; letter-spacing:-.025em; }
.dash-week-snapshot { background:linear-gradient(150deg,color-mix(in srgb,var(--accent) 8%,var(--surface)),var(--surface) 65%)!important; }
.dash-snapshot-value { font:730 clamp(44px,5vw,68px)/1 var(--sans); letter-spacing:-.06em; margin:26px 0 12px; color:var(--ink); }
.dash-snapshot-value span { font:500 13px var(--sans); letter-spacing:0; color:var(--ink-2); margin-left:7px; }
.dash-progress { height:8px; border-radius:10px; background:color-mix(in srgb,var(--accent) 12%,var(--surface)); overflow:hidden; }
.dash-progress span { display:block; height:100%; background:linear-gradient(90deg,#fbb274,var(--dash-coral)); border-radius:10px; }
.dash-week-snapshot p, .dash-next p { color:var(--ink-2); font-size:13px; margin:9px 0; }
.dash-snapshot-sub { display:flex; gap:8px; flex-wrap:wrap; margin:25px 0 8px; }
.dash-snapshot-sub span { padding:6px 9px; background:var(--plane); border-radius:8px; font:600 11px var(--mono); }
.dash-week-snapshot small { color:var(--ink-3); font-size:11px; }
.dash-next { min-height:142px; }
.dash-next h3 { margin-top:9px!important; }
.dash-section-head { display:flex; align-items:end; justify-content:space-between; flex-wrap:wrap; gap:8px; margin:30px 0 14px; }
.dash-section-head h2 { font-size:clamp(21px,2.3vw,28px); letter-spacing:-.035em; margin:2px 0 0; }
.dash-badge { display:inline-flex; border:1px solid color-mix(in srgb,var(--accent) 25%,var(--rule)); border-radius:30px; padding:5px 11px; color:var(--ink-2); background:var(--surface); font:600 11px var(--mono); }
.dash-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.dash-shell .dash-caption { font-size:12px; line-height:1.5; color:var(--ink-2); margin:0 0 10px; }
.dash-chart { overflow:auto; }
.dash-chart svg { width:100%; min-width:320px; height:auto; display:block; }
.dash-legend { display:flex; gap:18px; flex-wrap:wrap; font-size:11px; color:var(--ink-2); margin:0 0 8px; }
.dash-legend span { display:flex; gap:6px; align-items:center; }
.dash-legend i { width:13px; height:4px; border-radius:3px; }
.dash-note { border-top:1px solid var(--rule); padding-top:12px; font-size:11px; color:var(--ink-3); margin:16px 0 0; }
.dash-days { margin-top:12px; border-top:1px solid var(--rule); }
.dash-day { display:grid; grid-template-columns:67px 1fr; gap:8px; align-items:start; border-bottom:1px solid var(--rule); padding:9px 7px; }
.dash-day.is-today { background:color-mix(in srgb,var(--accent) 7%,var(--surface)); border-radius:8px; }
.dash-day-name { font:700 11px var(--mono); }
.dash-day-name small { display:block; color:var(--ink-3); font:10px var(--mono); }
.dash-day-body { display:grid; gap:3px; font-size:12px; }
.dash-muted { color:var(--ink-3); font-size:12px; }
.dash-done { background:none; border:0; color:var(--accent); font:600 11px var(--sans); cursor:pointer; text-align:left; padding:0; }
.dash-shell .tablewrap { max-height:295px; overflow:auto; border-top:1px solid var(--rule); margin-top:11px; }
.dash-shell .tablewrap table { font-size:11px; }
.dash-heat { overflow:auto; margin:12px 0 5px; }
.dash-heat svg { width:100%; min-width:400px; height:auto; display:block; }
.dash-heat-legend { display:flex; gap:5px; align-items:center; color:var(--ink-3); font:10px var(--mono); }
.dash-heat-legend i { width:12px; height:12px; border-radius:3px; background:#fbb78c; }
.dash-heat-legend i:nth-of-type(2) { background:#fa8555; }
.dash-heat-legend i:nth-of-type(3) { background:#f04d3c; }
.dash-mini { border-top:1px solid var(--rule); margin-top:23px; padding-top:18px; }
.dash-mini .dash-chart svg { max-height:235px; }
@media(max-width:1000px){.dash-lead { grid-template-columns:1fr; }.dash-stack { grid-template-columns:1fr 1fr; grid-template-rows:auto; }}
@media(max-width:720px){.dash-grid,.dash-stack { grid-template-columns:1fr; }.dash-route { min-height:450px; }.dash-route-info { padding:21px; }.dash-map-canvas { inset:170px -80px 38px; }.dash-run-metrics { gap:10px 18px; }.dash-snapshot-value { margin:15px 0; }.dash-shell .dash-panel { padding:18px; }}
@media(max-width:420px){.dash-route { min-height:490px; }.dash-map-canvas { inset:215px -100px 40px; }.dash-map-options { font-size:9px; }.dash-intro .dash-mark { display:none; }}
`;
