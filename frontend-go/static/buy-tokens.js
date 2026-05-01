(function () {
  const TOKEN_KEY = 'camme_access_token';
  const API_BASE = window.CAMME_API_BASE || '/api/v1';

  const buyGate = document.getElementById('buyGate');
  const buyDisabled = document.getElementById('buyDisabled');
  const buyError = document.getElementById('buyError');
  const buySuccess = document.getElementById('buySuccess');
  const buyPackages = document.getElementById('buyPackages');

  const params = new URLSearchParams(window.location.search);
  if (params.get('paid') === '1' && buySuccess) {
    buySuccess.hidden = false;
  }

  function fmtMajor(unitAmount, currency) {
    const n = Number(unitAmount) / 100;
    const cur = (currency || 'gbp').toUpperCase();
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur }).format(n);
    } catch (_) {
      return cur + ' ' + n.toFixed(2);
    }
  }

  async function load() {
    const token = localStorage.getItem(TOKEN_KEY);
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
      if (buyDisabled) buyDisabled.hidden = false;
      return;
    }

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
        try {
          const res = await fetch(`${API_BASE}/payments/stripe/checkout`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: 'Bearer ' + token,
            },
            body: JSON.stringify({ package_id: id }),
          });
          const text = await res.text();
          let payload;
          try {
            payload = JSON.parse(text);
          } catch (_) {
            payload = {};
          }
          if (!res.ok) {
            const detail = typeof payload.detail === 'string' ? payload.detail : text.slice(0, 200);
            if (buyError) {
              buyError.textContent = detail;
              buyError.hidden = false;
            }
            btn.disabled = false;
            return;
          }
          if (payload.url) {
            window.location.href = payload.url;
            return;
          }
          if (buyError) {
            buyError.textContent = 'No checkout URL returned';
            buyError.hidden = false;
          }
        } catch (_) {
          if (buyError) {
            buyError.textContent = 'Network error';
            buyError.hidden = false;
          }
        }
        btn.disabled = false;
      });
    });
  }

  load();
})();
