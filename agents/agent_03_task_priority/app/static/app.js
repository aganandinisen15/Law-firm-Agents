const API_BASE = window.location.origin;

const SAMPLE_DATA = {
  discovery: {
    title: 'Review and respond to discovery requests',
    description: 'Opposing counsel sent interrogatories - 30 day deadline.',
    matter_id: '123',
    due_date: '2026-01-25',
    source: 'email_agent',
    assigned_to: '',
    tags: 'discovery, deadline, court',
  },
  meeting: {
    title: 'Prepare for client lease meeting',
    description: 'Prep task generated from calendar scheduling.',
    matter_id: '123',
    due_date: '2026-01-24',
    source: 'calendar_agent',
    assigned_to: '',
    tags: 'meeting_prep, client_request',
  },
  deadline: {
    title: 'Prepare court filing packet',
    description: 'Task generated from deadline tracking workflow.',
    matter_id: '123',
    due_date: '2026-01-22',
    source: 'deadline_agent',
    assigned_to: '',
    tags: 'deadline, court, urgent',
  },
};

const els = {
  alertBar: document.getElementById('alertBar'),

  refreshOverviewBtn: document.getElementById('refreshOverviewBtn'),
  runDailyPlanBtn: document.getElementById('runDailyPlanBtn'),
  createTaskBtn: document.getElementById('createTaskBtn'),

  taskForm: document.getElementById('taskForm'),
  taskTitle: document.getElementById('taskTitle'),
  taskDescription: document.getElementById('taskDescription'),
  taskMatterId: document.getElementById('taskMatterId'),
  taskDueDate: document.getElementById('taskDueDate'),
  taskSource: document.getElementById('taskSource'),
  taskAssignedTo: document.getElementById('taskAssignedTo'),
  taskTags: document.getElementById('taskTags'),

  metricPendingTasks: document.getElementById('metricPendingTasks'),
  metricHighPriorityTasks: document.getElementById('metricHighPriorityTasks'),
  metricOverdueTasks: document.getElementById('metricOverdueTasks'),
  metricTotalTasks: document.getElementById('metricTotalTasks'),

  latestTaskId: document.getElementById('latestTaskId'),
  latestPriorityScore: document.getElementById('latestPriorityScore'),
  latestTaskStatus: document.getElementById('latestTaskStatus'),
  latestTaskSource: document.getElementById('latestTaskSource'),
  latestPriorityReasoning: document.getElementById('latestPriorityReasoning'),
  latestRecommendedDeadline: document.getElementById('latestRecommendedDeadline'),
  latestTaskTags: document.getElementById('latestTaskTags'),
  latestSheetSync: document.getElementById('latestSheetSync'),
  latestAlert: document.getElementById('latestAlert'),

  taskList: document.getElementById('taskList'),
  dailyPlanTop5: document.getElementById('dailyPlanTop5'),
  dailyPlanDeferred: document.getElementById('dailyPlanDeferred'),
  dailyPlanOverdue: document.getElementById('dailyPlanOverdue'),
  dailyPlanAlerts: document.getElementById('dailyPlanAlerts'),
};

