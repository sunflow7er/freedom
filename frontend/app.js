const API = '';

// ── State ─────────────────────────────────────────────────
const state = {
  role: 'operator',
  view: 'conversations',
  selectedConv: null,
};

// ── API helpers ───────────────────────────────────────────
async function api(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

// ── Navigation ────────────────────────────────────────────
function switchView(name) {
  state.view = name;
  document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('view-' + name)?.classList.remove('hidden');
  document.querySelector(`[data-view="${name}"]`)?.classList.add('active');

  const titles = { conversations: 'Диалоги', checklists: 'Чек-листы', appeals: 'Апелляции', analytics: 'Аналитика' };
  document.getElementById('topbar-title').textContent = titles[name] || name;

  // Show/hide topbar action buttons — only relevant on conversations view
  const tbActions = document.getElementById('topbar-actions');
  if (tbActions) tbActions.style.display = name === 'conversations' ? '' : 'none';

  if (name === 'checklists') window.loadChecklists?.();
  if (name === 'appeals')    window.loadAppeals?.();
  if (name === 'analytics')  window.loadAnalytics?.();
}

// ── Role toggle ───────────────────────────────────────────
function setRole(role) {
  state.role = role;
  document.querySelectorAll('.role-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.role === role)
  );
  document.dispatchEvent(new CustomEvent('rolechange', { detail: role }));
}

// ── Stats sidebar ─────────────────────────────────────────
async function refreshStats() {
  try {
    const convs = await api('/api/conversations');
    const total = convs.length;
    const evaluated = convs.filter(c => c.eval_id).length;
    const gross = convs.filter(c => c.gross_error).length;

    document.getElementById('stat-total').textContent = total || '—';
    document.getElementById('stat-evaluated').textContent = evaluated || '0';
    document.getElementById('stat-gross').textContent = gross || '0';
    document.getElementById('nav-badge-convs').textContent = total || '—';
  } catch {}
}

// ── Import ────────────────────────────────────────────────
async function doImport() {
  const groupId = prompt('Group ID для импорта:\n• DEV — 65 диалогов из API\n• SAMPLE — 10 тестовых диалогов (локально)', 'SAMPLE');
  if (!groupId) return;
  const btn = document.getElementById('btn-import');
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="border-top-color:var(--ink-2)"></span> Импорт…';
  try {
    const result = await api(`/api/datasets/${encodeURIComponent(groupId)}/import`, { method: 'POST' });
    const n = result.inserted ?? result.imported ?? result.total ?? '?';
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 7l3.5 3.5L11 3.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="square"/></svg> +${n} диалогов`;
    window.refreshConversations?.();
    refreshStats();
    setTimeout(() => {
      btn.disabled = false;
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1v8M3 6l3.5 3.5L10 6M2 11h9" stroke="currentColor" stroke-width="1.4" stroke-linecap="square"/></svg> Импорт`;
    }, 3000);
  } catch (e) {
    alert('Ошибка импорта: ' + e.message);
    btn.disabled = false;
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M6.5 1v8M3 6l3.5 3.5L10 6M2 11h9" stroke="currentColor" stroke-width="1.4" stroke-linecap="square"/></svg> Импорт`;
  }
}

// ── Batch evaluation ──────────────────────────────────────
async function doBatch() {
  const btn = document.getElementById('btn-batch');
  const wrap = document.getElementById('batch-progress-wrap');
  const bar  = document.getElementById('batch-progress-bar');
  const label = document.getElementById('batch-progress-label');
  const pct  = document.getElementById('batch-progress-pct');

  if (btn) btn.disabled = true;
  wrap?.classList.remove('hidden');

  try {
    const convs = await api('/api/conversations');
    const todo = convs.filter(c => !c.eval_id);
    const total = todo.length;

    if (total === 0) {
      if (label) label.textContent = 'Все диалоги уже оценены';
      setTimeout(() => wrap?.classList.add('hidden'), 2000);
      return;
    }

    let done = 0;
    for (const conv of todo) {
      if (label) label.textContent = `Оценка: ${conv.id}`;
      try {
        await api('/api/evaluations', {
          method: 'POST',
          body: JSON.stringify({ conversation_id: conv.id }),
        });
      } catch {}
      done++;
      const p = Math.round(done / total * 100);
      if (bar) bar.style.width = p + '%';
      if (pct) pct.textContent = `${done} / ${total}`;
    }

    if (label) label.textContent = `Готово: оценено ${done} диалогов`;
    window.refreshConversations?.();
    refreshStats();
    setTimeout(() => wrap?.classList.add('hidden'), 3000);
  } catch (e) {
    if (label) label.textContent = 'Ошибка: ' + e.message;
  } finally {
    if (btn) {
      btn.disabled = false;
    }
  }
}

