// index.js - the hosted API: ONE Cloudflare Worker on the free plan (hard limits, never bills - 100k requests/day,
// KV 1k writes/day, D1 5M row reads/day; partner IMPROVE 5: every provider named with its exhaustion behaviour in
// docs/SECURITY.md). Standard Web APIs only, no framework.
//
// Bindings (wrangler.toml): KV `KV` (sessions, magic links, trial registry, rate limits), D1 `DB` (accounts, blobs,
// reports, consent, jobs), secrets ACCESS_SECRET (HMAC for session cookies), RESEND_KEY (transactional mail),
// BILLING_WEBHOOK_SECRET (merchant-of-record webhook signature), VAPID_PUBLIC/VAPID_PRIVATE (web push).
//
// Routes
//   GET  /geo                       {country, lang}  - CF-IPCountry only; nothing stored
//   POST /auth/start {email}        magic link (rate-limited per IP + per e-mail; disposable domains refused)
//   GET  /auth/finish?t=            sets the session cookie
//   POST /auth/logout
//   GET  /me                        {email, plan, trialEndsAt, consent}
//   POST /consent {shareData}       the data-sharing switch (off by default)
//   GET  /blob/:name  PUT /blob/:name   per-user encrypted blobs (client-side encrypted; the server sees ciphertext)
//   POST /trial/claim {fp}          one trial per verified e-mail AND per Moodle identity fingerprint (both signals)
//   POST /billing/webhook           merchant-of-record events (idempotent by event id)
//   POST /report {kind,text,page}   bug / feature report (no personal data required)
//   POST /push/subscribe            web push subscription (VAPID)
//   POST /jobs  GET /jobs/:id       digest jobs for a worker (cloud tier; deferred - accepted only when ENABLE_JOBS=1)
//
// Data rules: no Moodle password, token, sesskey or cookie ever reaches this worker (they stay in the extension /
// connector). Course files never reach it either (local processing first - collab 2026-09-12). Blobs are ciphertext.

const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8' };
const DISPOSABLE = new Set(['mailinator.com', 'guerrillamail.com', '10minutemail.com', 'tempmail.com', 'yopmail.com', 'trashmail.com', 'sharklasers.com', 'getnada.com', 'temp-mail.org', 'dispostable.com']);
const COUNTRY_LANG = { LT: 'lt', LV: 'lv', EE: 'et', PL: 'pl', DE: 'de', AT: 'de', CH: 'de', FR: 'fr', BE: 'fr', ES: 'es', MX: 'es', AR: 'es', CL: 'es', CO: 'es', PE: 'es', IT: 'it', PT: 'pt', BR: 'pt', NL: 'nl', UA: 'uk', RU: 'ru', BY: 'ru', KZ: 'ru', TR: 'tr', SE: 'sv', NO: 'nb', DK: 'da', FI: 'fi', CZ: 'cs', SK: 'sk', HU: 'hu', RO: 'ro', BG: 'bg', GR: 'el', HR: 'hr', SI: 'sl', RS: 'sr', JP: 'ja', CN: 'zh', TW: 'zh', KR: 'ko', ID: 'id', VN: 'vi', TH: 'th', SA: 'ar', AE: 'ar', EG: 'ar', IL: 'he', IR: 'fa', IN: 'hi', PK: 'ur', BD: 'bn' };

function json(body, status = 200, extra = {}) { return new Response(JSON.stringify(body), { status, headers: { ...JSON_HEADERS, ...extra } }); }
function cors(req, env, res) {
  const origin = req.headers.get('Origin') || '';
  const allowed = (env.APP_ORIGINS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const h = new Headers(res.headers);
  if (allowed.includes(origin)) { h.set('Access-Control-Allow-Origin', origin); h.set('Access-Control-Allow-Credentials', 'true'); h.set('Vary', 'Origin'); }
  h.set('Access-Control-Allow-Headers', 'content-type'); h.set('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  h.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains'); h.set('X-Content-Type-Options', 'nosniff'); h.set('Referrer-Policy', 'no-referrer');
  return new Response(res.body, { status: res.status, headers: h });
}

const enc = new TextEncoder();
async function hmac(secret, data) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(data));
  return btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
