/* ═══════════════════════════════════════════════════════════════════
   Octo Agent — Dashboard JavaScript
   ═══════════════════════════════════════════════════════════════════ */

// ── State ───────────────────────────────────────────────────────────
let ws = null;
let termWs = null;
let isConnected = false;
let currentPanel = 'chat';
const termHistory = [];
let termHistoryIdx = -1;

// ── Theme ───────────────────────────────────────────────────────────
function getTheme() { return localStorage.getItem('octo-theme') || 'dark'; }
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('octo-theme', t);
  document.getElementById('theme-icon').textContent = t === 'dark' ? '🌙' : '☀️';
}
function toggleTheme() { setTheme(getTheme() === 'dark' ? 'light' : 'dark'); }
setTheme(getTheme());

// ── Navigation ──────────────────────────────────────────────────────
const panelTitles = {
  chat: ['Chat', 'Talk to Octo Agent'],
  dashboard: ['Dashboard', 'System overview and monitoring'],
  terminal: ['Terminal', 'Execute commands in workspace'],
  cron: ['Cron Jobs', 'Scheduled task management'],
  heartbeat: ['Heartbeats', 'Agent health monitoring'],
  mcp: ['MCP Servers', 'Model Context Protocol connections'],
  mpc: ['Multi-Party Chat', 'Multi-agent orchestration'],
  settings: ['Settings', 'Configuration and API Keys'],
  agents: ['Agents', 'Manage specialized sub-agents'],
  skills: ['Skills', 'Manage custom commands and workflows'],
  files: ['Files', 'Manage system context files'],
};

document.querySelectorAll('.nav-item[data-panel]').forEach(item => {
  item.addEventListener('click', () => switchPanel(item.dataset.panel));
});

function switchPanel(panel) {
  currentPanel = panel;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const navEl = document.querySelector(`[data-panel="${panel}"]`);
  if (navEl) navEl.classList.add('active');

  const [title, sub] = panelTitles[panel] || [panel, ''];
  document.getElementById('panel-title').textContent = title;
  document.getElementById('panel-subtitle').textContent = sub;

  document.querySelectorAll('.panel, .chat-panel, .terminal-panel').forEach(p => p.classList.remove('active'));
  const el = document.getElementById(`panel-${panel}`);
  if (el) el.classList.add('active');

  if (panel === 'dashboard') loadDashboard();
  if (panel === 'cron') loadCronJobs();
  if (panel === 'heartbeat') loadHeartbeats();
  if (panel === 'mcp') loadMCP();
  if (panel === 'mpc') loadMPCAgents();
  if (panel === 'terminal') connectTerminal();
  if (panel === 'settings') loadSettings();
  if (panel === 'agents') loadAgents();
  if (panel === 'skills') loadSkills();
}

// ── WebSocket Chat ──────────────────────────────────────────────────
function connectWebSocket() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws/chat`);
  ws.onopen = () => { isConnected = true; updateStatus('healthy'); };
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    removeTypingIndicator();
    // Show tool events if any
    if (data.tools && data.tools.length) {
      data.tools.forEach(t => appendToolEvent(t.tool, t.result));
    }
    appendMessage('assistant', data.content, data.timestamp);
    document.getElementById('chat-send').disabled = false;
    document.getElementById('chat-input').disabled = false;
  };
  ws.onerror = () => updateStatus('degraded');
  ws.onclose = () => {
    isConnected = false;
    updateStatus('offline');
    setTimeout(connectWebSocket, 3000);
  };
}

function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  appendMessage('user', text);
  ws.send(JSON.stringify({ content: text }));
  input.value = '';
  input.style.height = 'auto';
  showTypingIndicator();
  document.getElementById('chat-send').disabled = true;
  document.getElementById('chat-input').disabled = true;
}

function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
}

function appendMessage(role, content, timestamp) {
  const container = document.getElementById('chat-messages');
  const msg = document.createElement('div');
  msg.className = `chat-message ${role}`;
  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'assistant' ? '🐙' : '👤';
  const wrapper = document.createElement('div');
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = renderMarkdown(content);
  const time = document.createElement('div');
  time.className = 'msg-time';
  time.textContent = timestamp ? new Date(timestamp).toLocaleTimeString() : 'Just now';
  wrapper.appendChild(bubble);
  wrapper.appendChild(time);
  msg.appendChild(avatar);
  msg.appendChild(wrapper);
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

function appendToolEvent(toolName, result) {
  const container = document.getElementById('chat-messages');
  const el = document.createElement('div');
  el.className = 'tool-event';
  el.style.maxWidth = '800px';
  el.style.margin = '0 auto';
  el.innerHTML = `<span class="tool-name">🔧 ${esc(toolName)}</span> <span style="color:var(--text-muted)">${esc(result.substring(0, 120))}${result.length > 120 ? '…' : ''}</span>`;
  container.appendChild(el);
}

function showTypingIndicator() {
  const container = document.getElementById('chat-messages');
  const indicator = document.createElement('div');
  indicator.className = 'chat-message assistant';
  indicator.id = 'typing-indicator';
  indicator.innerHTML = `
    <div class="msg-avatar">🐙</div>
    <div>
      <div class="msg-bubble">
        <div class="typing-indicator"><span></span><span></span><span></span></div>
      </div>
    </div>`;
  container.appendChild(indicator);
  container.scrollTop = container.scrollHeight;
}

function removeTypingIndicator() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

// ── Terminal WebSocket ──────────────────────────────────────────────
function connectTerminal() {
  if (termWs && termWs.readyState === WebSocket.OPEN) return;
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  termWs = new WebSocket(`${proto}//${location.host}/ws/terminal`);
  termWs.onopen = () => appendTermLine('system', '✓ Terminal connected.');
  termWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    const lines = (data.output || '').split('\n');
    lines.forEach(l => appendTermLine(data.exit_code === 0 ? 'output' : 'error', l));
    document.getElementById('terminal-input').disabled = false;
    document.getElementById('terminal-input').focus();
  };
  termWs.onerror = () => appendTermLine('error', 'Terminal connection error.');
  termWs.onclose = () => appendTermLine('system', 'Terminal disconnected.');
}

