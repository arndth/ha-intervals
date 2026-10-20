/* Read-only view model for the running dashboard. Dates are local calendar
 * labels from Home Assistant; UTC arithmetic avoids timezone/DST shifts. */
const DAY = 86400000;
const asDate = (iso) => new Date(`${iso}T00:00:00Z`);
const iso = (d) => d.toISOString().slice(0, 10);
const addDays = (day, n) => iso(new Date(asDate(day).getTime() + n * DAY));
const monday = (day) => addDays(day, -(asDate(day).getUTCDay() + 6) % 7);
const sum = (xs, field) => xs.reduce((total, x) => total + (Number(x[field]) || 0), 0);

export function sixMonthsAgo(today) {
  const date = asDate(today);
  const day = date.getUTCDate();
  date.setUTCDate(1);
  date.setUTCMonth(date.getUTCMonth() - 6);
  const month = date.getUTCMonth();
  date.setUTCMonth(month + 1);
  date.setUTCDate(0);
  date.setUTCDate(Math.min(day, date.getUTCDate()));
  return iso(date);
}

function aggregate(runs, start, end) {
  const found = runs.filter((r) => r.day >= start && r.day <= end);
  return {
    start, end, count: found.length, km: sum(found, "km"),
    seconds: sum(found, "seconds"), load: sum(found, "load"),
    longest: found.length ? Math.max(...found.map((r) => Number(r.km) || 0)) : 0,
  };
}

export function overviewModel(data) {
  const today = data.stand;
  if (!/^\d{4}-\d\d-\d\d$/.test(today || "")) throw new Error("Standdatum fehlt");
  const runs = (data.trainings || []).filter((r) => r.day && r.day <= today)
    .slice().sort((a, b) => b.day.localeCompare(a.day));
  const planned = (data.plan || []).filter((p) => p.tag && p.art !== "ruhe")
    .slice().sort((a, b) => a.tag.localeCompare(b.tag));
  const start = monday(today), end = addDays(start, 6);
  const current = aggregate(runs, start, today);
  const currentPlan = planned.filter((p) => p.tag >= start && p.tag <= end);
  const planKm = sum(currentPlan, "km");
  const previous = Array.from({length: 4}, (_, i) => {
    const weekStart = addDays(start, -7 * (4 - i));
    return aggregate(runs, weekStart, addDays(weekStart, 6));
  });
  const since = sixMonthsAgo(today);
  const recent = aggregate(runs, since, today);
  const months = [];
  let cursor = since.slice(0, 7) + "-01";
  while (cursor <= today) {
    const next = asDate(cursor);
    next.setUTCMonth(next.getUTCMonth() + 1);
    const nextStart = iso(next);
    const from = cursor < since ? since : cursor;
    const to = addDays(nextStart, -1) > today ? today : addDays(nextStart, -1);
    months.push({...aggregate(runs, from, to), month: cursor.slice(0, 7), partial: from !== cursor || to !== addDays(nextStart, -1)});
    cursor = nextStart;
  }
  const next = planned.find((p) => p.tag > today) || planned.find((p) => p.tag === today) || null;
  return {
    today, weekStart: start, weekEnd: end, current, currentPlan,
    planKm, planCount: currentPlan.length, last: runs[0] || null, next,
    previous, fourWeeks: {
      count: sum(previous, "count"), km: sum(previous, "km"),
      seconds: sum(previous, "seconds"), load: sum(previous, "load"),
    },
    sixMonths: recent, months, since,
    // The API may omit restricted sources. Zero is only "no recorded runs".
    limitedHistory: (data.history_days ?? 0) < Math.ceil((asDate(today) - asDate(since)) / DAY),
  };
}
