/* CryNet dashboard — the hosted copy, as a Cloudflare Worker.
 *
 * This is a port of dashboard/server.py, which stays the offline copy a
 * caregiver can run with `python dashboard/server.py` and nothing else.
 * The two must agree field for field: the hub uploads the body that
 * firmware/tools/test_dashboard_contract.py builds, and the page in web/
 * renders whatever /api/v1 returns.  Where this copy differs from the
 * Python one it says why in a comment.
 *
 * The differences that matter:
 *   - Authentication covers every GET, not just the uploads.  On the
 *     public internet an open /api/v1/summary would publish the baby's
 *     whole cry record to anyone who guesses the URL.
 *   - Days, hours and nights are bucketed in the timezone the browser
 *     sends (?tz=Africa/Lagos).  This Worker runs in UTC; the caregiver
 *     does not.
 *   - The untimed-records window is split into two index-friendly halves
 *     instead of one CASE expression, so D1's 5M rows-read/day budget is
 *     spent on the window, not on the whole table.
 */

const NIGHT_START_HOUR = 20;
const NIGHT_END_HOUR = 6;
const DURATION_BUCKETS = [5, 15, 30, 60, 120, 300, 600];

/* ---------------------------------------------------------------- helpers */

/* Python's round() sends halves to the even side; Math.round sends them
   up.  The JSON the page eats should not depend on which copy served it. */
function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}
const r1 = (x) => pyRound(x * 10) / 10;
const r2 = (x) => pyRound(x * 100) / 100;

/* statistics.median(): the mean of the two middle values when even. */
function median(xs) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/* The hub's JSON values go through the same leniency as server.py's
   _int_or_none / _float_or_none: null and "" become NULL, anything that
   is not a number becomes NULL, a float that is a whole number stays a
   number (SQLite stores it fine in an INTEGER column). */
function toInt(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}
function toFloat(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function intParam(v, d) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : d;
}

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
      ...extra,
    },
  });
}

/* ------------------------------------------------------------- timezone */

const WEEKDAY = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };

/* Mirrors make_local() in server.py: the zone comes from the request,
   anything unknown falls back to UTC — which is where this runs.  The
   returned object carries exactly what the analytics need: an ISO date,
   the hour of day, and Python's weekday number (Monday = 0). */
function makeLocal(tz) {
  let dtf;
  try {
    dtf = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz || 'UTC',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', hourCycle: 'h23', weekday: 'short',
    });
  } catch (e) {
    return makeLocal('');
  }
  return (ts) => {
    const p = {};
    for (const part of dtf.formatToParts(new Date(ts * 1000))) p[part.type] = part.value;
    return {
      date: `${p.year}-${p.month}-${p.day}`,
      hour: Number(p.hour) % 24,
      weekday: WEEKDAY[p.weekday] ?? 0,
    };
  };
}

function dayBefore(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d) - 86400000).toISOString().slice(0, 10);
}

function nightKey(ts, lt) {
  const l = lt(ts);
  if (l.hour >= NIGHT_START_HOUR) return l.date;
  if (l.hour < NIGHT_END_HOUR) return dayBefore(l.date);
  return l.date;
}

/* ---------------------------------------------------------------- storage */

async function getDevices(db) {
  const r = await db.prepare('SELECT * FROM devices ORDER BY last_seen DESC').all();
  return r.results || [];
}

/* Mirrors Store.events().  A record with start_at 0 (or NULL) is one the
   hub made before it knew the time; it counts as evidence and is windowed
   by received_at.  server.py folds that into one CASE expression; here it
   is two ranges so each can use its own index. */