function handleTerminalKey(event) {
  if (event.key === 'Enter') {
    const input = document.getElementById('terminal-input');
    const cmd = input.value.trim();
    if (!cmd) return;
    termHistory.push(cmd);
    termHistoryIdx = termHistory.length;
    appendTermLine('command', cmd);
    input.value = '';
    input.disabled = true;
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(JSON.stringify({ command: cmd }));
    } else {
      appendTermLine('error', 'Not connected. Reconnecting...');
      input.disabled = false;
      connectTerminal();
    }
  } else if (event.key === 'ArrowUp') {
    if (termHistoryIdx > 0) {
      termHistoryIdx--;
      document.getElementById('terminal-input').value = termHistory[termHistoryIdx] || '';
    }
    event.preventDefault();
  } else if (event.key === 'ArrowDown') {
    if (termHistoryIdx < termHistory.length - 1) {
      termHistoryIdx++;
      document.getElementById('terminal-input').value = termHistory[termHistoryIdx] || '';
    } else {
      termHistoryIdx = termHistory.length;
      document.getElementById('terminal-input').value = '';
    }
    event.preventDefault();
  }
}

function appendTermLine(type, text) {
  const out = document.getElementById('terminal-output');
  const line = document.createElement('div');
  line.className = `terminal-line ${type}`;
  line.textContent = text;
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
}

// ── Conversations ───────────────────────────────────────────────────
async function loadConversations() {
  const data = await api('/api/conversations');
  if (!data) return;
  const list = document.getElementById('conversation-list');
  if (!data.conversations.length) {
    list.innerHTML = '<div style="padding:8px 12px;font-size:11px;color:var(--text-muted)">No conversations yet</div>';
    return;
  }
  list.innerHTML = data.conversations.slice(0, 10).map(c =>
    `<div class="conv-item" style="display: flex; justify-content: space-between; align-items: center;" onclick="openConversation('${c.id}')" title="${esc(c.preview || c.name)}">
      <span style="flex-grow: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${esc(c.name)}</span>
      <button onclick="deleteConversation('${c.id}', event)" style="background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 0 4px;" title="Delete">✕</button>
    </div>`
  ).join('');
}

async function deleteConversation(convId, event) {
  event.stopPropagation();
  if (!confirm(`Delete conversation?`)) return;
  await api(`/api/conversations/${convId}`, { method: 'DELETE' });
  loadConversations();
  if (currentPanel === 'dashboard') loadDashboard();
}

