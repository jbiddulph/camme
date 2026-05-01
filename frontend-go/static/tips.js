(function () {
  const TOKEN_KEY = 'camme_access_token';
  const API_BASE = window.CAMME_API_BASE || '/api/v1';

  const tipsGate = document.getElementById('tipsGate');
  const tipsError = document.getElementById('tipsError');
  const tipsSummary = document.getElementById('tipsSummary');
  const tipsTableSection = document.getElementById('tipsTableSection');
  const tipsTableBody = document.getElementById('tipsTableBody');
  const tipsEmpty = document.getElementById('tipsEmpty');
  const sumTokenVal = document.getElementById('sumTokenVal');
  const sumTokens = document.getElementById('sumTokens');
  const sumGbp = document.getElementById('sumGbp');
  const sumThreshold = document.getElementById('sumThreshold');
  const sumUntil = document.getElementById('sumUntil');
  const sumEligible = document.getElementById('sumEligible');
  const tipsProgressBar = document.getElementById('tipsProgressBar');

  function fmtIso(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toISOString().replace('T', ' ').slice(0, 19);
  }

  function fmtMoney(n) {
    return '£' + Number(n).toFixed(2);
  }

  async function load() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      if (tipsGate) tipsGate.hidden = false;
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/tips/earnings`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const text = await res.text();
      if (!res.ok) {
        let detail = text;
        try {
          const j = JSON.parse(text);
          detail = j.detail || text;
        } catch (_) {
          /* ignore */
        }
        if (tipsError) {
          tipsError.textContent = typeof detail === 'string' ? detail : 'Could not load tips';
          tipsError.hidden = false;
        }
        return;
      }
      const data = JSON.parse(text);
      const tokenVal = Number(data.token_value_gbp);
      const threshold = Number(data.payout_minimum_gbp);
      const earned = Number(data.total_earned_gbp);
      const pct = threshold > 0 ? Math.min(100, (earned / threshold) * 100) : 0;

      if (sumTokenVal) sumTokenVal.textContent = fmtMoney(tokenVal) + ' per tip token';
      if (sumTokens) sumTokens.textContent = String(data.total_tokens_received ?? 0);
      if (sumGbp) sumGbp.textContent = fmtMoney(data.total_earned_gbp);
      if (sumThreshold) sumThreshold.textContent = fmtMoney(data.payout_minimum_gbp);
      if (sumUntil) sumUntil.textContent = fmtMoney(data.until_payout_gbp);
      if (sumEligible) sumEligible.hidden = !data.payout_eligible;
      if (tipsProgressBar) tipsProgressBar.style.width = pct.toFixed(1) + '%';

      if (tipsSummary) tipsSummary.hidden = false;

      const tips = Array.isArray(data.tips) ? data.tips : [];
      if (tipsTableBody) tipsTableBody.innerHTML = '';
      if (!tips.length) {
        if (tipsEmpty) tipsEmpty.hidden = false;
      } else {
        if (tipsEmpty) tipsEmpty.hidden = true;
        for (const t of tips) {
          const gbp = (Number(t.amount) || 0) * tokenVal;
          const tr = document.createElement('tr');
          tr.innerHTML =
            '<td>' +
            fmtIso(t.created_at_iso) +
            '</td><td>' +
            (t.from_display_name || '—') +
            '</td><td>' +
            t.amount +
            '</td><td>' +
            fmtMoney(gbp) +
            '</td><td>' +
            (t.room_name || '—') +
            '</td>';
          tipsTableBody.appendChild(tr);
        }
      }
      if (tipsTableSection) tipsTableSection.hidden = false;
    } catch (e) {
      if (tipsError) {
        tipsError.textContent = 'Network error';
        tipsError.hidden = false;
      }
    }
  }

  load();
})();