async function fetchEvents(db, { since = 0, until = 0, cot = 0, kind = '', limit = 500 }) {
  let sql = 'SELECT * FROM events WHERE ((start_at > 0 AND start_at >= ?';
  const a = [since];
  if (until) { sql += ' AND start_at <= ?'; a.push(until); }
  sql += ') OR ((start_at IS NULL OR start_at = 0) AND received_at >= ?';
  a.push(since);
  if (until) { sql += ' AND received_at <= ?'; a.push(until); }
  sql += '))';
  if (cot) { sql += ' AND cot = ?'; a.push(cot); }
  if (kind) { sql += ' AND kind = ?'; a.push(kind); }
  sql += ' ORDER BY (CASE WHEN start_at > 0 THEN start_at ELSE received_at END) DESC, seq DESC LIMIT ?';
  a.push(limit);
  const r = await db.prepare(sql).bind(...a).all();
  return r.results || [];
}

/* Mirrors Store.all_cry_events(): every cry, oldest first, timed only. */
async function allCryEvents(db, since, until) {
  let sql = "SELECT * FROM events WHERE kind IN ('cry','test')";
  const a = [];
  if (since) { sql += ' AND start_at >= ?'; a.push(since); }
  if (until) { sql += ' AND start_at <= ?'; a.push(until); }
  sql += ' ORDER BY start_at ASC';
  const r = await db.prepare(sql).bind(...a).all();
  return r.results || [];
}

/* The untimed count server.py gets by scanning the window in Python; a
   COUNT here reads the same rows without shipping them. */
async function countUntimed(db, since, until) {
  let sql = "SELECT COUNT(*) AS n FROM events WHERE kind='cry' AND coalesce(start_at,0)=0 AND received_at >= ?";
  const a = [since];
  if (until) { sql += ' AND received_at <= ?'; a.push(until); }
  const r = await db.prepare(sql).bind(...a).first();
  return r ? r.n : 0;
}

/* -------------------------------------------------------------- summary */

