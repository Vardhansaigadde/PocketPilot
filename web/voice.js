// PocketPilot voice: hold-to-talk mic, typed commands, replies, Approve and Stop.
(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const PP = window.PP;
  const MAX_REC_MS = 12000;   // longest recording sent to the laptop
  const MIN_REC_MS = 350;     // shorter presses are treated as accidental

  const bubble = $('#bubble');
  const mic = $('#micBtn');
  let bubbleTimer = null;
  let heard = '';

  // ---- reply bubble + speech ------------------------------------------------
  function show(text, ok = true, keepMs = 6000) {
    bubble.textContent = '';
    if (heard) {
      const h = document.createElement('span');
      h.className = 'heard';
      h.textContent = '“' + heard + '”';
      bubble.appendChild(h);
    }
    bubble.appendChild(document.createTextNode(text));
    bubble.classList.toggle('bad', !ok);
    bubble.hidden = false;
    clearTimeout(bubbleTimer);
    if (keepMs) bubbleTimer = setTimeout(() => { bubble.hidden = true; heard = ''; }, keepMs);
  }

  function speak(text) {
    if (!PP.settings.speak || !('speechSynthesis' in window)) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-IN';
      speechSynthesis.speak(u);
    } catch { /* speech is optional */ }
  }

  // ---- messages from the laptop ---------------------------------------------
  PP.listeners.push((m) => {
    if (m.t === 'heard') {
      heard = m.text;
      show('…', true, 0);
    } else if (m.t === 'reply') {
      show(m.text, m.ok !== false);
      speak(m.text);
      heard = '';
    } else if (m.t === 'listening') {
      if (m.on) { heard = ''; show('Laptop is listening…', true, 0); }
    } else if (m.t === 'busy') {
      mic.classList.toggle('busy', !!m.on && !recording);
    } else if (m.t === 'approve_request') {
      closeChoices();
      askApproval(m);
    } else if (m.t === 'choices') {
      askChoice(m);
    } else if (m.t === 'hello') {
      mic.hidden = false;
      if (!window.isSecureContext || !navigator.mediaDevices) mic.title = 'Voice needs HTTPS';
    }
  });

  // ---- typed commands ---------------------------------------------------------
  $('#cmdForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const box = $('#cmdText');
    const text = box.value.trim();
    if (!text) return;
    heard = text;
    if (PP.send({ t: 'command', text: text.slice(0, 300) })) {
      show('…', true, 0);
      box.value = '';
    } else {
      show('Not connected to the laptop.', false);
    }
  });

  // ---- Stop (kill switch) -------------------------------------------------------
  $('#stopBtn').addEventListener('click', () => {
    if (recording) cancelRecording();
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    closeApproval();
    PP.send({ t: 'stop' });
    if (navigator.vibrate) navigator.vibrate([20, 40, 20]);
  });

  // ---- Approve card -----------------------------------------------------------
  const dlg = $('#approveDlg');
  let approval = null;
  let approvalTimer = null;

  // ---- "Which one?" card (e.g. several chats called "Akka") ---------------------
  // Tapping a name sends it as the answer; saying it or its number works too.
  const chooseDlg = $('#chooseDlg');

  function askChoice(m) {
    const list = $('#chooseList');
    list.textContent = '';
    $('#chooseTitle').textContent = (m.text || 'Which one?').split('?')[0] + '?';
    (m.options || []).forEach((name, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'choice';
      b.textContent = `${i + 1}  ${name}`;
      b.addEventListener('click', () => {
        closeChoices();
        heard = name;
        PP.send({ t: 'command', text: String(name).slice(0, 300) });
        show('…', true, 0);
      });
      list.appendChild(b);
    });
    if (typeof chooseDlg.showModal === 'function' && !chooseDlg.open) chooseDlg.showModal();
    if (navigator.vibrate) navigator.vibrate(20);
  }

  function closeChoices() {
    if (chooseDlg.open) chooseDlg.close();
  }

  $('#chooseCancel').addEventListener('click', () => {
    closeChoices();
    PP.send({ t: 'command', text: 'cancel' });
  });
  chooseDlg.addEventListener('cancel', (e) => { e.preventDefault(); closeChoices(); PP.send({ t: 'command', text: 'cancel' }); });

  function askApproval(m) {
    closeApproval();
    approval = { id: m.id, until: Date.now() + (m.seconds || 30) * 1000 };
    $('#approveText').textContent = m.text;
    const tick = () => {
      const left = Math.max(0, Math.round((approval.until - Date.now()) / 1000));
      $('#approveTimer').textContent = `Cancels itself in ${left} s`;
      if (left <= 0) closeApproval();
    };
    tick();
    approvalTimer = setInterval(tick, 1000);
    if (typeof dlg.showModal === 'function') dlg.showModal();
    if (navigator.vibrate) navigator.vibrate(30);
  }

  function closeApproval() {
    clearInterval(approvalTimer);
    approval = null;
    if (dlg.open) dlg.close();
  }

  function answer(ok) {
    if (approval) PP.send({ t: 'approve', id: approval.id, ok });
    closeApproval();
  }
  $('#okBtn').addEventListener('click', () => answer(true));
  $('#denyBtn').addEventListener('click', () => answer(false));
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); answer(false); });

  // ---- mic: hold to talk, slide right to lock (hands-free), slide left to cancel ------
  // Works like WhatsApp voice notes. Locked: keep talking with your thumb off,
  // then tap the ✓ button to send (or ■ to throw it away).
  const MAX_LOCKED_MS = 20000;   // the laptop listens to at most 20 s
  const LOCK_PX = 60;            // slide this far right to lock
  const CANCEL_PX = 80;          // slide this far left to cancel
  const voiceRow = $('.voice');
  const micIcon = mic.querySelector('use');
  const recBar = $('#recBar');
  const recTime = $('#recTime');
  const recHint = $('#recHint');

  let recording = false;
  let locked = false;
  let recorder = null;
  let stream = null;
  let chunks = [];
  let startedAt = 0;
  let stopTimer = null;
  let clockTimer = null;
  let discard = false;

  function pickType() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    return types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
  }

  function recordingUI(on) {
    voiceRow.classList.toggle('recording', on);
    recBar.hidden = !on;
    clearInterval(clockTimer);
    if (on) {
      const tick = () => {
        const s = Math.floor((Date.now() - startedAt) / 1000);
        recTime.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
      };
      tick();
      clockTimer = setInterval(tick, 250);
    }
  }

  function setLocked(on) {
    locked = on;
    voiceRow.classList.toggle('locked', on);
    micIcon.setAttribute('href', on ? '#i-check' : '#i-mic');
    mic.setAttribute('aria-label', on ? 'Send recording' : 'Hold to talk, slide right to lock');
    recHint.textContent = on ? 'Hands-free · tap ✓' : '→ lock  ·  ← cancel';
    mic.style.transform = '';
    if (on) {
      clearTimeout(stopTimer);
      stopTimer = setTimeout(stopRecording, Math.max(1000, MAX_LOCKED_MS - (Date.now() - startedAt)));
      if (navigator.vibrate) navigator.vibrate(20);
    }
  }

  async function startRecording() {
    if (recording) return;
    if (!window.isSecureContext || !navigator.mediaDevices || !window.MediaRecorder) {
      show('Voice needs the HTTPS link from the laptop (scan the QR again).', false);
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      show('Microphone blocked. Allow it in the browser settings for this site.', false);
      return;
    }
    const type = pickType();
    recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    chunks = [];
    discard = false;
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = finishRecording;
    recorder.start();
    recording = true;
    startedAt = Date.now();
    mic.classList.add('rec');
    setLocked(false);
    recordingUI(true);
    if (navigator.vibrate) navigator.vibrate(15);
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    stopTimer = setTimeout(stopRecording, MAX_REC_MS);
  }

  function stopRecording() {
    clearTimeout(stopTimer);
    if (!recording) return;
    recording = false;
    mic.classList.remove('rec');
    setLocked(false);
    recordingUI(false);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
  }

  function cancelRecording() {
    discard = true;
    stopRecording();
  }

  function finishRecording() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    const long = Date.now() - startedAt >= MIN_REC_MS;
    if (discard || !long || !chunks.length) {
      if (!discard && !long) show('Hold the mic while you speak, or slide it right for hands-free.', true, 3000);
      return;
    }
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
    heard = '';
    if (PP.sendAudio(blob)) show('Listening… (working it out)', true, 0);
    else show('Not connected to the laptop.', false);
  }

  let pressed = false;
  let startX = 0;
  mic.addEventListener('pointerdown', async (e) => {
    e.preventDefault();
    if (recording && locked) {           // locked: this tap sends it
      stopRecording();
      return;
    }
    pressed = true;
    startX = e.clientX;
    try { mic.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    await startRecording();
    // Released while the mic was still starting (e.g. the permission prompt)?
    if (!pressed && recording && !locked) cancelRecording();
  });
  mic.addEventListener('pointermove', (e) => {
    if (!pressed || !recording || locked) return;
    const dx = e.clientX - startX;
    mic.style.transform = `translateX(${Math.max(-CANCEL_PX, Math.min(LOCK_PX, dx))}px)`;
    if (dx >= LOCK_PX) {
      setLocked(true);
    } else if (dx <= -CANCEL_PX) {
      pressed = false;
      cancelRecording();
      show('Cancelled.', true, 1500);
    }
  });
  mic.addEventListener('pointerup', () => {
    pressed = false;
    mic.style.transform = '';
    if (!locked) stopRecording();
  });
  mic.addEventListener('pointercancel', () => {
    pressed = false;
    mic.style.transform = '';
    if (!locked) cancelRecording();
  });
  mic.addEventListener('contextmenu', (e) => e.preventDefault());

  // ---- "speak replies" setting --------------------------------------------------
  const speakBox = $('#speak');
  speakBox.checked = PP.settings.speak !== false;
  speakBox.addEventListener('change', () => { PP.settings.speak = speakBox.checked; PP.saveSettings(); });
})();
