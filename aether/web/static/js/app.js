const STORAGE_KEY = 'aether-ui-v1';

function getApiBase() {
  const saved = localStorage.getItem('aether-api-base');
  if (saved && saved.trim()) return saved.trim().replace(/\/$/, '');
  return '';
}

let deferredInstallPrompt = null;

const state = {
  sessions: [],
  activeSessionId: null,
  streaming: false,
  workflowRunning: false,
  selectedModel: '',
  settings: { model: '', elevenKey: '' },
};

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      state.sessions = data.sessions || [];
      state.activeSessionId = data.activeSessionId;
      state.settings = data.settings || state.settings;
    }
  } catch (_) {}
  if (!state.sessions.length) newSession();
  if (!state.activeSessionId) state.activeSessionId = state.sessions[0].id;
}

function saveState() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      sessions: state.sessions,
      activeSessionId: state.activeSessionId,
      settings: state.settings,
    }),
  );
}

function newSession() {
  const id = crypto.randomUUID();
  state.sessions.unshift({ id, title: 'New chat', messages: [] });
  state.activeSessionId = id;
  saveState();
  renderSessions();
  renderMessages();
}

function activeSession() {
  return state.sessions.find((s) => s.id === state.activeSessionId);
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

// DOM refs
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const pulse = $('#pulse');
const chatMessages = $('#chat-messages');
const emptyState = $('#empty-state');
const chatForm = $('#chat-form');
const chatInput = $('#chat-input');
const sendBtn = $('#send-btn');
const modelSelect = $('#model-select');
const healthPill = $('#health-pill');
const bannerOffline = $('#banner-offline');
const sessionList = $('#session-list');
const systemPanel = $('#system-panel');

async function api(path, opts = {}) {
  const res = await fetch(`${getApiBase()}${path}`, opts);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res;
}

async function checkHealth() {
  try {
    const data = await api('/api/health').then((r) => r.json());
    healthPill.textContent = data.ollama ? 'Ollama online' : 'Ollama offline';
    healthPill.className = `health-pill ${data.ollama ? 'ok' : 'bad'}`;
    $('#sys-ollama').textContent = data.ollama ? 'Online' : 'Offline';
    $('#sys-model').textContent = data.model || '-';
    bannerOffline.classList.toggle('hidden', data.ollama);
    return data;
  } catch {
    healthPill.textContent = 'Server offline';
    healthPill.className = 'health-pill bad';
    bannerOffline.classList.remove('hidden');
    return null;
  }
}

async function loadModels() {
  try {
    const data = await api('/api/models').then((r) => r.json());
    modelSelect.innerHTML = '';
    const list = data.data || [];
    const def = state.settings.model || data.default;
    list.forEach((m) => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name || m.id;
      modelSelect.appendChild(opt);
    });
    if (def) {
      modelSelect.value = def;
      state.selectedModel = def;
    } else if (list[0]) {
      state.selectedModel = list[0].id;
    }
  } catch (_) {
    modelSelect.innerHTML = '<option>llama3.1:8b</option>';
    state.selectedModel = 'llama3.1:8b';
  }
}

async function refreshSystemPanel() {
  try {
    const [agents, traces] = await Promise.all([
      api('/api/agents/status').then((r) => r.json()),
      api('/api/traces?limit=8').then((r) => r.json()),
    ]);
    const ul = $('#sys-agents');
    ul.innerHTML = '';
    (agents.agents || []).forEach((a) => {
      const li = document.createElement('li');
      li.innerHTML = `<span>${a.name}</span><span>${a.status}</span>`;
      ul.appendChild(li);
    });
    const tl = $('#sys-traces');
    tl.innerHTML = '';
    (traces.traces || []).forEach((t) => {
      const li = document.createElement('li');
      li.innerHTML = `<span>${t.kind}</span><span>${t.status}</span>`;
      tl.appendChild(li);
    });
  } catch (_) {}
}

