// collector.js - runs INSIDE the Moodle tab (injected by background.js with chrome.scripting), so every request is
// same-origin with the student's own cookies. Nothing here ever sees a password; the sesskey is read from the page
// (M.cfg.sesskey) and used only for Moodle's own ajax service, exactly like the site's own JavaScript does.
// Uses only the calls the personal tools proved at a Moodle 4.x school with the mobile service OFF:
//   core_course_get_enrolled_courses_by_timeline_classification, core_courseformat_get_state,
//   core_calendar_get_action_events_by_timesort, message_popup_get_popup_notifications, plus plain HTML pages.
// Returns ONE bundle {site, userid, courses[], calendar[], notifications[], collectedAt} for the local connector.
(async () => {
  const site = location.origin;
  const cfg = (window.M && window.M.cfg) || {};
  const sesskey = cfg.sesskey;
  const userid = cfg.userId || (document.body.className.match(/\buser-(\d+)\b/) || [])[1];
  if (!sesskey) return { error: 'not logged in (no sesskey on this page)' };

  const ajax = async (method, args) => {
    const r = await fetch(`${site}/lib/ajax/service.php?sesskey=${sesskey}&info=${method}`, {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify([{ index: 0, methodname: method, args }]) });
    const j = (await r.json())[0];
    if (j.error) throw new Error(`${method}: ${(j.exception && j.exception.message) || 'error'}`);
    return j.data;
  };
  const text = (html) => {
    const d = new DOMParser().parseFromString(html, 'text/html');
    d.querySelectorAll('script,style,nav,header,footer,.drawer,#nav-drawer,.navbar').forEach((e) => e.remove());
    const main = d.querySelector('[role="main"]') || d.body;
    return (main.innerText || main.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
  };
  const page = async (url) => { const r = await fetch(url, { credentials: 'same-origin' }); return { url: r.url, html: await r.text() }; };
  const host = location.host.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const fileLinks = (html, mod) => Array.from(new Set(Array.from(html.matchAll(new RegExp(`href="(https://${host}/pluginfile\\.php/\\d+/mod_${mod}/[^"]+)"`, 'g')).map((m) => m[1].replace(/&amp;/g, '&')))));

  const out = { site, userid: userid ? Number(userid) : null, collectedAt: new Date().toISOString(), courses: [], calendar: [], notifications: [], capabilities: {} };
  let courses = [];
  try { courses = (await ajax('core_course_get_enrolled_courses_by_timeline_classification', { offset: 0, limit: 0, classification: 'all', sort: 'fullname' })).courses || []; out.capabilities.courses = true; }
  catch (e) { out.capabilities.courses = String(e); }
  for (const c of courses) {
    const course = { id: c.id, fullname: c.fullname || c.displayname, sections: [], modules: [] };
    try {
      const st = JSON.parse(await ajax('core_courseformat_get_state', { courseid: c.id }));
      const cms = Object.fromEntries((st.cm || []).map((x) => [String(x.id), x]));
      for (const sec of st.section || []) {
        const title = sec.title || `Section ${sec.number}`;
        course.sections.push({ title, number: sec.number, summary: text(sec.summary || ''), cmlist: (sec.cmlist || []).map(String) });
        for (const id of sec.cmlist || []) {
          const cm = cms[String(id)]; if (!cm) continue;
          const m = { id: cm.id, module: cm.module, name: cm.name, url: cm.url || `${site}/mod/${cm.module}/view.php?id=${cm.id}`, section: title, files: [] };
          try {
            if (cm.module === 'label') { /* text lives in the section */ }
            else if (cm.module === 'resource') m.files.push({ name: cm.name, url: `${site}/mod/resource/view.php?id=${cm.id}&redirect=1` });
            else if (cm.module === 'folder') { const p = await page(`${site}/mod/folder/view.php?id=${cm.id}`); for (const u of fileLinks(p.html, 'folder')) m.files.push({ name: decodeURIComponent(u.split('/').pop().split('?')[0]), url: u }); }
            else if (cm.module === 'url') { const r = await fetch(`${site}/mod/url/view.php?id=${cm.id}`, { credentials: 'same-origin', redirect: 'manual' }); const h = await r.text(); const mm = h.match(/class="urlworkaround">[\s\S]*?href="([^"]+)"/) || h.match(new RegExp(`href="(https?://(?!${host})[^"]+)"`)); m.external = mm ? mm[1].replace(/&amp;/g, '&') : r.url; }
            else { const p = await page(m.url); m.text = text(p.html).slice(0, 200000); for (const u of fileLinks(p.html, '[a-z]+')) m.files.push({ name: decodeURIComponent(u.split('/').pop().split('?')[0]), url: u }); }
          } catch (e) { m.error = String(e); }
          course.modules.push(m);
        }
      }
      out.capabilities.state = true;
    } catch (e) { course.error = String(e); out.capabilities.state = String(e); }
    out.courses.push(course);
  }
  try {
    const now = Math.floor(Date.now() / 1000); let after = null;
    for (let i = 0; i < 20; i++) {
      const args = { timesortfrom: now - 86400, timesortto: now + 180 * 86400, limitnum: 50 }; if (after) args.aftereventid = after;
      const ev = (await ajax('core_calendar_get_action_events_by_timesort', args)).events || [];
      out.calendar.push(...ev); if (ev.length < 50) break; after = ev[ev.length - 1].id;
    }
    out.capabilities.calendar = true;
  } catch (e) { out.capabilities.calendar = String(e); }
  try { out.notifications = (await ajax('message_popup_get_popup_notifications', { useridto: Number(userid), limit: 50, offset: 0 })).notifications || []; out.capabilities.notifications = true; }
  catch (e) { out.capabilities.notifications = String(e); }
  // small files travel inline (<= 8 MB each) so the connector needs no session at all; bigger ones are listed by URL
  for (const c of out.courses) for (const m of c.modules) for (const f of m.files) {
    try { const r = await fetch(f.url, { credentials: 'same-origin' }); const ct = r.headers.get('content-type') || '';
      if (!r.ok || ct.includes('text/html')) continue; const b = await r.blob(); if (b.size > 8 * 1024 * 1024) continue;
      const cd = r.headers.get('content-disposition') || ''; const nm = (cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)/) || [])[1];
      if (nm) f.name = decodeURIComponent(nm);
      f.b64 = await new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(',')[1]); fr.readAsDataURL(b); });
    } catch (e) { f.error = String(e); }
  }
  return out;
})();
