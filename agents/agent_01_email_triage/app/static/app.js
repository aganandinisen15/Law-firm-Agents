const API_BASE = window.location.origin;

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
    subject: 'SCHEDULE: Client call',
    body: 'Please schedule a meeting on 25th April 2026 at 3 PM with client@example.com. Video call preferred.',
    attachments: false,
  },
};

const els = {
  alertBar: document.getElementById('alertBar'),

  refreshOverviewBtn: document.getElementById('refreshOverviewBtn'),
  runOnceBtn: document.getElementById('runOnceBtn'),
  startWatcherBtn: document.getElementById('startWatcherBtn'),
  stopWatcherBtn: document.getElementById('stopWatcherBtn'),
  manualTriageBtn: document.getElementById('manualTriageBtn'),

  watcherState: document.getElementById('watcherState'),
  gmailQuery: document.getElementById('gmailQuery'),
  pollSeconds: document.getElementById('pollSeconds'),
  gmailMailbox: document.getElementById('gmailMailbox'),
  lastChecked: document.getElementById('lastChecked'),
  lastProcessed: document.getElementById('lastProcessed'),
  sessionProcessed: document.getElementById('sessionProcessed'),
  gmailConfigured: document.getElementById('gmailConfigured'),
  defaultQuery: document.getElementById('defaultQuery'),
  lastError: document.getElementById('lastError'),

  metricProcessed: document.getElementById('metricProcessed'),
  metricUrgent: document.getElementById('metricUrgent'),
  metricDrafts: document.getElementById('metricDrafts'),
  metricCourt: document.getElementById('metricCourt'),
  metricTasks: document.getElementById('metricTasks'),
  metricMeetings: document.getElementById('metricMeetings'),

  latestCategory: document.getElementById('latestCategory'),
  latestUrgency: document.getElementById('latestUrgency'),
  latestResponse: document.getElementById('latestResponse'),
  latestRoutes: document.getElementById('latestRoutes'),
  latestSummary: document.getElementById('latestSummary'),
  latestDraft: document.getElementById('latestDraft'),
  latestActions: document.getElementById('latestActions'),

  processedList: document.getElementById('processedList'),
  taskList: document.getElementById('taskList'),
  meetingList: document.getElementById('meetingList'),
  errorList: document.getElementById('errorList'),

  manualForm: document.getElementById('manualForm'),
  manualFrom: document.getElementById('manualFrom'),
  manualSubject: document.getElementById('manualSubject'),
  manualBody: document.getElementById('manualBody'),
  manualAttachments: document.getElementById('manualAttachments'),

  calendarStatus: document.getElementById('calendarStatus'),
  calendarTriggered: document.getElementById('calendarTriggered'),
  calendarScheduledTime: document.getElementById('calendarScheduledTime'),
  calendarEventLink: document.getElementById('calendarEventLink'),
};

const state = {
  timer: null,
  loading: false,
  lastProcessedAt: null,
};

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatDate(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatCalendarStatus(status) {
  switch (status) {
    case 'scheduled_google':
      return 'Scheduled (Google Calendar)';
    case 'scheduled_local':
      return 'Scheduled (Local)';
    case 'conflict':
      return 'Conflict – alternatives generated';
    case 'calendar_error':
      return 'Error while scheduling';
    default:
      return status || '—';
  }
}

function showAlert(message, type = 'error') {
  if (!els.alertBar) return;
  els.alertBar.textContent = message || '';
  els.alertBar.className = `alert ${type}`;
}

function clearAlert() {
  if (!els.alertBar) return;
  els.alertBar.textContent = '';
  els.alertBar.className = 'alert hidden';
}

function setButtonsDisabled(disabled) {
  [
    els.refreshOverviewBtn,
    els.runOnceBtn,
    els.startWatcherBtn,
    els.stopWatcherBtn,
    els.manualTriageBtn,
  ].forEach((btn) => {
    if (btn) btn.disabled = disabled;
  });

  const submitBtn = document.querySelector('#manualForm button[type="submit"]');
  if (submitBtn) submitBtn.disabled = disabled;
}

async function api(url, options = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE}${url}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch (err) {
    console.error('Network error:', err);
    throw new Error('Cannot connect to backend.');
  }

  const rawText = await response.text();
  let payload = {};
  try {
    payload = rawText ? JSON.parse(rawText) : {};
  } catch {
    payload = { detail: rawText || 'Unknown server response' };
  }

  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }

  return payload;
}

function renderList(items, target, template, emptyMessage) {
  if (!target) return;

  if (!items || !items.length) {
    target.innerHTML = `<div class="item"><p>${escapeHtml(emptyMessage)}</p></div>`;
    return;
  }

  target.innerHTML = items.map(template).join('');
}

function manualPayload() {
  return {
    from: els.manualFrom?.value?.trim() || '',
    subject: els.manualSubject?.value?.trim() || '',
    body: els.manualBody?.value?.trim() || '',
    attachments: els.manualAttachments?.checked ? [{ filename: 'attachment.pdf' }] : [],
    metadata: { source: 'admin_panel_manual' },
  };
}

