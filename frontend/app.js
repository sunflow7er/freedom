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
  const btn = document.getElementById('btn-import');
  if (!btn) return;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="border-top-color:var(--ink-2)"></span> Импорт…';
  try {
    const result = await api('/api/datasets/DEV/import', { method: 'POST' });
    const n = result.imported ?? result.total ?? '?';
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 7l3.5 3.5L11 3.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="square"/></svg> ${n} загружено`;
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

  document.getElementById('btn-import')?.addEventListener('click', doImport);
  document.getElementById('btn-batch')?.addEventListener('click', doBatch);

  switchView('conversations');
  refreshStats();
});

window.appState   = state;
window.appApi     = api;
window.refreshStats = refreshStats;
window.animateScore = animateScore;
