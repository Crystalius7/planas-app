/* app.js - the dashboard. Talks to the local connector (http://127.0.0.1:8765) or, later, the hosted API; without either
   it runs in demo mode on sample data so the product can be shown (and looked at) before an account exists.
   No framework, no third-party script: the page's CSP allows only itself and the connector. */
(() => {
  'use strict';
  const CONNECTOR = 'http://127.0.0.1:8765';
  const CLOUD = (document.documentElement.dataset.api || '').replace(/\/$/, '');   // set at deploy time; empty on the demo
  const LANGS = { en: 'English', lt: 'Lietuvių', ru: 'Русский', pl: 'Polski', de: 'Deutsch', es: 'Español', fr: 'Français', pt: 'Português', it: 'Italiano', uk: 'Українська',
    lv: 'Latviešu', et: 'Eesti', fi: 'Suomi', sv: 'Svenska', nb: 'Norsk', da: 'Dansk', nl: 'Nederlands', cs: 'Čeština', sk: 'Slovenčina', hu: 'Magyar', ro: 'Română', bg: 'Български',
    el: 'Ελληνικά', hr: 'Hrvatski', sl: 'Slovenščina', sr: 'Srpski', tr: 'Türkçe', ar: 'العربية', he: 'עברית', fa: 'فارسی', hi: 'हिन्दी', bn: 'বাংলা', ur: 'اردو', id: 'Bahasa Indonesia',
    vi: 'Tiếng Việt', th: 'ไทย', ja: '日本語', zh: '中文', ko: '한국어' };
  const HAS_FILE = ['en', 'lt', 'ru', 'pl', 'de', 'es', 'fr', 'pt', 'it', 'uk'];
  const RTL = ['ar', 'he', 'fa', 'ur'];
  // mirror of engine/studycore/grades.py (best first)
  const SCALES = {
    pct: { name: 'Percent', g: ['100', '95', '90', '85', '80', '75', '70', '65', '60', '55', '50', '45', '40'], good: '80' },
    lt10: { name: 'Lithuania 1-10', g: ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1'], good: '8' },
    lv10: { name: 'Latvia 1-10', g: ['10', '9', '8', '7', '6', '5', '4', '3', '2', '1'], good: '8' },
    ee5: { name: 'Estonia 1-5', g: ['5', '4', '3', '2', '1'], good: '4' },
    pl6: { name: 'Poland 1-6', g: ['6', '5', '4', '3', '2', '1'], good: '4' },
    de6: { name: 'Germany 1-6 (1 best)', g: ['1', '2', '3', '4', '5', '6'], good: '2' },
    at5: { name: 'Austria 1-5 (1 best)', g: ['1', '2', '3', '4', '5'], good: '2' },
    ch6: { name: 'Switzerland 1-6', g: ['6', '5.5', '5', '4.5', '4', '3.5', '3', '2', '1'], good: '5' },
    fr20: { name: 'France 0-20', g: Array.from({ length: 21 }, (_, i) => String(20 - i)), good: '14' },
    es10: { name: 'Spain 0-10', g: Array.from({ length: 11 }, (_, i) => String(10 - i)), good: '8' },
    it10: { name: 'Italy 0-10', g: Array.from({ length: 11 }, (_, i) => String(10 - i)), good: '8' },
    pt20: { name: 'Portugal 0-20', g: Array.from({ length: 21 }, (_, i) => String(20 - i)), good: '14' },
    nl10: { name: 'Netherlands 1-10', g: Array.from({ length: 10 }, (_, i) => String(10 - i)), good: '8' },
    ua12: { name: 'Ukraine 1-12', g: Array.from({ length: 12 }, (_, i) => String(12 - i)), good: '9' },
    ru5: { name: '5-point (2-5)', g: ['5', '4', '3', '2'], good: '4' },
    us: { name: 'US letters', g: ['A', 'B', 'C', 'D', 'F'], good: 'B' },
    uk9: { name: 'UK GCSE 9-1', g: ['9', '8', '7', '6', '5', '4', '3', '2', '1', 'U'], good: '7' },
    fi10: { name: 'Finland 4-10', g: ['10', '9', '8', '7', '6', '5', '4'], good: '8' },
    se: { name: 'Sweden A-F', g: ['A', 'B', 'C', 'D', 'E', 'F'], good: 'B' },
    tr100: { name: 'Turkey 0-100', g: ['100', '95', '90', '85', '80', '75', '70', '65', '60', '55', '50'], good: '85' },
  };
  const COUNTRY_SCALE = { LT: 'lt10', LV: 'lv10', EE: 'ee5', PL: 'pl6', DE: 'de6', AT: 'at5', CH: 'ch6', FR: 'fr20', ES: 'es10', IT: 'it10', PT: 'pt20', BR: 'es10', NL: 'nl10', UA: 'ua12', RU: 'ru5', US: 'us', CA: 'us', GB: 'uk9', FI: 'fi10', SE: 'se', TR: 'tr100' };

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const S = { api: null, demo: true, lang: 'en', dict: {}, en: {}, settings: {}, status: {}, assessments: { upcoming: [], completed: [] }, material: [], notifs: [], est: null, country: null };

  // ---------- i18n ----------
  const get = (o, path) => path.split('.').reduce((a, k) => (a && a[k] != null ? a[k] : undefined), o);
  const t = (key, vars = {}) => {
    let s = get(S.dict, key); if (s === undefined) s = get(S.en, key); if (s === undefined) return key;
    return String(s).replace(/\{(\w+)\}/g, (_, k) => (vars[k] != null ? vars[k] : `{${k}}`));
  };
  async function loadLang(lang) {
    const code = HAS_FILE.includes(lang) ? lang : 'en';
    if (!Object.keys(S.en).length) S.en = await (await fetch('../i18n/en.json')).json();
    S.dict = code === 'en' ? S.en : await (await fetch(`../i18n/${code}.json`)).json().catch(() => S.en);
    S.lang = lang;
    document.documentElement.lang = lang;
    document.documentElement.dir = RTL.includes(lang) ? 'rtl' : 'ltr';
    try { localStorage.setItem('planas.lang', lang); } catch (e) { /* private mode */ }
    $$('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n, { year: new Date().getFullYear() }); });
    $$('[data-i18n-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    $$('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    $('#detected').textContent = S.country ? t('settings.detected', { lang: LANGS[lang] || lang }) : '';
    renderAll();
  }
  async function pickLang() {
    let saved = null; try { saved = localStorage.getItem('planas.lang'); } catch (e) { /* ignore */ }
    if (saved && LANGS[saved]) return saved;
    if (CLOUD) { try { const g = await (await fetch(CLOUD + '/geo')).json(); S.country = g.country; if (g.lang && LANGS[g.lang]) return g.lang; } catch (e) { /* offline */ } }
    const nav = (navigator.language || 'en').slice(0, 2).toLowerCase();
    return LANGS[nav] ? nav : 'en';
  }

  // ---------- api ----------
  async function api(path, opts = {}) {
    if (S.demo) return demoApi(path, opts);
    const r = await fetch(S.api + path, { ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) }, body: opts.body ? JSON.stringify(opts.body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }
  async function detect() {
    try { const r = await fetch(CONNECTOR + '/status', { signal: AbortSignal.timeout(1500) }); if (r.ok) { S.api = CONNECTOR; S.demo = false; S.status = await r.json(); return; } } catch (e) { /* not running */ }
    S.demo = true; S.status = DEMO.status;
  }

  // ---------- demo ----------
  const day = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  const DEMO = {
    status: { version: 'demo', moodle: { connected: false }, courses: ['Physics 11', 'Biology 11', 'English B2'], lastScan: { at: new Date().toISOString(), changes: 2 }, unread: 2 },
    settings: { minutesPerDay: 15, maxMinutesPerDay: 20, targetGrade: '8', gradeScale: 'lt10', factCheck: false, shareData: false, uiLang: 'en', digest: { provider: 'none' } },
    assessments: [
      { id: 'phys-1', subject: 'physics', subjectName: 'Physics 11', title: 'Kinematics test', kind: 'test', date: day(9), time: '09:00', confidence: 'confirmed', topics: ['Kinematics'], coverage: 0.86 },
      { id: 'bio-1', subject: 'biology', subjectName: 'Biology 11', title: 'Cell biology', kind: 'test', date: day(16), time: null, confidence: 'estimated', topics: ['The cell', 'Membranes'], coverage: 0.9 },
      { id: 'en-1', subject: 'english', subjectName: 'English B2', title: 'Module 1 test', kind: 'online-test', date: day(5), time: null, confidence: 'estimated', topics: ['Module 1'], coverage: 1 },
      { id: 'bio-0', subject: 'biology', subjectName: 'Biology 11', title: 'Diagnostic test', kind: 'test', date: day(-4), confidence: 'confirmed', topics: [], done: true, doneAt: day(-4) },
    ],
    material: [
      { course: 'Physics 11', section: 'Kinematics', name: 'Lesson 1 slides.pptx', module: 'resource', verdict: 'used', topic: 'Kinematics' },
      { course: 'Physics 11', section: 'Kinematics', name: 'Free fall (video)', module: 'url', verdict: 'used', topic: 'Kinematics', note: 'frames + transcript' },
      { course: 'Physics 11', section: 'Kinematics', name: 'Practice problems.pdf', module: 'resource', verdict: 'used', topic: 'Kinematics' },
      { course: 'Biology 11', section: 'The cell', name: 'Cell structure.docx', module: 'resource', verdict: 'used', topic: 'The cell' },
      { course: 'Biology 11', section: 'The cell', name: 'Membrane transport (page)', module: 'page', verdict: 'checked', topic: 'Membranes' },
      { course: 'Biology 11', section: 'The cell', name: 'Old syllabus 2019.pdf', module: 'resource', verdict: 'skip', topic: null, note: 'teacher marked as archive' },
      { course: 'English B2', section: 'Module 1', name: 'Grammar bank', module: 'book', verdict: 'used', topic: 'Module 1' },
      { course: 'Biology 11', section: 'The cell', name: 'NEW: Mitochondria worksheet.pdf', module: 'resource', verdict: 'not-yet', topic: null },
    ],
    notifs: [{ kind: 'file', course: 'Biology 11', text: 'Mitochondria worksheet.pdf', at: new Date().toISOString(), section: 'The cell', courseId: 2 }, { kind: 'deadline', course: 'English B2', text: 'Module 1 test closes', when: day(5) + 'T23:59', at: new Date().toISOString() }],
    reports: [],
  };
  function demoEstimate(minutes, grade) {
    const sc = SCALES[S.settings.gradeScale || 'lt10']; const idx = sc.g.indexOf(String(grade)); const cov = Math.min(1, Math.max(0.5, 1 - idx * 0.08));
    const minMinutes = Math.round(4 + cov * 12); const ideal = 16; const ratio = minMinutes ? Math.min(1, minutes / minMinutes) : 1;
    const est = (c) => { const score = 0.15 + 0.8 * c; const i = Math.max(0, Math.min(sc.g.length - 1, Math.round((1 - score) * (sc.g.length - 1)))); return { grade: sc.g[i], low: sc.g[Math.min(sc.g.length - 1, i + 1)], high: sc.g[Math.max(0, i - 1)], coverage: c }; };
    const forced = Math.max(minutes, minMinutes); const e = est(cov * ratio); const target = est(cov);
    return { minutesChosen: minutes, minMinutes, minutesForced: forced, forced: forced > minutes, idealMinutes: ideal, estimate: e, estimateAtTarget: target, gradeDropSteps: Math.max(0, sc.g.indexOf(e.grade) - sc.g.indexOf(target.grade)), minutesSavedPerDay: Math.max(0, ideal - forced), minutesSavedTotal: Math.max(0, ideal - forced) * 16, daysHorizon: 16, scale: S.settings.gradeScale, targetGrade: String(grade) };
  }
  async function demoApi(path, opts) {
    const b = opts.body || {};
    if (path === '/settings') { if (opts.method === 'POST') Object.assign(DEMO.settings, b); return DEMO.settings; }
    if (path === '/assessments') {
      if (opts.method === 'POST') {
        if (b.op === 'add') { DEMO.assessments.push({ id: 'x' + Date.now(), subject: b.subject, subjectName: b.subject, title: b.title, kind: b.kind, date: b.date, time: b.time || null, confidence: 'confirmed', topics: [] }); }
        const a = DEMO.assessments.find((x) => x.id === b.id);
        if (a && b.op === 'done') { a.done = true; a.doneAt = day(0); } if (a && b.op === 'undone') { a.done = false; }
        if (a && b.op === 'edit') { a.date = b.date || a.date; a.time = b.time ?? a.time; a.confidence = 'confirmed'; if (b.title) a.title = b.title; }
        if (b.op === 'delete') DEMO.assessments = DEMO.assessments.filter((x) => x.id !== b.id);
      }
      return { upcoming: DEMO.assessments.filter((x) => !x.done), completed: DEMO.assessments.filter((x) => x.done) };
    }
    if (path.startsWith('/estimate')) { const q = new URLSearchParams(path.split('?')[1] || ''); return demoEstimate(Number(q.get('minutes') || DEMO.settings.minutesPerDay), q.get('grade') || DEMO.settings.targetGrade); }
    if (path === '/material') return { items: DEMO.material };
    if (path === '/notifications') return { items: DEMO.notifs };
    if (path === '/notifications/read') { DEMO.notifs = []; return { ok: true }; }
    if (path === '/material/add') { DEMO.material.forEach((m) => { if (m.verdict === 'not-yet') { m.verdict = 'used'; m.topic = 'The cell'; } }); DEMO.notifs = DEMO.notifs.filter((n) => n.kind !== 'file'); return { routed: 1, unrouted: [] }; }
    if (path === '/plan') return { ok: true, days: 30 };
    if (path === '/scan') return { at: new Date().toISOString(), changes: 0 };
    if (path === '/report') { DEMO.reports.push(b); return { ok: true }; }
    if (path === '/corrections') return { items: [{ topic: 'The cell', was: 'Mitochondria have no DNA', now: 'Mitochondria carry their own circular DNA (mtDNA)', where: 'Cell structure.docx p. 4', basis: 'textbook-level fact' }] };
    if (path === '/status') return DEMO.status;
    return {};
  }

  // ---------- rendering ----------
  const fmtDate = (iso) => { const d = new Date(iso + 'T00:00'); return d.toLocaleDateString(S.lang, { day: 'numeric', month: 'short' }); };
  const daysLeft = (iso) => Math.round((new Date(iso + 'T00:00') - new Date(new Date().toDateString())) / 86400000);

  function renderMode() {
    $('#mode').textContent = S.demo ? t('app.demo') : t('app.connected');
    $('#openHub').href = S.demo ? 'demo-hub.html' : S.api + '/hub';
    const hub = $('#hub'); hub.hidden = false; hub.src = S.demo ? 'demo-hub.html' : S.api + '/hub';
  }
  function renderNextUp() {
    const up = S.assessments.upcoming.slice().sort((a, b) => a.date.localeCompare(b.date)).slice(0, 3);
    $('#nextUp').innerHTML = up.map((a) => {
      const n = daysLeft(a.date); const cov = a.coverage != null ? (typeof a.coverage === 'number' ? a.coverage : (a.coverage.weighted || 0)) : null;
      return `<div class="card"><div class="sub">${esc(a.subjectName || a.subject)} · ${t('tests.kinds.' + a.kind)}</div><div class="when">${n === 0 ? t('common.today') : n === 1 ? t('common.tomorrow') : t('today.daysLeft', { n })}</div><div>${esc(a.title)}</div><div class="sub">${fmtDate(a.date)}${a.time ? ' ' + (a.confidence === 'estimated' ? '~' : '') + a.time : ''} <span class="tag ${a.confidence}">${t('tests.confidence.' + a.confidence)}</span></div>${cov != null ? `<div class="bar"><i data-w="${Math.round(cov * 100)}"></i></div><div class="sub">${t('tests.coverage', { pct: Math.round(cov * 100) })}</div>` : ''}</div>`;
    }).join('') || `<div class="card muted">${t('today.noPlan')}</div>`;
    $$('#nextUp .bar > i').forEach((i) => { i.style.width = i.dataset.w + '%'; });   // CSSOM, not an inline style attribute (CSP style-src 'self')
  }
  function renderTests() {
    const li = (a, done) => `<li data-id="${esc(a.id)}"><div class="date">${fmtDate(a.date)}<small>${a.time ? (a.confidence === 'estimated' ? '~' : '') + a.time : ''} ${done ? '' : t('today.daysLeft', { n: daysLeft(a.date) })}</small></div><div><div class="title">${esc(a.title)}</div><div class="meta">${esc(a.subjectName || a.subject)} · ${t('tests.kinds.' + (a.kind || 'test'))} · <span class="tag ${a.confidence}">${t('tests.confidence.' + (a.confidence || 'confirmed'))}</span>${(a.topics || []).length ? ' · ' + t('tests.topics') + ': ' + esc((a.topics || []).join(', ')) : ''}</div></div><div class="acts">${done ? `<button class="btn" data-act="undone">${t('tests.undo')}</button>` : `<button class="btn primary" data-act="done">✓ ${t('tests.done')}</button><button class="btn" data-act="edit">${t('tests.edit')}</button>`}<button class="btn" data-act="delete">${t('tests.delete')}</button></div></li>`;
    const up = S.assessments.upcoming.slice().sort((a, b) => a.date.localeCompare(b.date));
    const done = S.assessments.completed.slice().sort((a, b) => b.date.localeCompare(a.date));
    $('#upcoming').innerHTML = up.map((a) => li(a, false)).join('') || `<li class="muted">${t('tests.emptyUpcoming')}</li>`;
    $('#completed').innerHTML = done.map((a) => li(a, true)).join('') || `<li class="muted">${t('tests.emptyCompleted')}</li>`;
    $('#completedCount').textContent = done.length;
  }
  function renderMaterial() {
    const q = ($('#materialFilter').value || '').toLowerCase();
    const rows = S.material.filter((m) => !q || `${m.course} ${m.section} ${m.name} ${m.topic || ''}`.toLowerCase().includes(q));
    $('#materialTable tbody').innerHTML = rows.map((m) => `<tr><td>${esc(m.course)}<div class="muted small">${esc(m.section || '')}</div></td><td>${esc(m.name)}<div class="muted small">${esc(m.module || '')}${m.note ? ' · ' + esc(m.note) : ''}</div></td><td><span class="v v-${m.verdict}">${t('material.verdicts.' + m.verdict)}</span></td><td>${esc(m.topic || '')}</td></tr>`).join('');
    const fresh = S.material.filter((m) => m.verdict === 'not-yet').length;
    $('#newMaterial').hidden = !fresh; $('#newMaterial').textContent = fresh ? t('material.newMaterial', { n: fresh }) : '';
    $('#addMaterial').hidden = !fresh;
    const used = [...new Set(S.material.filter((m) => m.verdict === 'used').map((m) => m.topic).filter(Boolean))];
    $('#digestOf').textContent = used.length ? t('material.digestOf', { list: used.join(', ') }) : '';
    $('#lastScan').textContent = S.status.lastScan && S.status.lastScan.at ? t('material.lastScan', { t: new Date(S.status.lastScan.at).toLocaleString(S.lang) }) : '';
  }
  function renderNotifs() {
    $('#bellCount').hidden = !S.notifs.length; $('#bellCount').textContent = S.notifs.length;
    $('#notifList').innerHTML = S.notifs.map((n) => `<li><div><span class="tag">${t('notifications.kinds.' + n.kind)}</span> <b>${esc(n.text || '')}</b><div class="meta">${esc(n.course || '')}${n.when ? ' · ' + esc(n.when.replace('T', ' ')) : ''}${n.was ? ' (' + esc(n.was) + ' → )' : ''}</div></div></li>`).join('') || `<li class="muted">${t('notifications.none')}</li>`;
  }
  function renderSliders() {
    const key = S.settings.gradeScale || 'pct'; const sc = SCALES[key] || SCALES.pct;
    const sel = $('#scale'); sel.innerHTML = Object.entries(SCALES).map(([k, v]) => `<option value="${k}" ${k === key ? 'selected' : ''}>${v.name}</option>`).join('');
    const g = $('#grade'); g.min = 0; g.max = sc.g.length - 1;
    const target = String(S.settings.targetGrade || sc.good); const idx = sc.g.indexOf(target);
    g.value = sc.g.length - 1 - (idx < 0 ? sc.g.indexOf(sc.good) : idx);
    $('#gradeOut').textContent = sc.g[sc.g.length - 1 - Number(g.value)];
    $('#minutes').value = S.settings.minutesPerDay || 15; $('#minutesOut').textContent = $('#minutes').value;
    refreshEstimate();
  }
  let estTimer = null;
  function refreshEstimate() {
    clearTimeout(estTimer);
    estTimer = setTimeout(async () => {
      const sc = SCALES[$('#scale').value] || SCALES.pct; const grade = sc.g[sc.g.length - 1 - Number($('#grade').value)];
      const minutes = Number($('#minutes').value);
      try { S.est = await api(`/estimate?minutes=${minutes}&grade=${encodeURIComponent(grade)}`); } catch (e) { S.est = null; return; }
      const e = S.est; const hint = $('#minHint');
      if (e.forced) { $('#minutes').value = Math.min(90, Math.ceil(e.minutesForced / 5) * 5); $('#minutesOut').textContent = $('#minutes').value; hint.textContent = t('sliders.forced', { n: e.minutesForced }); hint.className = 'hint forced'; }
      else { hint.textContent = t('sliders.minimum', { n: e.minMinutes }); hint.className = 'hint'; }
      const est = e.estimate || {};
      const stats = [
        `<div class="stat"><span class="muted">${t('sliders.note')}</span><b>${esc(est.grade || '-')}</b><span class="muted">${t('sliders.estimate', { g: est.grade, lo: est.low, hi: est.high })}</span></div>`,
        e.gradeDropSteps > 0 ? `<div class="stat drop"><b>−${e.gradeDropSteps}</b><span class="muted">${t('sliders.drop', { n: e.gradeDropSteps })}</span></div>` : `<div class="stat ok"><b>✓</b><span class="muted">${t('sliders.noDrop')}</span></div>`,
        e.minutesSavedPerDay > 0 ? `<div class="stat ok"><b>${e.minutesSavedPerDay} ${t('common.min')}</b><span class="muted">${t('sliders.saved', { m: e.minutesSavedPerDay, t: e.minutesSavedTotal })}</span></div>` : (e.minutesForced > e.idealMinutes && e.idealMinutes > 0 ? `<div class="stat"><b>+${e.minutesForced - e.idealMinutes} ${t('common.min')}</b><span class="muted">${t('sliders.over', { m: e.minutesForced - e.idealMinutes })}</span></div>` : ''),
        e.idealMinutes ? `<div class="stat"><b>${e.idealMinutes} ${t('common.min')}</b><span class="muted">${t('sliders.ideal', { n: e.idealMinutes })}</span></div>` : '',
      ];
      $('#readout').innerHTML = stats.join('');
    }, 120);
  }
  function renderSettings() {
    $('#factCheck').checked = !!S.settings.factCheck; $('#shareData').checked = !!S.settings.shareData;
    $('#provider').value = (S.settings.digest && S.settings.digest.provider) || 'none';
    $('#site').value = (S.status.moodle && S.status.moodle.site) || '';
    $('#planLine').textContent = S.demo ? t('settings.plan.none') : t('settings.plan.' + (S.status.plan || 'none'), { d: S.status.trialEndsAt || '' });
    $('#connectMsg').textContent = S.status.moodle && S.status.moodle.connected ? `${S.status.moodle.site} (${S.status.moodle.route})` : '';
    api('/corrections').then((r) => { $('#corrections').innerHTML = (r.items || []).map((c) => `<li><div><b>${esc(c.was)}</b> → ${esc(c.now)}<div class="meta">${esc(c.topic || '')} · ${esc(c.where || '')} · ${esc(c.basis || '')}</div></div></li>`).join('') || `<li class="muted">—</li>`; }).catch(() => {});
    renderRouteFields();
  }
  function renderRouteFields() {
    const r = ($('input[name=route]:checked') || {}).value;
    $('#routeFields').innerHTML = r === 'password' ? `<label><span>Username</span><input id="username" autocomplete="username"></label><label><span>Password</span><input id="password" type="password" autocomplete="current-password"></label>` : r === 'token' ? `<label><span>Token</span><input id="token"></label>` : `<p class="muted small">Install the browser extension, open your Moodle in a tab and press “Collect from this tab”.</p>`;
  }
  function renderAll() { renderMode(); renderNextUp(); renderTests(); renderMaterial(); renderNotifs(); renderSliders(); renderSettings(); }
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------- data ----------
  async function loadAll() {
    S.settings = await api('/settings'); S.assessments = await api('/assessments'); S.material = (await api('/material')).items || []; S.notifs = (await api('/notifications')).items || [];
  }

  // ---------- events ----------
  function bind() {
    $$('.tab').forEach((b) => b.addEventListener('click', () => { $$('.tab').forEach((x) => x.setAttribute('aria-selected', x === b)); $$('.view').forEach((v) => { v.hidden = v.dataset.view !== b.dataset.view; }); }));
    $('#lang').addEventListener('change', (e) => loadLang(e.target.value));
    $('#bell').addEventListener('click', () => { $('#drawer').hidden = !$('#drawer').hidden; });
    $('#markRead').addEventListener('click', async () => { await api('/notifications/read', { method: 'POST', body: {} }); S.notifs = []; renderNotifs(); $('#drawer').hidden = true; });
    $('#minutes').addEventListener('input', () => { $('#minutesOut').textContent = $('#minutes').value; refreshEstimate(); });
    $('#grade').addEventListener('input', () => { const sc = SCALES[$('#scale').value] || SCALES.pct; $('#gradeOut').textContent = sc.g[sc.g.length - 1 - Number($('#grade').value)]; refreshEstimate(); });
    $('#scale').addEventListener('change', async () => { S.settings.gradeScale = $('#scale').value; S.settings.targetGrade = SCALES[$('#scale').value].good; await api('/settings', { method: 'POST', body: { gradeScale: S.settings.gradeScale, targetGrade: S.settings.targetGrade } }); renderSliders(); });
    $('#applySliders').addEventListener('click', async () => {
      const sc = SCALES[$('#scale').value] || SCALES.pct; const grade = sc.g[sc.g.length - 1 - Number($('#grade').value)];
      const minutes = S.est && S.est.forced ? S.est.minutesForced : Number($('#minutes').value);
      S.settings = await api('/settings', { method: 'POST', body: { minutesPerDay: minutes, maxMinutesPerDay: Math.max(minutes + 5, S.settings.maxMinutesPerDay || 0), targetGrade: grade, gradeScale: $('#scale').value } });
      await api('/plan', { method: 'POST', body: {} }); await loadAll(); renderAll();
    });
    $('#buildPlan').addEventListener('click', async () => { $('#buildPlan').disabled = true; try { await api('/plan', { method: 'POST', body: {} }); await loadAll(); renderAll(); } catch (e) { alert(t('common.error', { e: e.message })); } $('#buildPlan').disabled = false; });
    $('#addTest').addEventListener('click', () => { const f = $('#testForm'); f.reset(); f.id.value = ''; f.hidden = false; });
    $('#cancelTest').addEventListener('click', () => { $('#testForm').hidden = true; });
    $('#testForm').addEventListener('submit', async (e) => {
      e.preventDefault(); const f = e.target; const b = { op: f.id.value ? 'edit' : 'add', id: f.id.value || undefined, subject: f.subject.value, title: f.title.value, kind: f.kind.value, date: f.date.value, time: f.time.value || null };
      S.assessments = await api('/assessments', { method: 'POST', body: b }); f.hidden = true; renderTests(); renderNextUp();
    });
    document.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-act]'); if (!b) return;
      const id = b.closest('li').dataset.id; const act = b.dataset.act;
      if (act === 'edit') { const a = [...S.assessments.upcoming, ...S.assessments.completed].find((x) => x.id === id); const f = $('#testForm'); f.id.value = a.id; f.subject.value = a.subjectName || a.subject || ''; f.title.value = a.title; f.kind.value = a.kind || 'test'; f.date.value = a.date; f.time.value = a.time || ''; f.hidden = false; f.scrollIntoView({ behavior: 'smooth' }); return; }
      if (act === 'delete' && !confirm(t('tests.delete') + '?')) return;
      S.assessments = await api('/assessments', { method: 'POST', body: { op: act, id } }); renderTests(); renderNextUp();
      if (act === 'done') { $('#mode').textContent = t('tests.digesting'); try { await api('/plan', { method: 'POST', body: {} }); } catch (err) { /* demo */ } setTimeout(renderMode, 1500); }
    });
    $('#materialFilter').addEventListener('input', renderMaterial);
    $('#scanNow').addEventListener('click', async () => { $('#scanNow').disabled = true; try { S.status.lastScan = await api('/scan', { method: 'POST', body: {} }); await loadAll(); renderAll(); } catch (e) { alert(t('common.error', { e: e.message })); } $('#scanNow').disabled = false; });
    $('#addMaterial').addEventListener('click', async () => { $('#newMaterial').textContent = t('material.adding'); try { await api('/material/add', { method: 'POST', body: {} }); await loadAll(); renderAll(); } catch (e) { alert(t('common.error', { e: e.message })); } });
    $$('input[name=route]').forEach((r) => r.addEventListener('change', renderRouteFields));
    $('#connect').addEventListener('click', async () => {
      const route = $('input[name=route]:checked').value; const site = $('#site').value.trim();
      if (route === 'extension') { $('#connectMsg').textContent = t('settings.routes.extension'); return; }
      const body = { site, route, username: ($('#username') || {}).value, password: ($('#password') || {}).value, token: ($('#token') || {}).value };
      try { const r = await api('/connect', { method: 'POST', body }); $('#connectMsg').textContent = `${r.site} (${r.route})`; if ($('#password')) $('#password').value = ''; } catch (e) { $('#connectMsg').textContent = t('common.error', { e: e.message }); }
    });
    $('#saveSettings').addEventListener('click', async () => {
      S.settings = await api('/settings', { method: 'POST', body: { factCheck: $('#factCheck').checked, shareData: $('#shareData').checked, uiLang: S.lang, digest: { ...(S.settings.digest || {}), provider: $('#provider').value } } });
      $('#settingsMsg').textContent = '✓'; setTimeout(() => { $('#settingsMsg').textContent = ''; }, 1500);
    });
    $('#startTrial').addEventListener('click', () => { alert(S.demo ? t('app.demo') : 'Trial: sign in first'); });
    $('#subscribe').addEventListener('click', () => { alert(S.demo ? t('app.demo') : 'Subscription: sign in first'); });
    $('#deleteAccount').addEventListener('click', () => { if (confirm(t('settings.deleteAccount') + '?')) alert(S.demo ? t('app.demo') : 'Local data lives in your workspace folder; delete it there. Cloud accounts: POST /account/delete.'); });
    $('#reportBtn').addEventListener('click', () => $('#reportDlg').showModal());
    $('#reportForm').addEventListener('submit', async (e) => {
      if (e.submitter && e.submitter.value === 'cancel') return;
      const f = e.target; await api('/report', { method: 'POST', body: { kind: f.kind.value, text: f.text.value, page: location.pathname } }); f.text.value = ''; $('#mode').textContent = t('report.thanks'); setTimeout(renderMode, 2500);
    });
  }

  // ---------- boot ----------
  (async () => {
    const sel = $('#lang'); sel.innerHTML = Object.entries(LANGS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
    await detect();
    try { await loadAll(); } catch (e) { S.demo = true; S.status = DEMO.status; await loadAll(); }
    const lang = await pickLang(); sel.value = lang;
    if (S.country && !S.settings.gradeScale) { S.settings.gradeScale = COUNTRY_SCALE[S.country] || 'pct'; }
    bind();
    await loadLang(lang);
  })();
})();
