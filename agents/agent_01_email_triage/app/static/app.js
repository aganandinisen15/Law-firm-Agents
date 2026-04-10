const API_BASE = "http://localhost:8011";
const SAMPLE_DATA = {
  urgent: {
    from: 'client@example.com',
    subject: 'URGENT: Need review before tomorrow hearing',
    body: 'We have a hearing tomorrow morning. Please review the attached materials and let me know next steps today.',
    attachments: true,
  },
  court: {
    from: 'notifications@court.gov',
    subject: 'Court notice and response deadline',
    body: 'Please take notice that responses are due on 2026-04-21. The hearing has been calendared.',
    attachments: true,
  },
  schedule: {
    from: 'client@example.com',
    subject: 'Schedule a meeting next week',
    body: 'Can we schedule a call next Tuesday or Wednesday afternoon to discuss the lease comments?',
    attachments: false,
  },
};

const els = {
  alert: document.getElementById('alertBar'),
  query: document.getElementById('gmailQuery'),
  poll: document.getElementById('pollSeconds'),
  watcherState: document.getElementById('watcherState'),
  gmailMailbox: document.getElementById('gmailMailbox'),
  lastChecked: document.getElementById('lastChecked'),
  lastProcessed: document.getElementById('lastProcessed'),
  sessionProcessed: document.getElementById('sessionProcessed'),
  latestCategory: document.getElementById('latestCategory'),
  latestUrgency: document.getElementById('latestUrgency'),
  latestResponse: document.getElementById('latestResponse'),
  latestRoutes: document.getElementById('latestRoutes'),
  latestSummary: document.getElementById('latestSummary'),
  latestDraft: document.getElementById('latestDraft'),
  latestActions: document.getElementById('latestActions'),
  processedList: document.getElementById('processedList'),
  taskList: document.getElementById('taskList'),
  errorList: document.getElementById('errorList'),
  gmailConfigured: document.getElementById('gmailConfigured'),
  defaultQuery: document.getElementById('defaultQuery'),
  lastError: document.getElementById('lastError'),
  metricProcessed: document.getElementById('metricProcessed'),
  metricUrgent: document.getElementById('metricUrgent'),
  metricDrafts: document.getElementById('metricDrafts'),
  metricCourt: document.getElementById('metricCourt'),
  metricTasks: document.getElementById('metricTasks'),
  metricMeetings: document.getElementById('metricMeetings'),
  manualFrom: document.getElementById('manualFrom'),
  manualSubject: document.getElementById('manualSubject'),
  manualBody: document.getElementById('manualBody'),
  manualAttachments: document.getElementById('manualAttachments'),
  manualForm: document.getElementById('manualForm'),
};

