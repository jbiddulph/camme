(function () {
  const TOKEN_KEY = 'camme_access_token';
  const API_BASE = window.CAMME_API_BASE || '/api/v1';

  const gate = document.getElementById('profileGate');
  const errEl = document.getElementById('profileError');
  const form = document.getElementById('profileForm');
  const saveStatus = document.getElementById('profileSaveStatus');
  const tokenBal = document.getElementById('profileTokenBalance');
  const emailEl = document.getElementById('profileEmail');
  const idStatusEl = document.getElementById('profileIdStatus');

  function authToken() {
    return (localStorage.getItem(TOKEN_KEY) || '').trim();
  }

  function setError(msg) {
    if (!errEl) return;
    errEl.hidden = !msg;
    errEl.textContent = msg || '';
  }

  function fillForm(profile) {
    document.getElementById('profileUsername').value = profile.username || '';
    document.getElementById('profileLegalName').value = profile.legal_name || '';
    document.getElementById('profileCountryCode').value = profile.country_code || '';
    document.getElementById('profilePayoutMethod').value = profile.payout_method || '';
    document.getElementById('profilePayoutDestination').value = profile.payout_destination || '';
    if (tokenBal) tokenBal.textContent = String(profile.token_balance ?? '—');
    if (emailEl) emailEl.textContent = profile.email || '—';
    if (idStatusEl) idStatusEl.textContent = profile.id_verification_status || 'pending';
  }

  async function loadProfile() {
    const token = authToken();
    if (!token) {
      window.location.assign('/auth');
      return;
    }
    setError('');
    const res = await fetch(`${API_BASE}/users/me/profile`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      throw new Error('Could not load your profile');
    }
    const data = await res.json();
    fillForm(data);
    if (gate) gate.hidden = true;
  }

  async function saveProfile(e) {
    e.preventDefault();
    const token = authToken();
    if (!token) {
      window.location.assign('/auth');
      return;
    }
    const payload = {
      username: document.getElementById('profileUsername').value.trim(),
      legal_name: document.getElementById('profileLegalName').value.trim() || null,
      country_code: document.getElementById('profileCountryCode').value.trim().toUpperCase() || null,
      payout_method: document.getElementById('profilePayoutMethod').value || null,
      payout_destination: document.getElementById('profilePayoutDestination').value.trim() || null,
    };
    if (saveStatus) saveStatus.textContent = 'Saving…';
    const res = await fetch(`${API_BASE}/users/me/profile`, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    const text = await res.text();
    let data = {};
    try {
      data = JSON.parse(text);
    } catch (_) {}
    if (!res.ok) {
      throw new Error((data && data.detail) || 'Could not save profile');
    }
    fillForm(data);
    if (saveStatus) saveStatus.textContent = 'Saved.';
    window.dispatchEvent(new CustomEvent('camme-wallet-refresh', { detail: { balance: data.token_balance } }));
  }

  if (form) {
    form.addEventListener('submit', (e) => {
      saveProfile(e).catch((err) => {
        if (saveStatus) saveStatus.textContent = '';
        setError(err && err.message ? err.message : String(err));
      });
    });
  }

  loadProfile().catch((err) => {
    if (gate) gate.hidden = true;
    setError(err && err.message ? err.message : String(err));
  });
})();
