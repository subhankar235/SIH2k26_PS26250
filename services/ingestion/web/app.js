import { safeSnapshot } from './format.js';
import { element, connection, summary, table, inspector, clearData, restoreInspectionFocus } from './render.js';

const PAGE_SIZE = 100;
let snapshot = null, page = 0, authenticated = true, timer, activeRequest, generation = 0;
let filters = { type: '', sourceId: '' };

function stop() {
  clearTimeout(timer); generation++; activeRequest?.abort(); activeRequest = null;
}
function showLogin(message = '') {
  stop(); authenticated = false; snapshot = null; clearData();
  element('workspace').hidden = true; element('login-panel').hidden = false;
  element('logout').hidden = true; element('login-message').textContent = message;
  element('viewer-token').focus();
}
function render() {
  if (!snapshot) return;
  page = Math.min(page, Math.max(0, Math.ceil(snapshot.records.length / PAGE_SIZE) - 1));
  summary(snapshot); table(snapshot, page, PAGE_SIZE, (record) => inspector(record, snapshot.generatedAt));
  element('download').disabled = false;
}
async function request(url, options = {}, controller) {
  const response = await fetch(url, { ...options, signal: controller.signal, credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) {
    const error = new Error('Request failed'); error.status = response.status;
    const body = await response.json().catch(() => null);
    error.code = body?.error?.code;
    throw error;
  }
  return response;
}
function schedule() {
  clearTimeout(timer);
  if (authenticated && !document.hidden) timer = setTimeout(refresh, 5000);
}
async function refresh() {
  if (!authenticated || activeRequest || document.hidden) return;
  clearTimeout(timer);
  const controller = new AbortController(); activeRequest = controller;
  const currentGeneration = generation;
  const timeout = setTimeout(() => controller.abort(), 12_000);
  element('refresh').disabled = true;
  if (!snapshot) connection('Loading selected source reports…');
  try {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) if (value) query.set(key, value);
    const response = await request(`/monitor/api/snapshot?${query}`, {}, controller);
    const data = await response.json();
    if (currentGeneration !== generation) return;
    if (!Array.isArray(data.records) || !data.summary || !data.scope || !data.delivery) throw new Error('Invalid snapshot');
    // Keep only the documented report schema in memory and downloadable content.
    snapshot = safeSnapshot(data);
    element('login-panel').hidden = true; element('workspace').hidden = false; element('logout').hidden = false;
    render(); connection('Updated · Auto-refresh every 5s', false, snapshot.generatedAt);
  } catch (error) {
    if (currentGeneration !== generation) return;
    if (error.status === 401) {
      showLogin(snapshot ? 'Your viewer session ended. Open a new session to continue.' : 'Enter a viewer token to access the monitor.');
    } else if (error.status === 403) {
      showLogin('Viewer access denied. A separate monitoring viewer token is required.');
    } else if (error.code === 'VIEWER_DISABLED') {
      showLogin('Monitoring viewer access is not configured. Contact the gateway administrator.');
    } else {
      element('workspace').hidden = false; element('logout').hidden = false;
      connection(snapshot ? 'Stale snapshot · Refresh failed. Retrying in 5s.' : 'Snapshot unavailable · Refresh failed. Retrying in 5s.', true, snapshot?.generatedAt);
      if (!snapshot) { element('table-state').textContent = 'Unable to load reports. Check the connection or refresh again.'; }
    }
  } finally {
    clearTimeout(timeout);
    if (activeRequest === controller) activeRequest = null;
    element('refresh').disabled = false;
    schedule();
  }
}

element('login-form').addEventListener('submit', async (event) => {
  event.preventDefault(); stop();
  const input = element('viewer-token'); const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12_000);
  element('login-submit').disabled = true; element('login-message').textContent = 'Opening viewer session…';
  try {
    const pending = request('/monitor/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: input.value }) }, controller);
    input.value = ''; await pending;
    authenticated = true; element('login-panel').hidden = true; element('workspace').hidden = false;
    element('login-message').textContent = ''; await refresh();
  } catch (error) {
    element('login-message').textContent = error.status === 401 || error.status === 403
      ? 'Viewer access denied. Check the separate viewer token and try again.'
      : error.code === 'VIEWER_DISABLED' ? 'Monitoring viewer access is not configured. Contact the gateway administrator.'
        : error.code === 'SESSION_CAPACITY' ? 'Viewer session capacity is full. Try again later.'
        : 'Could not open a session. Check the connection and try again.';
  } finally { input.value = ''; clearTimeout(timeout); element('login-submit').disabled = false; }
});

element('logout').addEventListener('click', async () => {
  stop(); authenticated = false; snapshot = null; clearData();
  element('logout').disabled = true;
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 12_000);
  try {
    await request('/monitor/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }, controller);
    showLogin('Signed out.'); element('viewer-token').focus();
  } catch {
    connection('Sign out failed · Data cleared locally. Retry Sign out to revoke the session.', true);
    element('table-state').textContent = 'Data cleared. Sign out could not be confirmed.';
  } finally { clearTimeout(timeout); element('logout').disabled = false; }
});

function applyFilters() {
  stop(); filters = { type: element('type-filter').value, sourceId: element('source-filter').value.trim() };
  snapshot = null; page = 0; clearData(); refresh();
}
element('filters').addEventListener('submit', (event) => { event.preventDefault(); applyFilters(); });
element('clear-filters').addEventListener('click', () => { element('filters').reset(); applyFilters(); });
element('refresh').addEventListener('click', refresh);
element('previous').addEventListener('click', () => { page--; render(); });
element('next').addEventListener('click', () => { page++; render(); });
element('close-inspector').addEventListener('click', () => element('inspector').close());
element('inspector').addEventListener('close', () => {
  element('inspector-content').replaceChildren();
  if (authenticated && snapshot) restoreInspectionFocus(element('inspector').dataset.inspectionId);
});
element('download').addEventListener('click', () => {
  if (!snapshot) return;
  const blob = new Blob([JSON.stringify(safeSnapshot(snapshot), null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const link = document.createElement('a');
  link.href = url; link.download = 'administrative-facts-snapshot.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
function resume() {
  if (!document.hidden && authenticated) refresh();
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { clearTimeout(timer); if (snapshot) connection('Refresh paused · Last snapshot retained while this tab is hidden.', true, snapshot.generatedAt); }
  else resume();
});
window.addEventListener('pageshow', resume); window.addEventListener('focus', resume);
element('workspace').hidden = false;
refresh();