function fillForm(data) {
  if (els.manualFrom) els.manualFrom.value = data.from || '';
  if (els.manualSubject) els.manualSubject.value = data.subject || '';
  if (els.manualBody) els.manualBody.value = data.body || '';
  if (els.manualAttachments) els.manualAttachments.checked = !!data.attachments;
}

function renderWorkflowResult(result) {
  const triage = result?.triage || result?.data || {};
  const calendar = result?.calendar || null;

  if (els.latestCategory) {
    els.latestCategory.textContent = triage.category || '—';
  }

  if (els.latestUrgency) {
    els.latestUrgency.textContent = triage.urgency_score ? `${triage.urgency_score}/10` : '—';
  }

  if (els.latestResponse) {
    els.latestResponse.textContent = triage.requires_response ? 'Yes' : 'No';
  }

  const routes = [];
  if (result?.routing?.task_count) routes.push(`${result.routing.task_count} task(s)`);
  if (result?.routing?.calendar_triggered) routes.push('calendar');
  if (result?.routing?.deadline_triggered) routes.push('deadline');

  if (els.latestRoutes) {
    els.latestRoutes.textContent = routes.length ? routes.join(' · ') : 'None';
  }

  if (els.latestSummary) {
    els.latestSummary.textContent = result?.summary || triage.key_points || 'Workflow complete.';
  }

  if (els.latestDraft) {
    els.latestDraft.textContent = triage.draft_response || 'No draft generated.';
  }

  if (els.latestActions) {
    const items = triage.action_items || [];
    els.latestActions.innerHTML = items.length
      ? items.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join('')
      : '<span class="tag">No action items</span>';
  }

  if (els.calendarTriggered) {
    els.calendarTriggered.textContent = result.calendar_triggered ? 'Yes' : 'No';
  }

  if (els.calendarStatus) {
    if (!result.calendar_triggered) {
      els.calendarStatus.textContent = 'Not a scheduling request';
    } else {
      els.calendarStatus.textContent = formatCalendarStatus(calendar?.status);
    }
  }

  if (els.calendarScheduledTime) {
    const scheduled =
      calendar?.scheduled_time ||
      calendar?.preferred_time ||
      calendar?.details?.proposed_times?.[0] ||
      null;

    els.calendarScheduledTime.textContent =
      scheduled ? new Date(scheduled).toLocaleString() : '—';
  }

  if (els.calendarEventLink) {
    const link =
      calendar?.calendar_event_link ||
      calendar?.event_link ||
      '';

    if (link) {
      els.calendarEventLink.textContent = 'Open Event';
      els.calendarEventLink.href = link;
    } else {
      els.calendarEventLink.textContent = '—';
      els.calendarEventLink.removeAttribute('href');
    }
  }
}

function updateWatcherLoop(seconds = 15) {
  if (state.timer) {
    clearInterval(state.timer);
  }

  const intervalMs = Math.max(5000, Number(seconds || 15) * 1000);

  state.timer = setInterval(() => {
    if (!document.hidden) {
      loadOverview({ silent: true });
    }
  }, intervalMs);
}

