const output = document.getElementById('broadcastResult');
const homeAuthState = document.getElementById('homeAuthState');
const btnStartBroadcastPublic = document.getElementById('btnStartBroadcastPublic');
const btnStartBroadcastPrivate = document.getElementById('btnStartBroadcastPrivate');
const liveBroadcasters = document.getElementById('liveBroadcasters');
const privateShareWrap = document.getElementById('privateShareWrap');
const privateShareLink = document.getElementById('privateShareLink');
const TOKEN_KEY = 'camme_access_token';
const API_BASE = window.CAMME_API_BASE || '/api/v1';

const homeNavDrawer = document.getElementById('homeNavDrawer');
const btnHomeNavToggle = document.getElementById('btnHomeNavToggle');
const drawerHomeLogin = document.getElementById('drawerHomeLogin');
const drawerHomeProfile = document.getElementById('drawerHomeProfile');
const drawerHomeLogout = document.getElementById('drawerHomeLogout');

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

wireHomeDrawerCloseHandlers();

if (btnHomeNavToggle && homeNavDrawer) {
  btnHomeNavToggle.addEventListener('click', () => setHomeDrawerOpen(!!homeNavDrawer.hidden));
}

const drawerHomeAuthStatus = document.getElementById('drawerHomeAuthStatus');

document.body.addEventListener('click', (e) => {
  const link = e.target.closest('a.js-home-logout');
  if (!link) return;
  e.preventDefault();
  localStorage.removeItem(TOKEN_KEY);
  renderHomeAuthState();
});

function renderHomeAuthState() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    const headerHtml = 'Logged in · <a href="#" class="js-home-logout">Log out</a>';
    if (homeAuthState) homeAuthState.innerHTML = headerHtml;
    if (drawerHomeAuthStatus) {
      drawerHomeAuthStatus.innerHTML =
        '<strong>Status</strong>' + headerHtml;
    }
    if (drawerHomeLogin) drawerHomeLogin.hidden = true;
    if (drawerHomeProfile) drawerHomeProfile.hidden = false;
    if (drawerHomeLogout) drawerHomeLogout.hidden = false;
    if (btnStartBroadcastPublic) btnStartBroadcastPublic.disabled = false;
    if (btnStartBroadcastPrivate) btnStartBroadcastPrivate.disabled = false;
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
  if (btnStartBroadcastPublic) btnStartBroadcastPublic.disabled = true;
  if (btnStartBroadcastPrivate) btnStartBroadcastPrivate.disabled = true;
}

if (drawerHomeLogout) {
  drawerHomeLogout.addEventListener('click', () => {
    localStorage.removeItem(TOKEN_KEY);
    setHomeDrawerOpen(false);
    renderHomeAuthState();
  });
}

function deriveWsUrl(httpUrl) {
  const u = (httpUrl || '').trim().replace(/\/$/, '');
  if (u.startsWith('https://')) return 'wss://' + u.slice(8);
  if (u.startsWith('http://')) return 'ws://' + u.slice(7);
  return u;
}

function buildLiveURL(room, token, livekitWs, mode) {
  const p = new URLSearchParams();
  p.set('room', room);
  p.set('token', token);
  p.set('livekit', livekitWs);
  p.set('mode', mode);
  return `/live?${p.toString()}`;
}

function authHeaders() {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function startBroadcast(visibility) {
    try {
      if (output) output.textContent = 'Starting broadcast…';
      if (privateShareWrap) privateShareWrap.hidden = true;
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) {
        if (output) output.textContent = 'Please log in first.';
        window.location.assign('/auth');
        return;
      }
      const response = await fetch(`${API_BASE}/broadcast/start?visibility=${encodeURIComponent(visibility)}`, {
        method: 'POST',
        headers: {
          ...authHeaders(),
        },
      });
      const text = await response.text();
      let data = {};
      try {
        data = JSON.parse(text);
      } catch (_) {
        data = { detail: text };
      }
      if (output) output.textContent = JSON.stringify(data, null, 2);
      if (!response.ok) return;
      if (!data.room_name || !data.host_token) {
        if (output) output.textContent += '\n\nInvalid /broadcast/start response (missing room/token).';
        return;
      }
      const wsUrl = data.livekit_ws_url || deriveWsUrl(data.livekit_url);
      if (visibility === 'private' && data.private_share_url && privateShareWrap && privateShareLink) {
        privateShareLink.href = data.private_share_url;
        privateShareLink.textContent = data.private_share_url;
        privateShareWrap.hidden = false;
      }
      const target = buildLiveURL(data.room_name, data.host_token, wsUrl, 'broadcast');
      window.location.assign(target);
    } catch (err) {
      if (output) {
        output.textContent = `Failed to start broadcast: ${err && err.message ? err.message : String(err)}`;
      }
    }
}

if (btnStartBroadcastPublic) {
  btnStartBroadcastPublic.addEventListener('click', () => startBroadcast('public'));
}

if (btnStartBroadcastPrivate) {
  btnStartBroadcastPrivate.addEventListener('click', () => startBroadcast('private'));
}

async function loadLiveBroadcasters() {
  if (!liveBroadcasters) return;
  liveBroadcasters.textContent = 'Loading…';
  const response = await fetch(`${API_BASE}/broadcast/live`);
  const ct = response.headers.get('content-type') || '';
  const text = await response.text();
  let payload = {};
  if (ct.includes('application/json')) {
    try {
      payload = JSON.parse(text);
    } catch (_) {
      liveBroadcasters.innerHTML =
        '<p class="error">Live list API returned invalid JSON. Check Heroku <code>BACKEND_BASE_URL</code> and API logs.</p>';
      return;
    }
  } else {
    liveBroadcasters.innerHTML =
      '<p class="error">Live list got HTML instead of JSON (status ' +
        response.status +
        '). On Heroku, set <strong>BACKEND_BASE_URL</strong> on the <strong>web</strong> app to your API URL, e.g. <code>https://camme-api-….herokuapp.com</code>, then <code>heroku ps:restart -a camme-web</code>.</p>';
    return;
  }
  const items = Array.isArray(payload.items) ? payload.items : [];
  if (!items.length) {
    liveBroadcasters.innerHTML = '<p class="hint">No one live right now.</p>';
    return;
  }
  liveBroadcasters.innerHTML = items
    .map((item) => {
      const img = item.thumbnail_data_url
        ? `<img src="${item.thumbnail_data_url}" alt="${item.display_name}" style="width:240px;height:135px;object-fit:cover;border-radius:8px;border:1px solid #30363d;">`
        : '<div style="width:240px;height:135px;display:flex;align-items:center;justify-content:center;background:#111827;border-radius:8px;border:1px solid #30363d;">No preview yet</div>';
      const watch = `/watch?room=${encodeURIComponent(item.room_name)}`;
      const viewers = Number.isFinite(item.viewer_count) ? item.viewer_count : 0;
      return `<div class="broadcaster-card">${img}<p><strong>${item.display_name}</strong></p><p class="hint">Viewers: ${viewers}</p><p><a href="${watch}">Watch live</a></p></div>`;
    })
    .join('');
}

renderHomeAuthState();
loadLiveBroadcasters().catch((err) => {
  if (liveBroadcasters) liveBroadcasters.textContent = `Could not load live broadcasters: ${err}`;
});