function renderSessions() {
  sessionList.innerHTML = '';
  state.sessions.forEach((s) => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.textContent = s.title;
    btn.className = s.id === state.activeSessionId ? 'active' : '';
    btn.onclick = () => {
      state.activeSessionId = s.id;
      saveState();
      renderSessions();
      renderMessages();
    };
    li.appendChild(btn);
    sessionList.appendChild(li);
  });
}

function renderMessages() {
  const session = activeSession();
  if (!session) return;
  const inner = document.createElement('div');
  inner.className = 'messages-inner';

  if (!session.messages.length) {
    chatMessages.innerHTML = '';
    emptyState.style.display = 'flex';
    $('#greeting').textContent = greeting();
    chatMessages.appendChild(emptyState);
    return;
  }

  emptyState.style.display = 'none';
  session.messages.forEach((m) => {
    inner.appendChild(messageEl(m.role, m.content, false));
  });
  chatMessages.innerHTML = '';
  chatMessages.appendChild(inner);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function messageEl(role, content, streaming) {
  const wrap = document.createElement('div');
  wrap.className = `msg ${role}${streaming ? ' streaming' : ''}`;
  wrap.innerHTML = `
    <span class="msg-role">${role}</span>
    <div class="msg-bubble">${escapeHtml(content)}</div>
  `;
  return wrap;
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function streamChat(messages, onDelta) {
  const res = await api('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      model: state.selectedModel || modelSelect.value,
      stream: true,
      speak: $('#speak-replies').checked,
    }),
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let full = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let event = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) event = line.slice(7).trim();
      else if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') return full;
        try {
          const parsed = JSON.parse(data);
          if (event === 'error') throw new Error(parsed.message);
          const delta = parsed.choices?.[0]?.delta?.content;
          if (delta) {
            full += delta;
            onDelta(full);
          }
        } catch (e) {
          if (e.message && event === 'error') throw e;
        }
        event = '';
      }
    }
  }
  return full;
}

async function sendMessage(text) {
  const session = activeSession();
  if (!session || !text.trim() || state.streaming) return;

  session.messages.push({ role: 'user', content: text.trim() });
  if (session.title === 'New chat') session.title = text.trim().slice(0, 40);
  saveState();
  renderSessions();
  renderMessages();

  state.streaming = true;
  sendBtn.disabled = true;
  pulse.className = 'pulse streaming';

  const inner = document.createElement('div');
  inner.className = 'messages-inner';
  session.messages.forEach((m) => inner.appendChild(messageEl(m.role, m.content, false)));
  const assistantEl = messageEl('assistant', '', true);
  inner.appendChild(assistantEl);
  chatMessages.innerHTML = '';
  chatMessages.appendChild(inner);

  const bubble = assistantEl.querySelector('.msg-bubble');

  try {
    const history = session.messages.slice(0, -1).map((m) => ({
      role: m.role,
      content: m.content,
    }));
    history.push({ role: 'user', content: text.trim() });

    const full = await streamChat(history, (partial) => {
      bubble.textContent = partial;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    });

    assistantEl.classList.remove('streaming');
    session.messages.push({ role: 'assistant', content: full });
    saveState();
    refreshSystemPanel();
    if (voiceAssistant.active || $('#speak-replies').checked) voiceAssistant.speak(full);
  } catch (err) {
    assistantEl.classList.remove('streaming');
    bubble.textContent = `Error: ${err.message}`;
  } finally {
    state.streaming = false;
    sendBtn.disabled = false;
    pulse.className = 'pulse idle';
  }
}

