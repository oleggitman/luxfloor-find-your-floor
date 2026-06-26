(function () {
  'use strict';

  var script = document.currentScript ||
    document.querySelector('script[data-backend]');
  var BACKEND = (script && script.getAttribute('data-backend')) || '';
  if (!BACKEND) { console.warn('FYF: data-backend missing'); return; }
  // normalize: collapse an accidental double scheme (https://https://...) and strip trailing slashes
  BACKEND = BACKEND.replace(/^(https?:\/\/)+/i, 'https://').replace(/\/+$/, '');

  var SESSION_KEY = 'fyf_session_id';
  var sessionId = null;
  try { sessionId = localStorage.getItem(SESSION_KEY); } catch (e) {}

  /* ---- styles ---- */
  var css = [
    '#fyf-btn{position:fixed!important;bottom:150px!important;right:20px!important;width:56px!important;height:56px!important;',
    'border-radius:50%!important;background:#A88E77!important;border:none!important;cursor:pointer!important;',
    'box-shadow:0 4px 14px rgba(0,0,0,.25)!important;z-index:2147483647!important;display:flex!important;',
    'align-items:center!important;justify-content:center!important;padding:0!important;margin:0!important;}',
    '#fyf-btn svg{pointer-events:none;}',
    '#fyf-bubble{position:fixed!important;bottom:160px!important;right:84px!important;max-width:210px!important;',
    'background:#fff!important;color:#333!important;padding:10px 12px!important;border-radius:12px!important;',
    'box-shadow:0 4px 16px rgba(0,0,0,.18)!important;z-index:2147483646!important;font-size:13px!important;',
    'line-height:1.4!important;font-family:system-ui,sans-serif!important;cursor:pointer!important;display:none!important;}',
    '#fyf-bubble-x{position:absolute!important;top:-8px!important;right:-8px!important;width:20px!important;height:20px!important;',
    'background:#A88E77!important;color:#fff!important;border-radius:50%!important;border:none!important;',
    'font-size:13px!important;line-height:1!important;cursor:pointer!important;display:flex!important;',
    'align-items:center!important;justify-content:center!important;}',
    '#fyf-panel{position:fixed;bottom:150px;right:20px;width:320px;',
    'max-height:520px;display:none;flex-direction:column;',
    'background:#fff;border-radius:12px;',
    'box-shadow:0 8px 32px rgba(0,0,0,.18);z-index:2147483646;overflow:hidden;',
    'font-family:system-ui,sans-serif;}',
    '#fyf-panel.open{display:flex;}',
    '#fyf-head{background:#333333;color:#fff;padding:12px 16px;',
    'display:flex;align-items:center;justify-content:space-between;',
    'font-size:14px;font-weight:600;letter-spacing:.3px;}',
    '#fyf-close{background:none;border:none;color:#fff;font-size:18px;',
    'cursor:pointer;line-height:1;padding:0 4px;}',
    '#fyf-msgs{flex:1;overflow-y:auto;padding:12px;',
    'display:flex;flex-direction:column;gap:8px;}',
    '.fyf-msg{max-width:86%;padding:8px 12px;border-radius:10px;',
    'font-size:13px;line-height:1.5;word-break:break-word;}',
    '.fyf-msg.bot{background:#f5f2ee;color:#2b2b2b;align-self:flex-start;}',
    '.fyf-msg.user{background:#A88E77;color:#fff;align-self:flex-end;}',
    '.fyf-typing{font-size:22px;letter-spacing:2px;color:#999;}',
    '#fyf-foot{border-top:1px solid #eee;padding:8px;',
    'display:flex;gap:6px;}',
    '#fyf-input{flex:1;border:1px solid #ddd;border-radius:8px;',
    'padding:8px 10px;font-size:13px;outline:none;resize:none;}',
    '#fyf-send{background:#A88E77;color:#fff;border:none;',
    'border-radius:8px;padding:8px 14px;cursor:pointer;font-size:13px;}',
    '@media(max-width:480px){',
    '#fyf-panel{width:100vw;right:0;bottom:0;border-radius:12px 12px 0 0;',
    'max-height:80vh;}',
    '#fyf-btn{bottom:150px!important;right:16px!important;}',
    '#fyf-bubble{bottom:160px!important;right:80px!important;max-width:170px!important;}}',
  ].join('');

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  /* ---- DOM ---- */
  var btn = document.createElement('button');
  btn.id = 'fyf-btn';
  btn.setAttribute('aria-label', 'Bodenberater starten');
  btn.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';

  var bubble = document.createElement('div');
  bubble.id = 'fyf-bubble';
  bubble.setAttribute('lang', 'de');
  bubble.setAttribute('translate', 'no');
  bubble.innerHTML = 'Haben Sie Fragen zu Ihrem Boden? Ich berate Sie gern.' +
    '<button id="fyf-bubble-x" aria-label="Schliessen">&times;</button>';

  var panel = document.createElement('div');
  panel.id = 'fyf-panel';
  panel.setAttribute('lang', 'de');
  panel.setAttribute('translate', 'no');
  panel.innerHTML = [
    '<div id="fyf-head">',
    '  <span>Bodenberater</span>',
    '  <button id="fyf-close" aria-label="Schliessen">&times;</button>',
    '</div>',
    '<div id="fyf-msgs"></div>',
    '<div id="fyf-foot">',
    '  <textarea id="fyf-input" rows="1"',
    '   placeholder="Ihre Frage..."></textarea>',
    '  <button id="fyf-send">&#10148;</button>',
    '</div>',
  ].join('');

  document.body.appendChild(btn);
  document.body.appendChild(bubble);
  document.body.appendChild(panel);

  var bubbleX = bubble.querySelector('#fyf-bubble-x');
  var msgs   = panel.querySelector('#fyf-msgs');
  var input  = panel.querySelector('#fyf-input');
  var sendBtn = panel.querySelector('#fyf-send');
  var closeBtn = panel.querySelector('#fyf-close');

  /* ---- helpers ---- */
  function linkify(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
      .replace(/\n/g, '<br>');
  }

  function addMsg(text, role) {
    var el = document.createElement('div');
    el.className = 'fyf-msg ' + role;
    el.innerHTML = linkify(text);
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
    return el;
  }

  panel.style.cssText = 'position:fixed!important;display:none!important;bottom:220px!important;right:20px!important;width:320px!important;max-height:520px!important;flex-direction:column!important;background:#fff!important;border-radius:12px!important;box-shadow:0 8px 32px rgba(0,0,0,.18)!important;z-index:2147483646!important;overflow:hidden!important;font-family:system-ui,sans-serif!important;';

  function hideBubble() {
    bubble.style.setProperty('display', 'none', 'important');
    try { localStorage.setItem('fyf_bubble_seen', '1'); } catch (e) {}
  }

  var opened = false;
  function open() {
    hideBubble();
    panel.style.setProperty('display', 'flex', 'important');
    opened = true;
    if (!msgs.children.length) {
      addMsg('Herzlich willkommen! Ich bin Ihr Bodenberater bei Lux-Floor. Wie kann ich Ihnen helfen?', 'bot');
    }
    input.focus();
  }
  function close() {
    panel.style.setProperty('display', 'none', 'important');
  }

  btn.addEventListener('click', function () { opened ? close() : open(); opened = !opened; });
  bubble.addEventListener('click', function (e) {
    if (e.target === bubbleX) return;
    open(); opened = true;
  });
  bubbleX.addEventListener('click', function (e) { e.stopPropagation(); hideBubble(); });

  /* gentle teaser: show the bubble once after 12s if the chat was never opened */
  var bubbleSeen = false;
  try { bubbleSeen = localStorage.getItem('fyf_bubble_seen') === '1'; } catch (e) {}
  if (!bubbleSeen) {
    setTimeout(function () {
      if (!opened) bubble.style.setProperty('display', 'block', 'important');
    }, 12000);
  }
  closeBtn.addEventListener('click', function () { close(); opened = false; });

  /* ---- send ---- */
  var busy = false;

  function send() {
    if (busy) return;
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = 'auto';
    addMsg(text, 'user');

    busy = true;
    sendBtn.disabled = true;

    var typing = addMsg('...', 'bot fyf-typing');

    var slowTimer = setTimeout(function () {
      typing.innerHTML = 'Einen Moment bitte…';
    }, 5000);

    var body = JSON.stringify({ session_id: sessionId, message: text });

    fetch(BACKEND + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        clearTimeout(slowTimer);
        msgs.removeChild(typing);
        sessionId = data.session_id;
        try { localStorage.setItem(SESSION_KEY, sessionId); } catch (e) {}
        addMsg(data.reply || '(keine Antwort)', 'bot');
      })
      .catch(function () {
        clearTimeout(slowTimer);
        msgs.removeChild(typing);
        addMsg('Entschuldigung, es gab einen Fehler. Bitte versuchen Sie es erneut.', 'bot');
      })
      .finally(function () {
        busy = false;
        sendBtn.disabled = false;
        input.focus();
      });
  }

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 80) + 'px';
  });
})();