async function openConversation(convId) {
  const data = await api(`/api/conversations/${convId}`);
  if (!data) return;
  switchPanel('chat');
  const container = document.getElementById('chat-messages');
  container.innerHTML = '';
  // Parse the markdown chat content
  const lines = (data.content || '').split('\n');
  let currentRole = null, currentContent = [];
  lines.forEach(line => {
    const match = line.match(/^### .+\((USER|ASSISTANT)\)$/);
    if (match) {
      if (currentRole && currentContent.length) {
        appendMessage(currentRole.toLowerCase(), currentContent.join('\n').trim());
      }
      currentRole = match[1];
      currentContent = [];
    } else if (currentRole) {
      currentContent.push(line);
    }
  });
  if (currentRole && currentContent.length) {
    appendMessage(currentRole.toLowerCase(), currentContent.join('\n').trim());
  }
}

async function createNewChat() {
  // Just reload the page to start a fresh WS connection
  const container = document.getElementById('chat-messages');
  container.innerHTML = `
    <div class="chat-message assistant">
      <div class="msg-avatar">🐙</div>
      <div>
        <div class="msg-bubble"><p>Hello! I'm Octo, your AI assistant. How can I help you today?</p></div>
        <div class="msg-time">Just now</div>
      </div>
    </div>`;
  switchPanel('chat');
  // Reconnect WS for fresh session
  if (ws) ws.close();
  setTimeout(connectWebSocket, 300);
  loadConversations();
}

// ── Markdown Renderer ───────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return '';
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\n/g, '<br/>');
  if (!html.includes('<h') && !html.includes('<pre>')) html = `<p>${html}</p>`;
  return html;
}

// ── Status ──────────────────────────────────────────────────────────
function updateStatus(state) {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  dot.className = 'status-dot';
  if (state === 'healthy') { text.textContent = 'Connected'; }
  else if (state === 'degraded') { dot.classList.add('degraded'); text.textContent = 'Degraded'; }
  else { dot.classList.add('offline'); text.textContent = 'Disconnected'; }
}

// ── API Helpers ─────────────────────────────────────────────────────
async function api(path, options = {}) {
  try {
    const resp = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
    return await resp.json();
  } catch (e) { console.error(`API error (${path}):`, e); return null; }
}

// ── Dashboard ───────────────────────────────────────────────────────
async function loadDashboard() {
  const data = await api('/api/status');
  if (!data) return;
  const statsEl = document.getElementById('dashboard-stats');
  const uptime = data.uptime ? formatUptime(data.uptime) : 'N/A';
  statsEl.innerHTML = `
    <div class="stat-card"><div class="stat-icon">🤖</div><div class="stat-label">Model</div><div class="stat-value" style="font-size:18px">${data.model || 'N/A'}</div><div class="stat-sub">Active model</div></div>
    <div class="stat-card"><div class="stat-icon">⏱</div><div class="stat-label">Uptime</div><div class="stat-value" style="font-size:22px">${uptime}</div><div class="stat-sub">Since agent start</div></div>
    <div class="stat-card"><div class="stat-icon">⏰</div><div class="stat-label">Cron Jobs</div><div class="stat-value">${data.cron_jobs}</div><div class="stat-sub">Scheduled tasks</div></div>
    <div class="stat-card"><div class="stat-icon">🔌</div><div class="stat-label">MCP Servers</div><div class="stat-value">${data.mcp_servers ? data.mcp_servers.length : 0}</div><div class="stat-sub">Connected protocols</div></div>`;
  const hbData = await api('/api/heartbeats');
  if (hbData && hbData.history.length) renderHeartbeatChart('mini-hb-chart', hbData.history.slice(-30));
  const convos = await api('/api/conversations');
  const convosEl = document.getElementById('recent-convos');
  if (convos && convos.conversations.length) {
    convosEl.innerHTML = convos.conversations.slice(0, 8).map(c =>
      `<div style="padding:8px 0;border-bottom:1px solid var(--border-color);font-size:13px;color:var(--text-secondary);cursor:pointer" onclick="openConversation('${c.id}')">📄 ${esc(c.name)} <span style="color:var(--text-muted);font-size:11px">${c.preview ? '— ' + esc(c.preview) : ''}</span></div>`
    ).join('');
  } else {
    convosEl.innerHTML = '<div class="empty-state"><div class="empty-icon">📝</div><div class="empty-text">No conversations yet</div></div>';
  }
}

