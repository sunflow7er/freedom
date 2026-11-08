// Appeals view — list open appeals, submit decision (reviewer role)
(function () {

  let appeals = [];

  const container = () => document.getElementById('appeals-view');

  function escHtml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function statusLabel(s) {
    if (s === 'open')     return '<span class="appeal-status status-open">Открыта</span>';
    if (s === 'approved') return '<span class="appeal-status status-approved">Одобрена</span>';
    if (s === 'rejected') return '<span class="appeal-status status-rejected">Отклонена</span>';
    return s;
  }

  // ── Render list ───────────────────────────────────────────
  function renderAppeals() {
    const c = container();
    if (!c) return;

    const isReviewer = window.appState?.role === 'reviewer';

    if (!appeals.length) {
      c.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <h2 style="font-size:14px;font-weight:600">Апелляции</h2>
          <button class="btn btn-ghost" id="btn-refresh-appeals">Обновить</button>
        </div>
        <div class="list-loading">Нет апелляций</div>`;
      document.getElementById('btn-refresh-appeals')?.addEventListener('click', loadAppeals);
      return;
    }

    const cards = appeals.map(a => {
      const decisionHtml = a.decision
        ? `<div style="margin-top:10px;padding:10px;background:var(--bg-2);border-radius:var(--r);font-size:12px">
            <div style="color:var(--ink-2);margin-bottom:4px">
              Решение: <strong style="color:var(--ink)">${a.decision.action === 'approve' ? 'Одобрено' : 'Отклонено'}</strong>
            </div>
            ${a.decision.reason ? `<div style="color:var(--ink-2)">${escHtml(a.decision.reason)}</div>` : ''}
           </div>`
        : '';

      const decideHtml = isReviewer && a.status === 'open'
        ? `<div style="margin-top:10px;display:flex;flex-direction:column;gap:6px">
            <textarea id="reason-${a.id}" placeholder="Причина решения (необязательно)"
              style="width:100%;background:var(--bg-2);border:1px solid var(--border);
                     border-radius:var(--r);color:var(--ink);padding:7px 10px;
                     font-size:12px;resize:vertical;min-height:52px;font-family:inherit"></textarea>
            <div style="display:flex;gap:8px">
              <button class="btn btn-primary" data-appeal="${a.id}" data-action="approve">Одобрить</button>
              <button class="btn btn-ghost" data-appeal="${a.id}" data-action="reject">Отклонить</button>
            </div>
           </div>`
        : '';

      return `<div class="appeal-card">
        <div class="appeal-header">
          ${statusLabel(a.status)}
          <span style="font-size:12px;color:var(--ink-2)">
            Диалог <strong style="color:var(--ink)">${escHtml(a.conversation_id || a.evaluation_id)}</strong>
            &nbsp;·&nbsp; Критерий <code style="color:var(--ink-3)">${escHtml(a.criterion_id)}</code>
          </span>
          <span style="font-size:11px;color:var(--ink-3);margin-left:auto">${a.created_at ? a.created_at.slice(0,16).replace('T',' ') : ''}</span>
        </div>
        <div style="font-size:12px;color:var(--ink-2)">${escHtml(a.comment || '')}</div>
        ${decisionHtml}
        ${decideHtml}
      </div>`;
    }).join('');

    c.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <h2 style="font-size:14px;font-weight:600">Апелляции</h2>
        <div style="display:flex;gap:8px;align-items:center">
          <select id="filter-appeal-status" class="filter-select" style="width:140px">
            <option value="">Все статусы</option>
            <option value="open">Открытые</option>
            <option value="approved">Одобренные</option>
            <option value="rejected">Отклонённые</option>
          </select>
          <button class="btn btn-ghost" id="btn-refresh-appeals">Обновить</button>
        </div>
      </div>
      <div id="appeals-list">${cards}</div>`;

    document.getElementById('btn-refresh-appeals')?.addEventListener('click', loadAppeals);

    document.getElementById('filter-appeal-status')?.addEventListener('change', async (e) => {
      const status = e.target.value;
      try {
        appeals = await window.appApi('/api/appeals' + (status ? `?status=${status}` : ''));
        renderAppeals();
      } catch {}
    });

    // Decision buttons
    c.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const appealId = parseInt(btn.dataset.appeal);
        const action = btn.dataset.action;
        const reason = document.getElementById('reason-' + appealId)?.value || '';
        btn.disabled = true;
        try {
          await window.appApi(`/api/appeals/${appealId}/decision`, {
            method: 'POST',
            body: JSON.stringify({ action, reason }),
          });
          await loadAppeals();
        } catch (e) {
          alert('Ошибка: ' + e.message);
          btn.disabled = false;
        }
      });
    });
  }

  // ── Load appeals ──────────────────────────────────────────
  async function loadAppeals() {
    const c = container();
    if (!c) return;

    try {
      // Also load conversation_id for display
      const rawAppeals = await window.appApi('/api/appeals');
      // Enrich with conversation info
      appeals = await Promise.all(rawAppeals.map(async a => {
        try {
          const ev = await window.appApi('/api/evaluations/' + a.evaluation_id);
          a.conversation_id = ev.conversation_id;
          // Attach decision if any
          const decisions = await window.appApi('/api/decisions?appeal_id=' + a.id).catch(() => []);
          a.decision = decisions[0] || null;
        } catch {}
        return a;
      }));
      renderAppeals();
    } catch (e) {
      if (c) c.innerHTML = `<div class="list-loading" style="color:var(--danger)">${e.message}</div>`;
    }
  }

  window.loadAppeals = loadAppeals;

  // Re-render on role change (show/hide decision buttons)
  document.addEventListener('rolechange', () => {
    if (appeals.length > 0) renderAppeals();
  });
})();