async function buildSummary(db, days, cot, tz) {
  const lt = makeLocal(tz);
  const now = Math.floor(Date.now() / 1000);
  const since = now - days * 86400;
  let events = await fetchEvents(db, { since, until: now + 86400, cot, kind: 'cry', limit: 100000 });
  events = events.filter((e) => e.kind === 'cry' || e.kind === 'test');
  events.sort((a, b) => (a.start_at || 0) - (b.start_at || 0));

  const durations = events.map((e) => Math.trunc(e.duration_s || 0));
  const totalS = durations.reduce((s, d) => s + d, 0);

  const perCot = new Map();
  const perDay = new Map();
  const perHour = new Array(24).fill(0);
  const perHourS = new Array(24).fill(0);
  const perWeekday = new Array(7).fill(0);
  const nights = new Map();
  const heatCounts = new Map();
  const heatSeconds = new Map();

  let untimed = 0;
  for (const e of events) {
    const ts = Math.trunc(e.start_at || 0);
    const c = Math.trunc(e.cot || 0);
    const dur = Math.trunc(e.duration_s || 0);

    // Which cot cried, how often and how loudly are facts whether or not
    // the hub knew the date, so they are counted for every record.
    // Only last_at needs a time.
    let b = perCot.get(c);
    if (!b) {
      b = { cot: c, cries: 0, seconds: 0, max_seconds: 0, last_at: 0, confidences: [] };
      perCot.set(c, b);
    }
    b.cries += 1;
    b.seconds += dur;
    b.max_seconds = Math.max(b.max_seconds, dur);
    if (e.peak_conf !== null && e.peak_conf !== undefined) b.confidences.push(Math.trunc(e.peak_conf));
    if (!ts) { untimed += 1; continue; }
    b.last_at = Math.max(b.last_at, ts);

    const local = lt(ts);
    const dkey = local.date;
    let day = perDay.get(dkey);
    if (!day) { day = { day: dkey, cries: 0, seconds: 0, cots: new Set() }; perDay.set(dkey, day); }
    day.cries += 1;
    day.seconds += dur;
    if (c) day.cots.add(c);

    perHour[local.hour] += 1;
    perHourS[local.hour] += dur;
    perWeekday[local.weekday] += 1;

    const nk = nightKey(ts, lt);
    let night = nights.get(nk);
    if (!night) { night = { night: nk, cries: 0, seconds: 0, cots: new Set() }; nights.set(nk, night); }
    night.cries += 1;
    night.seconds += dur;
    if (c) night.cots.add(c);

    if (c) {
      if (!heatCounts.has(c)) { heatCounts.set(c, new Array(24).fill(0)); heatSeconds.set(c, new Array(24).fill(0)); }
      heatCounts.get(c)[local.hour] += 1;
      heatSeconds.get(c)[local.hour] += dur;
    }
  }

  for (const b of perDay.values()) b.cots = [...b.cots].sort((x, y) => x - y);
  for (const b of nights.values()) b.cots = [...b.cots].sort((x, y) => x - y);

  const nightList = [...nights.values()].sort((a, b) => (a.night < b.night ? -1 : a.night > b.night ? 1 : 0));

  const gaps = [];
  for (let i = 1; i < events.length; i++) {
    const a = events[i - 1];
    const b = events[i];
    if (a.start_at && b.start_at) gaps.push(b.start_at - a.start_at);
  }

  const cotsSorted = [...perCot.values()].sort((a, b) => a.cot - b.cot);
  for (const b of cotsSorted) {
    const confs = b.confidences;
    delete b.confidences;
    b.avg_conf = confs.length ? r1(confs.reduce((s, x) => s + x, 0) / confs.length) : null;
  }

  const heatCots = [...heatCounts.keys()].sort((a, b) => a - b);
  const devices = await getDevices(db);
  const lastCryAt = events.reduce((m, e) => Math.max(m, Math.trunc(e.start_at || 0)), 0);

  return {
    device: devices.length ? devices[0] : null,
    devices,
    range: { from: since, to: now, days },
    kpis: {
      total_cries: events.length,
      timed_cries: events.length - untimed,
      untimed_cries: untimed,
      cries_per_day: days ? r2(events.length / days) : 0,
      total_cry_seconds: totalS,
      avg_cry_seconds: events.length ? r1(totalS / events.length) : 0,
      longest_cry_seconds: durations.length ? Math.max(...durations) : 0,
      median_cry_seconds: durations.length ? r1(median(durations)) : 0,
      cots_crying: perCot.size,
      nights_affected: nights.size,
      nights_per_week: days >= 7 ? r2(nights.size / (days / 7.0)) : 0,
      // A per-night average must divide like by like: a record with no
      // time cannot be attributed to a night.
      avg_cries_per_night: nights.size ? r2((events.length - untimed) / nights.size) : 0,
      last_cry_at: lastCryAt,
      median_gap_min: gaps.length ? r1(median(gaps) / 60.0) : null,
    },
    per_cot: cotsSorted,
    per_day: [...perDay.keys()].sort().map((k) => perDay.get(k)),
    per_night: nightList,
    per_hour: perHour.map((n, h) => ({ hour: h, cries: n, seconds: perHourS[h] })),
    per_weekday: perWeekday.map((n, w) => ({ weekday: w, cries: n })),
    heatmap: {
      cots: heatCots,
      counts: heatCots.map((c) => heatCounts.get(c)),
      seconds: heatCots.map((c) => heatSeconds.get(c)),
    },
    recent: events.slice(-400).map((e) => ({
      seq: e.seq, cot: e.cot, kind: e.kind,
      start: e.start_at, end: e.end_at,
      duration_s: e.duration_s, peak_conf: e.peak_conf,
      windows: e.windows, peak_rms: e.peak_rms,
      mean_rms: e.mean_rms,
    })),
  };
}

/* ------------------------------------------------------------ analytics */

function bucketPairs(edges) {
  const pairs = [];
  let lo = 0;
  for (const hi of edges) { pairs.push([lo, hi]); lo = hi; }
  pairs.push([lo, 1e9]);
  return pairs;
}

function bucketLabel(lo, hi) {
  if (hi >= 1e9) return `${Math.round(lo / 60)}+ min`;
  return hi - lo <= 60 ? `${lo}-${hi}s` : `${Math.floor(lo / 60)}-${Math.floor(hi / 60)} min`;
}