// ── Cron Jobs ───────────────────────────────────────────────────────
async function loadCronJobs() {
  const data = await api('/api/cron');
  if (!data) return;
  const el = document.getElementById('cron-list');
  document.getElementById('cron-badge').textContent = data.jobs.length;
  if (!data.jobs.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-icon">⏰</div><div class="empty-text">No cron jobs configured.</div></div>';
    return;
  }
  el.innerHTML = `<table class="data-table"><thead><tr><th>Name</th><th>Schedule</th><th>Status</th><th>Last Run</th><th>Runs</th><th>Actions</th></tr></thead><tbody>${data.jobs.map(j => `<tr><td><strong>${esc(j.name)}</strong></td><td><code>${esc(j.schedule)}</code></td><td><span class="pill ${j.enabled ? 'green' : 'yellow'}">${j.enabled ? 'Active' : 'Paused'}</span></td><td style="color:var(--text-muted)">${j.last_run ? new Date(j.last_run).toLocaleString() : 'Never'}</td><td>${j.run_count}</td><td><button class="btn btn-sm btn-secondary" onclick="toggleCron('${j.job_id}')">${j.enabled ? '⏸' : '▶'}</button> <button class="btn btn-sm btn-danger" onclick="deleteCron('${j.job_id}')">✕</button></td></tr>`).join('')}</tbody></table>`;
}

function openCronModal() { document.getElementById('cron-modal').classList.add('open'); }
function closeCronModal() { document.getElementById('cron-modal').classList.remove('open'); }

async function addCronJob() {
  const name = document.getElementById('cron-name').value.trim();
  const schedule = document.getElementById('cron-schedule').value.trim();
  const prompt = document.getElementById('cron-prompt').value.trim();
  if (!name || !schedule || !prompt) return;
  await api('/api/cron', { method: 'POST', body: JSON.stringify({ name, schedule, prompt }) });
  closeCronModal();
  ['cron-name','cron-schedule','cron-prompt'].forEach(id => document.getElementById(id).value = '');
  loadCronJobs();
}

async function toggleCron(id) { await api(`/api/cron/${id}/toggle`, { method: 'POST' }); loadCronJobs(); }
async function deleteCron(id) { await api(`/api/cron/${id}`, { method: 'DELETE' }); loadCronJobs(); }

// ── Heartbeats ──────────────────────────────────────────────────────
async function loadHeartbeats() {
  const data = await api('/api/heartbeats');
  if (!data) return;
  const history = data.history;
  const latest = history.length ? history[history.length - 1] : null;
  const statsEl = document.getElementById('hb-stats');
  if (latest) {
    const sys = latest.system || {};
    const proc = latest.process || {};
    statsEl.innerHTML = `
      <div class="stat-card"><div class="stat-icon">💚</div><div class="stat-label">Status</div><div class="stat-value" style="font-size:18px">${latest.status || 'unknown'}</div></div>
      <div class="stat-card"><div class="stat-icon">🖥</div><div class="stat-label">CPU</div><div class="stat-value">${sys.cpu_percent || 'N/A'}%</div></div>
      <div class="stat-card"><div class="stat-icon">🧠</div><div class="stat-label">Memory</div><div class="stat-value">${proc.memory_mb || 'N/A'} MB</div><div class="stat-sub">${sys.memory_used_percent || '?'}% system</div></div>
      <div class="stat-card"><div class="stat-icon">🌐</div><div class="stat-label">API</div><div class="stat-value" style="font-size:18px">${latest.api_reachable ? '✓ Online' : '✗ Offline'}</div></div>`;
  }
  renderHeartbeatChart('hb-chart', history.slice(-50));
  const tableEl = document.getElementById('hb-table-container');
  const recent = history.slice(-10).reverse();
  if (recent.length) {
    tableEl.innerHTML = `<table class="data-table"><thead><tr><th>Time</th><th>Status</th><th>CPU</th><th>Memory</th><th>API</th></tr></thead><tbody>${recent.map(h => { const s=h.system||{}; const p=h.process||{}; return `<tr><td style="color:var(--text-muted)">${new Date(h.timestamp).toLocaleTimeString()}</td><td><span class="pill ${h.status==='healthy'?'green':'yellow'}">${h.status}</span></td><td>${s.cpu_percent||'-'}%</td><td>${p.memory_mb||'-'} MB</td><td>${h.api_reachable?'<span class="pill green">✓</span>':'<span class="pill red">✗</span>'}</td></tr>`; }).join('')}</tbody></table>`;
  }
}

function renderHeartbeatChart(elementId, data) {
  const el = document.getElementById(elementId);
  if (!data.length) { el.innerHTML = '<span style="color:var(--text-muted)">No data yet</span>'; return; }
  const maxCpu = Math.max(...data.map(d => (d.system || {}).cpu_percent || 10), 10);
  el.innerHTML = data.map(d => {
    const cpu = (d.system || {}).cpu_percent || 0;
    const h = Math.max((cpu / maxCpu) * 100, 5);
    const cls = d.status === 'healthy' ? 'healthy' : 'degraded';
    return `<div class="hb-bar ${cls}" style="height:${h}%" title="${new Date(d.timestamp).toLocaleTimeString()}: CPU ${cpu}%"></div>`;
  }).join('');
}