async function runWorkflow(topic) {
  if (!topic.trim() || state.workflowRunning) return;
  const log = $('#workflow-log');
  log.innerHTML = '';
  const add = (t) => {
    const d = document.createElement('div');
    d.className = 'line';
    d.textContent = t;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  };

  state.workflowRunning = true;
  pulse.className = 'pulse workflow';
  add(`Starting workflow: ${topic}`);

  try {
    const res = await api('/api/workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic: topic.trim(),
        speak: $('#workflow-speak').checked,
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      let event = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) event = line.slice(7).trim();
        else if (line.startsWith('data: ')) {
          const raw = line.slice(6);
          if (raw === '[DONE]') continue;
          try {
            const data = JSON.parse(raw);
            if (event === 'workflow_progress') {
              add(`Progress: ${data.completed}/${data.total} (${Math.round(data.percent)}%)`);
            } else if (event === 'task_started') {
              add(`Task started: ${data.task}`);
            } else if (event === 'task_completed') {
              add(`Task done: ${data.task}`);
            } else if (event === 'workflow_done') {
              add(`Finished: ${data.status} (${data.tasks_completed} tasks)`);
              if (data.shared_context?.study_sheet) {
                add('Study sheet saved to data folder.');
              }
            } else if (event === 'workflow_start') {
              add(`Workflow: ${data.name}`);
            }
          } catch (_) {}
          event = '';
        }
      }
    }
    refreshSystemPanel();
    loadMemory();
  } catch (err) {
    add(`Error: ${err.message}`);
  } finally {
    state.workflowRunning = false;
    pulse.className = 'pulse idle';
  }
}

async function loadAgents() {
  const grid = $('#agents-grid');
  grid.innerHTML = '';
  try {
    const data = await api('/api/agents/status').then((r) => r.json());
    (data.agents || []).forEach((a) => {
      const card = document.createElement('div');
      card.className = 'agent-card';
      card.innerHTML = `
        <div class="role">${a.role}</div>
        <h3>${a.name}</h3>
        <div class="status">Status: ${a.status} · Done: ${a.completed} · Failed: ${a.failed}</div>
      `;
      grid.appendChild(card);
    });
  } catch (err) {
    grid.innerHTML = `<p class="hint">${err.message}</p>`;
  }
}

async function loadMemory() {
  const list = $('#memory-list');
  list.innerHTML = '';
  try {
    const data = await api('/api/memory').then((r) => r.json());
    const entries = data.entries || data;
    const keys = Object.keys(entries);
    if (!keys.length) {
      list.innerHTML = '<p class="hint" style="padding:24px">No stored topics yet. Run a workflow first.</p>';
      return;
    }
    keys.forEach((topic) => {
      const item = document.createElement('div');
      item.className = 'memory-item';
      const sheet = entries[topic].study_sheet || JSON.stringify(entries[topic], null, 2);
      item.innerHTML = `<h3>${escapeHtml(topic)}</h3><pre>${escapeHtml(String(sheet).slice(0, 2000))}</pre>`;
      list.appendChild(item);
    });
  } catch (err) {
    list.innerHTML = `<p class="hint">${err.message}</p>`;
  }
}

function switchView(view) {
  $$('.view').forEach((v) => v.classList.remove('active'));
  $$('.nav-item').forEach((n) => n.classList.remove('active'));
  $(`#view-${view}`).classList.add('active');
  $(`.nav-item[data-view="${view}"]`).classList.add('active');
  $('#view-title').textContent = view.charAt(0).toUpperCase() + view.slice(1);
  if (view === 'agents') loadAgents();
  if (view === 'memory') loadMemory();
  if (view === 'printer') loadPrinterView();
  if (view === 'autonomy') startAutoPolling();
  if (view === 'home') loadHomeView();
}

// ---- Build App ----
$('#run-build-app').onclick = async () => {
  const spec = $('#build-spec').value.trim();
  if (!spec) return alert('Describe what to build');
  const log = $('#build-app-log');
  log.innerHTML = '';
  $('#build-app-state').textContent = 'building';
  pulse.className = 'pulse workflow';
  const line = (m) => { const d = document.createElement('div'); d.className = 'line'; d.textContent = m; log.appendChild(d); log.scrollTop = log.scrollHeight; };
  try {
    await streamPost('/api/build-app', { spec, name: $('#build-name').value.trim() }, log, (ev, data) => {
      if (ev === 'planned') line(`Plan: ${data.project}: ${(data.stack || []).join(', ')} (${data.file_count} files)`);
      else if (ev === 'file_start') line(`Writing ${data.path} (${data.i}/${data.n})`);
      else if (ev === 'file_done') line(`  ✓ ${data.path} (${data.chars} chars)`);
      else if (ev === 'done') {
        line(`Done. Project at: ${data.dir}`);
        line(`Install: ${data.install_command}`);
        line(`Run: ${data.run_command}`);
        voiceAssistant.speak(`Your project is ready, ${voiceAssistant.persona.user_title}. ${data.files.length} files written.`);
      }
    });
  } catch (e) {
    line('Error: ' + e.message);
  } finally {
    $('#build-app-state').textContent = 'idle';
    pulse.className = 'pulse idle';
  }
};