async function buildAnalytics(db, days, tz) {
  const lt = makeLocal(tz);
  const now = Math.floor(Date.now() / 1000);
  const since = now - days * 86400;
  const events = (await allCryEvents(db, since, now + 86400)).filter((e) => e.start_at);
  const untimed = await countUntimed(db, since, now + 86400);

  const durations = events.map((e) => Math.trunc(e.duration_s || 0));
  const confs = events
    .filter((e) => e.peak_conf !== null && e.peak_conf !== undefined)
    .map((e) => Math.trunc(e.peak_conf));

  const pairs = bucketPairs(DURATION_BUCKETS);
  const hist = pairs.map(([lo, hi]) => ({ label: bucketLabel(lo, hi), count: 0 }));
  for (const d of durations) {
    for (let i = 0; i < pairs.length; i++) {
      if (d >= pairs[i][0] && d < pairs[i][1]) { hist[i].count += 1; break; }
    }
  }

  const gaps = [];
  for (let i = 1; i < events.length; i++) gaps.push(events[i].start_at - events[i - 1].start_at);

  const nightsMap = new Map();
  for (const e of events) {
    const k = nightKey(Math.trunc(e.start_at), lt);
    if (!nightsMap.has(k)) nightsMap.set(k, []);
    nightsMap.get(k).push(e);
  }

  // The hour each cot is most often heard in, and how sharp that peak is
  // -- a caregiver wants to know "cot 2 always wakes at 03:00".
  const perCot = [];
  const cots = [...new Set(events.map((e) => Math.trunc(e.cot || 0)))].sort((a, b) => a - b);
  for (const eCot of cots) {
    const sub = events.filter((e) => Math.trunc(e.cot || 0) === eCot);
    const byHour = new Array(24).fill(0);
    for (const e of sub) byHour[lt(Math.trunc(e.start_at)).hour] += 1;
    let peakHour = 0;
    for (let h = 1; h < 24; h++) if (byHour[h] > byHour[peakHour]) peakHour = h;
    const total = byHour.reduce((s, x) => s + x, 0);
    const share = total ? r1((100.0 * byHour[peakHour]) / total) : 0;
    const secs = sub.reduce((s, e) => s + Math.trunc(e.duration_s || 0), 0);
    const subDurs = sub.map((e) => Math.trunc(e.duration_s || 0));
    perCot.push({
      cot: eCot,
      cries: sub.length,
      seconds: secs,
      avg_seconds: sub.length ? r1(secs / sub.length) : 0,
      max_seconds: sub.length ? Math.max(...subDurs) : 0,
      median_seconds: sub.length ? r1(median(subDurs)) : 0,
      by_hour: byHour,
      peak_hour: peakHour,
      peak_share: share,
      night_cries: sub.filter((e) => {
        const h = lt(Math.trunc(e.start_at)).hour;
        return h >= NIGHT_START_HOUR || h < NIGHT_END_HOUR;
      }).length,
    });
  }

  const nights = [...nightsMap.keys()].sort().map((k) => {
    const v = nightsMap.get(k);
    return {
      night: k,
      cries: v.length,
      seconds: v.reduce((s, e) => s + Math.trunc(e.duration_s || 0), 0),
      cots: [...new Set(v.map((e) => Math.trunc(e.cot || 0)))].sort((a, b) => a - b),
      first: Math.min(...v.map((e) => Math.trunc(e.start_at))),
      last: Math.max(...v.map((e) => Math.trunc(e.start_at))),
    };
  });

  return {
    range: { from: since, to: now, days },
    duration_hist: hist,
    confidence: {
      min: confs.length ? Math.min(...confs) : null,
      median: confs.length ? r1(median(confs)) : null,
      max: confs.length ? Math.max(...confs) : null,
    },
    gaps: {
      count: gaps.length,
      median_min: gaps.length ? r1(median(gaps) / 60.0) : null,
      max_min: gaps.length ? r1(Math.max(...gaps) / 60.0) : null,
      min_min: gaps.length ? r1(Math.min(...gaps) / 60.0) : null,
    },
    nights,
    per_cot: perCot,
    // Every pattern on this page is a statement about *when*.  A record
    // with no time cannot take part in one, so it is counted and
    // reported rather than quietly folded in.
    untimed_cries: untimed,
    insights: buildInsights(events, perCot, nightsMap, gaps),
  };
}