function showAlert(message, type = 'error') {
  els.alert.textContent = message;
  els.alert.className = `alert ${type}`;
}
function clearAlert() {
  els.alert.textContent = '';
  els.alert.className = 'alert hidden';
}
function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
async function api(url, options = {}) {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || 'Request failed.');
  }
  return payload;
}
function renderList(items, target, template, emptyMessage) {
  if (!items || !items.length) {
    target.innerHTML = `<div class="item"><p>${escapeHtml(emptyMessage)}</p></div>`;
    return;
  }
  target.innerHTML = items.map(template).join('');
}
function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—';
}
function manualPayload() {
  return {
    from: els.manualFrom.value,
    subject: els.manualSubject.value,
    body: els.manualBody.value,
    attachments: els.manualAttachments.checked ? [{ filename: 'attachment.pdf' }] : [],
    metadata: { source: 'admin_panel_manual' },
  };
}
function fillForm(data) {
  els.manualFrom.value = data.from || '';
  els.manualSubject.value = data.subject || '';
  els.manualBody.value = data.body || '';
  els.manualAttachments.checked = !!data.attachments;
}
function renderWorkflowResult(result) {
  const triage = result.triage || result.data || {};
  els.latestCategory.textContent = triage.category || '—';
  els.latestUrgency.textContent = triage.urgency_score ? `${triage.urgency_score}/10` : '—';
  els.latestResponse.textContent = triage.requires_response ? 'Yes' : 'No';
  const routes = [];
  if (result.routing?.task_count) routes.push(`${result.routing.task_count} task(s)`);
  if (result.routing?.calendar_triggered) routes.push('calendar');
  if (result.routing?.deadline_triggered) routes.push('deadline');
  els.latestRoutes.textContent = routes.length ? routes.join(' · ') : 'None';
  els.latestSummary.textContent = result.summary || triage.summary || 'Workflow complete.';
  els.latestDraft.textContent = triage.draft_response || 'No draft generated.';
  els.latestActions.innerHTML = (triage.action_items || []).map(item => `<span class="tag">${escapeHtml(item)}</span>`).join('') || '<span class="tag">No action items</span>';
}
async function loadOverview() {
  const payload = await api('/api/admin/overview');
  const metrics = payload.metrics || {};
  const watcher = payload.watcher || {};
  const gmail = payload.gmail || {};

  els.metricProcessed.textContent = metrics.emails?.total_processed || 0;
  els.metricUrgent.textContent = metrics.emails?.urgent_count || 0;
  els.metricDrafts.textContent = metrics.emails?.drafts_created || 0;
  els.metricCourt.textContent = metrics.emails?.court_count || 0;
  els.metricTasks.textContent = metrics.tasks?.total_tasks || 0;
  els.metricMeetings.textContent = metrics.meetings?.total_meetings || 0;

  els.watcherState.textContent = watcher.running ? 'Running' : 'Stopped';
  els.watcherState.className = `status-chip ${watcher.running ? 'running' : 'stopped'}`;
  els.gmailMailbox.textContent = gmail.mailbox_user || 'me';
  els.lastChecked.textContent = watcher.last_checked_at ? formatDate(watcher.last_checked_at) : '—';
  els.lastProcessed.textContent = watcher.last_processed_at ? formatDate(watcher.last_processed_at) : '—';
  els.sessionProcessed.textContent = watcher.processed_session_count || 0;
  els.gmailConfigured.textContent = gmail.configured ? 'Yes' : 'No';
  els.defaultQuery.textContent = watcher.query || gmail.default_query || '—';
  els.lastError.textContent = watcher.last_error || 'None';

  if (watcher.query) els.query.value = watcher.query;
  if (watcher.poll_seconds) els.poll.value = String(watcher.poll_seconds);

  renderList(payload.recent_processed || [], els.processedList, (item) => `
    <article class="item">
      <h4>${escapeHtml(item.subject || '(No subject)')}</h4>
      <p>${escapeHtml(item.sender || 'Unknown sender')} · ${escapeHtml(item.category || '—')} · urgency ${escapeHtml(item.urgency_score || '0')}</p>
      <small>${formatDate(item.processed_at)}</small>
    </article>
  `, 'No processed emails yet.');

  renderList(payload.recent_tasks || [], els.taskList, (item) => `
    <article class="item">
      <h4>${escapeHtml(item.title || '(Untitled task)')}</h4>
      <p>Priority ${escapeHtml(item.priority_score || '0')} · ${escapeHtml(item.status || 'pending')}</p>
      <small>${formatDate(item.created_at)}</small>
    </article>
  `, 'No routed tasks yet.');

  renderList(payload.recent_errors || [], els.errorList, (item) => `
    <article class="item">
      <h4>${escapeHtml(item.agent_slug || 'agent')}</h4>
      <p>${escapeHtml(item.error_message || 'Unknown error')}</p>
      <small>${formatDate(item.created_at)}</small>
    </article>
  `, 'No recent errors.');
}
async function startWatcher() {
  clearAlert();
  const payload = await api('/api/admin/automation/start', {
    method: 'POST',
    body: JSON.stringify({ query: els.query.value, poll_seconds: Number(els.poll.value) }),
  });
  showAlert('Automation started.', 'success');
  return payload;
}
async function stopWatcher() {
  clearAlert();
  const payload = await api('/api/admin/automation/stop', { method: 'POST' });
  showAlert('Automation stopped.', 'success');
  return payload;
}
async function runOnce() {
  clearAlert();
  const payload = await api('/api/admin/automation/run-once', {
    method: 'POST',
    body: JSON.stringify({ query: els.query.value, poll_seconds: Number(els.poll.value) }),
  });
  if (payload.processed && payload.workflow) {
    renderWorkflowResult(payload.workflow);
    showAlert('Latest inbox email processed successfully.', 'success');
  } else {
    showAlert('No new unprocessed inbox email matched the Gmail query.', 'success');
  }
  return payload;
}
async function runManual(endpoint) {
  clearAlert();
  const payload = await api(endpoint, {
    method: 'POST',
    body: JSON.stringify(manualPayload()),
  });
  renderWorkflowResult(payload.data ? { data: payload.data, summary: payload.summary } : payload);
  showAlert(endpoint.includes('workflow') ? 'Manual workflow completed.' : 'Manual triage completed.', 'success');
}

document.getElementById('refreshOverviewBtn').addEventListener('click', async () => {
  try { clearAlert(); await loadOverview(); } catch (error) { showAlert(error.message); }
});
document.getElementById('startWatcherBtn').addEventListener('click', async () => {
  try { await startWatcher(); await loadOverview(); } catch (error) { showAlert(error.message); }
});
document.getElementById('stopWatcherBtn').addEventListener('click', async () => {
  try { await stopWatcher(); await loadOverview(); } catch (error) { showAlert(error.message); }
});
document.getElementById('runOnceBtn').addEventListener('click', async () => {
  try { await runOnce(); await loadOverview(); } catch (error) { showAlert(error.message); }
});
document.getElementById('manualTriageBtn').addEventListener('click', async () => {
  try { await runManual('/api/admin/manual/triage'); await loadOverview(); } catch (error) { showAlert(error.message); }
});
els.manualForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await runManual('/api/admin/manual/workflow'); await loadOverview(); } catch (error) { showAlert(error.message); }
});
document.querySelectorAll('.sample-btn').forEach((button) => {
  button.addEventListener('click', () => fillForm(SAMPLE_DATA[button.dataset.sample] || {}));
});

loadOverview().catch((error) => showAlert(error.message));