const state = {
  loading: false,
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
  [els.refreshOverviewBtn, els.runDailyPlanBtn, els.createTaskBtn].forEach((btn) => {
    if (btn) btn.disabled = disabled;
  });
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

function parseTags(raw) {
  return String(raw || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

function formPayload() {
  const matterIdRaw = els.taskMatterId?.value?.trim() || '';
  return {
    title: els.taskTitle?.value?.trim() || '',
    description: els.taskDescription?.value?.trim() || '',
    matter_id: matterIdRaw ? Number(matterIdRaw) : null,
    due_date: els.taskDueDate?.value || null,
    source: els.taskSource?.value?.trim() || 'manual',
    assigned_to: els.taskAssignedTo?.value?.trim() || null,
    tags: parseTags(els.taskTags?.value),
  };
}

function fillForm(sample) {
  if (!sample) return;
  if (els.taskTitle) els.taskTitle.value = sample.title || '';
  if (els.taskDescription) els.taskDescription.value = sample.description || '';
  if (els.taskMatterId) els.taskMatterId.value = sample.matter_id || '';
  if (els.taskDueDate) els.taskDueDate.value = sample.due_date || '';
  if (els.taskSource) els.taskSource.value = sample.source || 'manual';
  if (els.taskAssignedTo) els.taskAssignedTo.value = sample.assigned_to || '';
  if (els.taskTags) els.taskTags.value = sample.tags || '';
}

function renderLatestTask(result) {
  const task = result?.task || {};
  const sheetSync = result?.sheet_sync || {};
  const alert = result?.alert || {};

  if (els.latestTaskId) els.latestTaskId.textContent = task.task_id || '—';
  if (els.latestPriorityScore) els.latestPriorityScore.textContent = task.priority_score ?? '—';
  if (els.latestTaskStatus) els.latestTaskStatus.textContent = task.status || '—';
  if (els.latestTaskSource) els.latestTaskSource.textContent = task.source || '—';
  if (els.latestPriorityReasoning) els.latestPriorityReasoning.textContent = task.priority_reasoning || 'No reasoning available.';
  if (els.latestRecommendedDeadline) els.latestRecommendedDeadline.textContent = task.recommended_deadline || '—';

  if (els.latestTaskTags) {
    const tags = task.tags || [];
    els.latestTaskTags.innerHTML = tags.length
      ? tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join('')
      : '<span class="tag">No tags</span>';
  }

  if (els.latestSheetSync) {
    els.latestSheetSync.textContent = sheetSync.message || sheetSync.status || '—';
  }

  if (els.latestAlert) {
    els.latestAlert.textContent = alert.message || alert.status || '—';
  }
}

function renderOverview(overview) {
  const metrics = overview.metrics || {};
  const tasks = overview.tasks || [];

  if (els.metricPendingTasks) els.metricPendingTasks.textContent = metrics.pending_tasks || 0;
  if (els.metricHighPriorityTasks) els.metricHighPriorityTasks.textContent = metrics.high_priority_tasks || 0;
  if (els.metricOverdueTasks) els.metricOverdueTasks.textContent = metrics.overdue_tasks || 0;
  if (els.metricTotalTasks) els.metricTotalTasks.textContent = tasks.length || 0;

  renderList(
    tasks,
    els.taskList,
    (task) => `
      <article class="item">
        <h4>${escapeHtml(task.title || '(Untitled task)')}</h4>
        <p>
          Score ${escapeHtml(task.manual_priority_override || task.priority_score || 0)}
          · ${escapeHtml(task.status || 'pending')}
          · ${escapeHtml(task.source || 'manual')}
        </p>
        <small>Due: ${escapeHtml(task.due_date || '—')} · Created: ${formatDate(task.created_at)}</small>
      </article>
    `,
    'No tasks yet.'
  );
}

function renderDailyPlan(plan) {
  renderList(
    plan.top_5_tasks || [],
    els.dailyPlanTop5,
    (task) => `
      <article class="item">
        <h4>${escapeHtml(task.title || '(Untitled task)')}</h4>
        <p>${escapeHtml(task.estimated_time || '—')} · ${escapeHtml(task.why_priority || '')}</p>
      </article>
    `,
    'No top 5 tasks generated.'
  );

  renderList(
    plan.deferred_tasks || [],
    els.dailyPlanDeferred,
    (task) => `
      <article class="item">
        <h4>${escapeHtml(task.title || '(Untitled task)')}</h4>
        <p>Deferred · Score ${escapeHtml(task.manual_priority_override || task.priority_score || 0)}</p>
      </article>
    `,
    'No deferred tasks.'
  );

  renderList(
    plan.overdue_tasks || [],
    els.dailyPlanOverdue,
    (task) => `
      <article class="item">
        <h4>${escapeHtml(task.title || '(Untitled task)')}</h4>
        <p>Overdue · Due ${escapeHtml(task.due_date || '—')}</p>
      </article>
    `,
    'No overdue tasks.'
  );

  renderList(
    plan.alerts || [],
    els.dailyPlanAlerts,
    (alert) => `
      <article class="item">
        <p>${escapeHtml(alert)}</p>
      </article>
    `,
    'No alerts.'
  );
}

async function loadOverview() {
  if (state.loading) return;
  state.loading = true;

  try {
    const overview = await api('/api/overview');
    renderOverview(overview);
    clearAlert();
  } catch (error) {
    showAlert(error.message);
  } finally {
    state.loading = false;
  }
}

async function createTask() {
  const payload = formPayload();

  if (!payload.title) {
    throw new Error('Task title is required.');
  }

  const result = await api('/api/tasks/create', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  renderLatestTask(result);
  showAlert('Task created successfully.', 'success');
  return result;
}

async function runDailyPlan() {
  const result = await api('/api/daily-plan/run', {
    method: 'POST',
  });

  renderDailyPlan(result.plan || {});
  showAlert('Daily plan generated.', 'success');
  return result;
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

bindClick(els.runDailyPlanBtn, async () => {
  await runDailyPlan();
});

if (els.taskForm) {
  els.taskForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      setButtonsDisabled(true);
      await createTask();
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