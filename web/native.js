// PocketPilot: speech and vibration that also work inside the Android app (v6).
// In the app, Android's web view can't speak (Telugu replies) or vibrate reliably, so the
// page asks the app to do it through the "PocketPilotApp" channel. In a normal browser
// nothing changes.
(() => {
  'use strict';

  const app = () => (window.PocketPilotApp && window.PocketPilotApp.postMessage) ? window.PocketPilotApp : null;
  const send = (msg) => app().postMessage(JSON.stringify(msg));

  window.PPNative = {
    inApp: () => !!app(),

    /** Speak with the app's voice. Returns false in a browser (then use speechSynthesis). */
    speak(text, lang) {
      if (!app()) return false;
      send({ do: 'speak', text, lang });
      return true;
    },

    stopSpeaking() {
      if (app()) send({ do: 'stop' });
      else if ('speechSynthesis' in window) speechSynthesis.cancel();
    },

    /** A short buzz: a number of ms, or a pattern like [20, 40, 20]. */
    vibrate(pattern) {
      if (app()) {
        send({ do: 'vibrate', ms: Array.isArray(pattern) ? Math.max(...pattern) : pattern });
      } else if (navigator.vibrate) {
        navigator.vibrate(pattern);
      }
    },
  };
})();
