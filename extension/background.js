// background.js - MV3 service worker. Three jobs, none of which touches a password:
//  1. "Collect now": inject collector.js into the active Moodle tab (host permission granted per site by the student on
//     first use) and POST the bundle to the local connector (http://127.0.0.1:8765/bundle).
//  2. Route A on SSO sites: when the student opens the site's mobile launch page, Moodle redirects to
//     moodlemobile://token=<base64>; a web page cannot receive that scheme, an extension can observe the redirect
//     (webRequest.onBeforeRedirect) and hand the token to the connector (POST /connect route=token).
//  3. A periodic re-collect (alarm, default every 3 h while the browser runs) so new material is noticed.
const CONNECTOR = 'http://127.0.0.1:8765';
const DEFAULTS = { site: null, everyMinutes: 180, lastRun: null, lastResult: null };

async function state() { return { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) }; }

async function post(path, body) {
  const r = await fetch(CONNECTOR + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `connector ${r.status}`);
  return j;
}

async function collect(tabId) {
  const [res] = await chrome.scripting.executeScript({ target: { tabId }, files: ['collector.js'], world: 'MAIN' });
  const bundle = res && res.result;
  if (!bundle || bundle.error) throw new Error((bundle && bundle.error) || 'collector returned nothing');
  const out = await post('/bundle', bundle);
  await chrome.storage.local.set({ lastRun: new Date().toISOString(), lastResult: out, site: bundle.site });
  return out;
}

async function findSiteTab(site) {
  const tabs = await chrome.tabs.query({ url: site + '/*' });
  return tabs[0];
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.type === 'collect') {
      const tab = (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
      if (!tab || !/^https:\/\//.test(tab.url)) throw new Error('open your Moodle site in this tab first');
      const origin = new URL(tab.url).origin + '/*';
      const ok = await chrome.permissions.request({ origins: [origin] });
      if (!ok) throw new Error('permission for this site was not granted');
      reply({ ok: true, result: await collect(tab.id) });
    } else if (msg.type === 'status') {
      const st = await state();
      let connector = null;
      try { connector = await (await fetch(CONNECTOR + '/status')).json(); } catch (e) { connector = { error: 'connector not running' }; }
      reply({ ok: true, state: st, connector });
    } else if (msg.type === 'schedule') {
      await chrome.storage.local.set({ everyMinutes: msg.everyMinutes });
      await chrome.alarms.clear('recollect');
      if (msg.everyMinutes > 0) chrome.alarms.create('recollect', { periodInMinutes: msg.everyMinutes });
      reply({ ok: true });
    }
  })().catch((e) => reply({ ok: false, error: String(e.message || e) }));
  return true;
});

chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name !== 'recollect') return;
  const st = await state();
  if (!st.site) return;
  const tab = await findSiteTab(st.site);
  if (!tab) return;   // nothing to do without an open, logged-in tab; the student is never logged in on their behalf
  try { await collect(tab.id); } catch (e) { await chrome.storage.local.set({ lastResult: { error: String(e.message || e) } }); }
});

// Route A token capture: launch.php -> <scheme>://token=<base64>. Observed only; the extension never initiates a login.
if (chrome.webRequest && chrome.webRequest.onBeforeRedirect) {
  chrome.webRequest.onBeforeRedirect.addListener(async (d) => {
    const m = /^([a-z][a-z0-9+.-]*):\/\/token=([A-Za-z0-9+/=]+)/i.exec(d.redirectUrl || '');
    if (!m || !/\/admin\/tool\/mobile\/launch\.php/.test(d.url)) return;
    try {
      const site = new URL(d.url).origin;
      const passport = new URL(d.url).searchParams.get('passport') || '';
      await post('/connect', { site, route: 'launch', launchUrl: d.redirectUrl, passport });
      await chrome.storage.local.set({ site, lastResult: { connected: 'token' } });
    } catch (e) { await chrome.storage.local.set({ lastResult: { error: String(e.message || e) } }); }
  }, { urls: ['https://*/admin/tool/mobile/launch.php*'] });
}