function buildInsights(events, perCot, nightsMap, gaps) {
  const out = [];
  if (!events.length) return ['No cries have been recorded yet.'];

  const total = events.length;
  out.push(`${total} cry episode${total !== 1 ? 's' : ''} recorded.`);

  for (const c of perCot) {
    if (c.cries < 3) continue;
    if (c.peak_share >= 40) {
      out.push(
        `Cot ${c.cot} is usually heard around ${String(c.peak_hour).padStart(2, '0')}:00 ` +
        `(${c.peak_share}% of its cries fall in that hour).`
      );
    }
    if (c.night_cries / c.cries > 0.6) {
      out.push(`Cot ${c.cot} cries are mostly at night (${c.night_cries} of ${c.cries}).`);
    }
  }

  if (nightsMap.size) {
    const counts = [...nightsMap.values()].map((v) => v.length);
    const avg = counts.reduce((s, x) => s + x, 0) / counts.length;
    out.push(
      `On average ${avg.toFixed(1)} cry episodes per night across ` +
      `${nightsMap.size} night${nightsMap.size !== 1 ? 's' : ''}.`
    );
    let worstK = null;
    let worstV = null;
    for (const [k, v] of nightsMap) {
      if (worstV === null || v.length > worstV.length) { worstK = k; worstV = v; }
    }
    if (counts.length > 1 && worstV.length > avg * 1.5) {
      out.push(`The night of ${worstK} was the heaviest, with ${worstV.length} episodes.`);
    }
  }

  if (gaps.length) {
    const med = median(gaps) / 60.0;
    if (med < 30) {
      out.push(`Cries come roughly every ${med.toFixed(0)} minutes on average, which is a dense pattern.`);
    } else if (med > 240) {
      out.push(`Cries are well spread out -- about every ${(med / 60).toFixed(1)} hours.`);
    }
  }

  const durs = events.map((e) => Math.trunc(e.duration_s || 0));
  if (durs.length) {
    const medD = median(durs);
    if (medD >= 60) {
      out.push(`The median cry lasts ${(medD / 60).toFixed(1)} minutes, which is long for settling complaints.`);
    } else if (medD <= 15) {
      out.push(`The median cry lasts ${Math.round(medD)} seconds -- short, settling sounds.`);
    }
  }
  return out;
}

/* ----------------------------------------------------------------- auth */

async function sha256Bytes(s) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return new Uint8Array(d);
}

/* timingSafeEqual needs equal lengths, so both sides are hashed first. */
async function safeEqual(a, b) {
  const [da, db] = await Promise.all([sha256Bytes(a), sha256Bytes(b)]);
  return crypto.subtle.timingSafeEqual(da, db);
}

/* The hub sends X-CryNet-Token (net token <value> on its console); the
   caregiver's browser sends the Basic login it was asked for when the
   page was opened.  With neither secret set — local development — every
   request is allowed, exactly like server.py with no --token. */
async function authorised(request, env) {
  const token = env.UPLOAD_TOKEN || '';
  const pass = env.DASHBOARD_PASSWORD || '';
  const user = env.DASHBOARD_USER || 'caregiver';
  if (!token && !pass) return true;

  const got = request.headers.get('X-CryNet-Token') || '';
  if (token && got && (await safeEqual(got, token))) return true;

  const h = request.headers.get('Authorization') || '';
  if (pass && h.startsWith('Basic ')) {
    let dec = '';
    try { dec = atob(h.slice(6)); } catch (e) { return false; }
    const i = dec.indexOf(':');
    const u = i < 0 ? dec : dec.slice(0, i);
    const p = i < 0 ? '' : dec.slice(i + 1);
    if ((await safeEqual(u, user)) && (await safeEqual(p, pass))) return true;
  }
  return false;
}

