(function () {
  const TAB_SEARCH = 'tab-search';
  const TAB_HISTORY = 'tab-history';
  const PANEL_SEARCH = 'panel-search';
  const PANEL_HISTORY = 'panel-history';
  const SEARCH_DEBOUNCE_MS = 280;

  const tabSearch = document.getElementById('tab-search');
  const tabHistory = document.getElementById('tab-history');
  const panelSearch = document.getElementById('panel-search');
  const panelHistory = document.getElementById('panel-history');
  const searchQueryInput = document.getElementById('search-query');
  const searchResultEl = document.getElementById('search-result');
  const chatForm = document.getElementById('chat-form');
  const chatQueryInput = document.getElementById('chat-query');
  const chatHistoryEl = document.getElementById('chat-history');
  const debugCheckbox = document.getElementById('debug');
  const debugToggleBtn = document.getElementById('debug-toggle');

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s == null ? '' : String(s);
    return div.innerHTML;
  }

  function setActiveTab(tabId) {
    const isSearch = tabId === TAB_SEARCH;
    tabSearch.setAttribute('aria-selected', isSearch ? 'true' : 'false');
    tabHistory.setAttribute('aria-selected', isSearch ? 'false' : 'true');
    panelSearch.classList.toggle('hidden', !isSearch);
    panelHistory.classList.toggle('hidden', isSearch);
    if (isSearch) searchQueryInput.focus(); else chatQueryInput.focus();
  }

  tabSearch.addEventListener('click', function () { setActiveTab(TAB_SEARCH); });
  tabHistory.addEventListener('click', function () { setActiveTab(TAB_HISTORY); });

  // ---- Search mode: live as you type (POST /api/search, in-memory only; no Meilisearch from UI) ----
  let searchDebounceTimer = null;
  function runSearch() {
    const q = (searchQueryInput.value || '').trim();
    if (!q) {
      searchResultEl.innerHTML = '<p class="muted">Type a query to see HPO results (live).</p>';
      return;
    }
    searchResultEl.innerHTML = '<p class="loading"><span class="spinner" aria-hidden="true"></span> Searching…</p>';
    const debug = { request: { method: 'POST', url: '/api/search', body: { query: q } }, response: {} };
    fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q })
    })
      .then(function (res) { return res.json().then(function (data) { return { res, data }; }); })
      .then(function (_) {
        const res = _.res;
        const data = _.data;
        debug.response = { status: res.status, body: data };
        if (!res.ok) {
          searchResultEl.innerHTML = '<p class="error">Error: ' + escapeHtml(data.detail || res.statusText) + '</p>';
          if (debugCheckbox && debugCheckbox.checked) searchResultEl.innerHTML += renderDebugBlock(debug);
          return;
        }
        const list = data.results || [];
        const querySent = data.query_sent != null ? String(data.query_sent) : '';
        let html = '';
        if (querySent) html += '<p class="query-sent"><strong>Query:</strong> <code>' + escapeHtml(querySent) + '</code></p>';
        if (list.length === 0) {
          html += '<p>No HPO terms found.</p>';
        } else {
          html += '<ul class="result-list">' + list.map(function (t) {
            return '<li><span class="hpo-id">' + escapeHtml(t.hpo_id || '') + '</span> ' + escapeHtml(t.name || '') +
              (t.definition ? '<br><small>' + escapeHtml((t.definition || '').slice(0, 120)) + '…</small>' : '') + '</li>';
          }).join('') + '</ul>';
        }
        if (debugCheckbox && debugCheckbox.checked) updateDebugSidebar(debug);
        searchResultEl.innerHTML = html;
      })
      .catch(function (e) {
        searchResultEl.innerHTML = '<p class="error">Error: ' + escapeHtml(e.message) + '</p>';
        if (debugCheckbox && debugCheckbox.checked) {
          debug.response = { status: '—', body: { error: e.message } };
          updateDebugSidebar(debug);
        }
      });
  }

  searchQueryInput.addEventListener('input', function () {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(runSearch, SEARCH_DEBOUNCE_MS);
  });
  searchQueryInput.addEventListener('focus', function () {
    const q = (searchQueryInput.value || '').trim();
    if (q) runSearch();
  });

  // ---- History (chat) mode: post message, agent returns extracted terms ----
  var debugContentEl = document.getElementById('debug-content');
  var debugSidebarEl = document.getElementById('debug-sidebar');
  var debugDetailsEl = document.getElementById('debug-details');

  function updateDebugSidebar(debug) {
    if (!debugContentEl || !debugSidebarEl) return;
    if (debug && debugCheckbox && debugCheckbox.checked) {
      const req = debug.request || {};
      const res = debug.response || {};
      const reqBody = typeof req.body === 'string' ? req.body : JSON.stringify(req.body, null, 2);
      const resBody = typeof res.body === 'object' ? JSON.stringify(res.body, null, 2) : String(res.body);
      debugContentEl.innerHTML = '<strong>Request</strong>\n' + escapeHtml(reqBody) + '\n\n<strong>Response</strong>\n' + escapeHtml(resBody);
      debugSidebarEl.classList.add('open');
      if (debugDetailsEl) debugDetailsEl.setAttribute('open', '');
    } else {
      debugContentEl.innerHTML = '';
      if (!debugCheckbox || !debugCheckbox.checked) debugSidebarEl.classList.remove('open');
    }
  }

  debugToggleBtn.addEventListener('click', function () {
    debugCheckbox.checked = !debugCheckbox.checked;
    debugToggleBtn.classList.toggle('active', debugCheckbox.checked);
    if (debugCheckbox.checked) {
      debugSidebarEl.classList.add('open');
      if (debugDetailsEl) debugDetailsEl.setAttribute('open', '');
    } else {
      debugSidebarEl.classList.remove('open');
    }
  });

  function parseMarkdownTable(text) {
    var lines = (text || '').trim().split(/\r?\n/);
    var rows = [];
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line || line.indexOf('|') === -1) continue;
      var cells = line.split('|').map(function (s) { return s.trim(); });
      if (cells[0] === '' && cells[cells.length - 1] === '') cells = cells.slice(1, -1);
      if (cells.length < 2) continue;
      if (/^---+$/.test(cells.join('').replace(/\s/g, ''))) continue;
      rows.push(cells);
    }
    return rows.length ? rows : null;
  }

  function renderAgentResponseAsTable(text) {
    var rows = parseMarkdownTable(text);
    if (!rows || rows.length < 2) return null;
    var headers = rows[0];
    var colTerm = 0, colHpoId = 1, colDef = 2;
    var h0 = (headers[0] || '').toLowerCase();
    if (h0.indexOf('medical') !== -1) colTerm = 0;
    if (headers.length > 1 && (headers[1] || '').toLowerCase().indexOf('hpo') !== -1) colHpoId = 1;
    if (headers.length > 2) colDef = 2;
    var html = '<table class="extract-table"><thead><tr>';
    html += '<th class="col-term">Medical term</th><th class="col-hpo-id">HPO ID</th><th class="col-def">HPO definition</th></tr></thead><tbody>';
    for (var r = 1; r < rows.length; r++) {
      var row = rows[r];
      var term = (row[colTerm] || '').trim();
      var hpoId = (row[colHpoId] !== undefined ? row[colHpoId] : '').trim();
      var def = (row[colDef] !== undefined ? row[colDef] : '').trim();
      html += '<tr><td class="col-term">' + escapeHtml(term) + '</td><td class="col-hpo-id">' + escapeHtml(hpoId) + '</td><td class="col-def">' + escapeHtml(def) + '</td></tr>';
    }
    html += '</tbody></table>';
    return html;
  }

  function renderResultsFromApi(results) {
    if (!results || !results.length) return null;
    var html = '<table class="extract-table"><thead><tr>';
    html += '<th class="col-term">Medical term</th><th class="col-hpo-id">HPO ID</th><th class="col-name">HPO Name</th><th class="col-def">HPO Definition</th></tr></thead><tbody>';
    for (var i = 0; i < results.length; i++) {
      var r = results[i];
      var term = r.medical_term || '';
      var id = r.hpo_id || '—';
      var name = r.hpo_name || '—';
      var def = (r.hpo_definition || '').slice(0, 200);
      if (def.length === 200) def += '…';
      html += '<tr><td class="col-term">' + escapeHtml(term) + '</td>';
      html += '<td class="col-hpo-id"><span class="hpo-id">' + escapeHtml(id) + '</span></td>';
      html += '<td class="col-name">' + escapeHtml(name) + '</td>';
      html += '<td class="col-def">' + escapeHtml(def || '—') + '</td></tr>';
    }
    html += '</tbody></table>';
    return html;
  }

  var chatRequestInFlight = false;

  function renderSearchDebug(apiDebug) {
    if (!apiDebug) return '';
    var html = '<details class="search-debug"><summary>Search debug (' + (apiDebug.parsed_terms || []).length + ' terms)</summary>';
    html += '<p><strong>Parsed terms:</strong> ' + escapeHtml(JSON.stringify(apiDebug.parsed_terms)) + '</p>';
    var searches = apiDebug.term_searches || [];
    for (var i = 0; i < searches.length; i++) {
      var s = searches[i];
      html += '<div class="debug-term">';
      html += '<strong>' + escapeHtml(s.term) + '</strong>';
      html += ' → query_sent: <code>' + escapeHtml(s.query_sent || '') + '</code>';
      html += ' | hits: <strong>' + (s.hit_count || 0) + '</strong>';
      if (s.error) html += ' | <span class="error">ERROR: ' + escapeHtml(s.error) + '</span>';
      if (s.raw_first_hit_keys && s.raw_first_hit_keys.length) {
        html += ' | hit keys: <code>' + escapeHtml(s.raw_first_hit_keys.join(', ')) + '</code>';
      }
      if (s.search_params) html += ' | params: <code>' + escapeHtml(JSON.stringify(s.search_params)) + '</code>';
      if (s.top_result) html += '<br>top: <code>' + escapeHtml(JSON.stringify(s.top_result)) + '</code>';
      html += '</div>';
    }
    html += '</details>';
    return html;
  }

  function appendChatMessage(role, text, debug, resultsFromApi, apiDebug) {
    var wrap = document.createElement('div');
    wrap.className = 'chat-msg chat-msg-' + role;
    var content = '';
    if (role === 'agent') {
      if (resultsFromApi && resultsFromApi.length) {
        content = renderResultsFromApi(resultsFromApi);
      }
      if (!content && text) {
        var tableHtml = renderAgentResponseAsTable(text);
        content = tableHtml || (text || '').replace(/\n/g, '<br>');
      }
      if (!content) content = (text || '').replace(/\n/g, '<br>');
      // Append inline search debug when checkbox is on
      if (debugCheckbox && debugCheckbox.checked && apiDebug) {
        content += renderSearchDebug(apiDebug);
      }
    } else {
      content = (text || '').replace(/\n/g, '<br>');
    }
    wrap.innerHTML = '<div class="chat-bubble">' + content + '</div>';
    chatHistoryEl.appendChild(wrap);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
    if (debug) updateDebugSidebar(debug);
  }

  function showChatSpinner() {
    const wrap = document.createElement('div');
    wrap.id = 'chat-spinner-wrap';
    wrap.className = 'chat-msg chat-msg-agent chat-msg-loading';
    wrap.innerHTML = '<div class="chat-bubble"><span class="spinner" aria-hidden="true"></span> Agent is thinking…</div>';
    chatHistoryEl.appendChild(wrap);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  }

  function removeChatSpinner() {
    const el = document.getElementById('chat-spinner-wrap');
    if (el) el.remove();
  }

  function setChatFormDisabled(disabled) {
    chatRequestInFlight = disabled;
    chatQueryInput.disabled = disabled;
    chatSendBtn.disabled = disabled;
  }

  var chatSendBtn = document.getElementById('chat-send');

  chatForm.addEventListener('submit', function (e) {
    e.preventDefault();
    const q = (chatQueryInput.value || '').trim();
    if (!q || chatRequestInFlight) return;
    appendChatMessage('user', q);
    chatQueryInput.value = '';
    setChatFormDisabled(true);
    showChatSpinner();
    const debug = { request: { method: 'POST', url: '/api/chat', body: { query: q } }, response: {} };
    var timeoutMs = 120000; // 2 min for LLM
    var controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, timeoutMs);
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q }),
      signal: controller.signal
    })
      .then(function (res) { return res.json().then(function (data) { return { res, data }; }); })
      .then(function (_) {
        clearTimeout(timeoutId);
        removeChatSpinner();
        setChatFormDisabled(false);
        const res = _.res;
        const data = _.data;
        debug.response = { status: res.status, body: data };
        const responseText = data.response != null ? String(data.response) : '';
        const resultsFromApi = data.results || null;
        const apiDebug = data.debug || null;
        appendChatMessage('agent', responseText, debug, resultsFromApi, apiDebug);
      })
      .catch(function (e) {
        clearTimeout(timeoutId);
        removeChatSpinner();
        setChatFormDisabled(false);
        var msg = e.name === 'AbortError'
          ? 'Request timed out. The agent may be slow; try again or shorten the message.'
          : ('Error: ' + e.message);
        debug.response = { status: '—', body: { error: e.message } };
        appendChatMessage('agent', msg, debug);
      });
  });

  // Initial state
  searchResultEl.innerHTML = '<p class="muted">Type a query to see HPO results (live).</p>';
})();
