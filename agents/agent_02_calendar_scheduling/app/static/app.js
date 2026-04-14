const API_BASE = window.location.origin;

const SAMPLE_DATA = {
  client: {
    request_text: 'Can we schedule a call next Tuesday or Wednesday afternoon to discuss the lease comments? Please include client@example.com and opposing.counsel@example.com on the invite. 60 minutes, video call.',
    requester_email: 'client@example.com',
  },
  subject: {
    request_text: 'SCHEDULE: Closing coordination\nPlease schedule a meeting Thursday morning with buyer@example.com and seller@example.com. 90 minute video call.',
    requester_email: 'buyer@example.com',
  },
  conflict: {
    request_text: 'Can we meet next Tuesday at 2pm for 60 minutes regarding discovery strategy? Include client@example.com on the invite.',
    requester_email: 'client@example.com',
  },
};

const els = {
  alertBar: document.getElementById('alertBar'),
  refreshBtn: document.getElementById('refreshBtn'),
  scheduleForm: document.getElementById('scheduleForm'),
  requestText: document.getElementById('requestText'),
  requesterEmail: document.getElementById('requesterEmail'),
  matterId: document.getElementById('matterId'),
  autoCreateEvent: document.getElementById('autoCreateEvent'),
  googleMode: document.getElementById('googleMode'),
  metricMeetings: document.getElementById('metricMeetings'),
  metricScheduled: document.getElementById('metricScheduled'),
  metricConflicts: document.getElementById('metricConflicts'),
  metricDrafts: document.getElementById('metricDrafts'),
  latestStatus: document.getElementById('latestStatus'),
  latestTitle: document.getElementById('latestTitle'),
  latestLocation: document.getElementById('latestLocation'),
  latestScheduled: document.getElementById('latestScheduled'),
  latestAttendees: document.getElementById('latestAttendees'),
  availabilityList: document.getElementById('availabilityList'),
  alternativesList: document.getElementById('alternativesList'),
  meetingList: document.getElementById('meetingList'),
  taskList: document.getElementById('taskList'),
};

function showAlert(message, type='error') {
  if (!els.alertBar) return;
  els.alertBar.textContent = message;
  els.alertBar.className = `alert ${type}`;
}
function clearAlert() {
  if (!els.alertBar) return;
  els.alertBar.textContent = '';
  els.alertBar.className = 'alert hidden';
}
function escapeHtml(v='') {
  return String(v)
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;')
    .replaceAll("'",'&#39;');
}
function formatDate(v) {
  if (!v) return '—';
  try { return new Date(v).toLocaleString(); } catch { return v; }
}
function setBusy(disabled) {
  [els.refreshBtn, document.querySelector('#scheduleForm button[type="submit"]'), ...document.querySelectorAll('.sample-btn')]
    .filter(Boolean)
    .forEach((el) => { el.disabled = disabled; });
}
async function api(url, options={}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${url}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
  } catch (err) {
    console.error('Network error', err);
    throw new Error(`Cannot connect to backend at ${API_BASE}`);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || 'Request failed.');
  }
  return payload;
}
function renderList(items, target, renderer, empty='No records yet.') {
  if (!target) return;
  if (!items || !items.length) {
    target.innerHTML = `<div class="item"><p>${escapeHtml(empty)}</p></div>`;
    return;
  }
  target.innerHTML = items.map(renderer).join('');
}
function fillSample(key) {
  const sample = SAMPLE_DATA[key];
  if (!sample) return;
  els.requestText.value = sample.request_text || '';
  els.requesterEmail.value = sample.requester_email || '';
}
function renderOverview(data) {
  const metrics = data.metrics || {};
  const google = data.google || {};
  els.metricMeetings.textContent = metrics.meetings_total || 0;
  els.metricScheduled.textContent = metrics.scheduled_total || 0;
  els.metricConflicts.textContent = metrics.conflict_total || 0;
  els.metricDrafts.textContent = metrics.draft_total || 0;
  els.googleMode.textContent = google.mode || 'fallback';

  renderList(data.meetings || [], els.meetingList, (item) => `
    <article class="item">
      <h4>${escapeHtml(item.title || '(Untitled meeting)')}</h4>
      <p>${escapeHtml(item.status || '—')} · ${escapeHtml(item.location || '—')}</p>
      <small>${formatDate(item.scheduled_time || item.created_at)}</small>
    </article>
  `, 'No meetings logged yet.');

  renderList(data.tasks || [], els.taskList, (item) => `
    <article class="item">
      <h4>${escapeHtml(item.title || '(Untitled task)')}</h4>
      <p>${escapeHtml(item.status || 'pending')}</p>
      <small>Due ${escapeHtml(item.due_date || '—')}</small>
    </article>
  `, 'No tasks created yet.');
}
function renderResult(result) {
  const details = result.details || {};
  els.latestStatus.textContent = result.status || 'Completed';
  els.latestTitle.textContent = details.title || '—';
  els.latestLocation.textContent = details.location || '—';
  els.latestScheduled.textContent = result.scheduled_time ? formatDate(result.scheduled_time) : '—';
  els.latestAttendees.textContent = (details.attendees || []).map((a) => a.email || a.name).join(', ') || '—';

  renderList(result.availability || [], els.availabilityList, (slot) => `
    <article class="item">
      <h4>${formatDate(slot.start)}</h4>
      <p>${formatDate(slot.end)}</p>
      <div class="inline-badges">
        <span class="mini-badge ${slot.available ? 'success' : 'warning'}">${slot.available ? 'available' : 'conflict'}</span>
        <span class="mini-badge">${escapeHtml(slot.reason || '—')}</span>
      </div>
    </article>
  `, 'No availability checks yet.');

  renderList(result.alternatives || [], els.alternativesList, (alt) => `
    <article class="item">
      <h4>${formatDate(alt.time)}</h4>
      <p>${escapeHtml(alt.reason || 'Alternative')}</p>
    </article>
  `, 'No alternatives generated.');
}
async function loadOverview() {
  const data = await api('/api/overview');
  renderOverview(data);
}
async function submitWorkflow(event) {
  event.preventDefault();
  clearAlert();
  setBusy(true);
  try {
    const payload = {
      request_text: els.requestText.value.trim(),
      requester_email: els.requesterEmail.value.trim() || null,
      matter_id: els.matterId.value.trim() || null,
      auto_create_event: !!els.autoCreateEvent.checked,
      source: 'admin_panel',
    };
    const result = await api('/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    renderResult(result);
    await loadOverview();
    showAlert(result.status === 'scheduled' ? 'Meeting scheduled successfully.' : result.status === 'conflict' ? 'Conflicts found. Alternatives prepared.' : 'Request processed.', 'success');
  } catch (error) {
    showAlert(error.message);
  } finally {
    setBusy(false);
  }
}
document.querySelectorAll('.sample-btn').forEach((btn) => {
  btn.addEventListener('click', () => fillSample(btn.dataset.sample));
});
if (els.refreshBtn) {
  els.refreshBtn.addEventListener('click', async () => {
    clearAlert();
    setBusy(true);
    try {
      await loadOverview();
      showAlert('Panel refreshed.', 'success');
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  });
}
if (els.scheduleForm) {
  els.scheduleForm.addEventListener('submit', submitWorkflow);
}
(async function init() {
  try {
    const health = await api('/health');
    if (health.status !== 'ok') {
      showAlert('Backend health check failed.');
      return;
    }
    await loadOverview();
  } catch (error) {
    showAlert(error.message);
  }
})();