// ── MCP ─────────────────────────────────────────────────────────────
async function loadMCP() {
  const data = await api('/api/mcp');
  if (!data) return;
  const el = document.getElementById('mcp-list');
  if (!data.servers.length) {
    el.innerHTML = `<div class="empty-state"><div class="empty-icon">🔌</div><div class="empty-text">No MCP servers configured.<br/>Add servers to <code>mcp_config.json</code>.</div></div>`;
    return;
  }
  el.innerHTML = data.servers.map(s => `<div class="card"><div class="card-title">🔌 ${esc(s.name)} <span class="pill ${s.connected ? 'green' : 'red'}">${s.connected ? 'Connected' : 'Disconnected'}</span></div><div style="font-size:12px;color:var(--text-muted)">Command: <code>${esc(s.command)}</code><br/>Tools: ${s.tools_count}</div></div>`).join('');
}

// ── MPC ─────────────────────────────────────────────────────────────
async function loadMPCAgents() {
  const data = await api('/api/mpc/agents');
  if (!data) return;
  const el = document.getElementById('mpc-agents-list');
  if (!data.agents.length) { el.innerHTML = '<div style="color:var(--text-muted)">No agents available.</div>'; return; }
  el.innerHTML = data.agents.map(a => `<span class="pill purple" style="margin:4px">${esc(a)}</span>`).join('');
}

async function runPipeline() {
  const agents = document.getElementById('mpc-pipeline-agents').value.split(',').map(s => s.trim()).filter(Boolean);
  const task = document.getElementById('mpc-pipeline-task').value.trim();
  if (!agents.length || !task) return;
  displayMPCResults(await api('/api/mpc/pipeline', { method: 'POST', body: JSON.stringify({ agents, task }) }));
}

async function runDebate() {
  const agents = document.getElementById('mpc-pipeline-agents').value.split(',').map(s => s.trim()).filter(Boolean);
  const task = document.getElementById('mpc-pipeline-task').value.trim();
  if (!agents.length || !task) return;
  displayMPCResults(await api('/api/mpc/debate', { method: 'POST', body: JSON.stringify({ agents, task, rounds: 2 }) }));
}

function displayMPCResults(data) {
  if (!data || !data.results) return;
  const card = document.getElementById('mpc-results-card');
  const el = document.getElementById('mpc-results');
  card.style.display = 'block';
  el.innerHTML = data.results.map(r => `<div class="card" style="margin-bottom:12px"><div class="card-title"><span class="pill purple">${esc(r.agent)}</span> <span style="color:var(--text-muted);font-size:11px">Step ${r.step}</span></div><div style="font-size:13px">${renderMarkdown(r.content)}</div></div>`).join('');
}

// ── Utilities ───────────────────────────────────────────────────────
function esc(text) { const d = document.createElement('div'); d.textContent = text; return d.innerHTML; }
function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

async function refreshStatus() {
  if (currentPanel === 'dashboard') loadDashboard();
  else if (currentPanel === 'cron') loadCronJobs();
  else if (currentPanel === 'heartbeat') loadHeartbeats();
  else if (currentPanel === 'mcp') loadMCP();
  else if (currentPanel === 'mpc') loadMPCAgents();
  else if (currentPanel === 'settings') loadSettings();
  else if (currentPanel === 'agents') loadAgents();
  else if (currentPanel === 'skills') loadSkills();
}

// ── Settings ────────────────────────────────────────────────────────
async function loadSettings() {
  const data = await api('/api/settings');
  if (!data) return;
  document.getElementById('setting-or-key').value = data.OPENROUTER_API_KEY || '';
  document.getElementById('setting-or-model').value = data.OPENROUTER_MODEL || '';
  document.getElementById('setting-oa-key').value = data.OPENAI_API_KEY || '';
  document.getElementById('setting-oa-model').value = data.OPENAI_MODEL || '';
}

async function saveSettings() {
  const body = {
    OPENROUTER_API_KEY: document.getElementById('setting-or-key').value,
    OPENROUTER_MODEL: document.getElementById('setting-or-model').value,
    OPENAI_API_KEY: document.getElementById('setting-oa-key').value,
    OPENAI_MODEL: document.getElementById('setting-oa-model').value,
  };
  const res = await api('/api/settings', { method: 'POST', body: JSON.stringify(body) });
  if (res && res.status === 'ok') {
    alert('Settings saved. You may need to restart the agent to apply all changes.');
  }
}