// ---- Smart Home ----
let homeEntities = [];
async function loadHomeView() {
  const status = $('#home-status');
  try {
    const data = await api('/api/smarthome/entities').then((r) => r.json());
    if (!data.configured) {
      status.textContent = 'Home Assistant not configured. Set HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN in .env.';
      $('#home-entities').innerHTML = '';
      return;
    }
    homeEntities = data.entities || [];
    status.textContent = data.online ? `Connected: ${homeEntities.length} devices` : `Offline: ${data.error || 'cannot reach hub'}`;
    renderHome();
  } catch (e) {
    status.textContent = 'Cannot reach server: ' + e.message;
  }
}

function renderHome() {
  const wrap = $('#home-entities');
  const filter = ($('#home-search').value || '').toLowerCase();
  const controllable = homeEntities.filter((e) => ['light', 'switch', 'fan', 'input_boolean', 'climate'].includes(e.domain));
  wrap.innerHTML = '';
  controllable
    .filter((e) => !filter || e.name.toLowerCase().includes(filter) || e.entity_id.includes(filter))
    .slice(0, 60)
    .forEach((e) => {
      const row = document.createElement('div');
      row.className = 'home-row';
      const on = e.state === 'on';
      row.innerHTML = `<div><div class="home-name">${escapeHtml(e.name)}</div><div class="home-meta">${e.entity_id} · ${e.state}</div></div>`;
      const btn = document.createElement('button');
      btn.className = 'home-toggle' + (on ? ' on' : '');
      btn.textContent = on ? 'ON' : 'OFF';
      btn.onclick = async () => {
        await api('/api/smarthome/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device: e.entity_id, command: 'toggle' }) });
        setTimeout(loadHomeView, 400);
      };
      row.appendChild(btn);
      wrap.appendChild(row);
    });
}
$('#home-refresh').onclick = loadHomeView;
$('#home-search').oninput = renderHome;

// ---- Autonomy ----
let autoSeen = 0;
let autoPollTimer = null;

function autoLog(msg) {
  const log = $('#auto-log');
  const d = document.createElement('div');
  d.className = 'line';
  d.textContent = msg;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
}

function setAutoState(state) {
  const el = $('#auto-state');
  el.textContent = state;
  el.className = 'auto-state ' + state;
  if (state === 'running') pulse.className = 'pulse workflow';
  else if (state === 'idle' || state === 'stopped') pulse.className = 'pulse idle';
}

async function pollAuto() {
  try {
    const data = await api(`/api/auto/status?since=${autoSeen}`).then((r) => r.json());
    setAutoState(data.state || 'idle');
    (data.activity || []).forEach((entry) => {
      autoLog(`[${entry.kind}] ${entry.message}`);
    });
    if (typeof data.total === 'number') autoSeen = data.total;

    const approval = data.pending_approval;
    const box = $('#auto-approval');
    if (approval) {
      box.classList.remove('hidden');
      $('#auto-approval-text').textContent =
        `${approval.action}: ${approval.description || approval.topic || ''}`;
    } else {
      box.classList.add('hidden');
    }
  } catch (_) {}
}

function startAutoPolling() {
  if (autoPollTimer) return;
  pollAuto();
  autoPollTimer = setInterval(pollAuto, 1500);
}

$('#auto-start').onclick = async () => {
  const mission = $('#auto-mission').value.trim();
  if (!mission) return alert('Enter a mission');
  $('#auto-log').innerHTML = '';
  autoSeen = 0;
  try {
    await api('/api/auto/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mission,
        restrictions: $('#auto-restrictions').value,
        max_iterations: parseInt($('#auto-iters').value, 10) || 8,
        max_runtime_minutes: parseInt($('#auto-minutes').value, 10) || 20,
        allow_printing: $('#auto-print').checked,
        use_llm_review: $('#auto-review').checked,
      }),
    });
    autoLog('Started.');
    startAutoPolling();
  } catch (e) {
    autoLog('Error: ' + e.message);
  }
};

