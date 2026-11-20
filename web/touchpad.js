// PocketPilot phone app: turns touches into messages for the laptop.
(() => {
  'use strict';

  // ---- tuning -------------------------------------------------------------
  const TAP_MS = 250;         // a touch shorter than this can be a tap
  const TAP_SLOP = 10;         // ...if the fingers moved less than this (px)
  const LONG_MS = 450;         // hold this long without moving to start a drag
  const LONG_SLOP = 8;
  const SCROLL_PER_PX = 0.04;  // wheel notches per pixel of two-finger movement
  const ZOOM_PX = 40;          // pinch distance per zoom step
  const SWIPE_PX = 45;         // three-finger swipe distance (fires while fingers are still down)
  const DOUBLE_MS = 280;       // tap, then touch again within this time = double-tap / tap-and-drag

  const $ = (s) => document.querySelector(s);
  const pad = $('#pad');

  // ---- storage (can fail in private mode, so always wrapped) --------------
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } },
  };

  const settings = Object.assign(
    { sensitivity: 1.4, accel: 1.0, scroll: 1.0, natural: true, hints: true, speak: true, tapDrag: true },
    store.get('pp_settings', {}),
  );

  // ---- pairing token: from the QR link, then remembered -------------------
  const params = new URLSearchParams(location.search);
  let token = params.get('token');
  if (token) {
    store.set('pp_token', token);
    history.replaceState(null, '', location.pathname); // keep it out of the address bar
  } else {
    token = store.get('pp_token', null);
  }

  // ---- connection ---------------------------------------------------------
  let ws = null;
  let retry = 0;
  let pingTimer = null;
  let rejected = false;

  function setStatus(state, text) {
    $('#dot').className = 'dot ' + state;
    $('#status').textContent = text;
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) { ws.send(JSON.stringify(obj)); return true; }
    return false;
  }

  // Shared with voice.js: send messages / audio, and hear every laptop message.
  const PP = window.PP = {
    send,
    sendAudio(blob) {
      if (ws && ws.readyState === WebSocket.OPEN) { ws.send(blob); return true; }
      return false;
    },
    listeners: [],
    settings,
    saveSettings() { store.set('pp_settings', settings); },
  };

  function connect() {
    if (!token) { setStatus('bad', 'Not paired: scan the QR code on your laptop'); return; }
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}`);

    ws.onopen = () => {
      retry = 0;
      // The mic (voice, v2) only works on secure (HTTPS) pages.
      setStatus('ok', window.isSecureContext ? 'Connected' : 'Connected (no HTTPS: voice off)');
      clearInterval(pingTimer);
      pingTimer = setInterval(() => send({ t: 'ping', sent: performance.now() }), 2000);
    };
    ws.onmessage = (e) => {
      let m;
      try { m = JSON.parse(e.data); } catch { return; }
      if (m.t === 'pong' && typeof m.sent === 'number') {
        $('#lag').textContent = Math.round(performance.now() - m.sent) + ' ms';
      } else if (m.t === 'error') {
        console.warn('laptop:', m.msg);
      }
      PP.listeners.forEach((fn) => fn(m));
    };
    ws.onclose = (e) => {
      clearInterval(pingTimer);
      $('#lag').textContent = '';
      if (e.code === 1008) {
        rejected = true;
        setStatus('bad', 'Pairing rejected: scan the new QR code');
        return;
      }
      setStatus('wait', 'Reconnecting…');
      setTimeout(connect, Math.min(5000, 400 * 2 ** retry++));
    };
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !rejected) connect();
  });

  // ---- batching: at most one move/scroll message per screen frame --------
  const pend = { dx: 0, dy: 0, sx: 0, sy: 0 };
  let frameQueued = false;

  function queue() {
    if (!frameQueued) { frameQueued = true; requestAnimationFrame(flush); }
  }

  function flush() {
    frameQueued = false;
    const dx = Math.round(pend.dx), dy = Math.round(pend.dy);
    if (dx || dy) {
      send({ t: 'move', dx, dy });
      pend.dx -= dx; pend.dy -= dy;   // keep the leftover fraction for next frame
    }
    if (pend.sx || pend.sy) {
      send({ t: 'scroll', dx: +pend.sx.toFixed(3), dy: +pend.sy.toFixed(3) });
      pend.sx = 0; pend.sy = 0;
    }
  }

  const buzz = (ms) => { if (navigator.vibrate) navigator.vibrate(ms); };
  const click = (button) => { send({ t: 'click', button }); buzz(8); };

  // ---- gestures -----------------------------------------------------------
  function centroid(touches) {
    let x = 0, y = 0;
    for (const t of touches) { x += t.clientX; y += t.clientY; }
    return { x: x / touches.length, y: y / touches.length };
  }

  function spread(touches) {
    if (touches.length < 2) return 0;
    return Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
  }

  // Small label on the pad ("Switch app", "Dragging"...) so every gesture is visible.
  const chip = $('#gesture');
  let chipTimer = null;
  function flash(text, keep = false) {
    if (!chip) return;
    chip.textContent = text;
    chip.classList.add('show');
    clearTimeout(chipTimer);
    if (!keep) chipTimer = setTimeout(() => chip.classList.remove('show'), 900);
  }
  function unflash() { if (chip) chip.classList.remove('show'); }

  // Soft glow under the fingers.
  const glow = $('#glow');
  function showGlow(c) {
    if (!glow) return;
    const r = pad.getBoundingClientRect();
    glow.style.transform = `translate(${c.x - r.left}px, ${c.y - r.top}px)`;
    glow.classList.add('on');
  }

  const g = {
    active: false, start: 0, maxTouches: 0, moved: 0,
    last: null, lastT: 0, lastSpread: 0,
    mode: null, pinchAcc: 0, panAcc: 0, zoomAcc: 0,
    tx: 0, ty: 0, longTimer: null, dragging: false,
    swiped: false, secondTap: false,
  };
  // Double-tap state: a single tap waits DOUBLE_MS before clicking, in case a second touch follows.
  let pendingTap = null;

  function resetGesture() {
    Object.assign(g, {
      active: false, maxTouches: 0, moved: 0, mode: null,
      pinchAcc: 0, panAcc: 0, zoomAcc: 0, tx: 0, ty: 0, swiped: false, secondTap: false,
    });
  }

  function startDrag(label) {
    g.dragging = true;
    send({ t: 'button', button: 'left', action: 'down' });
    pad.classList.add('dragging');
    flash(label, true);
    buzz(25);
  }

  function endDrag() {
    send({ t: 'button', button: 'left', action: 'up' });
    g.dragging = false;
    pad.classList.remove('dragging');
    unflash();
  }

  // Three fingers: act as soon as the swipe is clear, while fingers are still down.
  // (Many phones cancel 3-finger touches for their own screenshot gesture.)
  function checkSwipe() {
    if (g.swiped) return;
    const ax = Math.abs(g.tx), ay = Math.abs(g.ty);
    if (Math.max(ax, ay) < SWIPE_PX) return;
    g.swiped = true;
    if (ax > ay) {
      send({ t: 'hotkey', combo: g.tx > 0 ? 'app_next' : 'app_prev' });
      flash(g.tx > 0 ? 'Next app' : 'Previous app');
    } else if (g.ty < 0) {
      send({ t: 'hotkey', combo: 'task_view' });
      flash('All windows');
    } else {
      send({ t: 'hotkey', combo: 'show_desktop' });
      flash('Desktop');
    }
    buzz(15);
  }

  pad.addEventListener('touchstart', (e) => {
    e.preventDefault();
    const n = e.touches.length;
    const now = performance.now();
    if (!g.active) {
      resetGesture();
      g.active = true;
      g.start = now;
    }
    g.maxTouches = Math.max(g.maxTouches, n);
    g.last = centroid(e.touches);
    g.lastT = now;
    g.lastSpread = spread(e.touches);
    showGlow(g.last);

    clearTimeout(g.longTimer);
    if (n > 1 && pendingTap) {
      // Tap followed by a multi-finger gesture: let the first tap click now.
      clearTimeout(pendingTap); pendingTap = null; click('left');
    }
    if (n === 1 && !g.dragging) {
      if (pendingTap) {
        // Second touch right after a tap: hold the button. Move = drag, lift quickly = double-click.
        clearTimeout(pendingTap); pendingTap = null;
        g.secondTap = true;
        startDrag('Dragging');
        return;
      }
      g.longTimer = setTimeout(() => {
        if (g.moved < LONG_SLOP && g.maxTouches === 1) startDrag('Dragging');
      }, LONG_MS);
    }
  }, { passive: false });

  pad.addEventListener('touchmove', (e) => {
    e.preventDefault();
    if (!g.active) return;
    const n = e.touches.length;
    const now = performance.now();
    const c = centroid(e.touches);
    const dx = c.x - g.last.x, dy = c.y - g.last.y;
    const dt = Math.max(1, now - g.lastT);
    g.last = c; g.lastT = now;
    g.moved += Math.hypot(dx, dy);
    if (g.moved > LONG_SLOP) clearTimeout(g.longTimer);
    showGlow(c);

    if (g.maxTouches >= 3) {
      // Once three fingers touched, only the swipe counts (no scrolling or cursor jumps
      // while the fingers lift one by one).
      if (n >= 3 || !g.swiped) { g.tx += dx; g.ty += dy; checkSwipe(); }
      return;
    }

    if (n === 1) {
      if (g.maxTouches >= 2) return;   // fingers lifting after a scroll/pinch: don't jump the cursor
      // Slow finger = precise, fast flick = crosses the screen.
      const speed = Math.hypot(dx, dy) / dt;  // px per ms
      const gain = settings.sensitivity * (1 + settings.accel * Math.min(speed, 3));
      pend.dx += dx * gain;
      pend.dy += dy * gain;
      queue();
    } else if (n === 2) {
      const s = spread(e.touches);
      const ds = s - g.lastSpread;
      g.lastSpread = s;
      g.pinchAcc += Math.abs(ds);
      if (!g.mode) {
        g.panAcc += Math.hypot(dx, dy);
        if (g.pinchAcc > 25 && g.pinchAcc > g.panAcc * 1.5) g.mode = 'zoom';
        else if (g.panAcc > 8) g.mode = 'scroll';
      }
      if (g.mode === 'scroll') {
        // Windows: wheel up = positive. Natural scrolling moves content with the fingers.
        const k = settings.scroll * SCROLL_PER_PX * (settings.natural ? 1 : -1);
        pend.sx += -dx * k;
        pend.sy += dy * k;
        queue();
      } else if (g.mode === 'zoom') {
        g.zoomAcc += ds;
        while (g.zoomAcc > ZOOM_PX) { send({ t: 'zoom', steps: 1 }); g.zoomAcc -= ZOOM_PX; }
        while (g.zoomAcc < -ZOOM_PX) { send({ t: 'zoom', steps: -1 }); g.zoomAcc += ZOOM_PX; }
      }
    }
  }, { passive: false });

  function touchEnd(e) {
    e.preventDefault();
    if (e.touches.length > 0) {
      // A finger lifted but others remain: re-anchor so the cursor doesn't jump.
      g.last = centroid(e.touches);
      g.lastSpread = spread(e.touches);
      return;
    }
    clearTimeout(g.longTimer);
    if (glow) glow.classList.remove('on');
    // A tap is short, barely moves, and isn't a pinch (a pinch keeps the centre still).
    const quick = performance.now() - g.start < TAP_MS && g.moved < TAP_SLOP
      && !g.mode && g.pinchAcc < TAP_SLOP;

    if (g.dragging) {
      endDrag();
      if (g.secondTap && quick) { click('left'); flash('Double-click'); }  // down+up+click = double-click
    } else if (g.maxTouches >= 3) {
      if (!g.swiped) {
        checkSwipe();                       // e.g. a touchcancel just before the threshold
        if (!g.swiped && quick) click('middle');
      }
    } else if (quick) {
      if (g.maxTouches === 2) click('right');
      else if (settings.tapDrag) {
        pendingTap = setTimeout(() => { pendingTap = null; click('left'); }, DOUBLE_MS);
      } else click('left');
    }
    flush();
    resetGesture();
  }
  pad.addEventListener('touchend', touchEnd, { passive: false });
  pad.addEventListener('touchcancel', touchEnd, { passive: false });

  // ---- mouse buttons: hold one and move on the pad to drag ---------------
  document.querySelectorAll('[data-button]').forEach((btn) => {
    const button = btn.dataset.button;
    let down = false;
    const release = () => {
      if (!down) return;
      down = false;
      btn.classList.remove('down');
      send({ t: 'button', button, action: 'up' });
    };
    btn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      down = true;
      btn.classList.add('down');
      send({ t: 'button', button, action: 'down' });
      buzz(8);
    });
    btn.addEventListener('pointerup', release);
    btn.addEventListener('pointercancel', release);
    btn.addEventListener('pointerleave', release);
  });

  // ---- keys, shortcuts, media --------------------------------------------
  document.querySelectorAll('[data-key]').forEach((b) =>
    b.addEventListener('click', () => { send({ t: 'key', key: b.dataset.key }); buzz(6); }));
  document.querySelectorAll('[data-hotkey]').forEach((b) =>
    b.addEventListener('click', () => { send({ t: 'hotkey', combo: b.dataset.hotkey }); buzz(6); }));
  document.querySelectorAll('[data-media]').forEach((b) =>
    b.addEventListener('click', () => { send({ t: 'media', key: b.dataset.media }); buzz(6); }));

  $('#arrowsBtn').addEventListener('click', (e) => {
    const box = $('#arrows');
    box.hidden = !box.hidden;
    e.currentTarget.setAttribute('aria-expanded', String(!box.hidden));
    e.currentTarget.classList.toggle('on', !box.hidden);
  });

  // ---- typing with the phone keyboard ------------------------------------
  // Phone keyboards rarely report real key presses, so we watch how the text
  // in a hidden box changes. A few placeholder characters at the start let us
  // notice Backspace even when the user hasn't typed anything yet.
  const kbd = $('#kbd');
  const SENTINEL = '    ';
  let prev = SENTINEL;
  let composing = false;

  function resetBox() {
    kbd.value = SENTINEL;
    prev = SENTINEL;
    kbd.setSelectionRange(SENTINEL.length, SENTINEL.length);
  }

  kbd.addEventListener('compositionstart', () => { composing = true; });
  kbd.addEventListener('compositionend', () => { composing = false; });

  kbd.addEventListener('input', () => {
    const cur = kbd.value;
    let i = 0;
    while (i < prev.length && i < cur.length && prev[i] === cur[i]) i++;
    const removed = prev.length - i;
    const added = cur.slice(i);
    for (let k = 0; k < removed; k++) send({ t: 'key', key: 'backspace' });
    if (added) send({ t: 'text', text: added.slice(0, 500) });
    prev = cur;
    if (!composing && (cur.length < SENTINEL.length || cur.length > 60 || !cur.startsWith(SENTINEL))) resetBox();
  });

  kbd.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      send({ t: 'key', key: 'enter' });
      resetBox();
    }
  });

  $('#kbdBtn').addEventListener('click', () => {
    if (document.activeElement === kbd) { kbd.blur(); return; }
    resetBox();
    kbd.focus();
  });

  // ---- settings -----------------------------------------------------------
  const dlg = $('#settings');
  const sliders = { sens: 'sensitivity', accel: 'accel', scroll: 'scroll' };

  function applySettings() {
    for (const [id, key] of Object.entries(sliders)) {
      $('#' + id).value = settings[key];
      $('#' + id + 'Out').textContent = Number(settings[key]).toFixed(1);
    }
    $('#natural').checked = settings.natural;
    $('#hints').checked = settings.hints;
    $('#tapdrag').checked = settings.tapDrag !== false;
    $('#hint').hidden = !settings.hints;
  }

  for (const [id, key] of Object.entries(sliders)) {
    $('#' + id).addEventListener('input', (e) => {
      settings[key] = parseFloat(e.target.value);
      store.set('pp_settings', settings);
      applySettings();
    });
  }
  $('#natural').addEventListener('change', (e) => { settings.natural = e.target.checked; store.set('pp_settings', settings); });
  $('#hints').addEventListener('change', (e) => { settings.hints = e.target.checked; store.set('pp_settings', settings); applySettings(); });
  $('#tapdrag').addEventListener('change', (e) => { settings.tapDrag = e.target.checked; store.set('pp_settings', settings); });
  $('#settingsBtn').addEventListener('click', () => {
    if (typeof dlg.showModal === 'function') dlg.showModal();
  });

  applySettings();
  connect();
})();
