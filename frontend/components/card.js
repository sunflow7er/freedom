// Conversation card: transcript + evaluation results
(function () {

  let currentConvId = null;

  // ── Helpers ───────────────────────────────────────────
  function scoreClass(n) {
    if (n === null || n === undefined) return 'none';
    const v = parseFloat(n);
    return v >= 75 ? 'high' : v >= 40 ? 'mid' : 'low';
  }

  function answerLabel(answer) {
    if (answer === 'yes') return 'Да';
    if (answer === 'no')  return 'Нет';
    if (answer === 'na')  return 'N/A';
    return answer;
  }

  function escHtml(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  const CRITERION_TITLES = {
    c01:'Установление контакта', c02:'Выявление потребности',
    c03:'Идентификация',         c04:'Корректная консультация',
    c05:'Эмпатия',               c06:'Управление диалогом',
    c07:'Завершение',            c08:'Грубые ошибки',
  };

  const CRITERION_WEIGHTS = { c01:10, c02:15, c03:20, c04:20, c05:15, c06:15, c07:5, c08:0 };

  function getCriterionTitle(id) { return CRITERION_TITLES[id] || id; }

  // ── Gauge ─────────────────────────────────────────────
  function buildGauge(total, grossError) {
    const cls    = scoreClass(total);
    const radius = 38;
    const circ   = 2 * Math.PI * radius; // ≈239
    const circ2  = circ.toFixed(2);

    const grossHtml = grossError
      ? `<div class="gross-badge">&#9888; Грубая ошибка</div>`
      : '';

    const scoreRight = `
      <div class="gauge-info">
        <span class="score-gauge-num ${cls}" id="gauge-num">
          ${total !== null ? parseFloat(total).toFixed(1) : '—'}
        </span>
        <span class="score-gauge-unit">/100</span>
        ${grossHtml}
      </div>`;

    return `
      <div class="score-gauge-wrap">
        <div class="score-gauge">
          <svg viewBox="0 0 90 90">
            <circle class="gauge-track" cx="45" cy="45" r="${radius}"/>
            <circle class="gauge-fill ${cls}" id="gauge-fill"
              cx="45" cy="45" r="${radius}"
              stroke-dasharray="${circ2}"
              stroke-dashoffset="${circ2}"/>
          </svg>
          <div class="score-gauge-center">
          </div>
        </div>
        ${scoreRight}
      </div>`;
  }

  function animateGauge(total) {
    const fill = document.getElementById('gauge-fill');
    if (!fill || total === null) return;
    const pct    = Math.max(0, Math.min(100, parseFloat(total)));
    const radius = 38;
    const circ   = 2 * Math.PI * radius;
    const offset = circ - (pct / 100) * circ;
    requestAnimationFrame(() => {
      fill.style.strokeDashoffset = offset;
    });
  }

  // ── "Why dropped" summary ─────────────────────────────
  function buildWhySummary(criteria) {
    const dropped = criteria
      .filter(c => c.criterion_id !== 'c08' && c.answer === 'no')
      .slice(0, 3);
    if (!dropped.length) return '';

    const rows = dropped.map(c => {
      const weight = CRITERION_WEIGHTS[c.criterion_id] || 0;
      return `<div class="score-why-item">
        <span class="score-why-crit">${getCriterionTitle(c.criterion_id)}</span>
        <span class="score-why-pts lost">−${weight}</span>
      </div>`;
    }).join('');

    return `<div class="score-why">
      <div class="score-why-title">Почему снижена оценка</div>
      ${rows}
    </div>`;
  }

  // ── Transcript ────────────────────────────────────────
  function renderTranscript(transcript) {
    return transcript.map((msg, i) => {
      const sp    = msg.speaker || 'unknown';
      const spLbl = { operator:'Опер.', client:'Клиент', bot:'Бот', system:'Система' }[sp] || sp;
      return `<div class="msg" data-idx="${i}" id="msg-${i}">
        <span class="msg-idx">${i}</span>
        <span class="msg-speaker speaker-${sp}">${spLbl}</span>
        <div class="msg-body">
          <span class="msg-time">${escHtml(msg.timestamp || '')}</span>
          <span class="msg-text">${escHtml(msg.text || '')}</span>
        </div>
      </div>`;
    }).join('');
  }

  function highlightMsg(idx) {
    document.querySelectorAll('.msg').forEach(m => m.classList.remove('highlighted'));
    const el = document.getElementById('msg-' + idx);
    if (el) { el.classList.add('highlighted'); el.scrollIntoView({ behavior:'smooth', block:'center' }); }
  }

  // ── Criterion card ────────────────────────────────────
  function renderCriterion(c, evalId) {
    const answerCls = `answer-${c.answer}`;
    const weight    = CRITERION_WEIGHTS[c.criterion_id] || 0;
    const pts       = c.points !== null && c.points !== undefined ? parseFloat(c.points) : null;

    // Score bar: pts / weight
    let scoreHtml = '';
    if (c.criterion_id !== 'c08' && weight > 0) {
      const ratio     = pts !== null ? pts / weight : 0;
      const barCls    = ratio >= .75 ? 'high' : ratio >= .4 ? 'mid' : 'low';
      const barWidth  = c.answer === 'na' ? 100 : Math.round(ratio * 100);
      const barClass  = c.answer === 'na' ? 'na' : barCls;
      const ptsLabel  = pts !== null
        ? `<span class="pts-num">${pts % 1 === 0 ? pts.toFixed(0) : pts.toFixed(1)}</span> / ${weight}`
        : `N/A`;
      scoreHtml = `<div class="criterion-score">
        <div class="criterion-score-bar">
          <div class="criterion-score-fill ${barClass}" style="width:${barWidth}%"></div>
        </div>
        <span class="criterion-score-label">${ptsLabel}</span>
      </div>`;
    }

    const evidenceHtml = (c.evidence || []).length
      ? `<div class="evidence-list">${(c.evidence).map(e =>
          `<div class="evidence-item" data-idx="${e.msg_index}">
            <span class="evidence-idx">[${e.msg_index}]</span>
            <span class="evidence-quote">${escHtml(e.quote || '')}</span>
          </div>`).join('')}
        </div>`
      : '';

    const isGross = c.criterion_id === 'c08' && c.answer === 'yes';
    const isNo    = c.answer === 'no' && c.criterion_id !== 'c08';

    return `<div class="criterion-card${isGross ? ' has-gross' : ''}${isNo ? ' has-no' : ''}">
      <div class="criterion-header">
        <span class="criterion-id">${c.criterion_id}</span>
        <span class="criterion-title">${getCriterionTitle(c.criterion_id)}</span>
        <span class="criterion-answer ${answerCls}">${answerLabel(c.answer)}</span>
      </div>
      ${scoreHtml}
      <div class="criterion-explanation">${escHtml(c.explanation || '')}</div>
      ${evidenceHtml}
      <button class="appeal-btn" data-eval="${evalId}" data-crit="${c.criterion_id}">
        Оспорить
      </button>
    </div>`;
  }

  // ── Render evaluation ─────────────────────────────────
  function renderEvaluation(ev) {
    const gaugeWrap   = document.getElementById('gauge-wrap');
    const whyWrap     = document.getElementById('why-wrap');
    const resultsBody = document.getElementById('results-body');
    if (!gaugeWrap || !resultsBody) return;

    const totalNum = ev.total !== null && ev.total !== undefined
      ? parseFloat(ev.total) : null;
    const criteria = (ev.criteria || []).map(c => ({ ...c, evaluation_id: ev.id }));

    gaugeWrap.innerHTML = buildGauge(totalNum, ev.gross_error);
    if (whyWrap) whyWrap.innerHTML = buildWhySummary(criteria);

    resultsBody.innerHTML = criteria.map(c => renderCriterion(c, ev.id)).join('');

    // Swap header button to re-evaluate ghost variant
    const evalBtn = document.getElementById('eval-btn');
    if (evalBtn) {
      evalBtn.className = 'btn btn-ghost btn-sm';
      evalBtn.textContent = 'Переоценить';
    }

    // Animate gauge after paint
    setTimeout(() => animateGauge(totalNum), 60);

    // Evidence → highlight
    resultsBody.querySelectorAll('.evidence-item').forEach(el =>
      el.addEventListener('click', () => highlightMsg(parseInt(el.dataset.idx)))
    );

    // Appeal buttons
    resultsBody.querySelectorAll('.appeal-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const comment = prompt(`Апелляция по критерию ${btn.dataset.crit}.\nОпишите причину:`);
        if (!comment) return;
        try {
          await window.appApi('/api/appeals', {
            method: 'POST',
            body: JSON.stringify({
              evaluation_id: parseInt(btn.dataset.eval),
              criterion_id: btn.dataset.crit,
              comment,
            }),
          });
          btn.textContent = 'Отправлено';
          btn.disabled = true;
          btn.style.color = 'var(--brand-light)';
        } catch (e) {
          alert('Ошибка: ' + e.message);
        }
      });
    });
  }

  // ── Evaluate ──────────────────────────────────────────
  async function evaluateConv(convId) {
    const btn = document.getElementById('eval-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Анализ…'; }
    try {
      const result = await window.appApi('/api/evaluations', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: convId }),
      });
      renderEvaluation(result);
      window.refreshConversations?.();
      window.refreshStats?.();
    } catch (e) {
      alert('Ошибка оценки: ' + e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Оценить диалог'; }
    }
  }

  // ── Open conversation ─────────────────────────────────
  async function openConversation(convId) {
    currentConvId = convId;

    document.getElementById('empty-state')?.classList.add('hidden');
    const card = document.getElementById('conv-card');
    card?.classList.remove('hidden');

    // Scroll main window to top so the right panel is immediately visible
    window.scrollTo({ top: 0, behavior: 'smooth' });

    card.innerHTML = `
      <div class="transcript-panel">
        <div class="transcript-header">
          <h3>Транскрипт <span class="text-muted" style="font-weight:400;font-size:11px">${convId}</span></h3>
        </div>
        <div class="transcript-body" id="transcript-body">
          <div class="list-loading">Загрузка…</div>
        </div>
      </div>
      <div class="results-panel">
        <div id="gauge-wrap"></div>
        <div id="why-wrap"></div>
        <div class="results-criteria-header">
          <span class="criteria-label">Критерии</span>
          <button class="btn btn-primary btn-sm" id="eval-btn">Оценить диалог</button>
        </div>
        <div class="results-body" id="results-body">
          <div class="list-loading">Нет оценки</div>
        </div>
      </div>`;

    document.getElementById('eval-btn')?.addEventListener('click', () => evaluateConv(convId));

    try {
      const [conv, evals] = await Promise.all([
        window.appApi('/api/conversations/' + convId),
        window.appApi('/api/conversations/' + convId + '/evaluations'),
      ]);

      document.getElementById('transcript-body').innerHTML =
        renderTranscript(conv.transcript || []);

      if (evals?.length > 0 && evals[0].status === 'done') {
        const full = await window.appApi('/api/evaluations/' + evals[0].id);
        renderEvaluation(full);
      }
    } catch (e) {
      const tb = document.getElementById('transcript-body');
      if (tb) tb.innerHTML = `<div class="list-loading" style="color:var(--danger)">${e.message}</div>`;
    }
  }

  window.openConversation = openConversation;
})();
