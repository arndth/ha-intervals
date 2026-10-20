/* GPS sketch with optional, user-initiated OSM tiles. No CDN libraries. */
const W = 900, H = 390, PAD = 46;
const clamp = (v, low, high) => Math.max(low, Math.min(high, v));
const world = ([lat, lon]) => {
  const rad = clamp(lat, -85, 85) * Math.PI / 180;
  return [(lon + 180) / 360 * 256,
    (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * 256];
};

export function routeGraphic(points, streets = false) {
  const valid = (points || []).filter((p) => Array.isArray(p) && p.length === 2 &&
    p.every(Number.isFinite) && Math.abs(p[0]) <= 85 && Math.abs(p[1]) <= 180);
  if (valid.length < 2) return '';
  const base = valid.map(world);
  const xs = base.map((x) => x[0]), ys = base.map((x) => x[1]);
  const dx = Math.max(...xs) - Math.min(...xs), dy = Math.max(...ys) - Math.min(...ys);
  const factor = Math.min((W - 2 * PAD) / Math.max(dx, 0.001),
    (H - 2 * PAD) / Math.max(dy, 0.001));
  const zoom = clamp(Math.floor(Math.log2(factor)), 2, 15);
  const scale = 2 ** zoom;
  const cx = (Math.min(...xs) + Math.max(...xs)) * scale / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) * scale / 2;
  const sx = (x) => x * scale - cx + W / 2;
  const sy = (y) => y * scale - cy + H / 2;
  const pts = base.map(([x, y]) => [sx(x), sy(y)]);
  const path = pts.map(([x,y],i) => `${i?'L':'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const grid = Array.from({length: 14},(_,i) => `<path d="M${i*82-90} 0 L${i*82+80} ${H}" stroke="currentColor" opacity=".08" stroke-width="1"/>`).join('');
  let tiles = '';
  if (streets) {
    const left = Math.floor((cx-W/2)/256), right = Math.floor((cx+W/2)/256);
    const top = Math.floor((cy-H/2)/256), bottom = Math.floor((cy+H/2)/256);
    for (let y=top; y<=bottom; y++) for(let x=left; x<=right; x++) {
      if (x < 0 || y < 0 || x >= 2**zoom || y >= 2**zoom) continue;
      tiles += `<image href="https://tile.openstreetmap.org/${zoom}/${x}/${y}.png" x="${(x*256-cx+W/2).toFixed(1)}" y="${(y*256-cy+H/2).toFixed(1)}" width="256" height="256"/>`;
    }
  }
  const [startX,startY]=pts[0], [endX,endY]=pts[pts.length-1];
  return `<svg class="route-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="GPS-Streckenverlauf von Start bis Ziel" preserveAspectRatio="xMidYMid meet">
    <defs><linearGradient id="route-line" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ff9557"/><stop offset="1" stop-color="#f04d3c"/></linearGradient></defs>
    <rect width="${W}" height="${H}" fill="${streets?'#ecefe8':'transparent'}"/>
    ${streets?tiles:grid}
    <path d="${path}" fill="none" stroke="${streets?'#21313c':'#162e38'}" stroke-width="11" opacity=".7" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="${path}" fill="none" stroke="url(#route-line)" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${startX.toFixed(1)}" cy="${startY.toFixed(1)}" r="10" fill="#55d6bb" stroke="#193238" stroke-width="4"/>
    <circle cx="${endX.toFixed(1)}" cy="${endY.toFixed(1)}" r="10" fill="#f35e4e" stroke="#193238" stroke-width="4"/>
  </svg>`;
}
