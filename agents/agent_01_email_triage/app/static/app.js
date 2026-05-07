const API = {
  email: 'http://localhost:8011',
  calendar: 'http://localhost:8012',
  task: 'http://localhost:8013',
  document: 'http://localhost:8014',
};

const els = {
  alertBar: document.getElementById('alertBar'),
  refreshAllBtn: document.getElementById('refreshAllBtn'),

  metricEmails: document.getElementById('metricEmails'),
  metricMeetings: document.getElementById('metricMeetings'),
  metricTasks: document.getElementById('metricTasks'),
  metricDocuments: document.getElementById('metricDocuments'),

  emailForm: document.getElementById('emailForm'),
  emailFrom: document.getElementById('emailFrom'),
  emailSubject: document.getElementById('emailSubject'),
  emailBody: document.getElementById('emailBody'),
  emailAttachments: document.getElementById('emailAttachments'),
  runEmailWorkflowBtn: document.getElementById('runEmailWorkflowBtn'),
  latestEmailCategory: document.getElementById('latestEmailCategory'),
  latestEmailUrgency: document.getElementById('latestEmailUrgency'),
  latestEmailResponse: document.getElementById('latestEmailResponse'),
  latestEmailCalendar: document.getElementById('latestEmailCalendar'),
  latestEmailSummary: document.getElementById('latestEmailSummary'),
  categorizedEmailTable: document.getElementById('categorizedEmailTable'),
  categorizedEmailList: document.getElementById('categorizedEmailList'),

  calendarForm: document.getElementById('calendarForm'),
  calendarRequest: document.getElementById('calendarRequest'),
  calendarRequester: document.getElementById('calendarRequester'),
  calendarMatterId: document.getElementById('calendarMatterId'),
  calendarAutoCreate: document.getElementById('calendarAutoCreate'),
  runCalendarBtn: document.getElementById('runCalendarBtn'),
  latestCalendarStatus: document.getElementById('latestCalendarStatus'),
  latestCalendarTime: document.getElementById('latestCalendarTime'),
  latestCalendarEventId: document.getElementById('latestCalendarEventId'),
  latestCalendarPrepTask: document.getElementById('latestCalendarPrepTask'),
  latestCalendarLink: document.getElementById('latestCalendarLink'),
  calendarEventList: document.getElementById('calendarEventList'),
  scheduledEmailMessages: document.getElementById('scheduledEmailMessages'),

  taskForm: document.getElementById('taskForm'),
  taskTitle: document.getElementById('taskTitle'),
  taskDescription: document.getElementById('taskDescription'),
  taskMatterId: document.getElementById('taskMatterId'),
  taskDueDate: document.getElementById('taskDueDate'),
  taskSource: document.getElementById('taskSource'),
  taskTags: document.getElementById('taskTags'),
  runDailyPlanBtn: document.getElementById('runDailyPlanBtn'),
  latestTaskId: document.getElementById('latestTaskId'),
  latestTaskPriority: document.getElementById('latestTaskPriority'),
  latestTaskStatus: document.getElementById('latestTaskStatus'),
  latestTaskSource: document.getElementById('latestTaskSource'),
  latestTaskReasoning: document.getElementById('latestTaskReasoning'),
  taskPriorityList: document.getElementById('taskPriorityList'),
  taskEmailList: document.getElementById('taskEmailList'),
  dailyPlanList: document.getElementById('dailyPlanList'),

  documentForm: document.getElementById('documentForm'),
  documentFilename: document.getElementById('documentFilename'),
  documentFileType: document.getElementById('documentFileType'),
  documentText: document.getElementById('documentText'),
  documentClient: document.getElementById('documentClient'),
  documentMatter: document.getElementById('documentMatter'),
  runDocumentBtn: document.getElementById('runDocumentBtn'),
  latestDocumentId: document.getElementById('latestDocumentId'),
  latestDocumentType: document.getElementById('latestDocumentType'),
  latestDocumentConfidence: document.getElementById('latestDocumentConfidence'),
  latestDocumentDeadline: document.getElementById('latestDocumentDeadline'),
  latestDocumentSummary: document.getElementById('latestDocumentSummary'),
  latestDocumentPath: document.getElementById('latestDocumentPath'),
  documentList: document.getElementById('documentList'),
};

let refreshInProgress = false;
let refreshTimer = null;

