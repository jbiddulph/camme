/**
 * Site-wide tipping wallet (viewer token_balance). Broadcasters see £ on /tips — separate balance.
 */
(function () {
  const TOKEN_KEY = 'camme_access_token';
  const API_BASE = window.CAMME_API_BASE || '/api/v1';

  const strip = document.getElementById('navWalletStrip');
  const balEl = document.getElementById('navWalletBalance');
  const drawerLine = document.getElementById('drawerWalletLine');
  const drawerBal = document.getElementById('drawerWalletBalance');

  function setBalanceText(v) {
    const s = v == null || v === '' ? '—' : String(v);
    if (balEl) balEl.textContent = s;
    if (drawerBal) drawerBal.textContent = s;
  }

  function hideStrip() {
    setBalanceText(null);
    if (strip) strip.hidden = true;
    if (drawerLine) drawerLine.hidden = true;
  }

  function showStrip(balance) {
    setBalanceText(balance);
    if (strip) strip.hidden = false;
    if (drawerLine) drawerLine.hidden = false;
  }

  async function refreshWalletHeader(evt) {
    const token = localStorage.getItem(TOKEN_KEY);
    const trimmed = token ? token.trim() : '';
    if (!trimmed) {
      hideStrip();
      return;
    }

    const d = evt && evt.detail;
    if (d && Object.prototype.hasOwnProperty.call(d, 'balance')) {
      showStrip(d.balance);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/users/me`, {
        headers: { Authorization: 'Bearer ' + trimmed },
      });
      if (!res.ok) throw new Error('me');
      const u = await res.json();
      showStrip(u.token_balance);
    } catch (_) {
      hideStrip();
    }
  }

  window.CammeRefreshWalletHeader = function () {
    return refreshWalletHeader();
  };

  window.addEventListener('camme-wallet-refresh', (e) => {
    void refreshWalletHeader(e);
  });
})();
