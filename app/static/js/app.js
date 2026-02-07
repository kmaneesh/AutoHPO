const mode = document.getElementById('mode');
const queryInput = document.getElementById('query');
const searchBtn = document.getElementById('search');
const result = document.getElementById('result');
const debugCheckbox = document.getElementById('debug');

function setResult(html, className) {
  result.innerHTML = html;
  result.className = className || '';
}

function renderDebugBlock(debug) {
  if (!debug || !debugCheckbox.checked) return '';
  const req = debug.request || {};
  const res = debug.response || {};
  const reqBody = typeof req.body === 'string' ? req.body : JSON.stringify(req.body, null, 2);
  const resBody = typeof res.body === 'object' ? JSON.stringify(res.body, null, 2) : String(res.body);
  return '<div class="debug-section"><details open><summary>Debug: request &amp; response</summary>' +
    '<p class="label">Request</p><p class="status">' + escapeHtml(req.method || '') + ' ' + escapeHtml(req.url || '') + ' → ' + escapeHtml(String(res.status || '')) + '</p>' +
    '<pre>' + escapeHtml(reqBody) + '</pre>' +
    '<p class="label">Response</p><pre>' + escapeHtml(resBody) + '</pre></details></div>';
}

function renderPureResults(data, debug) {
  const querySent = data.query_sent != null ? String(data.query_sent) : '';
  const list = data.results || [];
  let out = '';
  if (querySent !== '') {
    out += '<p class="query-sent"><strong>Query sent to search:</strong> <code>' + escapeHtml(querySent) + '</code></p>';
  } else {
    out += '<p class="query-sent"><strong>Query sent to search:</strong> <code>(empty after stop-word removal)</code></p>';
  }
  if (list.length === 0) {
    out += '<p>No HPO terms found.</p>';
    out += renderDebugBlock(debug);
    return out;
  }
  const items = list.map(t =>
    '<li><span class="hpo-id">' + escapeHtml(t.hpo_id || '') + '</span> ' + escapeHtml(t.name || '') +
    (t.definition ? '<br><small>' + escapeHtml((t.definition || '').slice(0, 120)) + '…</small>' : '') + '</li>'
  ).join('');
  out += '<ul>' + items + '</ul>';
  out += renderDebugBlock(debug);
  return out;
}
function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

document.getElementById('search-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = (queryInput.value || '').trim();
  if (!q) {
    setResult('Enter patient history or a query.', 'error');
    return;
  }
  const useAgent = mode.value === 'agent';
  setResult('Searching…', 'loading');

  const debug = { request: { method: 'POST', url: '', body: { query: q } }, response: {} };

  try {
    if (useAgent) {
      debug.request.url = '/api/chat';
      const reqBody = JSON.stringify({ query: q });
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: reqBody
      });
      const data = await res.json();
      debug.response = { status: res.status, body: data };
      if (!res.ok) throw new Error(data.detail || res.statusText);
      let html = (data.response || '').replace(/\n/g, '<br>');
      if (debugCheckbox.checked) html += renderDebugBlock(debug);
      setResult(html);
    } else {
      debug.request.url = '/api/search';
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q })
      });
      const data = await res.json();
      debug.response = { status: res.status, body: data };
      if (!res.ok) throw new Error(data.detail || res.statusText);
      setResult(renderPureResults(data, debug));
    }
  } catch (e) {
    if (!debug.response.status) debug.response = { status: '—', body: { error: e.message } };
    setResult('Error: ' + escapeHtml(e.message) + (debugCheckbox.checked ? renderDebugBlock(debug) : ''), 'error');
  }
});
