"""
JavaScript snippets injected into the live VC.ru page.

Jobs:
  1) build_autofill_js - watch for VC.ru's auth modal; pre-fill the saved
     e-mail/password, and remember whatever the user types so the next
     run can fill it in. Never clicks "Войти" - the user does that.
  2) build_insert_js   - drop HTML + images into the editor as a real paste,
     so VC.ru uploads the images itself and keeps formatting.

Selectors come from config.py and are formatted in at runtime.
"""


def build_autofill_js(email: str, password: str,
                      email_sel: list, pass_sel: list,
                      submit_sel: list, submit_texts: list) -> str:
    """
    Runs on every vc.ru page and keeps running: the auth modal can open at
    any moment, so a MutationObserver watches for it instead of a one-shot
    lookup.

    Autofill only. Submitting is left to the user, which keeps the flow
    predictable and avoids fighting the site's own validation.

    Credentials are captured on submit (click or Enter) and handed to
    Python via window.pywebview.api.remember_login.

    Guards:
      * every querySelector is wrapped in try/catch, because one bad
        selector must not abort the loop;
      * only visible fields are touched, so we never type into the site
        search box;
      * a filled field is not overwritten while the user is editing it.
    """
    import json
    return f"""
(function(){{
  if (window.__vcphAutofill) return;
  window.__vcphAutofill = true;

  const emailSel = {json.dumps(email_sel)};
  const passSel  = {json.dumps(pass_sel)};
  const subSel   = {json.dumps(submit_sel)};
  const subTexts = {json.dumps(submit_texts)};
  const EMAIL = {json.dumps(email)};
  const PW    = {json.dumps(password)};

  function visible(el){{
    if (!el) return false;
    if (el.offsetParent === null) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }}
  function pick(sels){{
    for (const s of sels){{
      let list = [];
      try {{ list = document.querySelectorAll(s); }} catch(e) {{ continue; }}
      for (const el of list){{ if (visible(el)) return el; }}
    }}
    return null;
  }}
  function setVal(el, val){{
    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, val);
    el.dispatchEvent(new Event('input',  {{bubbles:true}}));
    el.dispatchEvent(new Event('change', {{bubbles:true}}));
  }}

  // ---- remember what the user typed ----
  function remember(){{
    const e = pick(emailSel), p = pick(passSel);
    const em = e ? e.value.trim() : '';
    const pw = p ? p.value : '';
    if (!em || !pw) return;
    try {{
      if (window.pywebview && window.pywebview.api)
        window.pywebview.api.remember_login(em, pw);
    }} catch(err) {{}}
  }}

  document.addEventListener('click', function(ev){{
    const t = ev.target;
    if (!t) return;
    const btn = t.closest ? t.closest('button, [role="button"]') : null;
    if (!btn) return;
    const cap = (btn.textContent || '').trim().toLowerCase();
    let isSubmit = subTexts.some(x => cap === x || cap.startsWith(x));
    if (!isSubmit){{
      for (const s of subSel){{
        try {{ if (btn.matches(s)) {{ isSubmit = true; break; }} }} catch(e) {{}}
      }}
    }}
    if (isSubmit) remember();
  }}, true);

  document.addEventListener('keydown', function(ev){{
    if (ev.key !== 'Enter') return;
    const t = ev.target;
    if (!t || t.tagName !== 'INPUT') return;
    remember();
  }}, true);

  // ---- pre-fill the modal whenever it shows up ----
  let lastFilled = 0;
  function tryFill(){{
    if (!EMAIL && !PW) return;
    const p = pick(passSel);
    if (!p) return;                 // no password field => not the auth modal
    const e = pick(emailSel);
    const now = Date.now();
    if (now - lastFilled < 800) return;
    lastFilled = now;
    if (e && EMAIL && !e.value) setVal(e, EMAIL);
    if (PW && !p.value) setVal(p, PW);
  }}

  const obs = new MutationObserver(function(){{ tryFill(); }});
  obs.observe(document.documentElement,
              {{childList: true, subtree: true}});
  tryFill();
  setTimeout(tryFill, 1000);
  setTimeout(tryFill, 2500);
}})();
"""


def build_insert_js(editor_sel: list, title_sel: list) -> str:
    """
    Define window.__vcphInsert(html, title) on the page.

    The article is inserted by focusing the contenteditable area and
    dispatching a synthetic 'paste' ClipboardEvent carrying text/html.
    VC.ru's editor listens for paste and uploads embedded images
    (data-URIs) on its own. Falls back to execCommand insertHTML if the
    paste event is swallowed.

    Registered as a function (not run immediately) so the top bar can call
    it directly from JS, with no round-trip through Python.
    """
    import json
    return f"""
(function(){{
  const editorSel = {json.dumps(editor_sel)};
  const titleSel  = {json.dumps(title_sel)};

  function pick(sels){{
    for (const s of sels){{
      let el = null;
      try {{ el = document.querySelector(s); }} catch(e) {{ continue; }}
      if (el) return el;
    }}
    return null;
  }}

  function fillTitle(TITLE){{
    if (!TITLE) return;
    const t = pick(titleSel);
    if (!t) return;
    if (t.isContentEditable){{ t.textContent = TITLE; }}
    else {{
      const proto = t.tagName === 'TEXTAREA'
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto,'value').set;
      setter.call(t, TITLE);
    }}
    t.dispatchEvent(new Event('input', {{bubbles:true}}));
  }}

  function doPaste(target, HTML){{
    target.focus();
    const range = document.createRange();
    range.selectNodeContents(target);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(range);

    let ok = false;
    try {{
      const dt = new DataTransfer();
      dt.setData('text/html', HTML);
      dt.setData('text/plain', target.textContent || '');
      const ev = new ClipboardEvent('paste', {{
        bubbles:true, cancelable:true, clipboardData: dt
      }});
      ok = target.dispatchEvent(ev);
    }} catch(e) {{ ok = true; }}

    // If the editor ignored the paste, fall back. execCommand is
    // deprecated and RETURNS FALSE instead of throwing when unavailable,
    // so the result must be checked, not just wrapped in try/catch.
    setTimeout(function(){{
      if (target.textContent.trim().length >= 3) return;
      let done = false;
      try {{ done = document.execCommand('insertHTML', false, HTML) === true; }}
      catch(e) {{ done = false; }}
      if (!done || target.textContent.trim().length < 3){{
        try {{ target.innerHTML = HTML; }} catch(e) {{}}
        target.dispatchEvent(new Event('input', {{bubbles:true}}));
      }}
      const st = document.getElementById('vcph-status');
      if (st){{
        st.textContent = target.textContent.trim().length >= 3
          ? 'Статья вставлена'
          : 'Не удалось вставить - вставьте вручную (Ctrl+V)';
      }}
    }}, 500);
    return ok;
  }}

  // Exposed to the top bar: waits for the editor to appear, then pastes.
  window.__vcphInsert = function(HTML, TITLE){{
    let tries = 0;
    const timer = setInterval(function(){{
      tries++;
      const ed = pick(editorSel);
      if (ed){{
        clearInterval(timer);
        fillTitle(TITLE);
        setTimeout(function(){{ doPaste(ed, HTML); }}, 300);
        // Final wording is set by doPaste, once the result is known.
        const st = document.getElementById('vcph-status');
        if (st) st.textContent = 'Вставляю статью...';
      }}
      if (tries > 60){{
        clearInterval(timer);
        const st = document.getElementById('vcph-status');
        if (st) st.textContent = 'Редактор не найден - откройте его и повторите';
      }}
    }}, 500);
  }};
}})();
"""
