(function () {
  'use strict';

  /* ── 1. Disable right-click context menu ── */
  document.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    return false;
  });

  /* ── 2. Block keyboard shortcuts ── */
  document.addEventListener('keydown', function (e) {
    var blocked = false;

    // F12 — DevTools
    if (e.keyCode === 123) blocked = true;

    // F11 — Fullscreen (blocked per request)
    if (e.keyCode === 122) blocked = true;

    // Ctrl/Cmd + Shift + I — Inspect / DevTools
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.keyCode === 73)) blocked = true;

    // Ctrl/Cmd + Shift + J — Console
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.keyCode === 74)) blocked = true;

    // Ctrl/Cmd + Shift + C — Inspect element
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.keyCode === 67)) blocked = true;

    // Ctrl/Cmd + U — View source
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.keyCode === 85)) blocked = true;

    // Ctrl/Cmd + Shift + K — Firefox Console
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.keyCode === 75)) blocked = true;

    if (blocked) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }
  }, true);

  /* ── 3. DevTools open detection via window size ── */
  var THRESHOLD = 160;
  var warningVisible = false;

  function buildOverlay() {
    if (document.getElementById('__cx-shield')) return;
    var el = document.createElement('div');
    el.id = '__cx-shield';
    el.setAttribute('aria-hidden', 'true');
    el.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:2147483647',
      'background:rgba(2,6,23,.97)',
      'display:none', 'align-items:center', 'justify-content:center',
      'flex-direction:column', 'gap:20px',
      'font-family:Fira Sans,system-ui,sans-serif',
      'color:#F8FAFC', 'text-align:center', 'padding:32px'
    ].join(';');
    el.innerHTML =
      '<div style="width:64px;height:64px;background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);border-radius:16px;display:flex;align-items:center;justify-content:center;margin:0 auto">' +
        '<svg width="32" height="32" fill="none" viewBox="0 0 24 24" stroke="#EF4444" stroke-width="1.5">' +
          '<path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"/>' +
        '</svg>' +
      '</div>' +
      '<div style="font-size:22px;font-weight:700;color:#EF4444;letter-spacing:.3px">Developer Tools Detected</div>' +
      '<div style="font-size:14px;color:#94A3B8;max-width:360px;line-height:1.7">' +
        'This is a secured CCTV monitoring system.<br>' +
        'Inspection tools are not permitted.<br>' +
        '<strong style="color:#CBD5E1">Please close DevTools to continue.</strong>' +
      '</div>' +
      '<div style="font-family:Fira Code,monospace;font-size:11px;color:#475569;margin-top:4px">CCTRIX Security Shield · Unauthorized access is prohibited</div>';
    document.body.appendChild(el);
  }

  function showShield() {
    buildOverlay();
    var el = document.getElementById('__cx-shield');
    if (el) el.style.display = 'flex';
    warningVisible = true;
  }

  function hideShield() {
    var el = document.getElementById('__cx-shield');
    if (el) el.style.display = 'none';
    warningVisible = false;
  }

  function checkDevTools() {
    var wDiff = window.outerWidth  - window.innerWidth;
    var hDiff = window.outerHeight - window.innerHeight;
    if (wDiff > THRESHOLD || hDiff > THRESHOLD) {
      if (!warningVisible) showShield();
    } else {
      if (warningVisible) hideShield();
    }
  }

  /* ── 4. Debugger heartbeat (slows when DevTools pauses JS) ── */
  var _dtOpen = false;
  function devtoolsHeartbeat() {
    var start = new Date();
    // The debugger statement freezes if DevTools is open with "Pause on breakpoints"
    // eslint-disable-next-line no-debugger
    debugger;
    var elapsed = new Date() - start;
    if (elapsed > 100 && !_dtOpen) {
      _dtOpen = true;
      showShield();
    } else if (elapsed <= 100 && _dtOpen) {
      _dtOpen = false;
      hideShield();
    }
  }

  /* Start checks after DOM ready */
  function start() {
    setInterval(checkDevTools, 800);
    setInterval(devtoolsHeartbeat, 1500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
