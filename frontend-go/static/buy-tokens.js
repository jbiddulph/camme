(function () {
  const TOKEN_KEY = 'camme_access_token';
  const API_BASE = window.CAMME_API_BASE || '/api/v1';

  const buyGate = document.getElementById('buyGate');
  const buyDisabled = document.getElementById('buyDisabled');
  const buyError = document.getElementById('buyError');
  const buySuccess = document.getElementById('buySuccess');
  const buyPackages = document.getElementById('buyPackages');
  const buyCustomSection = document.getElementById('buyCustomSection');
  const customRateHint = document.getElementById('customRateHint');
  const customTokensInput = document.getElementById('customTokensInput');
  const customPriceDisplay = document.getElementById('customPriceDisplay');
  const btnCustomCheckout = document.getElementById('btnCustomCheckout');

  const params = new URLSearchParams(window.location.search);
  if (params.get('paid') === '1' && buySuccess) {
    buySuccess.hidden = false;
  }

  function fmtMajorFromPence(pence, currency) {
    const n = Number(pence) / 100;
    const cur = (currency || 'gbp').toUpperCase();
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur }).format(n);
    } catch (_) {
      return cur + ' ' + n.toFixed(2);
    }
  }

  function fmtMajor(unitAmount, currency) {
    return fmtMajorFromPence(unitAmount, currency);
  }

  function formatDetail(payload, fallback) {
    const d = payload && payload.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      return d
        .map((x) => (typeof x === 'object' && x.msg ? x.msg : JSON.stringify(x)))
        .join('; ');
    }
    return fallback || 'Request failed';
  }

  async function postCheckout(token, body) {
    const res = await fetch(`${API_BASE}/payments/stripe/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch (_) {
      payload = {};
    }
    if (!res.ok) {
      return { ok: false, detail: formatDetail(payload, text.slice(0, 240)) };
    }
    if (payload.url) {
      window.location.href = payload.url;
      return { ok: true };
    }
    return { ok: false, detail: 'No checkout URL returned' };
  }

  function setupCustomPurchase(data, token) {
    const cp = data.custom_purchase;
    if (!cp || !buyCustomSection || !customTokensInput || !customPriceDisplay || !btnCustomCheckout) return;

    const gbp = Number(cp.gbp_per_token);
    const minT = Number(cp.min_tokens) || 1;
    const maxT = Number(cp.max_tokens) || 50000;
    const cur = cp.currency || 'gbp';

    buyCustomSection.hidden = false;
    if (customRateHint) {
      customRateHint.textContent =
        'About ' +
        fmtMajorFromPence(Math.round(gbp * 100), cur) +
        ' per token. Minimum ' +
        minT +
        ' tokens (card minimum charge).';
    }
    customTokensInput.min = String(minT);
    customTokensInput.max = String(maxT);
    customTokensInput.value = String(minT);

    function updateCustomPrice() {
      let n = parseInt(customTokensInput.value, 10);
      if (!Number.isFinite(n)) {
        customPriceDisplay.textContent = '—';
        return;
      }
      n = Math.min(maxT, Math.max(minT, n));
      const pence = Math.round(n * gbp * 100);
      customPriceDisplay.textContent = fmtMajorFromPence(pence, cur);
    }

    customTokensInput.addEventListener('input', updateCustomPrice);
    updateCustomPrice();

    btnCustomCheckout.addEventListener('click', async () => {
      if (buyError) {
        buyError.textContent = '';
        buyError.hidden = true;
      }
      let n = parseInt(customTokensInput.value, 10);
      if (!Number.isFinite(n) || n < minT || n > maxT) {
        if (buyError) {
          buyError.textContent = 'Enter a valid number of tokens between ' + minT + ' and ' + maxT + '.';
          buyError.hidden = false;
        }
        return;
      }
      btnCustomCheckout.disabled = true;
      const result = await postCheckout(token, { custom_tokens: n });
      btnCustomCheckout.disabled = false;
      if (!result.ok && buyError) {
        buyError.textContent = result.detail;
        buyError.hidden = false;
      }
    });
  }

  function renderPresetPackages(data, token) {
    const packages = Array.isArray(data.packages) ? data.packages : [];
    if (!buyPackages || !packages.length) {
      if (buyError) {
        buyError.textContent = 'No packages configured';
        buyError.hidden = false;
      }
      return;
    }

    buyPackages.innerHTML = '';
    for (const p of packages) {
      const card = document.createElement('div');
      card.className = 'card buy-package-card';
      const price = fmtMajor(p.unit_amount, p.currency);
      card.innerHTML =
        '<h2>' +
        (p.label || p.tokens + ' tokens') +
        '</h2>' +
        '<p class="buy-price">' +
        price +
        '</p>' +
        '<p class="hint">' +
        p.tokens +
        ' tokens</p>' +
        '<button type="button" class="primary buy-btn" data-package-id="' +
        encodeURIComponent(p.id) +
        '">Pay with card</button>';
      buyPackages.appendChild(card);
    }

    buyPackages.hidden = false;

    buyPackages.querySelectorAll('.buy-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-package-id');
        if (!id) return;
        if (buyError) {
          buyError.textContent = '';
          buyError.hidden = true;
        }
        btn.disabled = true;
        const result = await postCheckout(token, { package_id: id });
        btn.disabled = false;
        if (!result.ok && buyError) {
          buyError.textContent = result.detail;
          buyError.hidden = false;
        }
      });
    });
  }

  async function load() {
    const raw = localStorage.getItem(TOKEN_KEY);
    const token = raw ? raw.trim() : '';
    if (!token) {
      if (buyGate) buyGate.hidden = false;
      return;
    }

    let data;
    try {
      const res = await fetch(`${API_BASE}/payments/stripe/packages`);
      const text = await res.text();
      if (!res.ok) {
        if (buyError) {
          buyError.textContent = 'Could not load packages';
          buyError.hidden = false;
        }
        return;
      }
      data = JSON.parse(text);
    } catch (_) {
      if (buyError) {
        buyError.textContent = 'Network error';
        buyError.hidden = false;
      }
      return;
    }

    if (!data.checkout_enabled) {
      if (buyDisabled) {
        buyDisabled.hidden = false;
        if (data.payments_hint) {
          buyDisabled.textContent = data.payments_hint;
        }
      }
      return;
    }

    setupCustomPurchase(data, token);
    renderPresetPackages(data, token);

    if (params.get('paid') === '1') {
      window.dispatchEvent(new Event('camme-wallet-refresh'));
    }
  }

  load();
})();
