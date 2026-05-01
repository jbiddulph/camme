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

  function renderNavAuthState() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      const headerHtml = 'Logged in · <a href="#" class="js-home-logout">Log out</a>';
      if (homeAuthState) homeAuthState.innerHTML = headerHtml;
      if (drawerHomeAuthStatus) {
        drawerHomeAuthStatus.innerHTML = '<strong>Status</strong>' + headerHtml;
      }
      if (drawerHomeLogin) drawerHomeLogin.hidden = true;
      if (drawerHomeProfile) drawerHomeProfile.hidden = false;
      if (drawerHomeLogout) drawerHomeLogout.hidden = false;
      return;
    }
    const guestHtml = 'Not signed in · <a href="/auth">Sign in</a>';
    if (homeAuthState) homeAuthState.innerHTML = guestHtml;
    if (drawerHomeAuthStatus) {
      drawerHomeAuthStatus.innerHTML = '<strong>Status</strong>' + guestHtml;
    }
    if (drawerHomeLogin) drawerHomeLogin.hidden = false;
    if (drawerHomeProfile) drawerHomeProfile.hidden = true;
    if (drawerHomeLogout) drawerHomeLogout.hidden = true;
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

  renderNavAuthState();
})();