async function sha256(s) { const d = await crypto.subtle.digest('SHA-256', enc.encode(s)); return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join(''); }
function rand(n = 32) { const a = new Uint8Array(n); crypto.getRandomValues(a); return [...a].map((b) => b.toString(16).padStart(2, '0')).join(''); }
function timingSafeEqual(a, b) { if (a.length !== b.length) return false; let r = 0; for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i); return r === 0; }

async function rateLimit(env, key, limit, windowSec) {
  const k = `rl:${key}:${Math.floor(Date.now() / 1000 / windowSec)}`;
  const n = Number((await env.KV.get(k)) || 0) + 1;
  await env.KV.put(k, String(n), { expirationTtl: windowSec + 5 });
  return n <= limit;
}

async function session(req, env) {
  const m = /(?:^|;\s*)sid=([^;]+)/.exec(req.headers.get('Cookie') || '');
  if (!m) return null;
  const [id, sig] = m[1].split('.');
  if (!id || !sig || !timingSafeEqual(sig, await hmac(env.ACCESS_SECRET, id))) return null;
  const s = await env.KV.get(`sess:${id}`, 'json');
  return s ? { ...s, id } : null;
}
async function setSession(env, userId, email) {
  const id = rand(24);
  await env.KV.put(`sess:${id}`, JSON.stringify({ userId, email, at: Date.now() }), { expirationTtl: 60 * 60 * 24 * 30 });
  return `sid=${id}.${await hmac(env.ACCESS_SECRET, id)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${60 * 60 * 24 * 30}`;
}

async function sendMail(env, to, subject, text) {
  if (!env.RESEND_KEY) return { skipped: 'RESEND_KEY not set' };
  const r = await fetch('https://api.resend.com/emails', { method: 'POST', headers: { Authorization: `Bearer ${env.RESEND_KEY}`, 'content-type': 'application/json' },
    body: JSON.stringify({ from: env.MAIL_FROM || 'Planas <noreply@example.invalid>', to: [to], subject, text }) });
  return { status: r.status };
}

async function user(env, email) {
  const row = await env.DB.prepare('SELECT id, email, plan, trial_ends_at AS trialEndsAt, share_data AS shareData, created_at AS createdAt FROM users WHERE email = ?').bind(email).first();
  if (row) return row;
  const id = rand(16);
  await env.DB.prepare('INSERT INTO users (id, email, plan, share_data, created_at) VALUES (?, ?, ?, 0, ?)').bind(id, email, 'none', new Date().toISOString()).run();
  return { id, email, plan: 'none', trialEndsAt: null, shareData: 0 };
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    if (req.method === 'OPTIONS') return cors(req, env, new Response(null, { status: 204 }));
    try {
      const res = await route(req, env, url, p);
      return cors(req, env, res);
    } catch (e) {
      return cors(req, env, json({ error: 'server error' }, 500));
    }
  },
};

