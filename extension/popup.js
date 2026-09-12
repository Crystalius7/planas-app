const $ = (id) => document.getElementById(id);
const send = (msg) => new Promise((res) => chrome.runtime.sendMessage(msg, res));

async function refresh() {
  const r = await send({ type: 'status' });
  const c = r && r.connector;
  if (!c || c.error) { $('connector').innerHTML = '<span class="bad">Planas app is not running on this computer.</span> Start it, then collect.'; $('collect').disabled = true; return; }
  $('collect').disabled = false;
  const last = r.state.lastRun ? new Date(r.state.lastRun).toLocaleString() : 'never';
  $('connector').innerHTML = `<span class="ok">Planas app found</span> · ${(c.courses || []).length} course(s) · last collect: ${last}`;
  $('every').value = String(r.state.everyMinutes || 0);
}

$('collect').addEventListener('click', async () => {
  $('collect').disabled = true; $('result').textContent = 'collecting…';
  const r = await send({ type: 'collect' });
  $('result').innerHTML = r.ok ? `<span class="ok">${r.result.courses.length} course(s), ${r.result.changes} change(s)</span>` : `<span class="bad">${r.error}</span>`;
  await refresh();
});
$('every').addEventListener('change', async (e) => { await send({ type: 'schedule', everyMinutes: Number(e.target.value) }); });
refresh();
