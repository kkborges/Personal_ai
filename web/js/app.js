/**
 * Personal AI Mobile — app.js
 * SPA completa com WebSocket, voz, Bluetooth, integrações e auto-melhoria.
 */

// ═══════════════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════════════
const State = {
  ws: null,
  online: false,
  listening: false,
  currentPage: 'chat',
  conversationId: null,
  mediaRecorder: null,
  audioChunks: [],
  theme: localStorage.getItem('theme') || 'dark',
  config: {},
  btDevices: [],
  currentAudio: null,
  metrics: {},
  wsReconnectTimeout: null,
};

const API = '/api';
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`;
// Tempo máximo para o WS conectar antes de desistir e usar polling HTTP
const WS_CONNECT_TIMEOUT = 4000;

// ═══════════════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  // 1. Tema já aplicado no HTML via script inline — nada a fazer aqui
  applyTheme(); // sincroniza emoji do botão

  // 2. Setup de eventos — síncrono, zero I/O
  setupNav();
  setupChat();
  setupVoice();

  // 3. Tudo que precisa de rede vai para depois do primeiro paint
  requestAnimationFrame(() => {
    connectWS();
    loadConfig().catch(() => {});
    loadStatus().catch(() => {});
    registerSW();
    setInterval(loadStatus, 30000);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// WebSocket
// ═══════════════════════════════════════════════════════════════════════════
function connectWS() {
  if (State.wsReconnectTimeout) clearTimeout(State.wsReconnectTimeout);
  if (State.wsDisabled) return; // WS indisponível, usar polling

  let connectTimer = null;

  try {
    State.ws = new WebSocket(WS_URL);
  } catch(e) {
    _wsFallbackToPolling();
    return;
  }

  // Timeout: se não conectar em WS_CONNECT_TIMEOUT ms, usa polling HTTP
  connectTimer = setTimeout(() => {
    if (State.ws && State.ws.readyState !== WebSocket.OPEN) {
      State.ws.close();
      _wsFallbackToPolling();
    }
  }, WS_CONNECT_TIMEOUT);

  State.ws.onopen = () => {
    clearTimeout(connectTimer);
    State.wsFailCount = 0;
    State.wsDisabled = false;
    setOnline(true);
  };

  State.ws.onmessage = ({ data }) => {
    try { handleWSMessage(JSON.parse(data)); }
    catch (e) {}
  };

  State.ws.onclose = () => {
    clearTimeout(connectTimer);
    setOnline(false);
    if (State.wsDisabled) return;
    // Backoff exponencial: 3s, 6s, 12s, máx 30s
    State.wsFailCount = (State.wsFailCount || 0) + 1;
    if (State.wsFailCount >= 3) {
      _wsFallbackToPolling();
      return;
    }
    const delay = Math.min(3000 * State.wsFailCount, 30000);
    State.wsReconnectTimeout = setTimeout(connectWS, delay);
  };

  State.ws.onerror = () => { /* onclose cuida */ };
}

function _wsFallbackToPolling() {
  // WS não disponível — usa polling HTTP como fallback silencioso
  State.wsDisabled = true;
  if (State.ws) { try { State.ws.close(); } catch(e){} State.ws = null; }
  // Polling de status a cada 10s (já existe setInterval de 30s, este é mais frequente)
  if (!State.pollingInterval) {
    State.pollingInterval = setInterval(() => {
      loadStatus().catch(() => {});
    }, 10000);
  }
}

function wsSend(data) {
  if (State.ws?.readyState === WebSocket.OPEN) {
    State.ws.send(JSON.stringify(data));
    return true;
  }
  return false;
}

function handleWSMessage(msg) {
  switch (msg.type) {
    case 'init':
      State.online = msg.data.online;
      setOnline(msg.data.online);
      break;
    case 'chat_response':
      appendMessage('assistant', msg.data.response, msg.data);
      if (msg.data.audio_url) playAudio(msg.data.audio_url);
      break;
    case 'voice_response':
      appendMessage('assistant', msg.data.text, {});
      if (msg.data.audio_url) playAudio(msg.data.audio_url);
      hideVoiceOverlay();
      break;
    case 'metrics':
      State.metrics = msg.data;
      updateMetricsUI(msg.data);
      break;
    case 'sync_complete':
      toast(`✅ Sincronizado: ${msg.data.synced} itens`, 'success');
      break;
    case 'bluetooth_scan_result':
      renderBluetoothDevices(msg.data.devices);
      break;
    case 'voice_command':
      appendMessage('assistant', `🎙️ ${msg.data.command}\n\n${msg.data.response}`, {});
      if (msg.data.audio_url) playAudio(msg.data.audio_url);
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════
function setupNav() {
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => navigate(tab.dataset.page));
  });
}

function navigate(page) {
  if (State.currentPage === page) return;

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`page-${page}`)?.classList.add('active');
  document.querySelector(`.nav-tab[data-page="${page}"]`)?.classList.add('active');

  State.currentPage = page;

  // Carrega dados APÓS a transição CSS (150ms) para não competir com o paint
  setTimeout(() => onPageChange(page), 160);
}

function onPageChange(page) {
  if (page === 'status') loadStatus();
  if (page === 'bluetooth') loadBluetoothDevices();
  if (page === 'calendar') loadCalendar();
  if (page === 'apps') loadApps();
}

// ═══════════════════════════════════════════════════════════════════════════
// CHAT
// ═══════════════════════════════════════════════════════════════════════════
function setupChat() {
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');

  sendBtn.addEventListener('click', sendMessage);

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    sendBtn.disabled = !input.value.trim();
  });

  // Extra buttons
  document.getElementById('btn-calendar-quick')?.addEventListener('click', () => {
    input.value = 'Quais são meus compromissos de hoje?';
    input.dispatchEvent(new Event('input'));
  });

  document.getElementById('btn-reminder-quick')?.addEventListener('click', () => {
    input.value = 'Criar lembrete para ';
    input.focus();
    input.dispatchEvent(new Event('input'));
  });

  document.getElementById('btn-call-quick')?.addEventListener('click', showCallSheet);
  document.getElementById('btn-spotify-quick')?.addEventListener('click', () => spotifyControl('play'));
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;

  appendMessage('user', text, {});
  input.value = '';
  input.style.height = '48px';
  document.getElementById('send-btn').disabled = true;

  // Try WebSocket first, fallback to HTTP
  if (!wsSend({ type: 'chat', message: text, conversation_id: State.conversationId, voice: State.config.voice_response })) {
    try {
      const res = await api('POST', '/api/chat', {
        message: text,
        conversation_id: State.conversationId,
        platform: 'mobile',
        voice_response: false,
      });
      State.conversationId = res.conversation_id;
      appendMessage('assistant', res.response, res);
      if (res.audio_url) playAudio(res.audio_url);
    } catch (e) {
      appendMessage('assistant', '⚠️ Erro de conexão. ' + e.message, {});
    }
  }
}

function appendMessage(role, content, meta = {}) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = content;

  div.appendChild(bubble);

  // Audio player for TTS
  if (meta.audio_url) {
    const player = document.createElement('div');
    player.className = 'audio-player';
    player.innerHTML = `
      <button class="audio-play-btn" onclick="playAudio('${meta.audio_url}')">▶</button>
      <span style="font-size:0.8rem;color:var(--text-muted)">Ouvir resposta</span>
    `;
    div.appendChild(player);
  }

  // Suggestions
  if (meta.suggestions?.length) {
    const actions = document.createElement('div');
    actions.className = 'message-actions';
    meta.suggestions.forEach(s => {
      const btn = document.createElement('button');
      btn.className = 'suggestion-btn';
      btn.textContent = s;
      btn.addEventListener('click', () => {
        document.getElementById('chat-input').value = s;
        document.getElementById('chat-input').dispatchEvent(new Event('input'));
      });
      actions.appendChild(btn);
    });
    div.appendChild(actions);
  }

  const metaDiv = document.createElement('div');
  metaDiv.className = 'message-meta';
  metaDiv.textContent = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (meta.provider_used) metaDiv.textContent += ` · ${meta.provider_used}`;
  div.appendChild(metaDiv);

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;

  // Typing indicator
  document.getElementById('typing-indicator')?.remove();
}

function showTyping() {
  const container = document.getElementById('chat-messages');
  const el = document.createElement('div');
  el.id = 'typing-indicator';
  el.className = 'message assistant';
  el.innerHTML = '<div class="message-bubble" style="color:var(--text-muted)"><span class="loading-dots">Processando</span></div>';
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

// ═══════════════════════════════════════════════════════════════════════════
// VOICE
// ═══════════════════════════════════════════════════════════════════════════
function setupVoice() {
  document.getElementById('voice-btn')?.addEventListener('click', toggleVoice);
  document.getElementById('voice-cancel-btn')?.addEventListener('click', stopVoice);
  document.getElementById('always-listen-toggle')?.addEventListener('change', toggleAlwaysListen);
}

async function toggleVoice() {
  if (State.listening) {
    stopVoice();
  } else {
    startVoice();
  }
}

async function startVoice() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    State.mediaRecorder = new MediaRecorder(stream);
    State.audioChunks = [];

    State.mediaRecorder.ondataavailable = e => State.audioChunks.push(e.data);
    State.mediaRecorder.onstop = sendAudioToSTT;
    State.mediaRecorder.start();
    State.listening = true;

    document.getElementById('voice-btn')?.classList.add('listening');
    showVoiceOverlay();
    document.getElementById('voice-status-text').textContent = 'Ouvindo... Fale agora';

    // Auto stop after 8s
    setTimeout(() => { if (State.listening) stopVoice(); }, 8000);
  } catch (e) {
    toast('Microfone não disponível: ' + e.message, 'error');
  }
}

function stopVoice() {
  if (State.mediaRecorder?.state === 'recording') {
    State.mediaRecorder.stop();
    State.mediaRecorder.stream?.getTracks().forEach(t => t.stop());
  }
  State.listening = false;
  document.getElementById('voice-btn')?.classList.remove('listening');
  document.getElementById('voice-status-text').textContent = 'Processando...';
}

async function sendAudioToSTT() {
  if (!State.audioChunks.length) { hideVoiceOverlay(); return; }
  const blob = new Blob(State.audioChunks, { type: 'audio/webm' });
  const form = new FormData();
  form.append('audio', blob, 'recording.webm');
  form.append('language', 'pt-BR');

  try {
    const result = await fetch(`${API}/voice/stt`, { method: 'POST', body: form }).then(r => r.json());
    if (result.text) {
      document.getElementById('voice-status-text').textContent = result.text;
      wsSend({ type: 'voice_command', text: result.text });
      setTimeout(hideVoiceOverlay, 1500);
    } else {
      toast('Não entendi. Tente novamente.', 'warning');
      hideVoiceOverlay();
    }
  } catch (e) {
    toast('Erro no reconhecimento de voz', 'error');
    hideVoiceOverlay();
  }
}

function showVoiceOverlay() {
  document.getElementById('voice-overlay')?.classList.add('active');
}

function hideVoiceOverlay() {
  document.getElementById('voice-overlay')?.classList.remove('active');
}

async function toggleAlwaysListen(e) {
  const enabled = e.target.checked;
  await api('POST', enabled ? '/api/voice/listen/start' : '/api/voice/listen/stop');
  toast(enabled ? '🎙️ Escuta contínua ativada' : '🔇 Escuta contínua desativada',
        enabled ? 'success' : 'warning');
}

// ═══════════════════════════════════════════════════════════════════════════
// AUDIO
// ═══════════════════════════════════════════════════════════════════════════
function playAudio(url) {
  if (State.currentAudio) {
    State.currentAudio.pause();
    State.currentAudio = null;
  }
  const audio = new Audio(url);
  State.currentAudio = audio;
  audio.play().catch(e => console.warn('Audio play error:', e));
}

// ═══════════════════════════════════════════════════════════════════════════
// STATUS PAGE
// ═══════════════════════════════════════════════════════════════════════════
async function loadStatus() {
  // Se já temos dados em cache, mostramos imediatamente (sem esperar API)
  if (State.metrics && Object.keys(State.metrics).length > 0) {
    updateStatusPage(State.metrics);
  }
  try {
    const data = await api('GET', '/api/status');
    State.metrics = data;
    updateStatusPage(data);
  } catch (e) {
    console.warn('Status load error:', e);
  }
}

function updateStatusPage(data) {
  setV('stat-cpu', data.cpu_percent?.toFixed(1) + '%');
  setV('stat-memory', data.memory_mb?.toFixed(0) + 'MB');
  setV('stat-health', data.health_score?.toFixed(0));
  setV('stat-uptime', formatUptime(data.uptime_s));
  setV('stat-bt', data.bluetooth_connected);
  setV('stat-calls', data.active_calls);
  setV('stat-jobs', data.jobs?.pending || 0);
  setV('stat-sync', data.sync?.pending_items || 0);
  setOnline(data.online);

  // Health circle
  const score = data.health_score || 0;
  const el = document.getElementById('health-circle');
  if (el) el.style.setProperty('--score', `${score}%`);
  setV('health-score-val', score.toFixed(0));

  // Progress bars
  setPBar('cpu-bar', data.cpu_percent);
  setPBar('mem-bar', data.memory_percent);

  // Provider info
  if (data.sync) {
    setV('sync-status-text', data.sync.online ? '🟢 Online' : '🔴 Offline');
    setV('pending-sync-count', data.sync.pending_items);
  }
}

function updateMetricsUI(data) {
  if (State.currentPage === 'status') {
    setV('stat-cpu', data.cpu_percent?.toFixed(1) + '%');
    setV('stat-memory', data.memory_percent?.toFixed(1) + '%');
    setV('stat-health', data.health_score?.toFixed(0));
    setPBar('cpu-bar', data.cpu_percent);
    setOnline(data.online);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// BLUETOOTH
// ═══════════════════════════════════════════════════════════════════════════
async function loadBluetoothDevices() {
  try {
    const devices = await api('GET', '/api/bluetooth/devices');
    renderBluetoothDevices(devices);
  } catch (e) { }
}

async function scanBluetooth() {
  toast('Escaneando dispositivos Bluetooth...', 'success');
  document.getElementById('bt-scan-btn').disabled = true;
  try {
    wsSend({ type: 'bluetooth_scan', duration: 10 });
    const result = await api('POST', '/api/bluetooth/scan?duration=10');
    renderBluetoothDevices(result.devices || []);
  } catch (e) {
    toast('Erro no scan Bluetooth: ' + e.message, 'error');
  } finally {
    document.getElementById('bt-scan-btn').disabled = false;
  }
}

function renderBluetoothDevices(devices) {
  State.btDevices = devices;
  const container = document.getElementById('bt-devices-list');
  if (!container) return;
  container.innerHTML = '';

  if (!devices.length) {
    container.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-muted)">Nenhum dispositivo encontrado</div>';
    return;
  }

  const icons = {
    speaker: '🔊', headphone: '🎧', tv: '📺',
    car_audio: '🚗', multimedia: '📱', phone: '📞', unknown: '📡'
  };

  devices.forEach(dev => {
    const el = document.createElement('div');
    el.className = 'bt-device';
    el.innerHTML = `
      <div class="bt-icon">${icons[dev.device_type] || '📡'}</div>
      <div style="flex:1;min-width:0">
        <div class="list-title">${dev.name || dev.mac_address}</div>
        <div class="list-subtitle">${dev.mac_address} · ${dev.device_type}</div>
        <div class="list-subtitle">${dev.is_connected ? '🟢 Conectado' : (dev.trusted ? '⭐ Pareado' : '⚪ Disponível')}</div>
      </div>
      <div class="bt-actions">
        ${!dev.is_connected
          ? `<button class="btn btn-primary btn-sm" onclick="btConnect('${dev.mac_address}')">Conectar</button>`
          : `<button class="btn btn-outline btn-sm" onclick="btDisconnect('${dev.mac_address}')">Desconectar</button>`}
        <button class="btn btn-outline btn-sm" onclick="btAudio('${dev.mac_address}')">🔊</button>
      </div>
    `;
    container.appendChild(el);
  });
}

async function btConnect(mac) {
  toast('Conectando...', 'success');
  const res = await api('POST', `/api/bluetooth/connect/${mac}`);
  toast(res.status === 'connected' ? `✅ ${res.name || mac} conectado` : '❌ Falha na conexão',
        res.status === 'connected' ? 'success' : 'error');
  loadBluetoothDevices();
}

async function btDisconnect(mac) {
  await api('POST', `/api/bluetooth/disconnect/${mac}`);
  toast('Dispositivo desconectado', 'warning');
  loadBluetoothDevices();
}

async function btAudio(mac) {
  const res = await api('POST', `/api/bluetooth/audio/${mac}`);
  toast(res.status === 'audio_routed' ? '🔊 Áudio roteado' : '⚠️ ' + (res.note || 'Erro'), 'success');
}

// ═══════════════════════════════════════════════════════════════════════════
// CALENDAR
// ═══════════════════════════════════════════════════════════════════════════
let calMonth = new Date().getMonth();
let calYear = new Date().getFullYear();
let calEvents = [];

async function loadCalendar() {
  try {
    const res = await api('GET', '/api/calendar/agenda');
    renderCalendarAgenda(res);
    renderMiniCal(calYear, calMonth);
    const evRes = await api('GET', '/api/calendar/events');
    calEvents = evRes.events || [];
    markCalendarDays();
  } catch (e) { }
}

function renderCalendarAgenda(agenda) {
  const el = document.getElementById('agenda-summary');
  if (el) el.textContent = agenda.summary || 'Nenhum compromisso hoje.';

  const list = document.getElementById('events-list');
  if (!list) return;
  list.innerHTML = '';

  (agenda.events || []).forEach(ev => {
    const item = document.createElement('div');
    item.className = 'list-item';
    const start = new Date(ev.start_datetime);
    item.innerHTML = `
      <div class="list-icon" style="background:var(--primary);color:white;font-size:0.85rem;text-align:center">
        ${start.getHours().toString().padStart(2,'0')}:${start.getMinutes().toString().padStart(2,'0')}
      </div>
      <div class="list-content">
        <div class="list-title">${ev.title}</div>
        <div class="list-subtitle">${ev.location || ''}</div>
      </div>
      <button class="btn btn-outline btn-sm" onclick="deleteEvent('${ev.id}')">🗑</button>
    `;
    list.appendChild(item);
  });
}

function renderMiniCal(year, month) {
  const grid = document.getElementById('mini-cal-grid');
  if (!grid) return;
  grid.innerHTML = '';
  const first = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  const today = new Date();

  for (let i = 0; i < first; i++) {
    const cell = document.createElement('div');
    cell.className = 'cal-cell other-month';
    grid.appendChild(cell);
  }

  for (let d = 1; d <= days; d++) {
    const cell = document.createElement('div');
    cell.className = 'cal-cell';
    if (d === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
      cell.classList.add('today');
    }
    cell.textContent = d;
    cell.onclick = () => loadDayAgenda(new Date(year, month, d));
    grid.appendChild(cell);
  }

  const monEl = document.getElementById('cal-month-label');
  if (monEl) monEl.textContent = new Date(year, month, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
}

function markCalendarDays() {
  const cells = document.querySelectorAll('.cal-cell');
  calEvents.forEach(ev => {
    const d = new Date(ev.start_datetime).getDate();
    cells[d]?.classList.add('has-event');
  });
}

function calPrev() { if (calMonth === 0) { calMonth = 11; calYear--; } else calMonth--; renderMiniCal(calYear, calMonth); }
function calNext() { if (calMonth === 11) { calMonth = 0; calYear++; } else calMonth++; renderMiniCal(calYear, calMonth); }

async function loadDayAgenda(day) {
  const res = await api('GET', `/api/calendar/agenda?date=${day.toISOString().split('T')[0]}`);
  renderCalendarAgenda(res);
}

async function deleteEvent(id) {
  await api('DELETE', `/api/calendar/events/${id}`);
  toast('Evento removido', 'warning');
  loadCalendar();
}

function showAddEventSheet() {
  document.getElementById('event-sheet')?.classList.add('active');
}

function hideAddEventSheet() {
  document.getElementById('event-sheet')?.classList.remove('active');
}

async function saveEvent() {
  const title = document.getElementById('ev-title')?.value.trim();
  const start = document.getElementById('ev-start')?.value;
  if (!title || !start) { toast('Preencha título e data', 'warning'); return; }

  await api('POST', '/api/calendar/events', {
    title,
    start_datetime: new Date(start).toISOString(),
    end_datetime: document.getElementById('ev-end')?.value
      ? new Date(document.getElementById('ev-end').value).toISOString() : null,
    location: document.getElementById('ev-location')?.value,
    description: document.getElementById('ev-desc')?.value,
    reminder_min: parseInt(document.getElementById('ev-reminder')?.value || '15'),
  });
  toast('✅ Evento criado!', 'success');
  hideAddEventSheet();
  loadCalendar();
}

async function createNaturalEvent() {
  const text = document.getElementById('natural-event-input')?.value.trim();
  if (!text) { toast('Digite o evento em linguagem natural', 'warning'); return; }
  const res = await api('POST', '/api/calendar/natural', { text });
  if (res?.title) {
    toast(`✅ Evento criado: ${res.title}`, 'success');
    document.getElementById('natural-event-input').value = '';
    loadCalendar();
  } else {
    toast('Não foi possível interpretar o evento', 'error');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// APPS
// ═══════════════════════════════════════════════════════════════════════════
const APP_ICONS = {
  netflix: { icon: '🎬', color: '#e50914' },
  'disney+': { icon: '🏰', color: '#113ccf' },
  amazon_prime: { icon: '📦', color: '#00a8e0' },
  'paramount+': { icon: '⭐', color: '#0064ff' },
  globoplay: { icon: '📡', color: '#ff5200' },
  youtube: { icon: '▶️', color: '#ff0000' },
  spotify: { icon: '🎵', color: '#1db954' },
  whatsapp: { icon: '💬', color: '#25d366' },
  outlook: { icon: '📧', color: '#0078d4' },
  teams: { icon: '👥', color: '#6264a7' },
};

async function loadApps() {
  const grid = document.getElementById('apps-grid');
  if (!grid) return;
  grid.innerHTML = '';
  const apps = await api('GET', '/api/apps/list').catch(() => []);
  (Array.isArray(apps) ? apps : []).forEach(app => {
    const info = APP_ICONS[app.name] || { icon: '📱', color: 'var(--primary)' };
    const el = document.createElement('div');
    el.className = 'app-icon';
    el.innerHTML = `
      <div class="app-icon-img" style="background:${info.color}20;border:2px solid ${info.color}40">${info.icon}</div>
      <div class="app-icon-label">${app.name.replace('_', ' ')}</div>
    `;
    el.onclick = () => launchApp(app.name);
    grid.appendChild(el);
  });
}

async function launchApp(appName) {
  const res = await api('POST', '/api/apps/launch', { app_name: appName, platform: 'web' });
  if (res.url) {
    window.open(res.url, '_blank');
  } else {
    toast(`Lançando ${appName}...`, 'success');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SPOTIFY
// ═══════════════════════════════════════════════════════════════════════════
async function spotifyControl(action, query = null) {
  const payload = { action };
  if (query) payload.query = query;
  const res = await api('POST', '/api/platforms/spotify/control', payload);
  toast(res.success ? `Spotify: ${action}` : '⚠️ Spotify não autenticado', res.success ? 'success' : 'warning');
}

// ═══════════════════════════════════════════════════════════════════════════
// TELEPHONY
// ═══════════════════════════════════════════════════════════════════════════
function showCallSheet() {
  document.getElementById('call-sheet')?.classList.add('active');
}

function hideCallSheet() {
  document.getElementById('call-sheet')?.classList.remove('active');
}

async function makeCall() {
  const number = document.getElementById('call-number')?.value.trim();
  if (!number) { toast('Digite o número', 'warning'); return; }
  const res = await api('POST', '/api/phone/call', { number, via: 'sip' });
  toast(`📞 Discando ${number}...`, 'success');
  hideCallSheet();
}

async function hangupCall() {
  await api('POST', '/api/phone/hangup');
  toast('📵 Chamada encerrada', 'warning');
}

// ═══════════════════════════════════════════════════════════════════════════
// SELF-MONITORING
// ═══════════════════════════════════════════════════════════════════════════
async function generateImprovement() {
  const btn = document.getElementById('improve-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Analisando...'; }
  try {
    const res = await api('POST', '/api/monitoring/improve', {});
    renderPatch(res);
    toast('💡 Melhoria gerada!', 'success');
  } catch (e) {
    toast('Erro ao gerar melhoria: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '💡 Gerar Melhoria'; }
  }
}

function renderPatch(patch) {
  const el = document.getElementById('improvement-result');
  if (!el) return;
  el.innerHTML = `
    <div class="card" style="margin:0">
      <div class="card-title">
        <span>${patch.patch_type === 'feature' ? '✨' : '⚡'}</span>
        Melhoria #${patch.patch_id?.substring(0, 8) || 'N/A'}
      </div>
      <p style="font-size:0.85rem;margin-bottom:12px;color:var(--text-muted)">${patch.description || ''}</p>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <span style="background:var(--primary)22;color:var(--primary);padding:4px 10px;border-radius:20px;font-size:0.75rem">
          Score: ${patch.health_score?.toFixed(0) || 0}
        </span>
        <span style="background:var(--accent)22;color:var(--accent);padding:4px 10px;border-radius:20px;font-size:0.75rem">
          ${patch.patch_type}
        </span>
      </div>
      ${patch.code ? `
        <details>
          <summary style="cursor:pointer;font-size:0.85rem;margin-bottom:8px">📄 Ver código gerado</summary>
          <pre style="font-size:0.72rem;overflow:auto;max-height:200px;padding:12px;background:var(--bg);border-radius:8px;border:1px solid var(--border)">${escHtml(patch.code)}</pre>
        </details>
        <div style="display:flex;gap:8px;margin-top:12px">
          <button class="btn btn-primary btn-sm" onclick="runTests('${patch.patch_id}')">🧪 Testar</button>
          <button class="btn btn-outline btn-sm" onclick="applyPatch('${patch.patch_id}')">⚡ Aplicar</button>
        </div>
      ` : ''}
    </div>
  `;
}

async function runTests(patchId) {
  toast('🧪 Executando testes...', 'success');
  const res = await api('POST', `/api/monitoring/patches/${patchId}/test`);
  toast(res.success ? '✅ Testes passaram!' : `❌ Testes falharam: ${res.error || ''}`, res.success ? 'success' : 'error');
}

async function applyPatch(patchId) {
  const res = await api('POST', `/api/monitoring/patches/${patchId}/apply`);
  toast(res.success ? '✅ Patch aplicado!' : '⚠️ ' + res.error, res.success ? 'success' : 'warning');
}

async function loadMonitoringReport() {
  try {
    const report = await api('GET', '/api/monitoring/report?hours=24');
    const el = document.getElementById('monitoring-report');
    if (!el) return;
    el.innerHTML = `
      <div class="card-title">📊 Relatório 24h</div>
      <p><strong>Score:</strong> ${report.health_score?.toFixed(1)}/100</p>
      <p><strong>Tendência:</strong> ${report.health_trend}</p>
      <p><strong>Anomalias:</strong> ${report.anomalies?.length || 0}</p>
      <div style="margin-top:12px">
        ${(report.recommendations || []).map(r => `<p style="font-size:0.85rem;margin:4px 0">${r}</p>`).join('')}
      </div>
    `;
  } catch (e) { }
}

// ═══════════════════════════════════════════════════════════════════════════
// SETTINGS
// ═══════════════════════════════════════════════════════════════════════════
async function loadConfig() {
  try {
    const config = await api('GET', '/api/config');
    State.config = config;
    applyConfigToUI(config);
  } catch (e) { }
}

function applyConfigToUI(config) {
  setCheck('always-listen-toggle', config.always_listen);
  setV('wake-word-display', config.wake_word);
  setV('tts-voice-display', config.tts_voice);
  setV('language-display', config.language);
  setV('autonomy-display', config.autonomy_level);
  setCheck('sync-toggle', config.sync_enabled);
}

async function saveSettings() {
  const updates = {
    tts_voice: document.getElementById('tts-voice-input')?.value,
    wake_word: document.getElementById('wake-word-input')?.value,
    autonomy_level: document.getElementById('autonomy-select')?.value,
    language: document.getElementById('language-select')?.value,
    sync_enabled: document.getElementById('sync-toggle')?.checked,
  };
  Object.keys(updates).forEach(k => { if (!updates[k]) delete updates[k]; });
  await api('PATCH', '/api/config', updates);
  toast('✅ Configurações salvas!', 'success');
  loadConfig();
}

// ═══════════════════════════════════════════════════════════════════════════
// SYNC
// ═══════════════════════════════════════════════════════════════════════════
async function syncNow() {
  toast('Sincronizando...', 'success');
  const res = await api('POST', '/api/sync/push');
  toast(`✅ Sync: ${res.synced} itens`, 'success');
}

async function syncPull() {
  toast('Baixando dados...', 'success');
  const res = await api('POST', '/api/sync/pull');
  toast(`✅ Recebidos: ${res.pulled} itens`, 'success');
}

// ═══════════════════════════════════════════════════════════════════════════
// THEME
// ═══════════════════════════════════════════════════════════════════════════
function toggleTheme() {
  State.theme = State.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', State.theme);
  applyTheme();
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', State.theme);
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = State.theme === 'dark' ? '☀️' : '🌙';
}

// ═══════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════
async function api(method, path, body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json().catch(() => ({}));
}

function toast(message, type = 'success', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️'}</span><span>${message}</span>`;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function setV(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '';
}