function unauthorised() {
  return json({ error: 'unauthorised' }, 401, {
    'WWW-Authenticate': 'Basic realm="Amazing\'s CryNet", charset="UTF-8"',
  });
}

/* --------------------------------------------------------------- upload */

async function handleUpload(db, request) {
  let body;
  try { body = await request.json(); } catch (e) {
    return json({ error: 'bad json' }, 400);
  }
  const device = String((body && body.device) || 'unknown');
  const hub = (body && body.hub) || {};
  const fw = String(hub.fw ?? '');
  const name = String(hub.name ?? '');
  const now = Math.floor(Date.now() / 1000);
  const evs = (body && body.events) || [];

  // One batch, so a half-applied upload cannot happen: the pair
  // (device, seq) makes re-uploading the same records harmless.
  const stmts = [];
  for (const ev of evs) {
    stmts.push(
      db.prepare(
        'INSERT OR IGNORE INTO events (device, seq, kind, cot, start_at,' +
        ' end_at, duration_s, peak_conf, windows, peak_rms, mean_rms,' +
        ' boot, uptime_ms, received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
      ).bind(
        device,
        toInt(ev.seq) ?? 0,
        String(ev.kind ?? 'cry'),
        toInt(ev.cot),
        toInt(ev.start),
        toInt(ev.end),
        toInt(ev.duration_s),
        toInt(ev.peak_conf),
        toInt(ev.windows),
        toFloat(ev.peak_rms),
        toFloat(ev.mean_rms),
        toInt(ev.boot),
        toInt(ev.uptime_ms),
        now
      )
    );
  }
  stmts.push(
    db.prepare(
      'INSERT INTO devices (device, name, fw, first_seen, last_seen)' +
      ' VALUES (?,?,?,?,?)' +
      ' ON CONFLICT(device) DO UPDATE SET' +
      '   name=COALESCE(excluded.name, devices.name),' +
      '   fw=COALESCE(excluded.fw, devices.fw),' +
      '   last_seen=excluded.last_seen'
    ).bind(device, name || null, fw || null, now, now)
  );

  const results = await db.batch(stmts);
  let accepted = 0;
  for (let i = 0; i < evs.length; i++) accepted += (results[i] && results[i].meta && results[i].meta.changes) || 0;
  return json({ accepted, received: evs.length, server_time: now });
}

/* ------------------------------------------------------------- presence */

/* A hub is taken to be there if it has said something in the last three
   quarters of a minute.  The hub says every fifteen seconds, so three is
   three chances missed before the dashboard calls it gone -- the same
   rule of three the offline server keeps, four times faster.  The owner
   asked for the hub's connection to be checked "as often as possible",
   and this is the middle link of the three that decide it: how often
   the hub speaks (15 s), how long this waits (45 s), and how often the
   page asks (10 s). */
const PRESENCE_STALE_S = 45;

/* Mirrors server.py's build_presence(): who is here, and which of them
   is still answering.  A record says what happened; this says whether the
   thing that watches is working, which is the other question. */
async function buildPresence(db) {
  const now = Math.floor(Date.now() / 1000);
  const devices = await getDevices(db);
  const demo = new Set();
  const hubs = devices.map((d) => {
    const seen = Number(d.last_seen) || 0;
    const isDemo = (d.fw || '') === 'demo';
    if (isDemo) demo.add(d.device);
    return {
      device: d.device,
      name: d.name,
      fw: d.fw,
      at: seen,
      age_s: seen ? now - seen : null,
      // The demo hub is not a thing that can go offline -- it is a made-up
      // hub with nothing posting it.
      online: isDemo || (!!seen && now - seen <= PRESENCE_STALE_S),
      demo: isDemo,
    };
  });
  const r = await db.prepare('SELECT * FROM presence ORDER BY device, cot').all();
  const nodes = (r.results || []).map((p) => ({
    device: p.device,
    cot: p.cot,
    online: demo.has(p.device) || !!p.online,
    deaf: !!p.deaf,
    rssi: p.rssi,
    at: p.at,
  }));
  return { now, hubs, nodes };
}