// ── Agents ──────────────────────────────────────────────────────────
async function loadAgents() {
  const data = await api('/api/agents');
  if (!data) return;
  const el = document.getElementById('agents-list');
  if (!data.agents.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-icon">🤖</div><div class="empty-text">No agents found</div></div>';
    return;
  }
  el.innerHTML = data.agents.map(a => `<div class="card"><div class="card-title">🤖 ${esc(a.name)} <div style="margin-left:auto"><button class="btn btn-sm btn-danger" onclick="deleteAgent('${esc(a.name)}')">Delete</button></div></div><pre style="max-height:100px;overflow:auto;font-size:12px">${esc(a.content)}</pre></div>`).join('');
}

function openAgentModal() {
  document.getElementById('agent-name').value = '';
  document.getElementById('agent-content').value = '';
  document.getElementById('agent-modal').classList.add('open');
}
function closeAgentModal() { document.getElementById('agent-modal').classList.remove('open'); }

async function saveAgent() {
  const name = document.getElementById('agent-name').value.trim();
  const content = document.getElementById('agent-content').value.trim();
  if (!name) return;
  await api('/api/agents', { method: 'POST', body: JSON.stringify({ name, content }) });
  closeAgentModal();
  loadAgents();
}
async function deleteAgent(name) {
  if (!confirm(`Delete agent ${name}?`)) return;
  await api(`/api/agents/${name}`, { method: 'DELETE' });
  loadAgents();
}

// ── Skills ──────────────────────────────────────────────────────────
async function loadSkills() {
  const data = await api('/api/skills');
  if (!data) return;
  const el = document.getElementById('skills-list');
  if (!data.skills.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-icon">🛠</div><div class="empty-text">No skills found</div></div>';
    return;
  }
  el.innerHTML = data.skills.map(s => `<div class="card"><div class="card-title">🛠 ${esc(s.name)} <div style="margin-left:auto"><button class="btn btn-sm btn-danger" onclick="deleteSkill('${esc(s.name)}')">Delete</button></div></div><pre style="max-height:100px;overflow:auto;font-size:12px">${esc(s.content)}</pre></div>`).join('');
}

function openSkillModal() {
  document.getElementById('skill-name').value = '';
  document.getElementById('skill-content').value = '';
  document.getElementById('skill-modal').classList.add('open');
}
function closeSkillModal() { document.getElementById('skill-modal').classList.remove('open'); }

async function saveSkill() {
  const name = document.getElementById('skill-name').value.trim();
  const content = document.getElementById('skill-content').value.trim();
  if (!name) return;
  await api('/api/skills', { method: 'POST', body: JSON.stringify({ name, content }) });
  closeSkillModal();
  loadSkills();
}
async function deleteSkill(name) {
  if (!confirm(`Delete skill ${name}?`)) return;
  await api(`/api/skills/${name}`, { method: 'DELETE' });
  loadSkills();
}

// ── Files ───────────────────────────────────────────────────────────
let currentEditingFile = null;
async function openFileEditor(filename) {
  const data = await api(`/api/files/${filename}`);
  if (!data) return;
  currentEditingFile = filename;
  document.getElementById('file-editor-title').textContent = `Editing: ${filename}`;
  document.getElementById('file-editor-content').value = data.content;
  document.getElementById('file-editor-card').style.display = 'block';
  document.getElementById('file-editor-content').scrollIntoView({ behavior: 'smooth' });
}

async function saveFileEditor() {
  if (!currentEditingFile) return;
  const content = document.getElementById('file-editor-content').value;
  const res = await api(`/api/files/${currentEditingFile}`, { method: 'POST', body: JSON.stringify({ content }) });
  if (res && res.status === 'ok') {
    alert(`${currentEditingFile} saved successfully.`);
  }
}

// ── Auto-resize textarea ────────────────────────────────────────────
const chatInput = document.getElementById('chat-input');
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

// ── Init ────────────────────────────────────────────────────────────
connectWebSocket();
loadConversations();
setInterval(async () => {
  const data = await api('/api/status');
  if (data) {
    updateStatus(data.heartbeat && data.heartbeat.status === 'healthy' ? 'healthy' : 'degraded');
    document.getElementById('cron-badge').textContent = data.cron_jobs || 0;
  }
}, 30000);
