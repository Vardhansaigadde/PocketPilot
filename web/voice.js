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
      askApproval(m);
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

  // ---- hold-to-talk mic -------------------------------------------------------
  let recording = false;
  let recorder = null;
  let stream = null;
  let chunks = [];
  let startedAt = 0;
  let stopTimer = null;
  let discard = false;

  function pickType() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    return types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
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
    if (navigator.vibrate) navigator.vibrate(15);
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    stopTimer = setTimeout(stopRecording, MAX_REC_MS);
  }

  function stopRecording() {
    clearTimeout(stopTimer);
    if (!recording) return;
    recording = false;
    mic.classList.remove('rec');
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
      if (!discard && !long) show('Hold the mic button while you speak.', true, 2500);
      return;
    }
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
    heard = '';
    if (PP.sendAudio(blob)) show('Listening… (working it out)', true, 0);
    else show('Not connected to the laptop.', false);
  }

  let pressed = false;
  mic.addEventListener('pointerdown', async (e) => {
    e.preventDefault();
    pressed = true;
    try { mic.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    await startRecording();
    // Released while the mic was still starting (e.g. the permission prompt)?
    if (!pressed && recording) cancelRecording();
  });
  mic.addEventListener('pointerup', () => { pressed = false; stopRecording(); });
  mic.addEventListener('pointercancel', () => { pressed = false; cancelRecording(); });
  mic.addEventListener('contextmenu', (e) => e.preventDefault());

  // ---- "speak replies" setting --------------------------------------------------
  const speakBox = $('#speak');
  speakBox.checked = PP.settings.speak !== false;
  speakBox.addEventListener('change', () => { PP.settings.speak = speakBox.checked; PP.saveSettings(); });
})();