function debounceRefresh(delay = 400) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => refreshAll(true), delay);
}

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
  els.alertBar.textContent = message || '';
  els.alertBar.className = `alert ${type}`;
}

function clearAlert() {
  els.alertBar.textContent = '';
  els.alertBar.className = 'alert hidden';
}

async function api(base, path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  const text = await response.text();
  let data = {};

  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text };
  }

  if (!response.ok) {
    throw new Error(data.detail || data.message || `Request failed: ${response.status}`);
  }

  return data;
}

function renderList(target, items, template, empty = 'No records yet.') {
  if (!target) return;

  if (!items || !items.length) {
    target.innerHTML = `<div class="item muted">${escapeHtml(empty)}</div>`;
    return;
  }

  target.innerHTML = items.map(template).join('');
}

function parseTags(value) {
  return String(value || '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

/* EMAIL */

async function syncLatestEmail() {
  try {
    return await api(API.email, '/api/admin/automation/run-once', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  } catch (error) {
    console.warn('Latest email sync failed:', error);
    return null;
  }
}

async function loadEmail() {
  const overview = await api(API.email, '/api/admin/overview');
  const history = await api(API.email, '/api/history?limit=20');

  const metrics = overview.metrics || {};
  const emails = Array.isArray(history) ? history : history.items || history.emails || [];

  els.metricEmails.textContent = metrics.emails?.total_processed || emails.length || 0;

  if (els.categorizedEmailTable) {
    els.categorizedEmailTable.innerHTML = emails.length
      ? emails.map((email) => `
        <tr>
          <td>${escapeHtml(email.subject || '(No subject)')}</td>
          <td>${escapeHtml(email.sender || email.from || '—')}</td>
          <td>${escapeHtml(email.category || '—')}</td>
          <td>${escapeHtml(email.urgency_score ?? '0')}</td>
          <td>${formatDate(email.processed_at || email.created_at)}</td>
        </tr>
      `).join('')
      : `<tr><td colspan="5">No categorized emails yet.</td></tr>`;
  }

  renderList(
    els.categorizedEmailList,
    emails,
    (email) => `
      <article class="item">
        <h5>${escapeHtml(email.subject || '(No subject)')}</h5>
        <p>${escapeHtml(email.sender || email.from || '—')} · ${escapeHtml(email.category || '—')} · Urgency ${escapeHtml(email.urgency_score ?? '0')}</p>
        <small>${formatDate(email.processed_at || email.created_at)}</small>
      </article>
    `,
    'No categorized emails yet.'
  );

  const emailTasks = emails
    .filter((email) => email.action_items)
    .flatMap((email) => {
      let items = email.action_items;
      if (typeof items === 'string') {
        try { items = JSON.parse(items); } catch { items = [items]; }
      }
      if (!Array.isArray(items)) items = [];
      return items.map((item) => ({ title: item, subject: email.subject, created_at: email.processed_at }));
    });

  renderList(
    els.taskEmailList,
    emailTasks,
    (task) => `
      <article class="item">
        <h5>${escapeHtml(task.title || 'Email task')}</h5>
        <p>${escapeHtml(task.subject || '—')}</p>
        <small>${formatDate(task.created_at)}</small>
      </article>
    `,
    'No email-generated task items yet.'
  );
}
async function processManualEmail() {
  const payload = {
    from: els.emailFrom.value.trim(),
    subject: els.emailSubject.value.trim(),
    body: els.emailBody.value.trim(),
    attachments: els.emailAttachments.checked ? [{ filename: 'attachment.pdf' }] : [],
  };

  const result = await api(API.email, '/api/admin/manual/workflow', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  const triage = result.triage || {};

  els.latestEmailCategory.textContent = triage.category || '—';
  els.latestEmailUrgency.textContent = triage.urgency_score ? `${triage.urgency_score}/10` : '—';
  els.latestEmailResponse.textContent = triage.requires_response ? 'Yes' : 'No';
  els.latestEmailCalendar.textContent = result.calendar_triggered ? (result.calendar?.status || 'Triggered') : 'No';
  els.latestEmailSummary.textContent = triage.key_points || result.summary || 'Email processed.';

  return result;
}

/* CALENDAR */

async function loadCalendar() {
  const overview = await api(API.calendar, '/api/overview');
  const metrics = overview.metrics || {};

  els.metricMeetings.textContent = metrics.meetings_total || 0;

  renderList(
    els.calendarEventList,
    overview.meetings || [],
    (meeting) => `
      <article class="item">
        <h5>${escapeHtml(meeting.title || '(Untitled meeting)')}</h5>
        <p>${escapeHtml(meeting.status || '—')} · ${formatDate(meeting.scheduled_time)} · ${escapeHtml(meeting.calendar_event_id || 'no event id')}</p>
      </article>
    `,
    'No calendar events yet.'
  );

  renderList(
    els.scheduledEmailMessages,
    overview.runs || [],
    (run) => `
      <article class="item">
        <h5>${escapeHtml(run.status || 'run')}</h5>
        <p>${escapeHtml(run.request_text || '').slice(0, 180)}</p>
        <small>${formatDate(run.created_at)}</small>
      </article>
    `,
    'No scheduled email messages/runs yet.'
  );
}

async function createCalendarEvent() {
  const payload = {
    request_text: els.calendarRequest.value.trim(),
    requester_email: els.calendarRequester.value.trim() || null,
    matter_id: els.calendarMatterId.value.trim() || null,
    source: 'unified_dashboard',
    auto_create_event: els.calendarAutoCreate.checked,
  };

  const result = await api(API.calendar, '/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  els.latestCalendarStatus.textContent = result.status || '—';
  els.latestCalendarTime.textContent = formatDate(result.scheduled_time || result.preferred_time);
  els.latestCalendarEventId.textContent = result.calendar_event_id || '—';
  els.latestCalendarPrepTask.textContent = result.prep_task?.task?.task_id || result.prep_task?.status || '—';

  const link = result.calendar_event_link || '';
  if (link) {
    els.latestCalendarLink.textContent = 'Open Google Calendar Event';
    els.latestCalendarLink.href = link;
  } else {
    els.latestCalendarLink.textContent = 'No event link';
    els.latestCalendarLink.removeAttribute('href');
  }

  return result;
}

/* TASKS */

async function loadTasks() {
  const overview = await api(API.task, '/api/overview');
  const tasks = overview.tasks || overview.items || [];

  els.metricTasks.textContent =
    overview.metrics?.total_tasks ||
    overview.metrics?.pending_tasks ||
    tasks.length ||
    0;

  renderList(
    els.taskPriorityList,
    tasks,
    (task) => `
      <article class="item">
        <h5>${escapeHtml(task.title || '(Untitled task)')}</h5>
        <p>
          Score ${escapeHtml(task.manual_priority_override || task.priority_score || 0)}
          · ${escapeHtml(task.status || 'pending')}
          · Due ${escapeHtml(task.due_date || '—')}
        </p>
        <small>
          Source: ${escapeHtml(task.source || 'manual')}
          · Created: ${formatDate(task.created_at)}
        </small>
      </article>
    `,
    'No tasks yet.'
  );
}

async function createTask() {
  const matterId = els.taskMatterId.value.trim();

  const payload = {
    title: els.taskTitle.value.trim(),
    description: els.taskDescription.value.trim(),
    matter_id: matterId ? Number(matterId) : null,
    due_date: els.taskDueDate.value || null,
    source: els.taskSource.value.trim() || 'manual',
    tags: parseTags(els.taskTags.value),
  };

  const result = await api(API.task, '/api/tasks/create', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  const task = result.task || {};

  els.latestTaskId.textContent = task.task_id || '—';
  els.latestTaskPriority.textContent = task.priority_score ?? '—';
  els.latestTaskStatus.textContent = task.status || '—';
  els.latestTaskSource.textContent = task.source || '—';
  els.latestTaskReasoning.textContent = task.priority_reasoning || 'Task created.';

  return result;
}

async function runDailyPlan() {
  const result = await api(API.task, '/api/daily-plan/run', {
    method: 'POST',
  });

  const plan = result.plan || {};

  renderList(
    els.dailyPlanList,
    plan.top_5_tasks || [],
    (task) => `
      <article class="item">
        <h5>${escapeHtml(task.title || '(Untitled task)')}</h5>
        <p>${escapeHtml(task.estimated_time || '—')} · ${escapeHtml(task.why_priority || '')}</p>
      </article>
    `,
    'No daily plan generated.'
  );

  return result;
}


/* DOCUMENTS */

async function loadDocuments() {
  const overview = await api(API.document, '/api/overview');
  const documents = overview.recent_documents || overview.items || [];
  const metrics = overview.metrics || {};
  if (els.metricDocuments) els.metricDocuments.textContent = metrics.total_documents || documents.length || 0;
  renderList(
    els.documentList,
    documents,
    (doc) => `
      <article class="item">
        <h5>${escapeHtml(doc.filename || '(Untitled document)')}</h5>
        <p>${escapeHtml(doc.doc_type || 'misc')} · ${escapeHtml(doc.client_name || 'Unknown Client')} · ${escapeHtml(doc.matter_name || 'Unknown Matter')}</p>
        <small>${escapeHtml(doc.file_path || '')}</small>
      </article>
    `,
    'No documents filed yet.'
  );
}

async function fileDocument() {
  const payload = {
    filename: els.documentFilename.value.trim() || 'document.pdf',
    file_type: els.documentFileType.value.trim() || 'pdf',
    extracted_text: els.documentText.value.trim(),
    client_name: els.documentClient.value.trim() || null,
    matter_name: els.documentMatter.value.trim() || null,
    source: 'unified_dashboard',
  };
  const result = await api(API.document, '/api/documents/file', { method: 'POST', body: JSON.stringify(payload) });
  const analysis = result.document_analysis || {};
  els.latestDocumentId.textContent = result.doc_id || '—';
  els.latestDocumentType.textContent = result.document_type || analysis.document_type || '—';
  els.latestDocumentConfidence.textContent = analysis.confidence_score ? `${analysis.confidence_score}/10` : '—';
  els.latestDocumentDeadline.textContent = result.deadline_triggered ? (analysis.deadline_date || 'Triggered') : 'No';
  els.latestDocumentSummary.textContent = result.summary || 'Document processed.';
  els.latestDocumentPath.textContent = result.file_path || result.target_folder || '—';
  return result;
}

/* REFRESH */

async function refreshAll(silent = false, processLatestEmail = false) {
  if (refreshInProgress) return;

  refreshInProgress = true;

  if (!silent) clearAlert();

  if (processLatestEmail) {
    await syncLatestEmail();
  }

  const [emailResult, calendarResult, taskResult, documentResult] = await Promise.allSettled([
    loadEmail(),
    loadCalendar(),
    loadTasks(),
    loadDocuments(),
  ]);

  refreshInProgress = false;

  const failed = [emailResult, calendarResult, taskResult, documentResult].filter(
    (result) => result.status === 'rejected'
  );

  if (failed.length && !silent) {
    showAlert(`Refresh completed with ${failed.length} error(s).`);
    return;
  }

  if (!silent) {
    showAlert('Panel refreshed.', 'success');
  }
}

els.refreshAllBtn.addEventListener('click', async () => {
  try {
    await refreshAll(false, true);
  } catch (error) {
    showAlert(error.message);
  }
});

els.emailForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await processManualEmail();
    debounceRefresh();
    showAlert('Email workflow completed.', 'success');
  } catch (error) {
    showAlert(error.message);
  }
});

els.runEmailWorkflowBtn.addEventListener('click', async () => {
  els.emailForm.requestSubmit();
});

els.calendarForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await createCalendarEvent();
    debounceRefresh();
    showAlert('Calendar workflow completed.', 'success');
  } catch (error) {
    showAlert(error.message);
  }
});

els.runCalendarBtn.addEventListener('click', async () => {
  els.calendarForm.requestSubmit();
});

els.taskForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await createTask();
    debounceRefresh();
    showAlert('Task created.', 'success');
  } catch (error) {
    showAlert(error.message);
  }
});

els.runDailyPlanBtn.addEventListener('click', async () => {
  try {
    await runDailyPlan();
    debounceRefresh();
    showAlert('Daily plan generated.', 'success');
  } catch (error) {
    showAlert(error.message);
  }
});


if (els.documentForm) {
  els.documentForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await fileDocument();
      debounceRefresh();
      showAlert('Document filed.', 'success');
    } catch (error) {
      showAlert(error.message);
    }
  });
}

if (els.runDocumentBtn && els.documentForm) {
  els.runDocumentBtn.addEventListener('click', async () => {
    els.documentForm.requestSubmit();
  });
}

refreshAll(true, true);