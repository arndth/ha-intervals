import test from 'node:test';
import assert from 'node:assert/strict';
import { overviewModel, sixMonthsAgo } from '../src/overview.js';
import { renderOverview } from '../src/overview-view.js';

const sample = {
  stand: '2026-10-20', history_days: 200,
  trainings: [
    {id: 'today', day: '2026-10-20', name: 'Locker', km: 8.44, seconds: 2679, load: 52, pace_s_km: 317},
    {id: 'prior', day: '2026-10-18', name: 'Hatten', km: 10, seconds: 3000, load: 65},
    {id: 'edge', day: '2026-04-20', name: 'Alt', km: 5, seconds: 1500, load: 30},
    {id: 'too-old', day: '2026-04-19', name: 'Zu alt', km: 100, seconds: 1, load: 99},
  ],
  plan: [
    {event_id: 'current', tag: '2026-10-20', name: 'Locker 8.5 km', km: 8.5, art: 'locker'},
    {event_id: 'next', tag: '2026-10-22', name: 'Locker 8.5 km', km: 8.5, art: 'locker'},
    {event_id: 'sunday', tag: '2026-10-25', name: 'Dauerlauf', km: 11.5, art: 'longrun'},
  ],
};

test('rolling six months and calendar-week boundaries include DST week correctly', () => {
  assert.equal(sixMonthsAgo('2026-10-20'), '2026-04-20');
  assert.equal(sixMonthsAgo('2026-08-31'), '2026-02-28');
  const m = overviewModel(sample);
  assert.deepEqual([m.weekStart, m.weekEnd], ['2026-10-19', '2026-10-25']);
  assert.equal(m.current.km, 8.44);
  assert.equal(m.planKm, 28.5);
  assert.equal(m.last.id, 'today');
  assert.equal(m.next.event_id, 'next');
  assert.equal(m.fourWeeks.count, 1);
  assert.equal(m.sixMonths.count, 3);
  assert.ok(Math.abs(m.sixMonths.km - 23.44) < 1e-9);
  assert.equal(m.months.length, 7); // two partial edge months plus five full months
  assert.deepEqual(m.previous.map((w) => w.start), ['2026-09-21','2026-09-28','2026-10-05','2026-10-12']);
});

test('empty data produces honest zero-record summary, not fabricated training', () => {
  const m = overviewModel({stand:'2026-10-20', history_days:30, trainings:[], plan:[]});
  assert.equal(m.last, null);
  assert.equal(m.next, null);
  assert.equal(m.fourWeeks.count, 0);
  assert.equal(m.limitedHistory, true);
});

test('dashboard renders all six sections and escapes user-provided names', () => {
  const html = renderOverview({...sample, trainings:[{...sample.trainings[0], name:'<script>'}]},
    (label, value) => `<div>${label}: ${value}</div>`);
  for (const title of ['Aktuelle Woche', 'Letztes Training', 'Nächstes Training',
    'Zusammenfassung dieser Woche', 'Letzte 4 abgeschlossene Wochen', 'Letzte 6 Monate']) {
    assert.ok(html.includes(title), title);
  }
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('data-detail="today"'));
  assert.ok(html.includes('data-tab="plan"'));
});
