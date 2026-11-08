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
  function typeSelect(current, idx) {
    const opts = [
      ['binary',    'Да/Нет'],
      ['binary_na', 'Да/Нет/N/A'],
      ['scale',     'Шкала'],
      ['flag',      'Флаг'],
    ];
    return `<select class="criterion-edit-input criterion-type-select" data-field="type" data-idx="${idx}" style="min-width:110px">
      ${opts.map(([v, l]) => `<option value="${v}" ${current === v ? 'selected' : ''}>${l}</option>`).join('')}
    </select>`;
  }

  function nextCriterionId() {
    const nums = editingCriteria
      .map(c => parseInt((c.id || '').replace(/\D/g, '')))
      .filter(n => !isNaN(n));
    const max = nums.length ? Math.max(...nums) : 0;
    return 'c' + String(max + 1).padStart(2, '0');
  }

  function renderChecklistDetail() {
    const content = document.getElementById('checklist-content');
    if (!content || !currentVersion) return;

    const versionLabel = `v${currentVersion.version}`;
    const rows = editingCriteria.map((cr, i) => `
      <tr data-idx="${i}">
        <td style="white-space:nowrap"><code style="font-size:11px;color:var(--ink-3)">${escHtml(cr.id)}</code></td>
        <td>
          <textarea class="criterion-edit-input criterion-na-input" data-field="title" data-idx="${i}"
                    rows="2">${escHtml(cr.title || '')}</textarea>
        </td>
        <td>${typeSelect(cr.type || 'binary', i)}</td>
        <td>
          <input class="criterion-edit-input weight-input" type="number" min="0" max="100"
                 data-field="weight" data-idx="${i}" value="${cr.weight || 0}">
        </td>
        <td>
          <textarea class="criterion-edit-input criterion-na-input" data-field="na_condition" data-idx="${i}"
                    placeholder="—" rows="2">${escHtml(cr.na_condition || '')}</textarea>
        </td>
        <td>
          <button class="btn-delete-crit" data-idx="${i}" title="Удалить критерий">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M2 3.5h9M5 3.5V2.5h3v1M5.5 5.5v4M7.5 5.5v4M3 3.5l.5 7h6l.5-7" stroke="currentColor" stroke-width="1.2" stroke-linecap="square"/>
            </svg>
          </button>
        </td>
      </tr>`).join('');

    content.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">
        <span style="font-size:12px;color:var(--ink-3)">
          Версия: <strong style="color:var(--ink)">${versionLabel}</strong>
          &nbsp;·&nbsp; Канал: <strong style="color:var(--ink)">${currentChecklist.channel || '—'}</strong>
        </span>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" id="btn-add-criterion">+ Добавить критерий</button>
          <button class="btn btn-ghost" id="btn-save-version">Сохранить версию</button>
          <button class="btn btn-primary" id="btn-reevaluate">Переоценить все</button>
        </div>
      </div>
      <table class="checklist-table">
        <thead>
          <tr>
            <th>ID</th><th>Критерий</th><th>Тип</th><th>Вес</th><th>N/A условие</th><th></th>
          </tr>
        </thead>
        <tbody id="criteria-tbody">${rows}</tbody>
      </table>`;

    // Live edit
    content.querySelectorAll('.criterion-edit-input').forEach(inp => {
      inp.addEventListener('input', () => {
        const idx   = parseInt(inp.dataset.idx);
        const field = inp.dataset.field;
        editingCriteria[idx][field] = field === 'weight' ? parseInt(inp.value) || 0 : inp.value;
      });
    });

    // Delete — inline confirm, no browser dialog
    content.querySelectorAll('.btn-delete-crit').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.idx);
        const tr  = btn.closest('tr');
        if (!tr) return;

        // If already showing confirm, just delete
        if (btn.dataset.confirming === '1') {
          editingCriteria.splice(idx, 1);
          renderChecklistDetail();
          return;
        }

        // Show inline confirm state
        btn.dataset.confirming = '1';
        btn.innerHTML = 'Удалить?';
        btn.style.color = 'var(--danger)';
        btn.style.borderColor = 'rgba(224,82,82,.3)';
        btn.style.background = 'var(--danger-dim)';
        btn.style.minWidth = '72px';

        // Cancel on click outside this row
        const cancel = (e) => {
          if (!tr.contains(e.target)) {
            btn.dataset.confirming = '';
            btn.textContent = '×';
            btn.style.color = '';
            btn.style.borderColor = '';
            btn.style.minWidth = '';
            document.removeEventListener('click', cancel);
          }
        };
        setTimeout(() => document.addEventListener('click', cancel), 0);
      });
    });

    // Add
    document.getElementById('btn-add-criterion')?.addEventListener('click', () => {
      editingCriteria.push({
        id: nextCriterionId(), title: 'Новый критерий',
        type: 'binary', weight: 10, na_condition: '',
      });
      renderChecklistDetail();
      document.getElementById('criteria-tbody')?.lastElementChild
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
