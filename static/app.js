(() => {
  // Small DOM/query helpers
  const $ = (id) => document.getElementById(id);
  const text = (id, v) => { const el = $(id); if (el) el.textContent = String(v); };

  // Network helper
  async function postJSON(url, payload) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    return r.json();
  }

  // ===== 20-20-20 リマインダー =====
  let timerId = null;
  let countdownId = null;
  let remaining = 0; // 秒

  function updateTimerText() {
    const el = $('timer');
    if (!el) return;
    if (!timerId) { el.textContent = '未開始'; return; }
    el.textContent = `次の休憩まで: ${Math.max(remaining, 0)}秒`;
  }

  function startReminder() {
    const intervalEl = $('intervalMin');
    const min = parseInt((intervalEl && intervalEl.value) || '20');
    remaining = min * 60;
    if (timerId) clearInterval(timerId);
    if (countdownId) clearInterval(countdownId);
    timerId = setInterval(() => {
      alert('20-20-20休憩: 20秒間、遠く(6m)を見ましょう。');
      const t0 = Date.now();
      const restTicker = setInterval(() => {
        if ((Date.now() - t0) / 1000 >= 20) clearInterval(restTicker);
      }, 1000);
      remaining = min * 60;
    }, min * 60 * 1000);
    countdownId = setInterval(() => { remaining--; updateTimerText(); }, 1000);
    updateTimerText();
  }

  function stopReminder() {
    if (timerId) clearInterval(timerId); timerId = null;
    if (countdownId) clearInterval(countdownId); countdownId = null;
    remaining = 0; updateTimerText();
  }

  $('btnStartTimer')?.addEventListener('click', startReminder);
  $('btnStopTimer')?.addEventListener('click', stopReminder);

  // ===== 交代調節（near-far） =====
  function doNearFar() {
    const el = $('nearfar');
    if (!el) return;
    const DURATION = 120 * 1000; // 2分
    const start = Date.now();

    function tick() {
      const t = Date.now() - start;
      if (t >= DURATION) {
        el.style.filter = 'blur(0px)';
        el.style.transform = 'scale(1)';
        postJSON('/api/log', { kind: 'session', type: 'nearfar', duration_sec: Math.round(DURATION / 1000) }).catch(() => {});
        return;
      }
      if (Math.floor(t / 3000) % 2 === 0) {
        el.style.filter = 'blur(3px)';
        el.style.transform = 'scale(1.15)';
      } else {
        el.style.filter = 'blur(0.5px)';
        el.style.transform = 'scale(1)';
      }
      requestAnimationFrame(tick);
    }
    tick();
  }

  $('btnNearFar')?.addEventListener('click', doNearFar);

  // ===== サッケード =====
  function doSaccade() {
    const target = $('target');
    const stage = $('scStage');
    if (!target || !stage) return;

    const rect = () => stage.getBoundingClientRect();
    let tries = 0, hit = 0;
    text('tries', '0');
    text('hit', '0');

    target.style.display = 'block';
    const DURATION = 60 * 1000 * 2; // 1分×2
    const start = Date.now();

    function placeRandom() {
      const r = rect();
      const margin = 20;
      const x = Math.random() * (r.width - 2 * margin) + margin;
      const y = Math.random() * (r.height - 2 * margin) + margin;
      target.style.left = `${x}px`;
      target.style.top = `${y}px`;
      tries++; text('tries', tries.toString());
    }

    function step() {
      const elapsed = Date.now() - start;
      if (elapsed >= DURATION) {
        target.style.display = 'none';
        postJSON('/api/log', {
          kind: 'session',
          type: 'saccade',
          duration_sec: Math.round(DURATION / 1000),
          meta: JSON.stringify({ tries, hit })
        }).catch(() => {});
        return;
      }
      placeRandom();
      setTimeout(step, 800);
    }

    target.onclick = () => { hit++; text('hit', hit.toString()); };

    step();
  }

  $('btnSaccade')?.addEventListener('click', doSaccade);

  // ===== メトリクス保存 =====
  async function saveMetric() {
    const date = new Date().toISOString().slice(0, 10);
    const payload = {
      kind: 'metric',
      date,
      fatigue_score: parseInt(($('fatigue')?.value) || '3'),
      near_work_min: parseInt(($('nearMin')?.value) || '0'),
      breaks: parseInt(($('breaks')?.value) || '0')
    };
    try {
      const j = await postJSON('/api/log', payload);
      const el = $('saveMsg');
      if (el) {
        el.textContent = j.ok ? '保存しました' : `保存失敗: ${j.error}`;
        setTimeout(() => { el.textContent = ''; }, 2500);
      }
    } catch (e) {
      const el = $('saveMsg');
      if (el) {
        el.textContent = '保存失敗: ネットワークエラー';
        setTimeout(() => { el.textContent = ''; }, 2500);
      }
    }
  }

  $('btnSaveMetric')?.addEventListener('click', saveMetric);

  // ===== CSVエクスポート =====
  $('btnExport')?.addEventListener('click', () => { window.location.href = '/api/export.csv'; });
})();