$('#auto-stop').onclick = async () => {
  try { await api('/api/auto/stop', { method: 'POST' }); autoLog('STOP sent.'); } catch (e) { autoLog(e.message); }
};
$('#auto-pause').onclick = async () => {
  try { await api('/api/auto/pause', { method: 'POST' }); } catch (e) { autoLog(e.message); }
};
$('#auto-resume').onclick = async () => {
  try { await api('/api/auto/resume', { method: 'POST' }); } catch (e) { autoLog(e.message); }
};
$('#auto-approve-yes').onclick = async () => {
  await api('/api/auto/approve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: true }) });
  $('#auto-approval').classList.add('hidden');
};
$('#auto-approve-no').onclick = async () => {
  await api('/api/auto/approve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: false }) });
  $('#auto-approval').classList.add('hidden');
};

async function loadPrinterView() {
  const box = $('#printer-status-box');
  const info = $('#printer-profile-info');
  try {
    const data = await api('/api/printer/status').then((r) => r.json());
    const vol = data.build_volume_mm || [220, 220, 250];
    info.textContent = `${data.profile_name || 'Ender 3 V3'} · bed ${vol[0]}×${vol[1]}×${vol[2]} mm · ${data.backend || 'not set'}`;
    if (!data.configured) {
      box.textContent = 'Printer API not configured on PC (.env OCTOPRINT_* or MOONRAKER_*).';
      return;
    }
    box.textContent = data.online
      ? `Online: ${JSON.stringify(data.state || data.objects || 'ready').slice(0, 120)}`
      : `Offline: ${data.error || 'cannot connect'}`;
  } catch (e) {
    box.textContent = `Cannot reach server: ${e.message}`;
  }
}

// Speech input
function setupMic() {
  const mic = $('#mic-btn');
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    mic.title = 'Speech not supported in this browser';
    mic.disabled = true;
    return;
  }
  const rec = new SR();
  rec.continuous = false;
  rec.interimResults = false;
  rec.onresult = (e) => {
    const text = e.results[0][0].transcript;
    chatInput.value = (chatInput.value + ' ' + text).trim();
    mic.classList.remove('listening');
  };
  rec.onend = () => mic.classList.remove('listening');
  rec.onerror = () => mic.classList.remove('listening');
  mic.onclick = () => {
    if (mic.classList.contains('listening')) {
      rec.stop();
      return;
    }
    mic.classList.add('listening');
    rec.start();
  };
}

// Events
$('#new-chat').onclick = newSession;
$('#toggle-panel').onclick = () => systemPanel.classList.toggle('closed');
$('#close-panel').onclick = () => systemPanel.classList.add('closed');
$('#toggle-sidebar').onclick = () => $('#sidebar').classList.toggle('open');

$$('.nav-item').forEach((btn) => {
  btn.onclick = () => switchView(btn.dataset.view);
});

chatForm.onsubmit = (e) => {
  e.preventDefault();
  const text = chatInput.value;
  chatInput.value = '';
  sendMessage(text);
};

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

modelSelect.onchange = () => {
  state.selectedModel = modelSelect.value;
  state.settings.model = modelSelect.value;
  saveState();
};

$$('.chip').forEach((chip) => {
  chip.onclick = () => {
    if (chip.dataset.workflow) {
      switchView('workflow');
      $('#workflow-topic').value = chip.dataset.workflow;
      runWorkflow(chip.dataset.workflow);
      return;
    }
    if (chip.dataset.prompt) {
      switchView('chat');
      sendMessage(chip.dataset.prompt);
    }
  };
});

$('#run-workflow').onclick = () => runWorkflow($('#workflow-topic').value);

async function streamPost(url, body, logEl, onEvent) {
  const res = await api(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    let event = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) event = line.slice(7).trim();
      else if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          onEvent(event, data, logEl);
        } catch (_) {}
        event = '';
      }
    }
  }
}

