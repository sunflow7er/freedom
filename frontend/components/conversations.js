// Conversation list with filters
(function () {
  let allConvs = [];
  let filters  = { q: '', lang: '', channel: '', status: '', gross: false };
  let sortMode = 'default';
  let page     = 1;
  const PAGE   = 7;

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

    // Clamp page
    const totalPages = Math.max(1, Math.ceil(items.length / PAGE));
    if (page > totalPages) page = totalPages;
    const pageItems = items.slice((page - 1) * PAGE, page * PAGE);

    // Smart pagination: 1 … (cur-1) cur (cur+1) … last
    function buildPageBar(cur, total) {
      if (total <= 1) return '';
      const pages = new Set([1, total, cur, cur - 1, cur + 1].filter(p => p >= 1 && p <= total));
      const sorted = [...pages].sort((a, b) => a - b);
      let btns = '';
      let prev = 0;
      for (const p of sorted) {
        if (p - prev > 1) btns += `<span class="page-ellipsis">…</span>`;
        btns += `<button class="page-btn${p === cur ? ' active' : ''}" data-page="${p}">${p}</button>`;
        prev = p;
      }
      return `<div class="pagination" id="pagination">
        <button class="page-btn" data-page="${cur - 1}" ${cur === 1 ? 'disabled' : ''}>‹</button>
        ${btns}
        <button class="page-btn" data-page="${cur + 1}" ${cur === total ? 'disabled' : ''}>›</button>
      </div>`;
    }
    const pageBar = buildPageBar(page, totalPages);

    list.innerHTML = pageItems.map(c => {
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

    // Append pagination after items
    list.insertAdjacentHTML('beforeend', pageBar);

    list.querySelectorAll('.conv-item').forEach(el => {
      el.addEventListener('click', () => {
        list.querySelectorAll('.conv-item').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        window.openConversation?.(el.dataset.id);
      });
    });

    list.querySelectorAll('.page-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = parseInt(btn.dataset.page);
        if (!isNaN(p) && p >= 1 && p <= totalPages) {
          page = p;
          renderList();
          list.scrollTo({ top: 0, behavior: 'smooth' });
        }
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

    const reset = () => { page = 1; renderList(); };
    q?.addEventListener('input',  () => { filters.q       = q.value;       reset(); });
    lang?.addEventListener('change',    () => { filters.lang    = lang.value;    reset(); });
    channel?.addEventListener('change', () => { filters.channel = channel.value; reset(); });
    status?.addEventListener('change',  () => { filters.status  = status.value;  reset(); });
    gross?.addEventListener('change',   () => { filters.gross   = gross.checked; reset(); });
    sortEl?.addEventListener('change',  () => { sortMode = sortEl.value;         reset(); });
  });

  window.refreshConversations = loadConversations;
})();