// ── Add conversation modal ────────────────────────────────
function openAddModal() {
  const modal = document.getElementById('add-conv-modal');
  if (!modal) return;
  // Reset form
  document.getElementById('new-conv-id').value = '';
  document.getElementById('new-conv-channel').value = 'agent chat';
  document.getElementById('new-conv-lang').value = 'RU';
  document.getElementById('transcript-rows').innerHTML = '';
  document.getElementById('modal-error').textContent = '';
  // Add two default rows: operator + client
  addTranscriptRow('operator', '');
  addTranscriptRow('client', '');
  modal.classList.remove('hidden');
  document.getElementById('new-conv-id').focus();
}

function closeAddModal() {
  document.getElementById('add-conv-modal')?.classList.add('hidden');
}

let msgRowIdx = 0;

function addTranscriptRow(speaker = 'operator', text = '') {
  const wrap = document.getElementById('transcript-rows');
  if (!wrap) return;
  const idx = msgRowIdx++;
  const div = document.createElement('div');
  div.className = 'transcript-row-wrap';
  div.dataset.rowIdx = idx;
  div.innerHTML = `
    <select class="modal-input msg-speaker" style="font-size:11px">
      <option value="operator" ${speaker==='operator'?'selected':''}>Оператор</option>
      <option value="client"   ${speaker==='client'  ?'selected':''}>Клиент</option>
      <option value="bot"      ${speaker==='bot'     ?'selected':''}>Бот</option>
      <option value="system"   ${speaker==='system'  ?'selected':''}>Система</option>
    </select>
    <input class="modal-input msg-ts" type="text" placeholder="00:00" value="00:00" style="font-size:12px;font-family:var(--mono)">
    <textarea class="modal-input msg-text" rows="2" placeholder="Текст реплики…" style="resize:vertical">${text}</textarea>
    <button class="msg-del-btn" type="button" title="Удалить реплику">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2 2l8 8M10 2L2 10" stroke="currentColor" stroke-width="1.4" stroke-linecap="square"/>
      </svg>
    </button>`;
  div.querySelector('.msg-del-btn').addEventListener('click', () => div.remove());
  wrap.appendChild(div);
}

async function saveNewConversation() {
  const idVal     = document.getElementById('new-conv-id').value.trim();
  const channel   = document.getElementById('new-conv-channel').value;
  const language  = document.getElementById('new-conv-lang').value;
  const errEl     = document.getElementById('modal-error');
  const saveBtn   = document.getElementById('btn-modal-save');
  errEl.textContent = '';

  // Collect transcript rows
  const rows = [...document.querySelectorAll('#transcript-rows .transcript-row-wrap')];
  const transcript = rows.map(row => ({
    speaker:   row.querySelector('.msg-speaker').value,
    timestamp: row.querySelector('.msg-ts').value.trim() || '00:00',
    text:      row.querySelector('.msg-text').value.trim(),
  })).filter(m => m.text);

  if (!transcript.length) {
    errEl.textContent = 'Добавьте хотя бы одну реплику с текстом';
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = 'Сохранение…';
  try {
    const body = { channel, language, transcript };
    if (idVal) body.id = idVal;
    await api('/api/conversations', { method: 'POST', body: JSON.stringify(body) });
    closeAddModal();
    window.refreshConversations?.();
    refreshStats();
  } catch (e) {
    errEl.textContent = e.message;
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Сохранить';
  }
}

// ── Toast notifications ───────────────────────────────────
function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = `cqa-toast cqa-toast-${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => t.classList.add('cqa-toast-in'));
  setTimeout(() => {
    t.classList.remove('cqa-toast-in');
    t.addEventListener('transitionend', () => t.remove(), { once: true });
  }, 3500);
}
window.showToast = showToast;

// ── Score odometer animation ──────────────────────────────
function animateScore(el, value) {
  if (!el || value === null || value === undefined) return;
  el.textContent = '';
  el.classList.remove('rolling');
  void el.offsetWidth; // reflow
  el.textContent = typeof value === 'number' ? value.toFixed(2) : value;
  el.classList.add('rolling');
}

// ── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.nav-item').forEach(el =>
    el.addEventListener('click', () => switchView(el.dataset.view))
  );
  document.querySelectorAll('.role-btn').forEach(el =>
    el.addEventListener('click', () => setRole(el.dataset.role))
  );

  document.getElementById('btn-add-conv')?.addEventListener('click', openAddModal);
  document.getElementById('btn-import')?.addEventListener('click', doImport);
  document.getElementById('btn-batch')?.addEventListener('click', doBatch);

  // Modal controls
  document.getElementById('modal-close')?.addEventListener('click', closeAddModal);
  document.getElementById('btn-modal-cancel')?.addEventListener('click', closeAddModal);
  document.getElementById('btn-modal-save')?.addEventListener('click', saveNewConversation);
  document.getElementById('btn-add-msg')?.addEventListener('click', () => addTranscriptRow('operator'));
  // Close on backdrop click
  document.getElementById('add-conv-modal')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeAddModal();
  });

  switchView('conversations');
  refreshStats();
});

window.appState   = state;
window.appApi     = api;
window.refreshStats = refreshStats;
window.animateScore = animateScore;