function masterLog(msg) {
  const log = $('#master-log');
  const d = document.createElement('div');
  d.className = 'line';
  d.textContent = msg;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
}

$('#run-learn').onclick = async () => {
  const topic = $('#master-topic').value.trim();
  if (!topic) return alert('Enter a topic');
  $('#master-log').innerHTML = '';
  pulse.className = 'pulse workflow';
  masterLog(`Learning: ${topic} (graduate depth, several minutes)...`);
  try {
    await streamPost('/api/learn', { topic }, $('#master-log'), (ev, data) => {
      if (ev === 'learn_done') masterLog(`Learn complete. Slug: ${data.slug}`);
      else if (ev === 'learn_start') masterLog('Started deep learn pipeline');
      else masterLog(`[${ev}]`);
    });
    loadMemory();
  } catch (e) {
    masterLog(`Error: ${e.message}`);
  } finally {
    pulse.className = 'pulse idle';
  }
};

$('#run-build').onclick = async () => {
  const topic = $('#master-topic').value.trim();
  const project = $('#master-project').value.trim();
  if (!topic || !project) return alert('Enter topic and project description');
  $('#master-log').innerHTML = '';
  pulse.className = 'pulse workflow';
  masterLog(`Building: ${project.slice(0, 80)}...`);
  try {
    await streamPost(
      '/api/build',
      { topic, project, printer: $('#master-printer').checked, auto_print: false },
      $('#master-log'),
      (ev, data) => {
        if (ev === 'build_done') {
          masterLog(`Build complete: ${data.build_dir}`);
          Object.entries(data.artifacts || {}).forEach(([k, v]) => masterLog(`  ${k}: ${v}`));
        } else masterLog(`[${ev}]`);
      },
    );
  } catch (e) {
    masterLog(`Error: ${e.message}`);
  } finally {
    pulse.className = 'pulse idle';
  }
};

$('#save-settings').onclick = () => {
  state.settings.model = $('#settings-model').value;
  state.settings.elevenKey = $('#settings-eleven').value;
  const base = $('#settings-api-base').value.trim();
  if (base) localStorage.setItem('aether-api-base', base);
  else localStorage.removeItem('aether-api-base');
  if (state.settings.model) {
    modelSelect.value = state.settings.model;
    state.selectedModel = state.settings.model;
  }
  saveState();
  alert('Settings saved.');
};

$('#test-connection').onclick = async () => {
  try {
    const h = await api('/api/health').then((r) => r.json());
    alert(h.ollama ? 'Connected. Ollama is online.' : 'Connected but Ollama is offline on the PC.');
  } catch (e) {
    alert('Failed: ' + e.message);
  }
};

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  $('#install-pwa').classList.remove('hidden');
});

$('#btn-install-pwa').onclick = async () => {
  if (!deferredInstallPrompt) {
    alert('Use Chrome menu → Install app, or Add to Home screen.');
    return;
  }
  deferredInstallPrompt.prompt();
  await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  $('#install-pwa').classList.add('hidden');
};

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}

