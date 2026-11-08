// Conversation list with filters
(function () {
  let allConvs = [];
  let filters = { q: '', lang: '', channel: '', status: '', gross: false };
  let sortMode = 'default'; // default | gross_first | score_desc | score_asc

  function scoreClass(total) {
    if (total === null || total === undefined) return 'score-none';
    const n = parseFloat(total);
    if (n >= 75) return 'score-high';
    if (n >= 40) return 'score-mid';
    return 'score-low';
  }

  function channelBadge(ch) {
    if (ch === 'agent chat') return '<span class="badge badge-chat">Чат</span>';
    if (ch === 'voice call') return '<span class="badge badge-call">Звонок</span>';
    return '';
  }

  function renderList() {
    const list = document.getElementById('conv-list');
    if (!list) return;

    let items = allConvs.filter(c => {
      if (filters.q && !c.id.toLowerCase().includes(filters.q.toLowerCase())) return false;
      if (filters.lang && c.language !== filters.lang) return false;
      if (filters.channel && c.channel !== filters.channel) return false;
      if (filters.status === 'evaluated' && !c.eval_id) return false;
      if (filters.status === 'pending' && c.eval_id) return false;
      if (filters.gross && !c.gross_error) return false;
      return true;
    });

    if (!items.length) {
      list.innerHTML = '<div class="list-loading">Нет диалогов</div>';
      return;
    }

    // Client-side sort when not using backend sort
    if (sortMode === 'gross_first') {
      items = [...items].sort((a, b) => (b.gross_error ? 1 : 0) - (a.gross_error ? 1 : 0));
    } else if (sortMode === 'score_desc') {
      items = [...items].sort((a, b) => (b.total ?? -1) - (a.total ?? -1));
    } else if (sortMode === 'score_asc') {
      items = [...items].sort((a, b) => {
        if (a.total == null) return 1;
        if (b.total == null) return -1;
        return a.total - b.total;
      });
    }

    list.innerHTML = items.map(c => {
      const score = c.total != null
        ? `<span class="conv-item-score ${scoreClass(c.total)}">${parseFloat(c.total).toFixed(1)}</span>`
        : `<span class="conv-item-score score-none">—</span>`;
      const gross = c.gross_error
        ? '<span class="badge badge-gross">! Грубая</span>'
        : '';
      const langBadge = `<span class="badge badge-${(c.language||'').toLowerCase()}">${c.language||''}</span>`;
      const preview = c.preview
        ? `<div class="conv-item-preview">${c.preview.length > 85 ? c.preview.slice(0, 85) + '…' : c.preview}</div>`
        : '';

      return `<div class="conv-item${c.gross_error ? ' has-gross' : ''}" data-id="${c.id}">
        <div class="conv-item-header">
          <span class="conv-item-id">${c.id}</span>
          ${score}
        </div>
        <div class="conv-item-meta">
          ${channelBadge(c.channel)}
          ${langBadge}
          ${gross}
        </div>
        ${preview}
      </div>`;
    }).join('');

    list.querySelectorAll('.conv-item').forEach(el => {
      el.addEventListener('click', () => {
        list.querySelectorAll('.conv-item').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        window.openConversation?.(el.dataset.id);
      });
    });
  }

  async function loadConversations() {
    const list = document.getElementById('conv-list');
    if (!list) return;
    list.innerHTML = '<div class="list-loading">Загрузка…</div>';
    try {
      allConvs = await window.appApi('/api/conversations');
      renderList();
    } catch (e) {
      list.innerHTML = `<div class="list-loading" style="color:var(--danger)">${e.message}</div>`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadConversations();

    const q = document.getElementById('filter-q');
    const lang = document.getElementById('filter-lang');
    const channel = document.getElementById('filter-channel');
    const status = document.getElementById('filter-status');
    const gross = document.getElementById('filter-gross');

    const sortEl = document.getElementById('filter-sort');

    q?.addEventListener('input', () => { filters.q = q.value; renderList(); });
    lang?.addEventListener('change', () => { filters.lang = lang.value; renderList(); });
    channel?.addEventListener('change', () => { filters.channel = channel.value; renderList(); });
    status?.addEventListener('change', () => { filters.status = status.value; renderList(); });
    gross?.addEventListener('change', () => { filters.gross = gross.checked; renderList(); });
    sortEl?.addEventListener('change', () => { sortMode = sortEl.value; renderList(); });
  });

  window.refreshConversations = loadConversations;
})();
