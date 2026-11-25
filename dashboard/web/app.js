/* Amazing's CryNet — the caregiver's record.
 *
 * Plain ES2019-ish vanilla JS.  No modules, no dependencies, no build step;
 * it is loaded with a plain <script src="app.js">.
 *
 * The rules this file lives by:
 *
 *   1. A record with start == 0 happened, but the hub did not know WHEN.
 *      It is never placed on a time axis.  Every series builder filters on
 *      a positive timestamp before it touches a date, and the episodes
 *      table prints "Time unknown" rather than inventing 1970.
 *   2. Nothing is ever NaN, undefined or "0/0".  A missing number is "—".
 *   3. An empty dashboard is a normal first run, not an error.
 *   4. A cot that went deaf was NOT being watched.  That is surfaced at
 *      the top of the page, because a quiet stretch during a deaf spell
 *      means nothing at all.
 *
 * Field names come from server.py's build_summary() / build_analytics(),
 * not from prose.  Note that /api/v1/events returns raw store columns
 * (start_at / end_at / received_at), while summary.recent uses start / end.
 */
(function () {
  'use strict';

  var API = '/api/v1';
  var POLL_MS = 30000;
  var PRESENCE_POLL_MS = 10000;
  var NS = 'http://www.w3.org/2000/svg';
  var NIGHT_START = 20;          // server.py: NIGHT_START_HOUR
  var NIGHT_END = 6;             // server.py: NIGHT_END_HOUR
  var RECENT_PAGE = 12;
  var NIGHTS_PAGE = 12;
  var SYSTEM_KINDS = ['deaf', 'heard', 'boot', 'test'];

  /* Fixed categorical order, assigned by cot number and never re-ranked. */
  var SERIES = ['--series-1', '--series-2', '--series-3', '--series-4',
                '--series-5', '--series-6', '--series-7', '--series-8'];
  /* Sequential ramp for magnitude only (heatmap). */
  var RAMP = ['--seq-100', '--seq-200', '--seq-300',
              '--seq-400', '--seq-500', '--seq-550'];

  function v(name) { return 'var(' + name + ')'; }

  /* ------------------------------------------------------------------ DOM */

  function apply(node, attrs) {
    if (!attrs) return node;
    for (var k in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
      var val = attrs[k];
      if (val === null || val === undefined || val === false) continue;
      if (k === 'text') node.appendChild(document.createTextNode(String(val)));
      else if (k === 'style') { for (var p in val) node.style[p] = val[p]; }
      else if (val === true) node.setAttribute(k, '');
      else node.setAttribute(k, String(val));
    }
    return node;
  }

  function kids(node, list) {
    if (list === null || list === undefined || list === false) return node;
    if (Array.isArray(list)) {
      for (var i = 0; i < list.length; i++) kids(node, list[i]);
      return node;
    }
    if (typeof list === 'string' || typeof list === 'number') {
      node.appendChild(document.createTextNode(String(list)));
      return node;
    }
    node.appendChild(list);
    return node;
  }

  function h(tag, attrs, content) {
    var n = apply(document.createElement(tag), attrs);
    return kids(n, content);
  }

  function svgEl(tag, attrs, content) {
    var n = apply(document.createElementNS(NS, tag), attrs);
    return kids(n, content);
  }

  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }
  function show(node, on) { if (node) node.hidden = !on; }
  function text(node, str) { if (node) node.textContent = str; }

  /* ----------------------------------------------------------- formatting */

  function isNum(x) { return typeof x === 'number' && isFinite(x); }

  function num(x) {
    if (x === null || x === undefined || x === '') return '—';
    if (!isNum(x)) { var n = Number(x); if (!isFinite(n)) return '—'; x = n; }
    return x.toLocaleString();
  }

  function dec(x, places) {
    if (x === null || x === undefined || x === '') return '—';
    if (!isNum(x)) { var n = Number(x); if (!isFinite(n)) return '—'; x = n; }
    return x.toFixed(places === undefined ? 1 : places);
  }

  function pct(x) {
    if (x === null || x === undefined || !isFinite(Number(x))) return '—';
    return Number(x).toFixed(1) + '%';
  }

  /* A duration in seconds, written the way a person reads it. */
  function dur(sec) {
    if (sec === null || sec === undefined || !isFinite(Number(sec))) return '—';
    var t = Math.round(Number(sec));
    if (t < 0) return '—';
    if (t < 60) return t + ' s';
    var m = Math.floor(t / 60), r = t % 60;
    if (m < 60) return r ? m + ' min ' + r + ' s' : m + ' min';
    var hh = Math.floor(m / 60), mm = m % 60;
    return mm ? hh + ' h ' + mm + ' min' : hh + ' h';
  }

  /* Compact form for axis ticks, where "1 min 15 s" is too long. */
  function durAxis(sec) {
    var t = Number(sec);
    if (!isFinite(t)) return '';
    if (t >= 3600) return (t / 3600).toFixed(t % 3600 ? 1 : 0) + 'h';
    if (t >= 60) return Math.round(t / 60) + 'm';
    return Math.round(t) + 's';
  }

  function minutes(min) {
    if (min === null || min === undefined || !isFinite(Number(min))) return '—';
    return dur(Number(min) * 60);
  }

  function ts(ms) { return new Date(ms * 1000); }

  function clockAt(sec) {
    if (!sec) return '—';
    return ts(sec).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  function dateAt(sec) {
    if (!sec) return '—';
    return ts(sec).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function dateTimeAt(sec) {
    if (!sec) return '—';
    return ts(sec).toLocaleString(undefined, {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
    });
  }

  function ago(sec) {
    if (!sec) return '—';
    var d = Math.round(Date.now() / 1000) - sec;
    if (d < 0) return 'just now';
    if (d < 60) return 'just now';
    if (d < 3600) return Math.round(d / 60) + ' min ago';
    if (d < 86400) return Math.round(d / 3600) + ' h ago';
    var days = Math.round(d / 86400);
    return days + (days === 1 ? ' day ago' : ' days ago');
  }

  /* "2026-11-20" is a LOCAL calendar day from the server.  Parsing it with
   * new Date(iso) would read it as UTC and shift it a day west of Greenwich,
   * so it is taken apart by hand. */
  function dayDate(iso) {
    var p = String(iso || '').split('-');
    if (p.length !== 3) return null;
    var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]), 12, 0, 0, 0);
    return isNaN(d.getTime()) ? null : d;
  }

  function isoDay(d) {
    var m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day);
  }

  function dayShort(iso) {
    var d = dayDate(iso);
    if (!d) return String(iso || '—');
    return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  }

  function dayLong(iso) {
    var d = dayDate(iso);
    if (!d) return String(iso || '—');
    return d.toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
  }

  /* A night is named by the evening it starts, exactly as server.py's
   * night_key() does: 20:00 on the 20th through 06:00 on the 21st is
   * "the night of the 20th". */
  function nightShort(iso) { return dayShort(iso); }
  function nightLong(iso) {
    var d = dayDate(iso);
    if (!d) return String(iso || '—');
    var next = new Date(d.getTime());
    next.setDate(next.getDate() + 1);
    var f = function (x) {
      return x.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    };
    return 'Night of ' + f(d) + ' into ' + f(next);
  }

  var WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  function weekdayName(w) { return WEEKDAYS[w] || ('—'); }
  function hourLabel(hh) { return (hh < 10 ? '0' + hh : String(hh)) + ':00'; }
  function isNightHour(hh) { return hh >= NIGHT_START || hh < NIGHT_END; }

  function cotName(c) { return c ? 'Cot ' + c : 'Cot unassigned'; }
  function cotColor(c) { return c ? v(SERIES[(c - 1) % SERIES.length]) : v('--series-other'); }
  function cotList(arr) {
    if (!arr || !arr.length) return '—';
    return arr.map(cotName).join(', ');
  }

  function hubName(d) {
    if (!d) return '';
    return d.name || d.device || 'Hub';
  }

  /* --------------------------------------------------------------- state */

  var ids = {};
  var ID_LIST = ['hubmeta', 'hubmeta-text', 'conn', 'conn-text', 'theme',
    'tab-overview', 'tab-patterns',
    'range', 'cot', 'device', 'device-control', 'scope-note', 'view-overview',
    'view-patterns', 'empty-overview', 'empty-overview-detail', 'overview-body',
    'kpis', 'untimed-note', 'presence-strip', 'system-strip', 'overview-grid',
    'empty-patterns',
    'patterns-body', 'patterns-scope', 'patterns-grid', 'footer-range',
    'footer-updated', 'tooltip'];

  var state = {
    days: 14,
    cot: 0,
    device: '',
    tab: 'overview',
    summary: null,
    analytics: null,
    devices: [],
    presence: null,
    system: [],
    systemOk: true,
    counts: null,
    knownCots: [],
    tables: {},
    recentAll: false,
    nightsAll: false,
    systemOpen: false,
    lastGood: 0,
    failures: 0,
    busy: false,
    busySince: 0,
    presenceBusy: false
  };

  var charts = [];      /* { host, draw } — redrawn on resize and tab change */
  var timer = null;
  var presenceTimer = null;
  var pristine = {};    /* original empty-state wording, restored after errors */

  /* --------------------------------------------------------------- fetch */

  /* Days, hours and nights are bucketed on the server, and the server may
     not be in the caregiver's timezone (the hosted copy runs in UTC), so
     every request says which zone the numbers should be counted in. */
  var TZ = '';
  try { TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { /* keep '' */ }

  /* A read that never comes back must not freeze the page.  The busy
   * flag below is only a guard against overlapping reads; if a request
   * hangs, the flag would stay set for ever and the page would sit on
   * its last answer -- which is how a hub that has gone offline keeps
   * reading as online.  So every read is given a deadline, and the
   * guard has a deadline of its own. */
  var FETCH_TIMEOUT_MS = 15000;
  var BUSY_STUCK_MS = 60000;

  function getJSON(path) {
    if (TZ) path += (path.indexOf('?') >= 0 ? '&' : '?') + 'tz=' + encodeURIComponent(TZ);
    var ctl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = null;
    if (ctl) timer = setTimeout(function () { ctl.abort(); }, FETCH_TIMEOUT_MS);
    function done(fn, arg) {
      if (timer) { clearTimeout(timer); timer = null; }
      return fn(arg);
    }
    return fetch(API + path, {
      cache: 'no-store',
      credentials: 'same-origin',
      signal: ctl ? ctl.signal : undefined
    })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (v) { return done(function () { return v; }); },
            function (e) { return done(function () { throw e; }); });
  }

  /* Never rejects: resolves to null so one bad endpoint cannot blank the page. */
  function soft(path) {
    return getJSON(path).catch(function () { return null; });
  }

  function refresh() {
    if (state.busy) {
      /* A read that has been running for a minute is a read that is
       * never going to finish; let this one go through. */
      if (Date.now() - state.busySince < BUSY_STUCK_MS) return;
      state.busy = false;
    }
    state.busy = true;
    state.busySince = Date.now();
    if (state.summary) {
      ids['view-overview'].classList.add('refreshing');
      ids['view-patterns'].classList.add('refreshing');
    }

    var now = Math.floor(Date.now() / 1000);
    var from = now - state.days * 86400;
    var to = now + 86400;
    var q = '?days=' + state.days + '&cot=' + state.cot;

    var jobs = [
      soft('/summary' + q),
      soft('/analytics?days=' + state.days),
      soft('/devices'),
      soft('/health'),
      soft('/presence')
    ].concat(SYSTEM_KINDS.map(function (k) {
      return soft('/events?kind=' + k + '&from=' + from + '&to=' + to + '&limit=300');
    }));

    Promise.all(jobs).then(function (res) {
      var summary = res[0], analytics = res[1], devices = res[2], health = res[3];
      var presence = res[4];
      var sysLists = res.slice(5);

      var sys = [], sysOk = true;
      sysLists.forEach(function (r) {
        if (!r || !Array.isArray(r.events)) { sysOk = false; return; }
        sys = sys.concat(r.events);
      });
      sys.sort(function (a, b) { return (b.start_at || 0) - (a.start_at || 0); });

      state.system = sys;
      state.systemOk = sysOk;

      if (devices && Array.isArray(devices.devices)) state.devices = devices.devices;
      else if (summary && Array.isArray(summary.devices)) state.devices = summary.devices;

      /* The presence is separate from the record: it says whether the
       * thing that watches is working, which is a different question
       * from what it has heard.  A service that does not have the
       * endpoint yet simply leaves it null. */
      setPresence(presence);

      if (analytics) state.analytics = analytics;

      if (summary) {
        state.summary = summary;
        state.lastGood = Date.now();
        state.failures = 0;
        rememberCots(summary, analytics);
        setConn(health && health.ok ? 'ok' : 'stale',
          health && health.ok ? 'Live · updated ' + clockAt(now)
                              : 'Service replied, but reports a problem');
        if (!sysOk) setConn('stale', 'Live · some system records unavailable');
      } else {
        state.failures++;
        setConn('stale', state.lastGood
          ? 'Offline · retrying (last read ' + clockAt(Math.round(state.lastGood / 1000)) + ')'
          : 'Offline · retrying every 30 s');
      }

      /* More than one hub: the API cannot split the totals, so at least
       * count what each hub uploaded and say so plainly. */
      if (state.devices.length > 1) {
        return soft('/events?kind=cry&from=' + from + '&to=' + to + '&limit=2000')
          .then(function (r) {
            if (r && Array.isArray(r.events)) {
              var counts = {};
              r.events.forEach(function (e) {
                var k = e.device || 'unknown';
                counts[k] = (counts[k] || 0) + 1;
              });
              state.counts = { counts: counts, capped: r.events.length >= 2000 };
            } else {
              state.counts = null;
            }
          });
      }
      state.counts = null;
      return null;
    }).catch(function () {
      state.failures++;
      setConn('stale', 'Offline · retrying every 30 s');
    }).then(function () {
      state.busy = false;
      ids['view-overview'].classList.remove('refreshing');
      ids['view-patterns'].classList.remove('refreshing');
      try {
        render();
      } catch (err) {
        setConn('stale', 'Could not draw the record · retrying');
        if (window.console && console.error) console.error(err);
      }
      schedule();
    });
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(refresh, POLL_MS);
  }

  /* The presence has its own, faster clock.
   *
   * The page asks the service every thirty seconds for the record, and
   * that is right: cries do not arrive every second, and the read is
   * not cheap.  But "is the hub still there" is a different question,
   * it is the one the owner opens the dashboard to ask, and it is
   * answered by one small endpoint.  So it is asked on its own, every
   * ten seconds, without dragging the rest of the page along with it.
   * The three links in the chain -- the hub speaks every 30 s, the
   * service calls a hub gone after 90 s, the page asks every 10 s --
   * add up to about two minutes between switching the hub off and the
   * page saying so.  The hub could speak every 15 s and this could be
   * shorter still, but the cots share the hub's radio and the owner
   * set the order: nothing costs the cots anything. */
  function refreshPresence() {
    if (state.presenceBusy) return;
    state.presenceBusy = true;
    soft('/presence').then(function (p) {
      state.presenceBusy = false;
      if (setPresence(p)) {
        try {
          renderChrome();
          renderPresence();
        } catch (err) {
          if (window.console && console.error) console.error(err);
        }
      }
      schedulePresence();
    });
  }

  /* Take the newest answer.  The fast poll and the full read both ask
   * for the presence, and they can arrive out of order; an older
   * answer must not replace a newer one, or the page would say the hub
   * is back when it has just gone. */
  function setPresence(p) {
    if (!p || !Array.isArray(p.hubs)) return false;
    if (state.presence && typeof p.now === 'number' &&
        typeof state.presence.now === 'number' &&
        p.now < state.presence.now) return false;
    state.presence = p;
    return true;
  }

  function schedulePresence() {
    if (presenceTimer) clearTimeout(presenceTimer);
    presenceTimer = setTimeout(refreshPresence, PRESENCE_POLL_MS);
  }

  function setConn(kind, msg) {
    if (!ids.conn) return;
    ids.conn.setAttribute('data-state', kind);
    text(ids['conn-text'], msg);
  }

  /* The cot list must survive a cot filter: summary.per_cot shrinks to the
   * chosen cot, but analytics.per_cot always covers every cot. */
  function rememberCots(summary, analytics) {
    var set = {};
    state.knownCots.forEach(function (c) { set[c] = true; });
    var add = function (c) { if (isNum(Number(c))) set[Number(c)] = true; };
    (summary && summary.per_cot || []).forEach(function (b) { add(b.cot); });
    (summary && summary.heatmap && summary.heatmap.cots || []).forEach(add);
    (analytics && analytics.per_cot || []).forEach(function (b) { add(b.cot); });
    state.knownCots = Object.keys(set).map(Number).sort(function (a, b) { return a - b; });
  }

  /* -------------------------------------------------------------- tooltip */

  function tipShow(x, y, data) {
    var el = ids.tooltip;
    if (!el || !data) return;
    clear(el);
    if (data.title) el.appendChild(h('div', { class: 'tt-title', text: data.title }));
    (data.rows || []).forEach(function (r) {
      el.appendChild(h('div', { class: 'tt-row' + (r.total ? ' tt-total' : '') }, [
        r.color ? h('span', { class: 'tt-key', style: { background: r.color } }) : null,
        h('span', { class: 'tt-name', text: r.name }),
        h('span', { class: 'tt-val', text: r.value })
      ]));
    });
    el.hidden = false;
    tipPlace(x, y);
  }

  function tipPlace(x, y) {
    var el = ids.tooltip;
    if (!el || el.hidden) return;
    var w = el.offsetWidth, hh = el.offsetHeight;
    var left = x + 14, top = y + 16;
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    if (left < 8) left = 8;
    if (top + hh > window.innerHeight - 8) top = y - hh - 12;
    if (top < 8) top = 8;
    el.style.left = left + 'px';
    el.style.top = top + 'px';
  }

  function tipHide() { if (ids.tooltip) ids.tooltip.hidden = true; }

  function tipify(node, build, highlight) {
    node.addEventListener('pointerenter', function (ev) {
      var d = build();
      if (d) tipShow(ev.clientX, ev.clientY, d);
      if (highlight) highlight(true);
    });
    node.addEventListener('pointermove', function (ev) { tipPlace(ev.clientX, ev.clientY); });
    node.addEventListener('pointerleave', function () {
      tipHide();
      if (highlight) highlight(false);
    });
    return node;
  }

  /* ---------------------------------------------------------------- icons */

  var ICON_PATHS = {
    alert: ['M8 2.3 1.7 13.5h12.6z', 'M8 6.5v3.1', 'M8 11.7h.01'],
    check: ['M8 1.9a6.1 6.1 0 1 0 0 12.2A6.1 6.1 0 0 0 8 1.9z', 'M5.2 8.1 7.2 10.1 10.8 6.1'],
    power: ['M8 2.2v5.1', 'M4.7 4.6a4.7 4.7 0 1 0 6.6 0'],
    test: ['M6 2.3h4', 'M6.7 2.3v4.3L4.3 12a1.3 1.3 0 0 0 1.2 1.9h5a1.3 1.3 0 0 0 1.2-1.9L9.3 6.6V2.3'],
    info: ['M8 1.9a6.1 6.1 0 1 0 0 12.2A6.1 6.1 0 0 0 8 1.9z', 'M8 7.3v3.6', 'M8 5.1h.01']
  };

  function icon(name, colorVar, cls) {
    var paths = ICON_PATHS[name] || ICON_PATHS.info;
    return svgEl('svg', {
      class: cls || 'icon', viewBox: '0 0 16 16', fill: 'none',
      stroke: v(colorVar), 'stroke-width': '1.5',
      'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true'
    }, paths.map(function (d) { return svgEl('path', { d: d }); }));
  }

  /* --------------------------------------------------------- chart basics */

  function niceMax(m) {
    if (!(m > 0)) return 1;
    var exp = Math.pow(10, Math.floor(Math.log(m) / Math.LN10));
    var f = m / exp;
    var n = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
    return n * exp;
  }

  /* Counts get an even top so both gridline labels stay whole numbers. */
  function evenMax(m) {
    if (!(m > 0)) return 2;
    if (m <= 2) return 2;
    if (m <= 10) return Math.ceil(m / 2) * 2;
    return niceMax(m);
  }

  function hostWidth(host) {
    return Math.round(host.clientWidth || host.getBoundingClientRect().width || 0);
  }

  /* A smooth curve through a set of points.
   *
   * A straight line between two counts draws a corner at every point,
   * and a corner in a chart of daily counts says something that is not
   * there: that the count jumped between two days and then stayed put.
   * So the line is curved.
   *
   * The curve must not overshoot.  A plain Catmull-Rom spline through
   * these points would dip below the baseline between two quiet days,
   * and a chart of counts that draws a negative count is lying.  The
   * tangents are chosen the Fritsch-Carlson way instead: each point's
   * slope is limited by its neighbours', so the curve turns at a point
   * and never past it, and it never crosses the line the points sit
   * on.
   *
   * pts is [[x, y], ...] with the x values rising. */
  function smoothPath(pts) {
    var n = pts.length;
    if (n < 2) return '';
    var slopes = new Array(n - 1);
    for (var i = 0; i < n - 1; i++) {
      var dx = pts[i + 1][0] - pts[i][0];
      slopes[i] = dx === 0 ? 0 : (pts[i + 1][1] - pts[i][1]) / dx;
    }
    var m = new Array(n);
    m[0] = slopes[0];
    m[n - 1] = slopes[n - 2];
    for (var j = 1; j < n - 1; j++) {
      var a = slopes[j - 1], b = slopes[j];
      if (a * b <= 0) {
        m[j] = 0;                       /* a peak or a trough: flat here */
      } else {
        var mid = (a + b) / 2;
        var lim = 3 * Math.min(Math.abs(a), Math.abs(b));
        m[j] = Math.abs(mid) > lim ? (mid < 0 ? -lim : lim) : mid;
      }
    }
    var d = [];
    for (var k = 0; k < n - 1; k++) {
      var x0 = pts[k][0], y0 = pts[k][1];
      var x1 = pts[k + 1][0], y1 = pts[k + 1][1];
      var h = (x1 - x0) / 3;
      if (k === 0) {
        d.push('M' + x0.toFixed(2) + ',' + y0.toFixed(2));
      }
      d.push('C' + (x0 + h).toFixed(2) + ',' + (y0 + m[k] * h).toFixed(2) +
             ' ' + (x1 - h).toFixed(2) + ',' + (y1 - m[k + 1] * h).toFixed(2) +
             ' ' + x1.toFixed(2) + ',' + y1.toFixed(2));
    }
    return d.join(' ');
  }

  /* A bar with a rounded top and a square foot.
   *
   * The foot stands on the axis, so it has to be square: a bar that
   * lifted off the line would read as floating above it.  The top is
   * rounded because a hard corner on a wide bar is a slab, and the
   * curve softens the shape without turning it into a blob. */
  function barPath(x, y, w, h, r) {
    r = Math.max(0, Math.min(r, w / 2, h));
    var f = function (n) { return Number(n).toFixed(2); };
    return 'M' + f(x) + ',' + f(y + h) +
           'V' + f(y + r) +
           'A' + f(r) + ',' + f(r) + ' 0 0 1 ' + f(x + r) + ',' + f(y) +
           'H' + f(x + w - r) +
           'A' + f(r) + ',' + f(r) + ' 0 0 1 ' + f(x + w) + ',' + f(y + r) +
           'V' + f(y + h) + 'Z';
  }

  function registerChart(host, draw) {
    charts.push({ host: host, draw: draw });
  }

  function drawCharts() {
    for (var i = 0; i < charts.length; i++) {
      var c = charts[i];
      if (!c.host.isConnected) continue;
      if (!hostWidth(c.host)) continue;      /* hidden tab: draw it when shown */
      try { c.draw(); } catch (err) { if (window.console) console.error(err); }
    }
  }

  /* A hand-built bar chart.  spec:
   *   items   [{ label, value, tip:{title,rows}, }]
   *   color(i) -> css colour,  tick(i) -> string|null
   *   bands   [{ from, to, label }] index ranges shaded behind the bars
   *   fmt     value formatter for tooltips,  axisFmt for the y axis
   */
  function barChart(host, spec) {
    registerChart(host, function () { drawBars(host, spec); });
  }

  function drawBars(host, spec) {
    var W = hostWidth(host);
    if (!W) return;
    var items = spec.items || [];
    var n = items.length;
    clear(host);
    if (!n) return;

    var H = spec.height || 168;
    var vals = items.map(function (it) { return Math.max(0, Number(it.value) || 0); });
    var maxV = Math.max.apply(null, vals);
    var top = spec.integer === false ? niceMax(maxV) : evenMax(maxV);
    if (!(top > 0)) top = 1;

    var axisFmt = spec.axisFmt || function (x) { return String(Math.round(x)); };
    var labels = [0, top / 2, top].map(axisFmt);
    var padL = 12;
    labels.forEach(function (t) { padL = Math.max(padL, String(t).length * 6.3 + 12); });
    var padR = 6, padT = 12, padB = spec.padB || 26;
    var plotW = Math.max(40, W - padL - padR);
    var plotH = Math.max(30, H - padT - padB);
    var band = plotW / n;
    var barW = Math.max(2, Math.min(band * 0.68, spec.maxBar || 30));

    var svg = svgEl('svg', {
      viewBox: '0 0 ' + W + ' ' + H, width: W, height: H,
      role: 'img', 'aria-label': spec.aria || ''
    }, [svgEl('title', { text: spec.aria || '' })]);

    (spec.bands || []).forEach(function (b) {
      var x0 = padL + band * b.from;
      var w = band * (b.to - b.from + 1);
      svg.appendChild(svgEl('rect', {
        x: x0, y: padT, width: w, height: plotH, fill: v('--wash')
      }));
      if (b.label && w > 44) {
        svg.appendChild(svgEl('text', {
          x: x0 + w / 2, y: padT + 10, 'text-anchor': 'middle',
          'font-size': '9.5', fill: v('--text-muted'), text: b.label
        }));
      }
    });

    for (var g = 0; g < 3; g++) {
      var y = padT + plotH * (1 - g / 2);
      svg.appendChild(svgEl('line', {
        x1: padL, x2: W - padR, y1: y, y2: y,
        stroke: g === 0 ? v('--axis') : v('--grid'), 'stroke-width': '1'
      }));
      svg.appendChild(svgEl('text', {
        x: padL - 6, y: y + 3.5, 'text-anchor': 'end',
        'font-size': '10.5', fill: v('--text-muted'), text: String(labels[g])
      }));
    }

    var tickEvery = spec.tickEvery || Math.max(1, Math.ceil(n / Math.max(3, Math.floor(plotW / 62))));

    items.forEach(function (it, i) {
      var val = vals[i];
      var cx = padL + band * i + band / 2;
      var bar = null;
      if (val > 0) {
        var bh = Math.max(1.5, plotH * (val / top));
        /* The top curve scales with the bar: a narrow bar cannot carry
         * a wide curve, and a tall one can carry more of it. */
        var r = Math.min(barW * 0.24, 6, bh);
        bar = svgEl('path', {
          d: barPath(cx - barW / 2, padT + plotH - bh, barW, bh, r),
          fill: spec.color ? spec.color(i) : v('--series-1'),
          /* An edge of its own, so a bar standing on a pale grid still
           * has a boundary the eye can find. */
          stroke: v('--axis'), 'stroke-width': '1', 'stroke-linejoin': 'round'
        });
        svg.appendChild(bar);
      }
      var lbl = spec.tick ? spec.tick(i) : (i % tickEvery === 0 ? it.label : null);
      if (lbl) {
        svg.appendChild(svgEl('text', {
          x: cx, y: H - padB + 15, 'text-anchor': 'middle',
          'font-size': '10.5', fill: v('--text-muted'), text: String(lbl)
        }));
      }
      var hit = svgEl('rect', {
        x: padL + band * i, y: padT, width: band, height: plotH,
        fill: 'transparent', 'pointer-events': 'all'
      }, [svgEl('title', { text: it.plain || (it.label + ': ' + (spec.fmt ? spec.fmt(val) : val)) })]);
      tipify(hit, function () { return it.tip; }, function (on) {
        if (bar) bar.setAttribute('fill-opacity', on ? '0.72' : '1');
      });
      svg.appendChild(hit);
    });

    host.appendChild(svg);
  }

  /* ---------------------------------------------------------------- cards */

  function makeCard(o) {
    var head = h('div', { class: 'card-head' }, [
      h('div', {}, [
        h('h3', { class: 'card-title', text: o.title }),
        o.sub ? h('p', { class: 'card-sub', text: o.sub }) : null
      ]),
      h('div', { class: 'spacer' })
    ]);
    var body = h('div', { class: 'card-body' });
    var root = h('div', { class: 'card' + (o.span2 ? ' span2' : '') }, [head, body]);
    return { root: root, head: head, body: body };
  }

  function note(msg) { return h('p', { class: 'card-note', text: msg }); }
  function miniEmpty(msg) { return h('p', { class: 'mini-empty', text: msg }); }

  function dataTable(headers, rows, caption) {
    var thead = h('tr', {}, headers.map(function (hd) {
      return h('th', { class: hd.n ? 'n' : null, scope: 'col', text: hd.t });
    }));
    var body = rows.map(function (cells) {
      return h('tr', {}, cells.map(function (c, i) {
        var attrs = { class: headers[i] && headers[i].n ? 'n' : null };
        if (typeof c === 'string' || typeof c === 'number') attrs.text = String(c);
        return h('td', attrs, (typeof c === 'string' || typeof c === 'number') ? null : c);
      }));
    });
    return h('table', { class: 'data' }, [
      caption ? h('caption', { class: 'sr-only', text: caption }) : null,
      h('thead', {}, thead), h('tbody', {}, body)
    ]);
  }

  function tableWrap(table, hidden) {
    return h('div', { class: 'table-wrap' + (hidden ? ' sr-only' : '') }, table);
  }

  /* Every chart ships a table twin.  It is always in the document for
   * screen readers (.sr-only) and the toggle makes it visible to everyone. */
  function chartWithTwin(card, key, headers, rows, caption, drawFn) {
    var host = h('div', { class: 'chart-host' });
    var wrap = tableWrap(dataTable(headers, rows, caption), !state.tables[key]);
    var btn = h('button', {
      class: 'toggle', type: 'button', 'aria-pressed': state.tables[key] ? 'true' : 'false',
      text: 'Table'
    });
    btn.addEventListener('click', function () {
      state.tables[key] = !state.tables[key];
      btn.setAttribute('aria-pressed', state.tables[key] ? 'true' : 'false');
      wrap.className = 'table-wrap' + (state.tables[key] ? '' : ' sr-only');
    });
    card.head.appendChild(btn);
    card.body.appendChild(host);
    card.body.appendChild(wrap);
    drawFn(host);
    return host;
  }

  function cotChip(c) {
    return h('span', { class: 'cot-chip' }, [
      h('i', { style: { background: cotColor(c) } }), h('span', { text: cotName(c) })
    ]);
  }

  function legendItem(color, label) {
    return h('span', { class: 'item' }, [
      h('span', { class: 'swatch', style: { background: color } }), h('span', { text: label })
    ]);
  }

  function figure(label, value, sub) {
    return h('div', { class: 'figure' }, [
      h('div', { class: 'label', text: label }),
      h('div', { class: 'value', text: value }),
      sub ? h('div', { class: 'sub', text: sub }) : null
    ]);
  }

  /* ------------------------------------------------------ series builders */

  /* Zero-fill a calendar span so a quiet day is drawn as a quiet day and
   * not silently dropped.  Records are keyed by the server's own local
   * day / night string; keys outside the span are kept, not discarded. */
  function spanSeries(range, records, keyName) {
    var map = {};
    (records || []).forEach(function (r) {
      var k = r[keyName];
      if (k) map[k] = r;
    });
    var out = [];
    var a = ts(range && range.from ? range.from : Math.floor(Date.now() / 1000));
    var b = ts(range && range.to ? range.to : Math.floor(Date.now() / 1000));
    a.setHours(12, 0, 0, 0);
    b.setHours(12, 0, 0, 0);
    var d = new Date(a.getTime()), guard = 0;
    while (d.getTime() <= b.getTime() && guard < 400) {
      var k = isoDay(d);
      out.push({ key: k, rec: map[k] || null });
      delete map[k];
      d.setDate(d.getDate() + 1);
      guard++;
    }
    Object.keys(map).forEach(function (k) { out.push({ key: k, rec: map[k] }); });
    out.sort(function (x, y) { return x.key < y.key ? -1 : x.key > y.key ? 1 : 0; });
    return out;
  }

  /* ------------------------------------------------------------- overview */

  function renderKpis(s) {
    var k = s.kpis || {};
    var host = ids.kpis;
    clear(host);

    var days = (s.range && s.range.days) || state.days;
    var scope = state.cot ? cotName(state.cot) : 'all cots';

    var hero = h('div', { class: 'tile hero' }, [
      h('div', { class: 'label', text: 'Cry episodes' }),
      h('div', { class: 'value', text: num(k.total_cries) }),
      h('div', { class: 'sub', text: 'in the last ' + days + ' days · ' + scope })
    ]);
    var spark = sparkline(s);
    if (spark) hero.appendChild(spark);
    host.appendChild(hero);

    host.appendChild(tile('Per day', dec(k.cries_per_day, 1),
      'average over ' + days + ' days'));

    host.appendChild(tile('Time crying', dur(k.total_cry_seconds),
      k.total_cries ? 'across ' + num(k.total_cries) + ' episodes' : 'no episodes in this range'));

    host.appendChild(tile('Typical cry', k.total_cries ? dur(k.median_cry_seconds) : '—',
      k.total_cries ? 'median · longest ' + dur(k.longest_cry_seconds)
                    : 'nothing recorded yet'));

    var nightSub;
    if (!k.nights_affected) nightSub = 'no night cries in this range';
    else if (days >= 7) nightSub = dec(k.nights_per_week, 1) + ' nights a week · ' +
      dec(k.avg_cries_per_night, 1) + ' episodes a night';
    else nightSub = 'nights with at least one cry';
    host.appendChild(tile('Nights affected', num(k.nights_affected), nightSub));
  }

  function tile(label, value, sub) {
    return h('div', { class: 'tile' }, [
      h('div', { class: 'label', text: label }),
      h('div', { class: 'value', text: value }),
      h('div', { class: 'sub', text: sub })
    ]);
  }

  function sparkline(s) {
    var series = spanSeries(s.range, s.per_day, 'day');
    if (series.length < 2) return null;
    var vals = series.map(function (x) { return x.rec ? x.rec.cries : 0; });
    var max = Math.max.apply(null, vals);
    if (!(max > 0)) return null;                 /* no empty chart frame */
    var W = 100, H = 34, pad = 3;
    var step = W / (vals.length - 1);
    var pts = vals.map(function (val, i) {
      return [i * step, H - pad - (H - pad * 2) * (val / max)];
    });
    var line = smoothPath(pts);
    return svgEl('svg', {
      class: 'spark', viewBox: '0 0 ' + W + ' ' + H, width: '100%', height: H,
      preserveAspectRatio: 'none', role: 'img',
      'aria-label': 'Daily cry counts across the range, peaking at ' + max + ' in one day.'
    }, [
      svgEl('title', { text: 'Cries per day across the range' }),
      svgEl('path', {
        d: line + ' L' + W + ',' + H + ' L0,' + H + ' Z',
        fill: v('--seq-100')
      }),
      svgEl('path', {
        d: line, fill: 'none', stroke: v('--series-1'),
        'stroke-width': '1.5', 'stroke-linejoin': 'round', 'stroke-linecap': 'round',
        'vector-effect': 'non-scaling-stroke'
      })
    ]);
  }

  /* The honesty rule.  A record with start == 0 happened at an unknown
   * time; it belongs in the count and nowhere on a time axis. */
  function untimedRecords(s) {
    return (s && s.recent || []).filter(function (r) { return !r.start; });
  }

  function renderUntimed(s) {
    var list = untimedRecords(s);
    var el = ids['untimed-note'];
    if (!list.length) { show(el, false); return; }
    var secs = list.reduce(function (a, r) { return a + (Number(r.duration_s) || 0); }, 0);
    text(el, list.length + (list.length === 1 ? ' episode has' : ' episodes have') +
      ' no known time — the hub had not reached a time server (' + dur(secs) +
      ' of crying). ' + (list.length === 1 ? 'It is' : 'They are') +
      ' counted in the totals, but not placed on any chart, and ' +
      (list.length === 1 ? 'it appears' : 'they appear') +
      ' as "Time unknown" in the episode list.');
    show(el, true);
  }

  /* ------------------------------------------------------------ the strip */

  function listeningState() {
    var byCot = {};
    state.system.forEach(function (e) {
      if (e.kind !== 'deaf' && e.kind !== 'heard') return;
      if (!e.start_at) return;                    /* untimed: cannot order it */
      var c = Number(e.cot) || 0;
      if (!byCot[c] || e.start_at > byCot[c].start_at) byCot[c] = e;
    });
    return byCot;
  }

  function deafNow() {
    var m = listeningState(), out = [];
    Object.keys(m).forEach(function (c) {
      if (m[c].kind === 'deaf') out.push({ cot: Number(c), since: m[c].start_at });
    });
    out.sort(function (a, b) { return a.cot - b.cot; });
    return out;
  }

  function renderSystemStrip() {
    var el = ids['system-strip'];
    clear(el);
    var sys = state.system;

    el.appendChild(h('span', { class: 'strip-label', text: 'System' }));

    var listening = listeningState();
    var cots = Object.keys(listening).map(Number).sort(function (a, b) { return a - b; });
    cots.forEach(function (c) {
      var e = listening[c];
      var deaf = e.kind === 'deaf';
      el.appendChild(chip(
        deaf ? 'alert' : 'check',
        deaf ? '--critical' : '--good',
        cotName(c) + (deaf ? ' not being heard' : ' hearing again'),
        (deaf ? 'since ' : '') + clockAt(e.start_at) + ' · ' + ago(e.start_at)
      ));
    });

    var deafCount = sys.filter(function (e) { return e.kind === 'deaf'; }).length;
    if (deafCount) {
      el.appendChild(chip('alert', '--serious',
        deafCount + (deafCount === 1 ? ' deaf spell' : ' deaf spells'), 'in this range'));
    }

    var boots = sys.filter(function (e) { return e.kind === 'boot' && e.start_at; });
    if (boots.length) {
      el.appendChild(chip('power', '--text-secondary',
        'Hub restarted' + (boots.length > 1 ? ' ×' + boots.length : ''),
        ago(boots[0].start_at)));
    }

    var tests = sys.filter(function (e) { return e.kind === 'test'; }).length;
    if (tests) {
      el.appendChild(chip('test', '--text-secondary',
        tests + (tests === 1 ? ' test record' : ' test records'), 'in this range'));
    }

    if (!sys.length) {
      el.appendChild(chip('info', '--text-secondary',
        state.systemOk ? 'No deaf spells, restarts or tests uploaded'
                       : 'System records could not be read',
        state.systemOk ? 'in this range' : 'retrying'));
    }

    var btn = h('button', {
      class: 'linkish', type: 'button',
      text: state.systemOpen ? 'Hide system records' : 'Show system records'
    });
    btn.addEventListener('click', function () {
      state.systemOpen = !state.systemOpen;
      render();
    });
    el.appendChild(btn);
    show(el, true);
  }

  function chip(iconName, colorVar, label, when) {
    return h('span', { class: 'health-chip' }, [
      icon(iconName, colorVar),
      h('span', { text: label }),
      when ? h('span', { class: 'when', text: when }) : null
    ]);
  }

  function systemCard() {
    var card = makeCard({
      title: 'System records', span2: true,
      sub: 'When the hub was listening, and when it stopped.'
    });
    var rows = state.system.filter(function (e) { return e.start_at; });
    if (!rows.length) {
      card.body.appendChild(miniEmpty('No system records have been uploaded for this range.'));
      return card.root;
    }
    var headers = [{ t: 'When' }, { t: 'Record' }, { t: 'Cot' }, { t: 'Lasted', n: true }, { t: 'Hub' }];
    var body = rows.slice(0, 200).map(function (e) {
      var kindText = { deaf: 'Stopped hearing', heard: 'Hearing again', boot: 'Hub restarted', test: 'Test' }[e.kind] || e.kind;
      var kindIcon = { deaf: 'alert', heard: 'check', boot: 'power', test: 'test' }[e.kind] || 'info';
      var kindColor = e.kind === 'deaf' ? '--critical' : e.kind === 'heard' ? '--good' : '--text-secondary';
      return [
        h('span', {}, [dateTimeAt(e.start_at), h('span', { class: 'sub', text: ago(e.start_at) })]),
        h('span', { class: 'kind-tag' }, [icon(kindIcon, kindColor), h('span', { text: kindText })]),
        e.cot ? cotChip(e.cot) : '—',
        e.duration_s ? dur(e.duration_s) : '—',
        e.device || '—'
      ];
    });
    card.body.appendChild(tableWrap(dataTable(headers, body, 'System records, newest first'), false));
    card.body.appendChild(note('A deaf spell means that cot was not being watched.' +
      (rows.length > 200 ? ' Showing the most recent 200 of ' + rows.length + '.' : '')));
    return card.root;
  }

  /* ------------------------------------------------------- overview cards */

  function renderOverviewGrid(s) {
    var grid = ids['overview-grid'];
    clear(grid);
    if (state.systemOpen) grid.appendChild(systemCard());
    grid.appendChild(dayCard(s));
    grid.appendChild(nightCard(s));
    grid.appendChild(hourCard(s));
    grid.appendChild(weekdayCard(s));
    grid.appendChild(cotCard(s));
    grid.appendChild(recentCard(s));
  }

  function dayCard(s) {
    var series = spanSeries(s.range, s.per_day, 'day');
    var total = series.reduce(function (a, x) { return a + (x.rec ? x.rec.cries : 0); }, 0);
    var card = makeCard({
      title: 'Cries by day', span2: true,
      sub: 'Every day in the range.'
    });
    if (!total) {
      card.body.appendChild(miniEmpty('No cry episodes fall in this range yet.'));
      return card.root;
    }
    var items = series.map(function (x) {
      var c = x.rec ? x.rec.cries : 0;
      return {
        label: dayShort(x.key), value: c,
        plain: dayLong(x.key) + ': ' + c + ' cries',
        tip: {
          title: dayLong(x.key),
          rows: [
            { name: 'Cries', value: num(c) },
            { name: 'Time crying', value: dur(x.rec ? x.rec.seconds : 0) },
            { name: 'Cots', value: x.rec ? cotList(x.rec.cots) : '—' }
          ]
        }
      };
    });
    var rows = series.map(function (x) {
      return [dayShort(x.key), num(x.rec ? x.rec.cries : 0),
        dur(x.rec ? x.rec.seconds : 0), x.rec ? cotList(x.rec.cots) : '—'];
    });
    chartWithTwin(card, 'day', [{ t: 'Day' }, { t: 'Cries', n: true },
      { t: 'Time crying', n: true }, { t: 'Cots' }], rows,
      'Cry episodes per day', function (host) {
        barChart(host, {
          items: items, height: 190, integer: true,
          color: function () { return v('--series-1'); },
          aria: 'Bar chart of cry episodes per day over ' + series.length + ' days, ' +
                total + ' in total. The same numbers are in the table below.',
          fmt: function (x) { return num(x) + ' cries'; }
        });
      });
    card.body.appendChild(note('A day with no bar had no uploaded cries.'));
    return card.root;
  }

  function nightCard(s) {
    var series = spanSeries(s.range, s.per_night, 'night');
    var total = series.reduce(function (a, x) { return a + (x.rec ? x.rec.cries : 0); }, 0);
    var k = s.kpis || {};
    var card = makeCard({
      title: 'Night by night', span2: true,
      sub: '20:00 to 06:00, named by the evening it starts.'
    });
    if (!total) {
      card.body.appendChild(miniEmpty('No night cries in this range.'));
      return card.root;
    }
    var items = series.map(function (x) {
      var c = x.rec ? x.rec.cries : 0;
      return {
        label: nightShort(x.key), value: c,
        plain: nightLong(x.key) + ': ' + c + ' cries',
        tip: {
          title: nightLong(x.key),
          rows: [
            { name: 'Cries', value: num(c) },
            { name: 'Time crying', value: dur(x.rec ? x.rec.seconds : 0) },
            { name: 'Cots', value: x.rec ? cotList(x.rec.cots) : '—' }
          ]
        }
      };
    });
    var rows = series.map(function (x) {
      return [nightShort(x.key), num(x.rec ? x.rec.cries : 0),
        dur(x.rec ? x.rec.seconds : 0), x.rec ? cotList(x.rec.cots) : '—'];
    });
    chartWithTwin(card, 'night', [{ t: 'Night of' }, { t: 'Cries', n: true },
      { t: 'Time crying', n: true }, { t: 'Cots' }], rows,
      'Cry episodes per night, 20:00 to 06:00', function (host) {
        barChart(host, {
          items: items, height: 190, integer: true,
          color: function () { return v('--series-1'); },
          aria: 'Bar chart of cry episodes per night over ' + series.length +
                ' nights, ' + total + ' in total. The same numbers are in the table below.',
          fmt: function (x) { return num(x) + ' cries'; }
        });
      });
    if (k.nights_affected) {
      card.body.appendChild(note(num(k.nights_affected) + ' of ' + series.length +
        ' nights had at least one cry, averaging ' + dec(k.avg_cries_per_night, 1) +
        ' episodes on those nights. Nights with no bar were quiet.'));
    }
    return card.root;
  }

  function hourCard(s) {
    var hours = s.per_hour || [];
    var total = hours.reduce(function (a, x) { return a + (x.cries || 0); }, 0);
    var card = makeCard({
      title: 'When in the day',
      sub: 'Local hour. Shaded hours are night.'
    });
    if (!total) {
      card.body.appendChild(miniEmpty('No cry episodes to place on a clock yet.'));
      return card.root;
    }
    var items = hours.map(function (x) {
      return {
        label: hourLabel(x.hour), value: x.cries,
        plain: hourLabel(x.hour) + ': ' + x.cries + ' cries',
        tip: {
          title: hourLabel(x.hour) + ' · ' + (isNightHour(x.hour) ? 'night' : 'daytime'),
          rows: [
            { name: 'Cries', value: num(x.cries) },
            { name: 'Time crying', value: dur(x.seconds) },
            { name: 'Share', value: pct(100 * x.cries / total) }
          ]
        }
      };
    });
    var rows = hours.map(function (x) {
      return [hourLabel(x.hour), isNightHour(x.hour) ? 'night' : 'day',
        num(x.cries), dur(x.seconds)];
    });
    chartWithTwin(card, 'hour', [{ t: 'Hour' }, { t: 'Part of day' },
      { t: 'Cries', n: true }, { t: 'Time crying', n: true }], rows,
      'Cry episodes by local hour of day', function (host) {
        barChart(host, {
          items: items, height: 178, integer: true, maxBar: 22,
          bands: [{ from: 0, to: NIGHT_END - 1, label: 'night' },
                  { from: NIGHT_START, to: 23, label: 'night' }],
          tick: function (i) { return i % 3 === 0 ? hourLabel(i) : null; },
          color: function (i) { return isNightHour(i) ? v('--series-1') : v('--seq-250'); },
          aria: 'Bar chart of cry episodes by hour of the day. ' + total +
                ' episodes in total. The same numbers are in the table below.',
          fmt: function (x) { return num(x) + ' cries'; }
        });
      });
    card.body.appendChild(h('div', { class: 'legend' }, [
      legendItem(v('--series-1'), 'Night (20:00–06:00)'),
      legendItem(v('--seq-250'), 'Daytime (06:00–20:00)')
    ]));
    return card.root;
  }

  function weekdayCard(s) {
    var wd = s.per_weekday || [];
    var total = wd.reduce(function (a, x) { return a + (x.cries || 0); }, 0);
    var card = makeCard({ title: 'Day of the week' });
    if (!total) {
      card.body.appendChild(miniEmpty('No cry episodes to spread across the week yet.'));
      return card.root;
    }
    var items = wd.map(function (x) {
      return {
        label: weekdayName(x.weekday).slice(0, 3), value: x.cries,
        plain: weekdayName(x.weekday) + ': ' + x.cries + ' cries',
        tip: {
          title: weekdayName(x.weekday),
          rows: [{ name: 'Cries', value: num(x.cries) },
                 { name: 'Share', value: pct(100 * x.cries / total) }]
        }
      };
    });
    var rows = wd.map(function (x) { return [weekdayName(x.weekday), num(x.cries)]; });
    chartWithTwin(card, 'weekday', [{ t: 'Weekday' }, { t: 'Cries', n: true }], rows,
      'Cry episodes by day of the week', function (host) {
        barChart(host, {
          items: items, height: 178, integer: true, maxBar: 34,
          color: function () { return v('--series-1'); },
          aria: 'Bar chart of cry episodes by weekday, ' + total +
                ' in total. The same numbers are in the table below.',
          fmt: function (x) { return num(x) + ' cries'; }
        });
      });
    return card.root;
  }

  function cotCard(s) {
    var list = s.per_cot || [];
    var card = makeCard({
      title: 'By cot', span2: true,
      sub: 'Each cot keeps its own colour.'
    });
    if (!list.length) {
      card.body.appendChild(miniEmpty('No cot has a recorded cry in this range.'));
      return card.root;
    }
    var maxCri = Math.max.apply(null, list.map(function (b) { return b.cries || 0; })) || 1;
    var headers = [{ t: 'Cot' }, { t: 'Cries', n: true }, { t: 'Share' },
      { t: 'Time crying', n: true }, { t: 'Average', n: true },
      { t: 'Longest', n: true }, { t: 'Confidence', n: true }, { t: 'Last heard' }];
    var rows = list.map(function (b) {
      var avg = b.cries ? b.seconds / b.cries : null;
      return [
        cotChip(b.cot),
        num(b.cries),
        h('span', {}, [
          h('span', { class: 'meter' }, [
            h('i', { style: { width: (100 * (b.cries || 0) / maxCri).toFixed(1) + '%' } })
          ]),
          h('span', { text: pct(100 * (b.cries || 0) / (s.kpis.total_cries || 1)) })
        ]),
        dur(b.seconds),
        dur(avg),
        dur(b.max_seconds),
        b.avg_conf === null || b.avg_conf === undefined ? '—' : dec(b.avg_conf, 1) + '%',
        b.last_at ? h('span', {}, [dateTimeAt(b.last_at),
          h('span', { class: 'sub', text: ago(b.last_at) })]) : '—'
      ];
    });
    card.body.appendChild(tableWrap(dataTable(headers, rows, 'Cry record by cot'), false));
    return card.root;
  }

  function recentCard(s) {
    var all = (s.recent || []).slice().reverse();   /* newest first */
    var card = makeCard({
      title: 'The last episodes', span2: true,
      sub: 'Newest first.'
    });
    if (!all.length) {
      card.body.appendChild(miniEmpty('No episodes have been uploaded for this range.'));
      return card.root;
    }
    var shown = state.recentAll ? all : all.slice(0, RECENT_PAGE);
    var maxRms = Math.max.apply(null, all.map(function (r) { return Number(r.peak_rms) || 0; }));

    var toggle = h('button', {
      class: 'toggle', type: 'button', 'aria-pressed': state.recentAll ? 'true' : 'false',
      text: state.recentAll ? 'Show fewer' : 'Show all ' + all.length
    });
    toggle.addEventListener('click', function () {
      state.recentAll = !state.recentAll;
      render();
    });
    card.head.appendChild(toggle);

    var headers = [{ t: 'When' }, { t: 'Cot' }, { t: 'Length', n: true },
      { t: 'Confidence', n: true }, { t: 'Loudness' }];
    var rows = shown.map(function (r) {
      var when;
      if (r.start) {
        when = h('span', {}, [
          dateTimeAt(r.start),
          h('span', { class: 'sub', text: ago(r.start) +
            (r.kind === 'test' ? ' · test record' : '') })
        ]);
      } else {
        when = h('span', {}, [
          'Time unknown',
          h('span', { class: 'sub', text: 'no clock when it happened · record #' + r.seq })
        ]);
      }
      var rms = Number(r.peak_rms);
      var loud = isFinite(rms) && maxRms > 0
        ? h('span', {}, [
            h('span', { class: 'meter' }, [
              h('i', { style: { width: (100 * rms / maxRms).toFixed(1) + '%' } })
            ]),
            h('span', { text: rms.toFixed(3) })
          ])
        : '—';
      return [
        when,
        cotChip(r.cot),
        h('span', {}, [dur(r.duration_s),
          h('span', { class: 'sub', text: (r.windows ? r.windows + ' windows' : 'record #' + r.seq) })]),
        r.peak_conf === null || r.peak_conf === undefined ? '—' : r.peak_conf + '%',
        loud
      ];
    });
    card.body.appendChild(tableWrap(dataTable(headers, rows, 'The most recent cry episodes'), false));

    var untimed = all.filter(function (r) { return !r.start; }).length;
    var foot = 'Showing ' + shown.length + ' of ' + all.length + ' episodes held on this page.';
    if (all.length >= 400) foot += ' The API returns the last 400; the charts above use every record in the range.';
    if (untimed) foot += ' ' + untimed + ' of them have no known time and are listed last.';
    card.body.appendChild(h('div', { class: 'table-foot' }, [h('span', { text: foot })]));
    return card.root;
  }

  /* ------------------------------------------------------------- patterns */

  function renderPatternsGrid(a) {
    var grid = ids['patterns-grid'];
    clear(grid);
    grid.appendChild(durationCard(a));
    grid.appendChild(gapCard(a));
    grid.appendChild(heatmapCard(a));
    grid.appendChild(cotPatternCard(a));
    grid.appendChild(nightsCard(a));
    grid.appendChild(insightCard(a));
  }

  function durationCard(a) {
    var hist = a.duration_hist || [];
    var total = hist.reduce(function (x, b) { return x + (b.count || 0); }, 0);
    var card = makeCard({
      title: 'How long the cries last',
      sub: 'Short on the left, long on the right.'
    });
    if (!total) {
      card.body.appendChild(miniEmpty('No timed episodes to measure yet.'));
      return card.root;
    }
    var items = hist.map(function (b) {
      return {
        label: b.label, value: b.count,
        plain: b.label + ': ' + b.count + ' episodes',
        tip: {
          title: 'Lasted ' + b.label,
          rows: [{ name: 'Episodes', value: num(b.count) },
                 { name: 'Share', value: pct(100 * b.count / total) }]
        }
      };
    });
    var rows = hist.map(function (b) {
      return [b.label, num(b.count), pct(100 * b.count / total)];
    });
    chartWithTwin(card, 'dur', [{ t: 'Length' }, { t: 'Episodes', n: true },
      { t: 'Share', n: true }], rows, 'Episode counts by duration bucket', function (host) {
        barChart(host, {
          items: items, height: 186, integer: true, maxBar: 34,
          color: function () { return v('--series-1'); },
          aria: 'Bar chart of episode counts by how long the cry lasted, ' + total +
                ' episodes in total. The same numbers are in the table below.',
          fmt: function (x) { return num(x) + ' episodes'; }
        });
      });
    return card.root;
  }

  function gapCard(a) {
    var g = a.gaps || {}, c = a.confidence || {};
    var card = makeCard({
      title: 'Between cries, and how sure the model was',
      sub: 'Gaps are measured between consecutive timed episodes.'
    });
    var figs = h('div', { class: 'figures' }, [
      figure('Typical gap', minutes(g.median_min),
        g.count ? 'median of ' + num(g.count) + ' gaps' : 'needs at least two timed episodes'),
      figure('Shortest gap', minutes(g.min_min), g.count ? 'closest pair' : '—'),
      figure('Longest gap', minutes(g.max_min), g.count ? 'longest quiet stretch' : '—'),
      figure('Confidence', c.median === null || c.median === undefined ? '—' : dec(c.median, 1) + '%',
        c.min === null || c.min === undefined ? 'no confidence values yet'
          : 'median · range ' + c.min + '–' + c.max + '%')
    ]);
    card.body.appendChild(figs);
    card.body.appendChild(note('Confidence is the model’s own peak score for an episode, ' +
      'not a measure of how distressed the baby was. A gap only counts between two ' +
      'episodes the hub could put a time on.'));
    return card.root;
  }

  function heatmapCard(a) {
    var cots = (a.per_cot || []).slice();
    var card = makeCard({
      title: 'Hour by cot', span2: true,
      sub: 'Every cell prints its own count.'
    });
    var max = 0;
    cots.forEach(function (c) {
      (c.by_hour || []).forEach(function (x) { if (x > max) max = x; });
    });
    if (!cots.length || !max) {
      card.body.appendChild(miniEmpty('No timed episodes to place on a clock yet.'));
      return card.root;
    }

    var rows = [];
    cots.forEach(function (c) {
      var line = [cotName(c.cot)];
      for (var hh = 0; hh < 24; hh++) line.push(num((c.by_hour || [])[hh] || 0));
      rows.push(line);
    });
    var headers = [{ t: 'Cot' }];
    for (var i = 0; i < 24; i++) headers.push({ t: hourLabel(i), n: true });
    chartWithTwin(card, 'heat', headers, rows, 'Cry episodes by cot and local hour',
      function (host) {
        registerChart(host, function () { drawHeatmap(host, cots, max); });
      });

    var ramp = h('div', { class: 'ramp' }, RAMP.map(function (name) {
      return h('i', { style: { background: v(name) } });
    }));
    card.body.appendChild(h('div', { class: 'scale-legend' }, [
      h('span', { text: '0' }), ramp, h('span', { text: num(max) + ' cries in an hour' })
    ]));
    card.body.appendChild(note('Columns run 00:00 to 23:00 in this device’s time zone. ' +
      'The hours 20:00–06:00 are the night.'));
    return card.root;
  }

  function rampLevel(value, max) {
    if (!(value > 0)) return -1;
    var idx = Math.ceil((value / max) * RAMP.length) - 1;
    return Math.max(0, Math.min(RAMP.length - 1, idx));
  }

  function drawHeatmap(host, cots, max) {
    var W = hostWidth(host);
    if (!W) return;
    clear(host);
    var darkTheme = document.documentElement.getAttribute('data-theme') === 'dark';
    var padL = 62, padR = 6, padT = 16, padB = 22;
    cots.forEach(function (c) {
      padL = Math.max(padL, cotName(c.cot).length * 6.6 + 12);
    });
    var rowH = 26, gap = 3;
    var H = padT + cots.length * rowH + padB;
    var cellW = (W - padL - padR) / 24;

    var svg = svgEl('svg', {
      viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img',
      'aria-label': 'Grid of cry counts by cot and hour of day. Peak ' + max +
                    ' in one hour. The same numbers are in the table below.'
    }, [svgEl('title', { text: 'Cry episodes by cot and local hour' })]);

    /* Mark the night columns with a written bracket, not colour alone. */
    [[0, NIGHT_END - 1], [NIGHT_START, 23]].forEach(function (span) {
      var x0 = padL + cellW * span[0], w = cellW * (span[1] - span[0] + 1);
      svg.appendChild(svgEl('line', {
        x1: x0 + 1, x2: x0 + w - 1, y1: padT - 8, y2: padT - 8,
        stroke: v('--axis'), 'stroke-width': '1'
      }));
      if (w > 40) {
        svg.appendChild(svgEl('text', {
          x: x0 + w / 2, y: padT - 11, 'text-anchor': 'middle',
          'font-size': '9.5', fill: v('--text-muted'), text: 'night'
        }));
      }
    });

    cots.forEach(function (c, r) {
      var y = padT + r * rowH;
      svg.appendChild(svgEl('text', {
        x: padL - 8, y: y + rowH / 2 + 3.5, 'text-anchor': 'end',
        'font-size': '11.5', fill: v('--text-primary'), text: cotName(c.cot)
      }));
      for (var hh = 0; hh < 24; hh++) {
        var val = (c.by_hour || [])[hh] || 0;
        var lvl = rampLevel(val, max);
        var x = padL + cellW * hh;
        var fill = lvl < 0 ? v('--surface-2') : v(RAMP[lvl]);
        svg.appendChild(svgEl('rect', {
          x: x + 0.5, y: y + 0.5, width: Math.max(1, cellW - 1), height: rowH - gap,
          fill: fill, stroke: v('--grid'), 'stroke-width': '0.5', rx: 2
        }));
        if (val > 0 && cellW >= 17) {
          /* The number wears ink, not the cell's colour: white on the deep
           * end of the light ramp, near-black on the bright end of the dark
           * ramp.  The dark ramp runs the other way, so its switch sits one
           * step earlier. */
          var hi = lvl >= (darkTheme ? 3 : 4);
          svg.appendChild(svgEl('text', {
            x: x + cellW / 2, y: y + rowH / 2 + 3, 'text-anchor': 'middle',
            'font-size': '10.5', 'font-weight': '600',
            class: hi ? 'heat-hi' : 'heat-lo', text: String(val)
          }));
        }
        var hit = svgEl('rect', {
          x: x, y: y, width: cellW, height: rowH - gap + 1,
          fill: 'transparent', 'pointer-events': 'all'
        }, [svgEl('title', { text: cotName(c.cot) + ' at ' + hourLabel(hh) + ': ' + val + ' cries' })]);
        (function (cot, hour, value, cotTotal) {
          tipify(hit, function () {
            return {
              title: cotName(cot) + ' · ' + hourLabel(hour) +
                     ' · ' + (isNightHour(hour) ? 'night' : 'daytime'),
              rows: [
                { name: 'Cries', value: num(value), color: cotColor(cot) },
                { name: 'Of this cot', value: cotTotal ? pct(100 * value / cotTotal) : '—' }
              ]
            };
          });
        })(c.cot, hh, val, c.cries);
        svg.appendChild(hit);
      }
    });

    for (var hh2 = 0; hh2 < 24; hh2 += 3) {
      svg.appendChild(svgEl('text', {
        x: padL + cellW * hh2 + cellW / 2, y: H - 6, 'text-anchor': 'middle',
        'font-size': '10.5', fill: v('--text-muted'), text: hourLabel(hh2)
      }));
    }
    host.appendChild(svg);
  }

  function cotPatternCard(a) {
    var list = a.per_cot || [];
    var card = makeCard({
      title: 'Each cot’s pattern', span2: true,
      sub: 'When each cot is usually heard.'
    });
    if (!list.length) {
      card.body.appendChild(miniEmpty('No cot has enough records for a pattern yet.'));
      return card.root;
    }
    var headers = [{ t: 'Cot' }, { t: 'Cries', n: true }, { t: 'Median', n: true },
      { t: 'Longest', n: true }, { t: 'Usual hour' }, { t: 'At night' }];
    var rows = list.map(function (c) {
      var share = c.cries ? 100 * c.night_cries / c.cries : 0;
      return [
        cotChip(c.cot),
        num(c.cries),
        dur(c.median_seconds),
        dur(c.max_seconds),
        h('span', {}, [hourLabel(c.peak_hour),
          h('span', { class: 'sub', text: pct(c.peak_share) + ' of its cries' })]),
        h('span', {}, [num(c.night_cries) + ' of ' + num(c.cries),
          h('span', { class: 'sub', text: pct(share) + ' between 20:00 and 06:00' })])
      ];
    });
    card.body.appendChild(tableWrap(dataTable(headers, rows, 'Pattern by cot'), false));
    return card.root;
  }

  function nightsCard(a) {
    var list = (a.nights || []).slice().reverse();
    var card = makeCard({
      title: 'The nights', span2: true,
      sub: 'Newest first.'
    });
    if (!list.length) {
      card.body.appendChild(miniEmpty('No night has a recorded cry in this range.'));
      return card.root;
    }
    var shown = state.nightsAll ? list : list.slice(0, NIGHTS_PAGE);
    var toggle = h('button', {
      class: 'toggle', type: 'button', 'aria-pressed': state.nightsAll ? 'true' : 'false',
      text: state.nightsAll ? 'Show fewer' : 'Show all ' + list.length
    });
    toggle.addEventListener('click', function () {
      state.nightsAll = !state.nightsAll;
      render();
    });
    card.head.appendChild(toggle);

    var headers = [{ t: 'Night of' }, { t: 'Cries', n: true }, { t: 'Time crying', n: true },
      { t: 'First cry' }, { t: 'Last cry' }, { t: 'Cots' }];
    var rows = shown.map(function (nn) {
      return [
        nightShort(nn.night),
        num(nn.cries),
        dur(nn.seconds),
        clockAt(nn.first),
        clockAt(nn.last),
        cotList(nn.cots)
      ];
    });
    card.body.appendChild(tableWrap(dataTable(headers, rows, 'Cry record night by night'), false));
    card.body.appendChild(h('div', { class: 'table-foot' }, [
      h('span', { text: 'Showing ' + shown.length + ' of ' + list.length +
        ' nights with at least one cry. A night that is not listed was quiet.' })
    ]));
    return card.root;
  }

  function insightCard(a) {
    var list = a.insights || [];
    var card = makeCard({
      title: 'What the record says', span2: true,
      sub: 'From the numbers above.'
    });
    if (!list.length) {
      card.body.appendChild(miniEmpty('Nothing to report yet.'));
      return card.root;
    }
    card.body.appendChild(h('ul', { class: 'insights' }, list.map(function (line) {
      return h('li', {}, [h('span', { class: 'bullet' }), h('span', { text: String(line) })]);
    })));
    return card.root;
  }

  /* --------------------------------------------------------------- chrome */

  function renderControls() {
    var sel = ids.cot;
    var want = ['0'].concat(state.knownCots.map(String));
    var have = Array.prototype.map.call(sel.options, function (o) { return o.value; });
    if (want.join('|') !== have.join('|')) {
      clear(sel);
      sel.appendChild(h('option', { value: '0', text: 'All cots' }));
      state.knownCots.forEach(function (c) {
        sel.appendChild(h('option', { value: String(c), text: cotName(c) }));
      });
    }
    sel.value = String(state.cot);
    if (sel.value !== String(state.cot)) { state.cot = 0; sel.value = '0'; }

    var ds = ids.device;
    var dwant = [''].concat(state.devices.map(function (d) { return d.device; }));
    var dhave = Array.prototype.map.call(ds.options, function (o) { return o.value; });
    if (dwant.join('|') !== dhave.join('|')) {
      clear(ds);
      ds.appendChild(h('option', { value: '', text: 'All hubs' }));
      state.devices.forEach(function (d) {
        ds.appendChild(h('option', { value: d.device, text: hubName(d) }));
      });
    }
    ds.value = state.device;
    if (ds.value !== state.device) { state.device = ''; ds.value = ''; }
    show(ids['device-control'], state.devices.length > 1);

    Array.prototype.forEach.call(ids.range.querySelectorAll('button'), function (b) {
      b.setAttribute('aria-pressed',
        Number(b.getAttribute('data-days')) === state.days ? 'true' : 'false');
    });
  }

  function currentHub() {
    if (state.device) {
      for (var i = 0; i < state.devices.length; i++) {
        if (state.devices[i].device === state.device) return state.devices[i];
      }
    }
    if (state.devices.length === 1) return state.devices[0];
    return (state.summary && state.summary.device) || state.devices[0] || null;
  }

  /* ---------------------------------------------------------------- presence */

  /* Who is here.
   *
   * The hub reports in once a minute whether or not there is anything to
   * record, so this is what answers the question a caregiver opens the
   * dashboard with after a quiet week: was the baby quiet, or did the
   * hub stop?  A record cannot answer that -- it only says what was
   * heard. */
  function presenceHub() {
    var p = state.presence;
    if (!p || !p.hubs || !p.hubs.length) return null;
    var dev = state.device;
    if (!dev) {
      var cur = currentHub();
      dev = cur && cur.device ? cur.device : null;
    }
    if (dev) {
      for (var i = 0; i < p.hubs.length; i++) {
        if (p.hubs[i].device === dev) return p.hubs[i];
      }
    }
    return p.hubs[0];
  }

  function presenceNodes(device) {
    var p = state.presence;
    if (!p || !p.nodes) return [];
    return p.nodes.filter(function (n) {
      return !device || n.device === device;
    });
  }

  function presenceRow(name, word, dotState, detail) {
    return h('span', { class: 'presence-chip', 'data-state': dotState }, [
      h('span', { class: 'presence-dot', 'aria-hidden': 'true' }),
      h('span', { class: 'p-name', text: name }),
      h('span', { class: 'p-word', text: word }),
      detail ? h('span', { class: 'p-detail', text: detail }) : null
    ]);
  }

  /* Who is here, as a strip under the numbers.
   *
   * The hub reports in once a minute whether or not there is anything
   * to record, so this is what answers the question a caregiver opens
   * the dashboard with after a quiet week: was the baby quiet, or did
   * the hub stop?  A record cannot answer that -- it only says what
   * was heard. */
  function renderPresence() {
    var el = ids['presence-strip'];
    if (!el) return;
    clear(el);
    var ph = presenceHub();
    if (!ph) {
      show(el, false);
      return;
    }

    el.appendChild(h('span', { class: 'strip-label', text: 'Here' }));

    var hubBits = [];
    if (ph.fw && ph.fw !== 'demo') hubBits.push('firmware ' + ph.fw);
    if (ph.online) {
      if (!ph.demo) hubBits.push('reported ' + ago(ph.at));
    } else {
      hubBits.push('last report ' + ago(ph.at));
    }
    el.appendChild(presenceRow(
      hubName(ph), ph.online ? 'online' : 'offline',
      ph.online ? 'on' : 'off', hubBits.join(' · ')));

    presenceNodes(ph.device).forEach(function (n) {
      var word, dot;
      if (!n.online) {
        word = 'offline';
        dot = 'off';
      } else if (n.deaf) {
        word = 'not heard';
        dot = 'deaf';
      } else {
        word = 'online';
        dot = 'on';
      }
      var bits = [];
      if (n.online && n.rssi) bits.push(n.rssi + ' dBm');
      if (n.deaf) bits.push('the hub cannot get a window from it');
      if (!n.online) bits.push('not answering');
      el.appendChild(presenceRow(cotName(n.cot), word, dot, bits.join(' · ')));
    });

    show(el, true);
  }

  function renderChrome() {
    var s = state.summary;
    var days = (s && s.range && s.range.days) || state.days;
    var hub = currentHub();

    /* hubmeta */
    var meta, dotState = 'none';
    var ph = presenceHub();
    if (ph) {
      dotState = ph.online ? 'on' : 'off';
      var bits = [hubName(ph), ph.online ? 'online' : 'offline'];
      var pnodes = presenceNodes(ph.device);
      if (pnodes.length) {
        var up = pnodes.filter(function (n) { return n.online; }).length;
        bits.push(up === pnodes.length
          ? pnodes.length + (pnodes.length === 1 ? ' cot online' : ' cots online')
          : up + ' of ' + pnodes.length + ' cots online');
      }
      meta = bits.join(' · ');
    } else if (!state.devices.length) {
      meta = 'No hub has uploaded to this dashboard yet.';
    } else if (state.devices.length > 1 && !state.device) {
      var newest = state.devices.reduce(function (a, d) {
        return (d.last_seen || 0) > (a.last_seen || 0) ? d : a;
      }, state.devices[0]);
      meta = state.devices.length + ' hubs have uploaded · last upload ' + ago(newest.last_seen);
    } else {
      meta = hubName(hub) + (hub && hub.fw ? ' · firmware ' + hub.fw : '') +
        ' · last upload ' + ago(hub && hub.last_seen);
    }
    text(ids['hubmeta-text'], meta);
    ids.hubmeta.setAttribute('data-state', dotState);
    if (hub && hub.device) ids.hubmeta.setAttribute('title', hub.device);
    else ids.hubmeta.removeAttribute('title');

    /* footer */
    if (s && s.range) {
      text(ids['footer-range'], 'Last ' + days + ' days · ' +
        dateAt(s.range.from) + ' to ' + dateAt(s.range.to) + ' · ' +
        (state.cot ? cotName(state.cot) : 'all cots'));
    } else {
      text(ids['footer-range'], 'Last ' + days + ' days');
    }
    text(ids['footer-updated'], state.lastGood
      ? 'Updated ' + clockAt(Math.round(state.lastGood / 1000)) + ' · checks every 30 s'
      : 'Waiting for the first read · checks every 30 s');

    /* scope note */
    var parts = [];
    parts.push('The last ' + days + ' days, ' +
      (state.cot ? cotName(state.cot) + ' only' : 'every cot') +
      '. A night is 20:00–06:00, named by the evening it starts.');

    if (state.devices.length > 1) {
      var line = 'The totals and charts cover every hub.';
      if (state.counts) {
        var bits = state.devices.map(function (d) {
          return hubName(d) + ' ' + num(state.counts.counts[d.device] || 0);
        });
        line += ' Timed records in this range: ' + bits.join(', ') +
          (state.counts.capped ? ' (most recent 2000)' : '') + '.';
      }
      if (state.device) line += ' "' + hubName(hub) + '" is selected above.';
      parts.push(line);
    }

    var deaf = deafNow();
    if (deaf.length) {
      parts.push(deaf.map(function (d) {
        return cotName(d.cot) + ' has not been heard since ' + clockAt(d.since) +
          ' (' + ago(d.since) + ')';
      }).join('; ') + ' — that cot was not being watched.');
    }

    text(ids['scope-note'], parts.join(' '));
    show(ids['scope-note'], true);
  }

  function setEmptyDetail(node, msg) {
    if (!node) return;
    if (!pristine[node.id || node.className]) pristine[node.id || node.className] = node.textContent;
    node.textContent = msg || pristine[node.id || node.className];
  }

  function renderOverview() {
    var s = state.summary;
    var empty = ids['empty-overview'];
    var body = ids['overview-body'];
    var emptyHead = empty.querySelector('h2');
    if (!pristine.head) pristine.head = emptyHead ? emptyHead.textContent : '';

    if (!s) {
      if (emptyHead) emptyHead.textContent = 'Cannot reach the dashboard service';
      setEmptyDetail(ids['empty-overview-detail'],
        'The page could not read the record from the service. It keeps trying every 30 seconds ' +
        'and will fill in by itself once the service answers.');
      show(empty, true);
      show(body, false);
      return;
    }

    var hasCries = (s.kpis && s.kpis.total_cries > 0) || (s.recent || []).length > 0;
    var hasSystem = state.system.length > 0;

    if (!hasCries && !hasSystem) {
      if (emptyHead) emptyHead.textContent = pristine.head;
      var hub = currentHub();
      if (hub) {
        setEmptyDetail(ids['empty-overview-detail'],
          hubName(hub) + ' last uploaded ' + ago(hub.last_seen) + ', but no cry episodes fall ' +
          'in the last ' + ((s.range && s.range.days) || state.days) + ' days' +
          (state.cot ? ' for ' + cotName(state.cot) : '') +
          '. Try a longer range, or another cot.');
      } else {
        setEmptyDetail(ids['empty-overview-detail'], null);
      }
      show(empty, true);
      show(body, false);
      return;
    }

    if (emptyHead) emptyHead.textContent = pristine.head;
    show(empty, false);
    show(body, true);
    renderKpis(s);
    renderUntimed(s);
    renderSystemStrip();
    renderOverviewGrid(s);
  }

  function renderPatterns() {
    var a = state.analytics;
    var empty = ids['empty-patterns'];
    var body = ids['patterns-body'];
    var emptyHead = empty.querySelector('h2');
    var emptyP = empty.querySelector('p');
    if (!pristine.phead) pristine.phead = emptyHead ? emptyHead.textContent : '';
    if (!pristine.pp) pristine.pp = emptyP ? emptyP.textContent : '';

    var total = a ? (a.duration_hist || []).reduce(function (x, b) { return x + (b.count || 0); }, 0) : 0;

    if (!a || !total) {
      if (emptyHead) emptyHead.textContent = a ? pristine.phead : 'Patterns could not be read';
      if (emptyP) {
        emptyP.textContent = a ? pristine.pp
          : 'The dashboard service did not answer the patterns request. The page keeps trying ' +
            'every 30 seconds. The Overview is unaffected.';
      }
      show(empty, true);
      show(body, false);
      return;
    }

    if (emptyHead) emptyHead.textContent = pristine.phead;
    if (emptyP) emptyP.textContent = pristine.pp;
    show(empty, false);
    show(body, true);

    var days = (a.range && a.range.days) || state.days;
    var scopeParts = ['Patterns cover the last ' + days + ' days across every cot and every hub.'];
    if (state.cot) {
      scopeParts.push('The cot filter above applies to the Overview only — ' +
        'the patterns API has no cot filter, so ' + cotName(state.cot) +
        ' is not singled out here.');
    }
    var s = state.summary;
    if (s && s.kpis && total !== s.kpis.total_cries) {
      scopeParts.push('This tab counts ' + num(total) + ' episodes against the Overview’s ' +
        num(s.kpis.total_cries) + ': patterns include the hub’s test records and ignore ' +
        'the cot filter, while the Overview counts cries only.');
    }
    scopeParts.push('Episodes the hub could not put a time on are left out of the patterns entirely.');
    text(ids['patterns-scope'], scopeParts.join(' '));
    show(ids['patterns-scope'], true);

    renderPatternsGrid(a);
  }

  function render() {
    tipHide();
    charts = [];
    renderControls();
    renderChrome();
    /* Who is here is drawn from the presence alone, so it is drawn
     * whatever the record has to show -- including nothing at all,
     * which is when the caregiver most wants to know. */
    renderPresence();
    renderOverview();
    renderPatterns();
    drawCharts();
  }

  /* ----------------------------------------------------------------- tabs */

  function setTab(name) {
    state.tab = name;
    var over = name === 'overview';
    ids['tab-overview'].setAttribute('aria-selected', over ? 'true' : 'false');
    ids['tab-patterns'].setAttribute('aria-selected', over ? 'false' : 'true');
    show(ids['view-overview'], over);
    show(ids['view-patterns'], !over);
    tipHide();
    drawCharts();
  }

  /* ----------------------------------------------------------------- boot */

  function boot() {
    ID_LIST.forEach(function (id) { ids[id] = document.getElementById(id); });
    if (!ids.kpis || !ids['overview-grid']) return;

    ids['tab-overview'].addEventListener('click', function () { setTab('overview'); });
    ids['tab-patterns'].addEventListener('click', function () { setTab('patterns'); });

    var tabs = [ids['tab-overview'], ids['tab-patterns']];
    tabs.forEach(function (btn, i) {
      btn.addEventListener('keydown', function (ev) {
        var k = ev.key, next = -1;
        if (k === 'ArrowRight') next = (i + 1) % tabs.length;
        else if (k === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
        else if (k === 'Home') next = 0;
        else if (k === 'End') next = tabs.length - 1;
        if (next < 0) return;
        ev.preventDefault();
        tabs[next].focus();
        setTab(next === 0 ? 'overview' : 'patterns');
      });
    });

    /* The theme.  The inline script in <head> has already stamped the
     * saved choice (or the OS setting) before first paint; this keeps the
     * button's label honest, remembers a deliberate choice, and follows
     * the OS live while no choice has been made.  Charts are redrawn so
     * the heatmap's cell numbers pick the right ink for the new ramp. */
    function themeName() {
      return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }
    function themeLabel() {
      if (ids.theme) {
        ids.theme.setAttribute('aria-label',
          themeName() === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
      }
    }
    themeLabel();
    if (ids.theme) {
      ids.theme.addEventListener('click', function () {
        var next = themeName() === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem('crynet-theme', next); } catch (e) { /* private mode */ }
        themeLabel();
        drawCharts();
      });
    }
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var followOS = function () {
        var stored = null;
        try { stored = localStorage.getItem('crynet-theme'); } catch (e) { /* keep null */ }
        if (stored === 'light' || stored === 'dark') return;
        document.documentElement.setAttribute('data-theme', mq.matches ? 'dark' : 'light');
        themeLabel();
        drawCharts();
      };
      if (mq.addEventListener) mq.addEventListener('change', followOS);
    }

    ids.range.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('button[data-days]') : null;
      if (!btn) return;
      var d = Number(btn.getAttribute('data-days'));
      if (!isFinite(d) || d === state.days) return;
      state.days = d;
      state.recentAll = false;
      state.nightsAll = false;
      renderControls();
      refresh();
    });

    ids.cot.addEventListener('change', function () {
      state.cot = Number(ids.cot.value) || 0;
      state.recentAll = false;
      refresh();
    });

    ids.device.addEventListener('change', function () {
      state.device = ids.device.value || '';
      render();
    });

    var resizeTimer = null;
    window.addEventListener('resize', function () {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () { tipHide(); drawCharts(); }, 160);
    });
    window.addEventListener('scroll', tipHide, true);

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) return;
      /* Coming back to the tab is the moment the caregiver most wants
       * an answer, so the presence is asked for at once -- a browser
       * may have throttled the timers while the tab was in the
       * background. */
      refreshPresence();
      if (Date.now() - state.lastGood > POLL_MS) refresh();
      else drawCharts();
    });

    /* Nothing may escape as an unhandled rejection. */
    window.addEventListener('unhandledrejection', function (ev) {
      ev.preventDefault();
      setConn('stale', 'Offline · retrying every 30 s');
    });

    setTab('overview');
    setConn('loading', 'Connecting');
    refresh();
    refreshPresence();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();