// ---- Hands-free voice mode ----
const voiceAssistant = {
  active: false,
  awaitingCommand: false,
  persona: { name: 'A.E.T.H.E.R.', wake_word: 'aether', user_title: 'sir', greeting: '' },
  rec: null,
  voice: null,
  starting: false,

  async loadPersona() {
    try {
      this.persona = await api('/api/persona').then((r) => r.json());
      const g = $('#greeting');
      if (g) g.textContent = this.persona.time_greeting || `${greeting()}, ${this.persona.user_title}`;
      const acronym = $('#brand-acronym');
      if (acronym && this.persona.acronym_line) acronym.textContent = this.persona.acronym_line;
      const input = $('#chat-input');
      if (input && this.persona.name) input.placeholder = `Message ${this.persona.name}…`;
    } catch (_) {}
    this.pickVoice();
  },

  // Greet on arrival and begin listening: no button needed. Browsers require a
  // user gesture before mic/audio, so we arm on the first interaction.
  armAutoStart() {
    if (localStorage.getItem('aether-handsfree') === 'off') return;
    const kick = () => {
      document.removeEventListener('pointerdown', kick);
      document.removeEventListener('keydown', kick);
      if (!this.active) this.start();
    };
    document.addEventListener('pointerdown', kick, { once: true });
    document.addEventListener('keydown', kick, { once: true });
  },

  pickVoice() {
    if (!('speechSynthesis' in window)) return;
    const voices = speechSynthesis.getVoices();
    // Prefer a clear English voice for spoken replies.
    const prefer = [
      (v) => /en-GB/i.test(v.lang) && /male|daniel|george|arthur|ryan/i.test(v.name),
      (v) => /en-GB/i.test(v.lang),
      (v) => /daniel|google uk english/i.test(v.name),
      (v) => /^en/i.test(v.lang),
    ];
    for (const test of prefer) {
      const found = voices.find(test);
      if (found) { this.voice = found; return; }
    }
  },

  setStatus(text, cls) {
    const bar = $('#voice-status');
    bar.classList.remove('hidden', 'speaking', 'thinking');
    if (cls) bar.classList.add(cls);
    $('#voice-status-text').textContent = text;
  },

  speak(text) {
    if (!('speechSynthesis' in window) || !text) return;
    const clean = String(text).replace(/[*_`#>]/g, '').replace(/\s+/g, ' ').slice(0, 700);
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(clean);
    if (this.voice) u.voice = this.voice;
    u.rate = 1.02;
    u.pitch = 0.95;
    if (this.active) {
      this.setStatus(`${this.persona.name} speaking…`, 'speaking');
      // Pause recognition while speaking to avoid hearing itself.
      this.pauseListening();
      u.onend = () => this.resumeListening();
    }
    speechSynthesis.speak(u);
  },

  toggle() {
    if (this.active) this.stop();
    else this.start();
  },

  async start() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert('Voice recognition is not supported in this browser. Try Chrome or Edge.'); return; }
    await this.loadPersona();
    this.active = true;
    $('#voice-toggle').classList.add('active');
    this.setStatus(`Listening for "${this.persona.wake_word}"…`);
    this.speak(this.persona.time_greeting || this.persona.greeting || `${this.persona.name} online.`);

    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = 'en-US';
    rec.onresult = (e) => this.onResult(e);
    rec.onerror = (e) => { if (e.error === 'not-allowed') { alert('Microphone blocked. Allow mic access.'); this.stop(); } };
    rec.onend = () => { if (this.active && !this.starting) { try { rec.start(); } catch (_) {} } };
    this.rec = rec;
    try { rec.start(); } catch (_) {}
  },

  pauseListening() { this.starting = true; try { this.rec && this.rec.stop(); } catch (_) {} },
  resumeListening() {
    this.starting = false;
    if (this.active && this.rec) { try { this.rec.start(); } catch (_) {} this.setStatus(`Listening for "${this.persona.wake_word}"…`); }
  },

  stop() {
    this.active = false;
    this.starting = true;
    $('#voice-toggle').classList.remove('active');
    $('#voice-status').classList.add('hidden');
    try { this.rec && this.rec.stop(); } catch (_) {}
    speechSynthesis.cancel();
  },

  onResult(e) {
    const transcript = Array.from(e.results).slice(-1)[0][0].transcript.trim();
    const lower = transcript.toLowerCase();
    const wake = (this.persona.wake_word || 'aether').toLowerCase();

    if (this.awaitingCommand) {
      this.awaitingCommand = false;
      this.runCommand(transcript);
      return;
    }
    const idx = lower.indexOf(wake);
    if (idx === -1) return;
    // Command may follow the wake word in the same utterance.
    const after = transcript.slice(idx + wake.length).replace(/^[,.\s]+/, '').trim();
    if (after.length > 1) {
      this.runCommand(after);
    } else {
      this.awaitingCommand = true;
      this.setStatus(`Yes, ${this.persona.user_title}?`, 'thinking');
      const beep = new SpeechSynthesisUtterance('Yes?');
      if (this.voice) beep.voice = this.voice;
      speechSynthesis.speak(beep);
    }
  },

  isActionCommand(text) {
    const t = text.toLowerCase();
    return /(build|engineer|make me|create|scaffold|learn|study|research|japanese|nihongo|turn on|turn off|switch on|switch off|toggle|lights?|plug|thermostat)/.test(t);
  },

  async runCommand(text) {
    this.setStatus(`${this.persona.name} working…`, 'thinking');
    switchView('chat');
    // Conversational requests stream via chat; action requests go to the commander.
    if (!this.isActionCommand(text)) {
      sendMessage(text);
      return;
    }
    const session = activeSession();
    session.messages.push({ role: 'user', content: text });
    renderMessages();
    const inner = document.createElement('div');
    inner.className = 'messages-inner';
    session.messages.forEach((m) => inner.appendChild(messageEl(m.role, m.content, false)));
    const assistantEl = messageEl('assistant', 'On it…', false);
    inner.appendChild(assistantEl);
    chatMessages.innerHTML = '';
    chatMessages.appendChild(inner);
    const bubble = assistantEl.querySelector('.msg-bubble');
    const lines = [];
    try {
      await streamPost('/api/command', { request: text }, null, (ev, data) => {
        if (ev === 'intent') lines.push(`Intent: ${data.intent}`);
        else if (ev === 'file_done') lines.push(`✓ ${data.path}`);
        else if (ev === 'planned') lines.push(`Planning ${data.project} (${data.file_count} files)`);
        else if (ev === 'command_done') {
          const summary = this.summarize(data);
          lines.push(summary);
          this.speak(summary);
        }
        bubble.textContent = lines.join('\n');
        chatMessages.scrollTop = chatMessages.scrollHeight;
      });
      session.messages.push({ role: 'assistant', content: bubble.textContent });
      saveState();
    } catch (e) {
      bubble.textContent = 'Error: ' + e.message;
    }
  },

  summarize(data) {
    const t = this.persona.user_title;
    if (data.intent === 'build_app') return `Done, ${t}. Built ${(data.files || []).length} files in ${data.dir}. Run with: ${data.run_command || 'see BUILD_REPORT.md'}.`;
    if (data.intent === 'learn') return `I've finished studying ${data.topic}, ${t}.`;
    if (data.intent === 'build_cad') return `CAD package ready, ${t}.`;
    if (data.intent === 'smart_home') {
      if (data.status === 'not_configured') return data.message;
      if (data.action) return `${data.device} is now ${data.action}, ${t}.`;
      return `I found ${(data.entities || []).length} devices, ${t}.`;
    }
    return data.reply || `Done, ${t}.`;
  },
};

$('#voice-toggle').onclick = () => voiceAssistant.toggle();
if ('speechSynthesis' in window) {
  speechSynthesis.onvoiceschanged = () => voiceAssistant.pickVoice();
}

// Init
loadState();
$('#settings-model').value = state.settings.model || '';
$('#settings-eleven').value = state.settings.elevenKey || '';
$('#settings-api-base').value = localStorage.getItem('aether-api-base') || '';
if (/Android|iPhone|iPad/i.test(navigator.userAgent)) {
  document.body.classList.add('is-mobile');
}
$('#greeting').textContent = greeting();
renderSessions();
renderMessages();
setupMic();
voiceAssistant.loadPersona().then(() => voiceAssistant.armAutoStart());
checkHealth().then(loadModels);
refreshSystemPanel();
setInterval(checkHealth, 30000);
setInterval(refreshSystemPanel, 10000);