/* The hub says who is here.  One row per cot, replaced each time, so
   what is stored is always the last thing the hub knew. */
async function handlePresence(db, request) {
  let body;
  try { body = await request.json(); } catch (e) {
    return json({ error: 'bad json' }, 400);
  }
  const device = String((body && body.device) || 'unknown');
  const hub = (body && body.hub) || {};
  const fw = String(hub.fw ?? '');
  const name = String(hub.name ?? '');
  const now = Math.floor(Date.now() / 1000);
  const nodes = Array.isArray(body && body.nodes) ? body.nodes : [];

  const stmts = [
    db.prepare(
      'INSERT INTO devices (device, name, fw, first_seen, last_seen)' +
      ' VALUES (?,?,?,?,?)' +
      ' ON CONFLICT(device) DO UPDATE SET' +
      '   name=COALESCE(excluded.name, devices.name),' +
      '   fw=COALESCE(excluded.fw, devices.fw),' +
      '   last_seen=excluded.last_seen'
    ).bind(device, name || null, fw || null, now, now),
  ];
  let written = 0;
  for (const n of nodes) {
    const cot = toInt(n && n.cot);
    if (cot === null || cot === undefined) continue;
    stmts.push(
      db.prepare(
        'INSERT INTO presence (device, cot, online, deaf, rssi, at)' +
        ' VALUES (?,?,?,?,?,?)' +
        ' ON CONFLICT(device, cot) DO UPDATE SET' +
        '   online=excluded.online,' +
        '   deaf=excluded.deaf,' +
        '   rssi=excluded.rssi,' +
        '   at=excluded.at'
      ).bind(
        device,
        cot,
        n && n.online ? 1 : 0,
        n && n.deaf ? 1 : 0,
        toInt(n && n.rssi),
        now
      )
    );
    written++;
  }
  await db.batch(stmts);
  return json({ ok: true, cots: written, server_time: now });
}

/* --------------------------------------------------------------- router */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const q = url.searchParams;
    try {
      if (path === '/api/v1/health') {
        const r = await env.DB.prepare('SELECT COUNT(*) AS n FROM devices').first();
        return json({ ok: true, time: Math.floor(Date.now() / 1000), devices: r ? r.n : 0 });
      }

      if (path === '/api/v1/events' && request.method === 'POST') {
        if (!(await authorised(request, env))) return json({ error: 'unauthorised' }, 401);
        return await handleUpload(env.DB, request);
      }

      if (path === '/api/v1/presence' && request.method === 'POST') {
        if (!(await authorised(request, env))) return json({ error: 'unauthorised' }, 401);
        return await handlePresence(env.DB, request);
      }

      if (path.startsWith('/api/')) {
        if (!(await authorised(request, env))) return unauthorised();
        if (path === '/api/v1/devices') return json({ devices: await getDevices(env.DB) });
        if (path === '/api/v1/presence') return json(await buildPresence(env.DB));
        if (path === '/api/v1/summary') {
          return json(
            await buildSummary(env.DB, intParam(q.get('days'), 14), intParam(q.get('cot'), 0), q.get('tz') || '')
          );
        }
        if (path === '/api/v1/analytics') {
          return json(await buildAnalytics(env.DB, intParam(q.get('days'), 30), q.get('tz') || ''));
        }
        if (path === '/api/v1/events') {
          const rows = await fetchEvents(env.DB, {
            since: intParam(q.get('from'), 0),
            until: intParam(q.get('to'), 0),
            cot: intParam(q.get('cot'), 0),
            kind: q.get('kind') || '',
            limit: Math.min(intParam(q.get('limit'), 200), 2000),
          });
          return json({ events: rows });
        }
        return json({ error: 'not found' }, 404);
      }

      // The page and its assets — behind the same login, so the browser
      // asks once on opening the dashboard and then attaches it to every
      // fetch the page makes.
      if (!(await authorised(request, env))) return unauthorised();
      return env.ASSETS.fetch(request);
    } catch (err) {
      return json({ error: 'internal', detail: String(err) }, 500);
    }
  },
};