function setCheck(id, val) {
  const el = document.getElementById(id);
  if (el) el.checked = !!val;
}

function setPBar(id, val) {
  const el = document.getElementById(id);
  if (!el) return;
  const pct = Math.min(100, Math.max(0, val || 0));
  el.style.width = pct + '%';
  el.className = 'progress-fill' + (pct > 85 ? ' danger' : pct > 60 ? ' warn' : '');
}

function setOnline(online) {
  State.online = online;
  document.querySelectorAll('.status-dot').forEach(d => {
    d.classList.toggle('online', online);
  });
  const label = document.getElementById('online-label');
  if (label) label.textContent = online ? 'Online' : 'Offline';
}

function formatUptime(seconds) {
  if (!seconds) return '0s';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function escHtml(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function registerSW() {
  // Registra SW apenas em produção (HTTPS) para evitar erros em dev
  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  }
}

// ─── GLOBAL EXPORTS ─────────────────────────────────────────────────────────
window.navigate = navigate;
window.sendMessage = sendMessage;
window.toggleVoice = toggleVoice;
window.toggleTheme = toggleTheme;
window.scanBluetooth = scanBluetooth;
window.btConnect = btConnect;
window.btDisconnect = btDisconnect;
window.btAudio = btAudio;
window.showCallSheet = showCallSheet;
window.hideCallSheet = hideCallSheet;
window.makeCall = makeCall;
window.hangupCall = hangupCall;
window.spotifyControl = spotifyControl;
window.showAddEventSheet = showAddEventSheet;
window.hideAddEventSheet = hideAddEventSheet;
window.saveEvent = saveEvent;
window.createNaturalEvent = createNaturalEvent;
window.calPrev = calPrev;
window.calNext = calNext;
window.deleteEvent = deleteEvent;
window.launchApp = launchApp;
window.generateImprovement = generateImprovement;
window.runTests = runTests;
window.applyPatch = applyPatch;
window.loadMonitoringReport = loadMonitoringReport;
window.syncNow = syncNow;
window.syncPull = syncPull;
window.saveSettings = saveSettings;
window.playAudio = playAudio;
