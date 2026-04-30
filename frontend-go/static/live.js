(function () {
  const params = new URLSearchParams(window.location.search);
  const roomName = params.get('room');
  const token = params.get('token');
  const wsUrlRaw = params.get('livekit');
  const mode = (params.get('mode') || 'watch').toLowerCase();

  const statusEl = document.getElementById('liveStatus');
  const viewerCountEl = document.getElementById('viewerCount');
  const errorEl = document.getElementById('liveError');
  const diagEl = document.getElementById('liveDiag');
  const gridEl = document.getElementById('videoGrid');
  const btnLeave = document.getElementById('btnLeave');
  const btnToggleMic = document.getElementById('btnToggleMic');
  const btnToggleCam = document.getElementById('btnToggleCam');
  const broadcastPanel = document.getElementById('broadcastPanel');
  const btnStartBroadcast = document.getElementById('btnStartBroadcast');
  const btnRawMedia = document.getElementById('btnRawMedia');
  const rawWrap = document.getElementById('rawWrap');
  const rawPreview = document.getElementById('rawPreview');
  const rawStatus = document.getElementById('rawStatus');
  const step2Wrap = document.getElementById('step2Wrap');
  const chatMessagesEl = document.getElementById('chatMessages');
  const chatForm = document.getElementById('chatForm');
  const chatInput = document.getElementById('chatInput');
  const chatHint = document.getElementById('chatHint');
  const participantListEl = document.getElementById('participantList');
  const btnHelp = document.getElementById('btnHelp');
  const btnCloseHelp = document.getElementById('btnCloseHelp');
  const helpModal = document.getElementById('helpModal');
  const liveBadge = document.getElementById('liveBadge');
  const postBroadcastModal = document.getElementById('postBroadcastModal');
  const btnClosePostBroadcast = document.getElementById('btnClosePostBroadcast');
  const btnSaveChatTranscript = document.getElementById('btnSaveChatTranscript');
  const btnDeleteAllChat = document.getElementById('btnDeleteAllChat');
  const postBroadcastStatus = document.getElementById('postBroadcastStatus');

  const LK = window.LivekitClient;
  const TOKEN_KEY = 'camme_access_token';
  const API_BASE = window.CAMME_API_BASE || '/api/v1';

  /** @type {MediaStream | null} */
  let rawStream = null;
  let heartbeatTimer = null;
  let chatPollTimer = null;
  let lastViewerCount = 0;
  let lastChatId = 0;
  let hasBroadcasted = false;

  function jwtPayload(jwt) {
    const parts = String(jwt).split('.');
    if (parts.length < 2) return null;
    let b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const pad = b64.length % 4;
    if (pad) b64 += '='.repeat(4 - pad);
    try {
      const json = atob(b64);
      return JSON.parse(json);
    } catch (_) {
      return null;
    }
  }

  function tokenAllowsPublish(jwt) {
    const p = jwtPayload(jwt);
    if (!p) return false;
    if (typeof p.sub === 'string' && p.sub.startsWith('host:')) return true;
    if (p.video && p.video.canPublish === true) return true;
    return false;
  }

  /** Host / broadcast URL — Step 2 is relevant */
  const wantsPublish = mode === 'broadcast' || tokenAllowsPublish(token);

  function trimSurroundingQuotes(s) {
    let v = String(s || '').trim();
    while (v.length >= 2) {
      const first = v[0];
      const last = v[v.length - 1];
      if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
        v = v.slice(1, -1).trim();
        continue;
      }
      break;
    }
    return v;
  }

  function normalizeWsUrl(input) {
    let v = trimSurroundingQuotes(input).replace(/\/+$/, '');
    if (!v) return '';
    if (v.startsWith('https://')) return 'wss://' + v.slice('https://'.length);
    if (v.startsWith('http://')) return 'ws://' + v.slice('http://'.length);
    return v;
  }

  const wsUrl = normalizeWsUrl(wsUrlRaw);
  if (!roomName || !token || !wsUrl) {
    showError('Missing query parameters: room, token, and livekit (WebSocket URL) are required.');
    return;
  }

  function showDiag(lines) {
    if (!diagEl) return;
    diagEl.textContent = lines.join('\n');
    diagEl.hidden = false;
  }

  const host = window.location.hostname;
  const diagLines = [
    'hostname=' + host,
    'window.isSecureContext=' + window.isSecureContext,
    'location=' + window.location.href.split('?')[0],
    'mode=' + mode + ' wantsPublish(step2)=' + wantsPublish,
    'livekit_ws=' + wsUrl,
    'navigator.mediaDevices=' + !!navigator.mediaDevices,
    'ua=' + String(navigator.userAgent).slice(0, 200),
  ];

  if (host !== 'localhost' && host !== '127.0.0.1') {
    diagLines.push('NOTE: Camera APIs work best on http://localhost:8080 or http://127.0.0.1:8080');
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = false;
    statusEl.textContent = 'Error';
    if (btnStartBroadcast) btnStartBroadcast.disabled = true;
  }

  function clearError() {
    errorEl.hidden = true;
    errorEl.textContent = '';
  }

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function setLiveBadgeVisible(visible) {
    if (!liveBadge) return;
    liveBadge.hidden = !visible;
  }

  function setPostBroadcastStatus(text) {
    if (!postBroadcastStatus) return;
    postBroadcastStatus.textContent = text;
  }

  function formatTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function renderChatMessage(item) {
    if (!chatMessagesEl) return;
    const wrap = document.createElement('div');
    wrap.className = 'chat-item';
    const meta = document.createElement('div');
    meta.className = 'chat-meta';
    meta.textContent = `${item.display_name} • ${formatTime(item.created_at_iso)}`;
    const body = document.createElement('div');
    body.className = 'chat-body';
    body.textContent = item.body;
    wrap.appendChild(meta);
    wrap.appendChild(body);
    chatMessagesEl.appendChild(wrap);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  }

  async function loadChatMessages() {
    if (!chatMessagesEl) return;
    const res = await fetch(`${API_BASE}/chat/messages?room=${encodeURIComponent(roomName)}&limit=150`);
    if (!res.ok) return;
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const newItems = items.filter((i) => Number(i.id) > lastChatId);
    if (!lastChatId) {
      chatMessagesEl.innerHTML = '';
      items.forEach(renderChatMessage);
      if (items.length) lastChatId = Number(items[items.length - 1].id || 0);
      return;
    }
    newItems.forEach(renderChatMessage);
    if (newItems.length) lastChatId = Number(newItems[newItems.length - 1].id || lastChatId);
  }

  function startChatPolling() {
    stopChatPolling();
    loadChatMessages().catch(() => {});
    chatPollTimer = setInterval(() => {
      loadChatMessages().catch(() => {});
    }, 3000);
  }

  function stopChatPolling() {
    if (chatPollTimer) {
      clearInterval(chatPollTimer);
      chatPollTimer = null;
    }
  }

  function computeViewerCount() {
    const participants = [room.localParticipant, ...Array.from(room.remoteParticipants.values())];
    const viewerParticipants = participants.filter((p) => p && !String(p.identity || '').startsWith('host:'));
    return viewerParticipants.length;
  }

  function updateViewerCountUI() {
    const count = computeViewerCount();
    lastViewerCount = count;
    if (viewerCountEl) viewerCountEl.textContent = `Viewers: ${count}`;
  }

  if (step2Wrap) step2Wrap.hidden = !wantsPublish;
  setLiveBadgeVisible(false);

  if (btnHelp && helpModal) {
    btnHelp.addEventListener('click', () => {
      helpModal.hidden = false;
    });
  }
  if (btnCloseHelp && helpModal) {
    btnCloseHelp.addEventListener('click', () => {
      helpModal.hidden = true;
    });
  }
  if (helpModal) {
    helpModal.addEventListener('click', (e) => {
      if (e.target === helpModal) helpModal.hidden = true;
    });
  }
  if (btnClosePostBroadcast && postBroadcastModal) {
    btnClosePostBroadcast.addEventListener('click', () => {
      postBroadcastModal.hidden = true;
      setPostBroadcastStatus('');
    });
  }
  if (postBroadcastModal) {
    postBroadcastModal.addEventListener('click', (e) => {
      if (e.target === postBroadcastModal) {
        postBroadcastModal.hidden = true;
        setPostBroadcastStatus('');
      }
    });
  }

  if (typeof LK !== 'undefined' && LK && typeof LK.isBrowserSupported === 'function') {
    try {
      diagLines.push('LiveKit isBrowserSupported=' + LK.isBrowserSupported());
    } catch (e) {
      diagLines.push('LiveKit isBrowserSupported=(error: ' + e + ')');
    }
  } else {
    diagLines.push('LiveKit=NOT_LOADED');
  }
  showDiag(diagLines);

  (async function permissionDiag() {
    if (!navigator.permissions || !navigator.permissions.query) {
      diagLines.push('Permissions API: unavailable in this browser');
      showDiag(diagLines);
      return;
    }
    for (const name of ['camera', 'microphone']) {
      try {
        const r = await navigator.permissions.query({ name });
        diagLines.push('permission.' + name + '=' + r.state);
      } catch (_) {
        diagLines.push('permission.' + name + '=query-not-supported');
      }
    }
    showDiag(diagLines);
  })();

  async function stopRawStream() {
    if (rawStream) {
      rawStream.getTracks().forEach((t) => t.stop());
      rawStream = null;
    }
    if (rawPreview) {
      rawPreview.srcObject = null;
    }
  }

  function getUserMediaWithTimeout(constraints, ms) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(new Error('getUserMedia not available'));
    }
    const p = navigator.mediaDevices.getUserMedia(constraints);
    const t = new Promise((_, rej) =>
      setTimeout(() => rej(new Error('Timed out after ' + ms + 'ms — check OS dialog or blocked device')), ms)
    );
    return Promise.race([p, t]);
  }

  if (btnRawMedia) {
    btnRawMedia.addEventListener('click', async () => {
      clearError();
      if (rawStatus) rawStatus.textContent = 'Clicked — calling getUserMedia now…';
      await stopRawStream();
      if (rawWrap) rawWrap.hidden = true;

      if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
        showError(
          'No getUserMedia here. Open this exact URL in Chrome or Safari (normal window), not an IDE embedded browser.'
        );
        return;
      }

      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        diagLines.push('enumerateDevices count=' + devices.length);
        showDiag(diagLines);
      } catch (e) {
        diagLines.push('enumerateDevices error=' + e);
        showDiag(diagLines);
      }

      setStatus('Step 1: waiting on browser / OS for camera+mic…');

      const tryConstraints = [
        { video: { facingMode: 'user' }, audio: true },
        { video: true, audio: true },
        { video: true, audio: false },
      ];

      let lastErr = null;
      for (const constraints of tryConstraints) {
        try {
          rawStream = await getUserMediaWithTimeout(constraints, 30000);
          lastErr = null;
          break;
        } catch (err) {
          lastErr = err;
          console.warn('getUserMedia attempt failed', constraints, err);
        }
      }

      if (!rawStream) {
        console.error(lastErr);
        const name = lastErr && lastErr.name ? lastErr.name : 'Error';
        const msg = lastErr && lastErr.message ? lastErr.message : String(lastErr);
        showError(
          'Step 1 failed (' +
            name +
            '): ' +
            msg +
            ' — Reset site permissions (Chrome: lock → Site settings). macOS: System Settings → Privacy → Camera & Microphone → enable your browser. Close other apps using the camera.'
        );
        if (rawStatus) rawStatus.textContent = '';
        return;
      }

      const vTracks = rawStream.getVideoTracks();
      const aTracks = rawStream.getAudioTracks();
      if (rawStatus) {
        rawStatus.textContent =
          'Stream OK: ' + vTracks.length + ' video track(s), ' + aTracks.length + ' audio track(s). If no green camera light, the OS may still be blocking this browser.';
      }

      if (vTracks.length === 0) {
        showError('getUserMedia returned no video track — check camera hardware / OS privacy / no other app locking the camera.');
        return;
      }

      vTracks.forEach((t) => {
        t.onended = () => {
          if (rawStatus) rawStatus.textContent += ' (video track ended)';
        };
      });

      if (rawPreview) {
        rawPreview.srcObject = rawStream;
        try {
          await rawPreview.play();
        } catch (e) {
          console.warn(e);
        }
      }
      if (rawWrap) rawWrap.hidden = false;
      setStatus('Step 1 OK — then Step 2 when Connected (hosts only)');
    });
  }

  if (!LK) {
    showError('LiveKit script did not load (network/adblock). Step 1 still tests the camera. Fix the script to use Step 2.');
    if (step2Wrap) step2Wrap.hidden = true;
    btnLeave.addEventListener('click', () => {
      stopRawStream();
    });
    return;
  }

  const room = new LK.Room({
    adaptiveStream: true,
    dynacast: true,
    audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true },
  });

  /** @type {Map<string, string>} */
  let viewerLabelBySid = new Map();

  function viewerJoinedAt(p) {
    try {
      if (p.joinedAt && typeof p.joinedAt.getTime === 'function') return p.joinedAt.getTime();
    } catch (_) {
      /* ignore */
    }
    return 0;
  }

  function refreshViewerLabels() {
    const viewers = [];
    for (const p of [room.localParticipant, ...room.remoteParticipants.values()]) {
      if (!p) continue;
      const id = String(p.identity || '');
      if (!id.startsWith('viewer:')) continue;
      viewers.push({ p, t: viewerJoinedAt(p), id });
    }
    viewers.sort((a, b) => a.t - b.t || a.id.localeCompare(b.id));
    const map = new Map();
    viewers.forEach((v, i) => map.set(v.p.sid, `Viewer${i + 1}`));
    viewerLabelBySid = map;
  }

  function participantLabel(participant) {
    const id = String(participant.identity || 'participant');
    if (id.startsWith('host:')) {
      return participant.isLocal ? 'You (Broadcaster)' : 'Broadcaster';
    }
    if (id.startsWith('viewer:')) {
      const tag = viewerLabelBySid.get(participant.sid) || 'Viewer';
      return participant.isLocal ? `You (${tag})` : tag;
    }
    return participant.isLocal ? `You (${id})` : id;
  }

  function renderParticipants() {
    if (!participantListEl) return;
    refreshViewerLabels();
    const list = [room.localParticipant, ...Array.from(room.remoteParticipants.values())]
      .filter(Boolean)
      .map((p) => ({
        sid: p.sid,
        label: participantLabel(p),
      }));
    participantListEl.innerHTML = '';
    list.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item.label;
      participantListEl.appendChild(li);
    });
  }

  function guestChatDisplayName() {
    refreshViewerLabels();
    const lp = room.localParticipant;
    const id = String(lp.identity || '');
    if (id.startsWith('host:')) return 'Broadcaster';
    if (id.startsWith('viewer:')) return viewerLabelBySid.get(lp.sid) || 'Viewer';
    return 'Guest';
  }

  /** @type {Map<string, HTMLElement>} */
  const tiles = new Map();

  function labelForParticipant(participant) {
    refreshViewerLabels();
    return participantLabel(participant);
  }

  function videoTileKey(participant) {
    return `${participant.sid}-video`;
  }

  function attachTrack(track, participant) {
    if (track.kind === LK.Track.Kind.Audio) {
      const el = track.attach();
      el.style.display = 'none';
      document.body.appendChild(el);
      return;
    }

    const key = videoTileKey(participant);
    let tile = tiles.get(key);
    if (!tile) {
      tile = document.createElement('div');
      tile.className = 'video-tile';
      const label = document.createElement('div');
      label.className = 'video-label';
      label.textContent = labelForParticipant(participant);
      const media = document.createElement('div');
      media.className = 'video-media';
      tile.appendChild(label);
      tile.appendChild(media);
      gridEl.appendChild(tile);
      tiles.set(key, tile);
    } else {
      tile.querySelector('.video-label').textContent = labelForParticipant(participant);
    }

    const media = tile.querySelector('.video-media');
    media.innerHTML = '';
    const videoEl = track.attach();
    videoEl.playsInline = true;
    videoEl.autoplay = true;
    videoEl.setAttribute('playsinline', '');
    videoEl.muted = true;
    media.appendChild(videoEl);
    videoEl.play().catch(() => {});
  }

  function detachTrack(track, participant) {
    if (track.kind === LK.Track.Kind.Audio) {
      track.detach().forEach((el) => el.remove());
      return;
    }
    const key = videoTileKey(participant);
    const tile = tiles.get(key);
    if (tile) {
      tile.remove();
      tiles.delete(key);
    } else {
      track.detach();
    }
  }

  room
    .on(LK.RoomEvent.TrackSubscribed, (track, _pub, participant) => {
      attachTrack(track, participant);
    })
    .on(LK.RoomEvent.TrackUnsubscribed, (track, _pub, participant) => {
      detachTrack(track, participant);
    })
    .on(LK.RoomEvent.LocalTrackPublished, (pub) => {
      if (pub.track) attachTrack(pub.track, room.localParticipant);
    })
    .on(LK.RoomEvent.ParticipantConnected, () => {
      updateViewerCountUI();
      renderParticipants();
    })
    .on(LK.RoomEvent.ParticipantDisconnected, () => {
      updateViewerCountUI();
      renderParticipants();
    })
    .on(LK.RoomEvent.MediaDevicesError, (err) => {
      console.error('LiveKit MediaDevicesError', err);
      let detail = err && err.message ? err.message : String(err);
      if (LK.MediaDeviceFailure && typeof LK.MediaDeviceFailure.getFailure === 'function') {
        try {
          detail = LK.MediaDeviceFailure.getFailure(err) + ' — ' + detail;
        } catch (_) {
          /* ignore */
        }
      }
      showError('Camera/microphone error: ' + detail);
    })
    .on(LK.RoomEvent.Disconnected, () => {
      setStatus('Left room');
      updateViewerCountUI();
      renderParticipants();
      btnToggleMic.hidden = true;
      btnToggleCam.hidden = true;
      if (btnStartBroadcast) btnStartBroadcast.disabled = true;
      setLiveBadgeVisible(false);
      stopChatPolling();
    });

  btnLeave.addEventListener('click', () => {
    stopBroadcastHeartbeat();
    stopChatPolling();
    stopRawStream();
    room.disconnect();
    if (wantsPublish && hasBroadcasted && postBroadcastModal) {
      postBroadcastModal.hidden = false;
      setPostBroadcastStatus('');
    }
  });

  let micOn = true;
  let camOn = true;

  btnToggleMic.addEventListener('click', async () => {
    micOn = !micOn;
    await room.localParticipant.setMicrophoneEnabled(micOn);
    btnToggleMic.textContent = micOn ? 'Mute mic' : 'Unmute mic';
  });

  btnToggleCam.addEventListener('click', async () => {
    camOn = !camOn;
    await room.localParticipant.setCameraEnabled(camOn);
    btnToggleCam.textContent = camOn ? 'Stop camera' : 'Start camera';
  });

  async function startBroadcastMediaFromUserGesture() {
    if (!wantsPublish) {
      showError('This link is a viewer token — use the host / broadcast link for Step 2.');
      return;
    }
    clearError();
    setStatus('Publishing to LiveKit…');
    await stopRawStream();
    if (rawWrap) rawWrap.hidden = true;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showError('navigator.mediaDevices missing. Use Chrome/Safari at http://localhost:8080');
      return;
    }

    try {
      if (typeof LK.createLocalTracks === 'function') {
        const tracks = await LK.createLocalTracks({
          audio: true,
          video: true,
        });
        for (const t of tracks) {
          await room.localParticipant.publishTrack(t);
        }
      } else if (typeof room.localParticipant.enableCameraAndMicrophone === 'function') {
        await room.localParticipant.enableCameraAndMicrophone();
      } else {
        await room.localParticipant.setCameraEnabled(true);
        await room.localParticipant.setMicrophoneEnabled(true);
      }

      if (typeof room.startAudio === 'function') {
        await room.startAudio();
      }
    } catch (err) {
      console.error(err);
      const name = err && err.name ? err.name : 'Error';
      const msg = err && err.message ? err.message : String(err);
      showError('Step 2 failed (' + name + '): ' + msg);
      return;
    }

    if (broadcastPanel) broadcastPanel.hidden = true;
    btnToggleMic.hidden = false;
    btnToggleCam.hidden = false;
    setStatus('Broadcasting — preview below');
    setLiveBadgeVisible(true);
    hasBroadcasted = true;

    room.localParticipant.videoTrackPublications.forEach((pub) => {
      if (pub.track) attachTrack(pub.track, room.localParticipant);
    });
    room.localParticipant.audioTrackPublications.forEach((pub) => {
      if (pub.track) attachTrack(pub.track, room.localParticipant);
    });
    startBroadcastHeartbeat();
  }

  if (btnStartBroadcast) {
    btnStartBroadcast.addEventListener('click', () => {
      startBroadcastMediaFromUserGesture();
    });
  }

  async function start() {
    const wsCandidates = Array.from(
      new Set([
        wsUrl,
        'ws://localhost:7880',
        'ws://127.0.0.1:7880',
      ].filter(Boolean))
    );

    let lastErr = null;
    try {
      for (const candidate of wsCandidates) {
        try {
          setStatus(`Connecting to "${roomName}" via ${candidate}…`);
          await room.connect(candidate, token, { autoSubscribe: true });
          lastErr = null;
          break;
        } catch (err) {
          lastErr = err;
          console.warn('LiveKit connect failed', candidate, err);
        }
      }

      if (lastErr) {
        throw lastErr;
      }

      diagLines.push('connectionState=' + (room.connectionState ?? 'n/a'));
      showDiag(diagLines);

      if (wantsPublish) {
        setStatus('Connected — Step 1 (camera test) anytime, then Step 2');
        if (btnStartBroadcast) btnStartBroadcast.disabled = false;
      } else {
        setStatus('Connected · watching (viewer)');
      }
      updateViewerCountUI();
      renderParticipants();
      startChatPolling();

      if (!wantsPublish) {
        room.localParticipant.videoTrackPublications.forEach((pub) => {
          if (pub.track) attachTrack(pub.track, room.localParticipant);
        });
        room.localParticipant.audioTrackPublications.forEach((pub) => {
          if (pub.track) attachTrack(pub.track, room.localParticipant);
        });
      }
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      showError(
        'LiveKit connection failed: ' +
          msg +
          '. Check LiveKit is running and reachable at ws://localhost:7880 (or ws://127.0.0.1:7880).'
      );
    }
  }

  function getAuthHeaders() {
    const token = localStorage.getItem(TOKEN_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function captureLocalPreviewDataURL() {
    const localVideo = gridEl.querySelector('.video-tile video');
    if (!localVideo || !localVideo.videoWidth || !localVideo.videoHeight) return null;
    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 180;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(localVideo, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.7);
  }

  async function sendBroadcastHeartbeat() {
    if (!wantsPublish) return;
    const thumbnail = captureLocalPreviewDataURL();
    await fetch(`${API_BASE}/broadcast/heartbeat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        room_name: roomName,
        thumbnail_data_url: thumbnail,
        viewer_count: lastViewerCount,
      }),
    });
  }

  function startBroadcastHeartbeat() {
    stopBroadcastHeartbeat();
    sendBroadcastHeartbeat().catch((err) => console.warn('heartbeat failed', err));
    heartbeatTimer = setInterval(() => {
      sendBroadcastHeartbeat().catch((err) => console.warn('heartbeat failed', err));
    }, 60 * 1000);
  }

  function stopBroadcastHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    if (!wantsPublish) return;
    fetch(`${API_BASE}/broadcast/stop?room=${encodeURIComponent(roomName)}`, {
      method: 'POST',
      headers: {
        ...getAuthHeaders(),
      },
    }).catch(() => {});
  }

  window.addEventListener('beforeunload', () => {
    stopBroadcastHeartbeat();
    stopChatPolling();
  });

  async function fetchChatForTranscript() {
    const res = await fetch(`${API_BASE}/chat/messages?room=${encodeURIComponent(roomName)}&limit=500`);
    if (!res.ok) throw new Error('Could not load chat for transcript');
    const data = await res.json();
    return Array.isArray(data.items) ? data.items : [];
  }

  function downloadTextFile(filename, content) {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  if (btnSaveChatTranscript) {
    btnSaveChatTranscript.addEventListener('click', async () => {
      try {
        setPostBroadcastStatus('Preparing transcript…');
        const items = await fetchChatForTranscript();
        const lines = items.map((m) => `[${formatTime(m.created_at_iso)}] ${m.display_name}: ${m.body}`);
        const filename = `camme-chat-${roomName}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.txt`;
        downloadTextFile(filename, lines.join('\n'));
        setPostBroadcastStatus('Chat transcript saved.');
      } catch (err) {
        setPostBroadcastStatus('Could not save chat transcript.');
      }
    });
  }

  if (btnDeleteAllChat) {
    btnDeleteAllChat.addEventListener('click', async () => {
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) {
        setPostBroadcastStatus('Sign in as broadcaster to delete chat.');
        return;
      }
      if (!window.confirm('Delete all chat messages for this room? This cannot be undone.')) return;
      try {
        setPostBroadcastStatus('Deleting chat messages…');
        const res = await fetch(`${API_BASE}/chat/messages/delete-all?room=${encodeURIComponent(roomName)}`, {
          method: 'POST',
          headers: {
            ...getAuthHeaders(),
          },
        });
        if (!res.ok) throw new Error('delete failed');
        chatMessagesEl.innerHTML = '';
        lastChatId = 0;
        setPostBroadcastStatus('All chat messages deleted.');
        if (postBroadcastModal) postBroadcastModal.hidden = true;
        setPostBroadcastStatus('');
        if (broadcastPanel) broadcastPanel.hidden = false;
        setStatus('Ready to start a new broadcast.');
      } catch (err) {
        setPostBroadcastStatus('Could not delete chat messages (broadcaster only).');
      }
    });
  }

  if (chatForm && chatInput) {
    chatForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const body = chatInput.value.trim();
      if (!body) return;
      const token = localStorage.getItem(TOKEN_KEY);
      const payload = { room_name: roomName, body };
      /** @type {Record<string, string>} */
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        Object.assign(headers, getAuthHeaders());
      } else {
        const guestName = guestChatDisplayName();
        if (!guestName || guestName === 'Guest') {
          if (chatHint) chatHint.textContent = 'Reconnect to the room to chat as a viewer.';
          return;
        }
        payload.viewer_display_name = guestName;
      }
      const res = await fetch(`${API_BASE}/chat/messages`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        if (chatHint) chatHint.textContent = 'Could not send message.';
        return;
      }
      const item = await res.json();
      renderChatMessage(item);
      lastChatId = Math.max(lastChatId, Number(item.id || 0));
      chatInput.value = '';
      if (chatHint) {
        chatHint.textContent = token
          ? 'Signed-in: messages use your username.'
          : 'Guest: messages use your viewer label (Viewer1, Viewer2, …).';
      }
    });
  }

  start();
})();
