// Analytics dashboard
(function () {

  const CRIT_TITLES = {
    c01:'Установление контакта', c02:'Выявление потребности',
    c03:'Идентификация',         c04:'Корректная консультация',
    c05:'Эмпатия',               c06:'Управление диалогом',
    c07:'Завершение',            c08:'Грубые ошибки',
  };

  function escHtml(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function scoreColor(n) {
    if (n === null || n === undefined) return 'var(--ink-3)';
    return n >= 75 ? 'var(--brand-light)' : n >= 40 ? 'var(--warn)' : 'var(--danger)';
  }

  // ── KPI tiles ────────────────────────────────────────────
  function kpiTile(label, value, sub, color) {
    return `<div class="kpi-tile">
      <div class="kpi-value" style="color:${color || 'var(--ink)'}">${value}</div>
      <div class="kpi-label">${label}</div>
      ${sub ? `<div class="kpi-sub">${sub}</div>` : ''}
    </div>`;
  }

  // ── Horizontal bar ───────────────────────────────────────
  function hbar(label, count, max, color, pct) {
    const w = max > 0 ? Math.round((count / max) * 100) : 0;
    return `<div class="hbar-row">
      <span class="hbar-label">${label}</span>
      <div class="hbar-track">
        <div class="hbar-fill" style="width:${w}%;background:${color}"></div>
      </div>
      <span class="hbar-count">${count}</span>
      ${pct !== undefined ? `<span class="hbar-pct">${pct}%</span>` : ''}
    </div>`;
  }

  // ── Render ───────────────────────────────────────────────
  function render(data) {
    const el = document.getElementById('analytics-view');
    if (!el) return;

    const t = data.totals || {};
    const d = data.distribution || {};
    const pctEval = t.total_convs > 0
      ? Math.round((t.evaluated / t.total_convs) * 100) : 0;
    const avgFmt = t.avg_score != null ? parseFloat(t.avg_score).toFixed(1) : '—';

    // Distribution: max bucket
    const distBuckets = [
      { label: '90–100', count: d.d90 || 0, color: 'var(--brand-light)' },
      { label: '75–89',  count: d.d75 || 0, color: 'var(--brand)' },
      { label: '50–74',  count: d.d50 || 0, color: 'var(--warn)' },
      { label: '25–49',  count: d.d25 || 0, color: '#d47217' },
      { label: '0–24',   count: d.d0  || 0, color: 'var(--danger)' },
    ];
    const maxBucket = Math.max(...distBuckets.map(b => b.count), 1);

    // Criteria failures
    const crits = (data.criteria || []).filter(c => c.criterion_id !== 'c08');
    const maxFail = Math.max(...crits.map(c => c.failures || 0), 1);

    // By channel / lang
    const byChannel = data.by_channel || [];
    const byLang    = data.by_lang    || [];

    el.innerHTML = `
      <div class="analytics-wrap">
        <div class="analytics-section-title">Общая статистика</div>

        <div class="kpi-row">
          ${kpiTile('Диалогов', t.total_convs ?? '—', null, 'var(--ink)')}
          ${kpiTile('Оценено', t.evaluated ?? '—', `${pctEval}% от всех`, 'var(--brand-light)')}
          ${kpiTile('Средняя оценка', avgFmt, null, scoreColor(t.avg_score))}
          ${kpiTile('Грубых ошибок', t.gross_errors ?? '—', null, t.gross_errors > 0 ? 'var(--danger)' : 'var(--ink-3)')}
        </div>

        <div class="analytics-grid">
          <!-- Score distribution -->
          <div class="analytics-card">
            <div class="analytics-card-title">Распределение оценок</div>
            <div class="hbar-list">
              ${distBuckets.map(b => hbar(b.label, b.count, maxBucket, b.color)).join('')}
            </div>
          </div>

          <!-- Criteria failures -->
          <div class="analytics-card">
            <div class="analytics-card-title">Топ провальных критериев</div>
            <div class="hbar-list">
              ${crits.slice(0, 7).map(c => {
                const failRate = c.total > 0 ? Math.round((c.failures / c.total) * 100) : 0;
                return hbar(
                  CRIT_TITLES[c.criterion_id] || c.criterion_id,
                  c.failures,
                  maxFail,
                  failRate > 50 ? 'var(--danger)' : failRate > 25 ? 'var(--warn)' : 'var(--brand)',
                  failRate
                );
              }).join('')}
            </div>
          </div>

          <!-- By channel -->
          <div class="analytics-card">
            <div class="analytics-card-title">По каналу</div>
            ${byChannel.length ? `<table class="analytics-table">
              <thead><tr><th>Канал</th><th>Оценено</th><th>Средняя</th></tr></thead>
              <tbody>${byChannel.map(r => `<tr>
                <td>${r.channel === 'agent chat' ? 'Чат' : r.channel === 'voice call' ? 'Звонок' : escHtml(r.channel)}</td>
                <td>${r.evaluated}</td>
                <td style="color:${scoreColor(r.avg_score)};font-family:var(--mono);font-weight:600">${r.avg_score ?? '—'}</td>
              </tr>`).join('')}</tbody>
            </table>` : '<div class="list-loading" style="padding:20px 0">Нет данных</div>'}
          </div>

          <!-- By language -->
          <div class="analytics-card">
            <div class="analytics-card-title">По языку</div>
            ${byLang.length ? `<table class="analytics-table">
              <thead><tr><th>Язык</th><th>Оценено</th><th>Средняя</th></tr></thead>
              <tbody>${byLang.map(r => `<tr>
                <td><span class="badge badge-${(r.language||'').toLowerCase()}">${r.language}</span></td>
                <td>${r.evaluated}</td>
                <td style="color:${scoreColor(r.avg_score)};font-family:var(--mono);font-weight:600">${r.avg_score ?? '—'}</td>
              </tr>`).join('')}</tbody>
            </table>` : '<div class="list-loading" style="padding:20px 0">Нет данных</div>'}
          </div>
        </div>
      </div>`;
  }

  async function loadAnalytics() {
    const el = document.getElementById('analytics-view');
    if (!el) return;
    el.innerHTML = '<div class="list-loading">Загрузка…</div>';
    try {
      const data = await window.appApi('/api/analytics');
      render(data);
    } catch (e) {
      el.innerHTML = `<div class="list-loading" style="color:var(--danger)">${e.message}</div>`;
    }
  }

  window.loadAnalytics = loadAnalytics;
})();