async function loadOverview({ silent = false } = {}) {
  if (state.loading) return;
  state.loading = true;

  try {
    const overview = await api('/api/admin/overview');
    const metrics = overview.metrics || {};
    const watcher = overview.watcher || {};
    const gmail = overview.gmail || {};

    if (
      state.lastProcessedAt &&
      watcher.last_processed_at &&
      state.lastProcessedAt !== watcher.last_processed_at
    ) {
      showAlert('New processing result received. Panel updated.', 'success');
    }

    state.lastProcessedAt = watcher.last_processed_at || state.lastProcessedAt;

    if (els.metricProcessed) els.metricProcessed.textContent = metrics.emails?.total_processed || 0;
    if (els.metricUrgent) els.metricUrgent.textContent = metrics.emails?.urgent_count || 0;
    if (els.metricDrafts) els.metricDrafts.textContent = metrics.emails?.drafts_created || 0;
    if (els.metricCourt) els.metricCourt.textContent = metrics.emails?.court_count || 0;
    if (els.metricTasks) els.metricTasks.textContent = metrics.tasks?.total_tasks || 0;
    if (els.metricMeetings) els.metricMeetings.textContent = metrics.meetings?.total_meetings || 0;

    if (els.watcherState) {
      els.watcherState.textContent = watcher.running ? 'Running' : 'Stopped';
      els.watcherState.className = `status-chip ${watcher.running ? 'running' : 'stopped'}`;
    }

    if (els.gmailMailbox) els.gmailMailbox.textContent = gmail.mailbox_user || 'me';
    if (els.lastChecked) els.lastChecked.textContent = formatDate(watcher.last_checked_at);
    if (els.lastProcessed) els.lastProcessed.textContent = formatDate(watcher.last_processed_at);
    if (els.sessionProcessed) els.sessionProcessed.textContent = watcher.processed_session_count || 0;
    if (els.gmailConfigured) els.gmailConfigured.textContent = gmail.configured ? 'Yes' : 'No';
    if (els.defaultQuery) els.defaultQuery.textContent = watcher.query || gmail.default_query || '—';
    if (els.lastError) els.lastError.textContent = watcher.last_error || 'None';

    if (els.gmailQuery && watcher.query) {
      els.gmailQuery.value = watcher.query;
    }

    if (els.pollSeconds && watcher.poll_seconds) {
      els.pollSeconds.value = String(watcher.poll_seconds);
    }

    renderList(
      overview.recent_processed || [],
      els.processedList,
      (item) => `
        <article class="item">
          <h4>${escapeHtml(item.subject || '(No subject)')}</h4>
          <p>${escapeHtml(item.sender || 'Unknown sender')} · ${escapeHtml(item.category || '—')} · urgency ${escapeHtml(item.urgency_score || '0')}</p>
          <small>${formatDate(item.processed_at)}</small>
        </article>
      `,
      'No processed emails yet.'
    );

    renderList(
      overview.recent_tasks || [],
      els.taskList,
      (item) => `
        <article class="item">
          <h4>${escapeHtml(item.title || '(Untitled task)')}</h4>
          <p>Priority ${escapeHtml(item.priority_score || '0')} · ${escapeHtml(item.status || 'pending')}</p>
          <small>${formatDate(item.created_at)}</small>
        </article>
      `,
      'No routed tasks yet.'
    );

    renderList(
      overview.recent_meetings || [],
      els.meetingList,
      (item) => `
        <article class="item">
          <h4>${escapeHtml(item.title || '(Untitled meeting)')}</h4>
          <p>${escapeHtml(item.status || 'scheduled')} · ${formatDate(item.scheduled_time)}</p>
          <small>${formatDate(item.created_at)}</small>
        </article>
      `,
      'No routed meetings yet.'
    );

    renderList(
      overview.recent_errors || [],
      els.errorList,
      (item) => `
        <article class="item">
          <h4>${escapeHtml(item.agent_slug || 'agent')}</h4>
          <p>${escapeHtml(item.error_message || 'Unknown error')}</p>
          <small>${formatDate(item.created_at)}</small>
        </article>
      `,
      'No recent errors.'
    );

    updateWatcherLoop(watcher.running ? watcher.poll_seconds || 30 : 15);

    if (!silent) clearAlert();
  } catch (error) {
    if (!silent) showAlert(error.message);
  } finally {
    state.loading = false;
  }
}

async function startWatcher() {
  const payload = await api('/api/admin/automation/start', {
    method: 'POST',
    body: JSON.stringify({
      query: els.gmailQuery?.value || '',
      poll_seconds: Number(els.pollSeconds?.value || 30),
    }),
  });
  showAlert('Automation started.', 'success');
  return payload;
}

async function stopWatcher() {
  const payload = await api('/api/admin/automation/stop', {
    method: 'POST',
  });
  showAlert('Automation stopped.', 'success');
  return payload;
}

async function runOnce() {
  const payload = await api('/api/admin/automation/run-once', {
    method: 'POST',
    body: JSON.stringify({
      query: els.gmailQuery?.value || '',
      poll_seconds: Number(els.pollSeconds?.value || 30),
    }),
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
  const payload = await api(endpoint, {
    method: 'POST',
    body: JSON.stringify(manualPayload()),
  });

  renderWorkflowResult(payload.data ? { data: payload.data, summary: payload.summary } : payload);
  showAlert(endpoint.includes('workflow') ? 'Manual workflow completed.' : 'Manual triage completed.', 'success');

  return payload;
}

function bindClick(el, handler) {
  if (!el) return;
  el.addEventListener('click', async () => {
    try {
      setButtonsDisabled(true);
      await handler();
      await loadOverview();
    } catch (error) {
      showAlert(error.message);
    } finally {
      setButtonsDisabled(false);
    }
  });
}

bindClick(els.refreshOverviewBtn, async () => {
  clearAlert();
  await loadOverview();
});

bindClick(els.startWatcherBtn, async () => {
  await startWatcher();
});

bindClick(els.stopWatcherBtn, async () => {
  await stopWatcher();
});

bindClick(els.runOnceBtn, async () => {
  await runOnce();
});

bindClick(els.manualTriageBtn, async () => {
  await runManual('/api/admin/manual/triage');
});

if (els.manualForm) {
  els.manualForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      setButtonsDisabled(true);
      await runManual('/api/admin/manual/workflow');
      await loadOverview();
    } catch (error) {
      showAlert(error.message);
    } finally {
      setButtonsDisabled(false);
    }
  });
}

document.querySelectorAll('.sample-btn').forEach((button) => {
  button.addEventListener('click', () => {
    const sample = SAMPLE_DATA[button.dataset.sample];
    if (sample) fillForm(sample);
  });
});

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    loadOverview({ silent: true });
  }
});

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