async function route(req, env, url, p) {
  const ip = req.headers.get('CF-Connecting-IP') || '0';
  if (p === '/geo' && req.method === 'GET') {
    const cc = (req.cf && req.cf.country) || req.headers.get('CF-IPCountry') || 'XX';
    return json({ country: cc, lang: COUNTRY_LANG[cc] || null }, 200, { 'cache-control': 'no-store' });
  }
  if (p === '/auth/start' && req.method === 'POST') {
    const { email } = await req.json().catch(() => ({}));
    const e = String(email || '').trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e)) return json({ error: 'invalid email' }, 400);
    if (DISPOSABLE.has(e.split('@')[1])) return json({ error: 'disposable e-mail addresses cannot start a trial' }, 400);
    if (!(await rateLimit(env, `ip:${ip}`, 10, 3600)) || !(await rateLimit(env, `em:${await sha256(e)}`, 3, 3600))) return json({ error: 'too many attempts, try later' }, 429);
    const t = rand(24);
    await env.KV.put(`magic:${t}`, e, { expirationTtl: 900 });
    const link = `${env.API_ORIGIN}/auth/finish?t=${t}`;
    await sendMail(env, e, 'Your sign-in link', `Open this link within 15 minutes to sign in:\n${link}\n\nIf you did not ask for it, ignore this e-mail.`);
    return json({ ok: true });
  }
  if (p === '/auth/finish' && req.method === 'GET') {
    const t = url.searchParams.get('t') || '';
    const e = await env.KV.get(`magic:${t}`);
    if (!e) return new Response('This link has expired. Ask for a new one.', { status: 400 });
    await env.KV.delete(`magic:${t}`);
    const u = await user(env, e);
    const cookie = await setSession(env, u.id, e);
    return new Response(null, { status: 302, headers: { Location: `${env.APP_ORIGIN}/app/`, 'Set-Cookie': cookie } });
  }
  if (p === '/auth/logout' && req.method === 'POST') {
    const s = await session(req, env);
    if (s) await env.KV.delete(`sess:${s.id}`);
    return json({ ok: true }, 200, { 'Set-Cookie': 'sid=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0' });
  }
  if (p === '/report' && req.method === 'POST') {
    if (!(await rateLimit(env, `rep:${ip}`, 20, 86400))) return json({ error: 'too many reports today' }, 429);
    const b = await req.json().catch(() => ({}));
    const s = await session(req, env);
    await env.DB.prepare('INSERT INTO reports (id, user_id, kind, text, page, created_at) VALUES (?, ?, ?, ?, ?, ?)')
      .bind(rand(12), s ? s.userId : null, String(b.kind || 'bug').slice(0, 20), String(b.text || '').slice(0, 4000), String(b.page || '').slice(0, 200), new Date().toISOString()).run();
    return json({ ok: true });
  }
  if (p === '/billing/webhook' && req.method === 'POST') {
    const raw = await req.text();
    const sig = req.headers.get('X-Signature') || req.headers.get('creem-signature') || '';
    const expect = await hmac(env.BILLING_WEBHOOK_SECRET || '', raw);
    if (!env.BILLING_WEBHOOK_SECRET || !timingSafeEqual(sig, expect)) return json({ error: 'bad signature' }, 401);
    const ev = JSON.parse(raw);
    const evId = String(ev.id || ev.event_id || '');
    if (evId && (await env.KV.get(`ev:${evId}`))) return json({ ok: true, duplicate: true });   // idempotent (partner IMPROVE 5)
    const email = String((ev.customer && ev.customer.email) || (ev.data && ev.data.customer && ev.data.customer.email) || '').toLowerCase();
    const type = String(ev.eventType || ev.type || '');
    if (email) {
      const u = await user(env, email);
      const plan = /cancel|expired|refund|paused/i.test(type) ? 'none' : /trial/i.test(type) ? 'trial' : /paid|active|subscription/i.test(type) ? 'paid' : u.plan;
      await env.DB.prepare('UPDATE users SET plan = ?, billing_ref = ? WHERE id = ?').bind(plan, String((ev.data && ev.data.id) || ev.subscription_id || ''), u.id).run();
    }
    if (evId) await env.KV.put(`ev:${evId}`, '1', { expirationTtl: 60 * 60 * 24 * 90 });
    return json({ ok: true });
  }
  // ---- authenticated ---------------------------------------------------------------------------------------------
  const s = await session(req, env);
  if (!s) return json({ error: 'sign in first' }, 401);
  if (p === '/me' && req.method === 'GET') {
    const u = await user(env, s.email);
    return json({ email: u.email, plan: u.plan, trialEndsAt: u.trialEndsAt, shareData: !!u.shareData });
  }
  if (p === '/consent' && req.method === 'POST') {
    const b = await req.json().catch(() => ({}));
    await env.DB.prepare('UPDATE users SET share_data = ?, consent_at = ? WHERE id = ?').bind(b.shareData ? 1 : 0, new Date().toISOString(), s.userId).run();
    return json({ ok: true, shareData: !!b.shareData });
  }
  if (p === '/trial/claim' && req.method === 'POST') {
    const b = await req.json().catch(() => ({}));
    const fp = String(b.fp || '').slice(0, 64);   // client-reported Moodle identity fingerprint: one signal, not proof
    const u = await user(env, s.email);
    if (u.plan !== 'none' || u.trialEndsAt) return json({ error: 'a trial was already used on this account' }, 409);
    if (fp && (await env.KV.get(`trialfp:${fp}`))) return json({ error: 'a trial was already used for this Moodle account' }, 409);
    // IP is a SIGNAL, not an entitlement (decision review 2026-09-12: classmates share school Wi-Fi): a high daily cap stops
    // scripted farming, and the count is kept for review instead of refusing the 4th student on the same network
    if (!(await rateLimit(env, `trial:${ip}`, 25, 86400))) return json({ error: 'too many trials from this network today' }, 429);
    const ends = new Date(Date.now() + 7 * 86400 * 1000).toISOString();
    await env.DB.prepare('UPDATE users SET plan = ?, trial_ends_at = ?, trial_fp = ? WHERE id = ?').bind('trial', ends, fp || null, u.id).run();
    if (fp) await env.KV.put(`trialfp:${fp}`, u.id, { expirationTtl: 60 * 60 * 24 * 365 });
    return json({ ok: true, trialEndsAt: ends });
  }
  const blob = /^\/blob\/([a-z0-9_-]{1,40})$/.exec(p);
  if (blob) {
    if (req.method === 'GET') {
      const row = await env.DB.prepare('SELECT data, updated_at AS updatedAt FROM blobs WHERE user_id = ? AND name = ?').bind(s.userId, blob[1]).first();
      return row ? json(row) : json({ error: 'not found' }, 404);
    }
    if (req.method === 'PUT') {
      const data = await req.text();
      if (data.length > 2_000_000) return json({ error: 'blob too large (2 MB)' }, 413);
      await env.DB.prepare('INSERT INTO blobs (user_id, name, data, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, name) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at')
        .bind(s.userId, blob[1], data, new Date().toISOString()).run();
      return json({ ok: true });
    }
    if (req.method === 'DELETE') {
      await env.DB.prepare('DELETE FROM blobs WHERE user_id = ? AND name = ?').bind(s.userId, blob[1]).run();
      return json({ ok: true });
    }
  }
  if (p === '/account/delete' && req.method === 'POST') {
    await env.DB.batch([env.DB.prepare('DELETE FROM blobs WHERE user_id = ?').bind(s.userId), env.DB.prepare('DELETE FROM push WHERE user_id = ?').bind(s.userId),
      env.DB.prepare('DELETE FROM users WHERE id = ?').bind(s.userId)]);
    await env.KV.delete(`sess:${s.id}`);
    return json({ ok: true, deleted: true }, 200, { 'Set-Cookie': 'sid=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0' });
  }
  if (p === '/push/subscribe' && req.method === 'POST') {
    const sub = await req.json().catch(() => null);
    if (!sub || !sub.endpoint) return json({ error: 'bad subscription' }, 400);
    await env.DB.prepare('INSERT OR REPLACE INTO push (user_id, endpoint, data, created_at) VALUES (?, ?, ?, ?)').bind(s.userId, sub.endpoint, JSON.stringify(sub), new Date().toISOString()).run();
    return json({ ok: true });
  }
  if (p === '/jobs' && req.method === 'POST') {
    if (env.ENABLE_JOBS !== '1') return json({ error: 'remote processing is not enabled yet - use the local app' }, 503);
    const b = await req.json().catch(() => ({}));
    const id = rand(12);
    await env.DB.prepare('INSERT INTO jobs (id, user_id, kind, payload, status, created_at) VALUES (?, ?, ?, ?, ?, ?)').bind(id, s.userId, String(b.kind || 'digest'), JSON.stringify(b.payload || {}).slice(0, 500000), 'queued', new Date().toISOString()).run();
    return json({ ok: true, id, status: 'queued', note: 'processing is delayed while no worker is online' });
  }
  const job = /^\/jobs\/([a-f0-9]{24})$/.exec(p);
  if (job && req.method === 'GET') {
    const row = await env.DB.prepare('SELECT id, kind, status, result, created_at AS createdAt, updated_at AS updatedAt FROM jobs WHERE id = ? AND user_id = ?').bind(job[1], s.userId).first();
    return row ? json(row) : json({ error: 'not found' }, 404);
  }
  return json({ error: 'no such route' }, 404);
}
