// Checklist editor — view and edit criteria, manage versions
(function () {

  let checklists = [];
  let currentChecklist = null;
  let currentVersion = null;
  let editingCriteria = [];

  const container = () => document.getElementById('checklist-editor');

  // ── Helpers ───────────────────────────────────────────────
  function typeLabel(t) {
    if (t === 'binary') return 'Да/Нет';
    if (t === 'binary_na') return 'Да/Нет/N/A';
    if (t === 'scale') return 'Шкала';
    if (t === 'flag') return 'Флаг';
    return t;
  }

  function escHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Render checklist list ─────────────────────────────────
  function renderChecklistTabs() {
    const c = container();
    if (!c) return;

    const tabs = checklists.map(cl =>
      `<button class="tab-btn ${currentChecklist && currentChecklist.id === cl.id ? 'active' : ''}"
               data-id="${cl.id}">${escHtml(cl.name)}</button>`
    ).join('');

    c.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <h2 style="font-size:14px;font-weight:600">Чек-листы</h2>
      </div>
      <div class="checklist-tabs">${tabs}</div>
      <div id="checklist-content">
        ${currentChecklist ? '' : '<div class="list-loading">Выберите чек-лист</div>'}
      </div>`;

    c.querySelectorAll('.tab-btn').forEach(btn =>
      btn.addEventListener('click', () => selectChecklist(parseInt(btn.dataset.id)))
    );

    if (currentChecklist) renderChecklistDetail();
  }

  // ── Select checklist ──────────────────────────────────────
  async function selectChecklist(id) {
    const cl = checklists.find(c => c.id === id);
    if (!cl) return;
    currentChecklist = cl;

    // Load active version
    const content = document.getElementById('checklist-content');
    if (content) content.innerHTML = '<div class="list-loading">Загрузка версии…</div>';

    try {
      const versions = await window.appApi(`/api/checklists/${id}/versions`);
      currentVersion = versions.find(v => v.id === cl.active_version_id) || versions[0] || null;
      if (currentVersion) {
        editingCriteria = JSON.parse(JSON.stringify(
          (typeof currentVersion.config === 'string'
            ? JSON.parse(currentVersion.config)
            : currentVersion.config
          ).criteria || []
        ));
      }
    } catch (e) {
      console.error('Failed to load versions', e);
    }

    renderChecklistTabs();
  }

  // ── Render checklist detail ───────────────────────────────
  function renderChecklistDetail() {
    const content = document.getElementById('checklist-content');
    if (!content || !currentVersion) return;

    const versionLabel = `v${currentVersion.version}`;
    const rows = editingCriteria.map((cr, i) => `
      <tr data-idx="${i}">
        <td style="white-space:nowrap"><code style="font-size:11px;color:var(--ink-3)">${escHtml(cr.id)}</code></td>
        <td>
          <input class="criterion-edit-input" data-field="title" data-idx="${i}"
                 value="${escHtml(cr.title || '')}" style="width:100%">
        </td>
        <td style="white-space:nowrap">${typeLabel(cr.type || '')}</td>
        <td>
          <input class="criterion-edit-input weight-input" type="number" min="0" max="100"
                 data-field="weight" data-idx="${i}" value="${cr.weight || 0}">
        </td>
        <td>
          <textarea class="criterion-edit-input criterion-na-input" data-field="na_condition" data-idx="${i}"
                    placeholder="—" rows="2">${escHtml(cr.na_condition || '')}</textarea>
        </td>
      </tr>`).join('');

    content.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <span style="font-size:12px;color:var(--ink-3)">Активная версия: <strong style="color:var(--ink)">${versionLabel}</strong>
          &nbsp;·&nbsp; Канал: <strong style="color:var(--ink)">${currentChecklist.channel || '—'}</strong>
        </span>
        <div style="display:flex;gap:8px">
          <button class="btn btn-ghost" id="btn-save-version">Сохранить как новую версию</button>
          <button class="btn btn-primary" id="btn-reevaluate">Переоценить все</button>
        </div>
      </div>
      <table class="checklist-table">
        <thead>
          <tr>
            <th>ID</th><th>Критерий</th><th>Тип</th><th>Вес</th><th>N/A условие</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;

    // Live edit
    content.querySelectorAll('.criterion-edit-input').forEach(inp => {
      inp.addEventListener('input', () => {
        const idx = parseInt(inp.dataset.idx);
        const field = inp.dataset.field;
        editingCriteria[idx][field] = field === 'weight' ? parseInt(inp.value) || 0 : inp.value;
      });
    });

    document.getElementById('btn-save-version')?.addEventListener('click', saveNewVersion);
    document.getElementById('btn-reevaluate')?.addEventListener('click', reevaluateAll);
  }

  // ── Save new version ──────────────────────────────────────
  async function saveNewVersion() {
    if (!currentChecklist) return;
    const btn = document.getElementById('btn-save-version');
    if (btn) { btn.disabled = true; btn.textContent = 'Сохранение…'; }

    try {
      const config = {
        ...(typeof currentVersion.config === 'string'
          ? JSON.parse(currentVersion.config) : currentVersion.config),
        criteria: editingCriteria
      };
      const result = await window.appApi(`/api/checklists/${currentChecklist.id}/versions`, {
        method: 'POST',
        body: JSON.stringify({ config, comment: 'Изменено через интерфейс' }),
      });
      currentVersion = result;
      editingCriteria = JSON.parse(JSON.stringify(
        (typeof result.config === 'string' ? JSON.parse(result.config) : result.config).criteria || []
      ));
      // Reload checklists to get updated active_version_id
      await loadChecklists();
      alert('Новая версия сохранена');
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Сохранить как новую версию'; }
    }
  }

  // ── Re-evaluate all conversations ─────────────────────────
  async function reevaluateAll() {
    if (!confirm('Запустить переоценку всех диалогов с текущей версией чек-листа?')) return;
    const btn = document.getElementById('btn-reevaluate');
    if (btn) { btn.disabled = true; btn.textContent = 'Запуск…'; }

    try {
      const convs = await window.appApi('/api/conversations');
      let done = 0;
      for (const conv of convs) {
        try {
          await window.appApi('/api/evaluations', {
            method: 'POST',
            body: JSON.stringify({
              conversation_id: conv.id,
              checklist_version_id: currentVersion?.id,
            }),
          });
          done++;
          if (btn) btn.textContent = `Оценено ${done}/${convs.length}…`;
        } catch {}
      }
      window.refreshConversations?.();
      alert(`Переоценка завершена: ${done}/${convs.length} диалогов`);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Переоценить все'; }
    }
  }

  // ── Load checklists ───────────────────────────────────────
  async function loadChecklists() {
    try {
      checklists = await window.appApi('/api/checklists');
      if (!currentChecklist && checklists.length > 0) {
        currentChecklist = checklists[0];
        await selectChecklist(checklists[0].id);
        return;
      }
      if (currentChecklist) {
        // Refresh current
        currentChecklist = checklists.find(c => c.id === currentChecklist.id) || checklists[0];
      }
      renderChecklistTabs();
    } catch (e) {
      const c = container();
      if (c) c.innerHTML = `<div class="list-loading" style="color:var(--danger)">${e.message}</div>`;
    }
  }

  window.loadChecklists = loadChecklists;
})();
