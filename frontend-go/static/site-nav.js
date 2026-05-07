/**
 * Shared mobile drawer + auth line for pages that do not load app.js (home).
 */
(function () {
  const TOKEN_KEY = 'camme_access_token';

  const homeNavDrawer = document.getElementById('homeNavDrawer');
  const btnHomeNavToggle = document.getElementById('btnHomeNavToggle');
  const drawerHomeLogin = document.getElementById('drawerHomeLogin');
  const drawerHomeProfile = document.getElementById('drawerHomeProfile');
  const drawerHomeLogout = document.getElementById('drawerHomeLogout');
  const drawerHomeAuthStatus = document.getElementById('drawerHomeAuthStatus');
  const homeAuthState = document.getElementById('homeAuthState');
  const headerLoginLink = document.getElementById('headerLoginLink');
  const headerProfileLink = document.getElementById('headerProfileLink');
  const headerProfileSep = document.getElementById('headerProfileSep');
  const headerLogoutBtn = document.getElementById('headerLogoutBtn');
  const API_BASE = window.CAMME_API_BASE || '/api/v1';

  function setHomeDrawerOpen(open) {
    if (!homeNavDrawer || !btnHomeNavToggle) return;
    homeNavDrawer.hidden = !open;
    btnHomeNavToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    document.body.style.overflow = open ? 'hidden' : '';
  }

  function wireHomeDrawerCloseHandlers() {
    if (!homeNavDrawer) return;
    homeNavDrawer.querySelectorAll('[data-close-drawer]').forEach((el) => {
      el.addEventListener('click', () => setHomeDrawerOpen(false));
    });
  }

  async function fetchUserName(token) {
    try {
      const res = await fetch(`${API_BASE}/users/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('unauthorized');
      const me = await res.json();
      return (me && me.username) || 'User';
    } catch (_) {
      return null;
    }
  }

  async function renderNavAuthState() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      const username = await fetchUserName(token.trim());
      if (!username) {
        localStorage.removeItem(TOKEN_KEY);
        return renderNavAuthState();
      }
      const headerHtml = `Signed in as <strong>${username}</strong>`;
      if (homeAuthState) homeAuthState.innerHTML = headerHtml;
      if (drawerHomeAuthStatus) {
        drawerHomeAuthStatus.innerHTML = '<strong>Status</strong>' + headerHtml;
      }
      if (drawerHomeLogin) drawerHomeLogin.hidden = true;
      if (drawerHomeProfile) drawerHomeProfile.hidden = false;
      if (drawerHomeLogout) drawerHomeLogout.hidden = false;
      if (headerLoginLink) headerLoginLink.hidden = true;
      if (headerProfileLink) headerProfileLink.hidden = false;
      if (headerProfileSep) headerProfileSep.hidden = false;
      if (headerLogoutBtn) headerLogoutBtn.hidden = false;
    } else {
      const guestHtml = 'Not signed in · <a href="/auth">Sign in</a>';
      if (homeAuthState) homeAuthState.innerHTML = guestHtml;
      if (drawerHomeAuthStatus) {
        drawerHomeAuthStatus.innerHTML = '<strong>Status</strong>' + guestHtml;
      }
      if (drawerHomeLogin) drawerHomeLogin.hidden = false;
      if (drawerHomeProfile) drawerHomeProfile.hidden = true;
      if (drawerHomeLogout) drawerHomeLogout.hidden = true;
      if (headerLoginLink) headerLoginLink.hidden = false;
      if (headerProfileLink) headerProfileLink.hidden = true;
      if (headerProfileSep) headerProfileSep.hidden = true;
      if (headerLogoutBtn) headerLogoutBtn.hidden = true;
    }
    window.dispatchEvent(new Event('camme-wallet-refresh'));
  }

  document.body.addEventListener('click', (e) => {
    const link = e.target.closest('a.js-home-logout');
    if (!link) return;
    e.preventDefault();
    localStorage.removeItem(TOKEN_KEY);
    renderNavAuthState();
  });

  wireHomeDrawerCloseHandlers();

  if (btnHomeNavToggle && homeNavDrawer) {
    btnHomeNavToggle.addEventListener('click', () => setHomeDrawerOpen(!!homeNavDrawer.hidden));
  }

  if (drawerHomeLogout) {
    drawerHomeLogout.addEventListener('click', () => {
      localStorage.removeItem(TOKEN_KEY);
      setHomeDrawerOpen(false);
      renderNavAuthState();
    });
  }

  if (headerLogoutBtn) {
    headerLogoutBtn.addEventListener('click', () => {
      localStorage.removeItem(TOKEN_KEY);
      renderNavAuthState();
    });
  }

  renderNavAuthState();
})();
