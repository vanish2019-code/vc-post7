"""
VC Paste Helper - main application.

Design rule learned the hard way: never call a GUI-blocking pywebview
method (load_url, create_file_dialog) from a JS event handler - on some
Windows/WebView2 setups that call never returns and the UI hangs forever.

So:
  * navigation      -> plain JS (window.location)
  * file picking     -> hidden <input type=file> + FileReader in the page
  * Python's job     -> convert bytes to HTML. Pure computation, no GUI.
"""
import base64
import os
import sys

import webview

from . import config, storage
from .converter import convert_bytes
from .inject_js import build_autofill_js, build_insert_js


def _asset(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    cand = [
        os.path.join(base, "vcpaste", "assets", name),
        os.path.join(base, "assets", name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name),
    ]
    for c in cand:
        if os.path.exists(c):
            return c
    return cand[-1]


def _storage_dir() -> str:
    """Folder where the WebView engine keeps cookies/session between runs."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "VCPasteHelper", "session")
    os.makedirs(d, exist_ok=True)
    return d


class Api:
    """Bridge exposed to JavaScript. Contains no GUI calls by design."""

    def __init__(self):
        self.window = None

    def remember_login(self, email, password):
        """Called from the page when the user submits the auth modal."""
        if email and password:
            storage.save_profile(email, password)
        return True

    def convert_document(self, name, b64):
        """
        Convert a document the page already read for us.

        Returns {'ok': True, 'html', 'title', 'images'} or
                {'ok': False, 'msg'}.
        The page then calls window.__vcphInsert(html, title) itself.
        """
        try:
            raw = base64.b64decode(b64.split(",")[-1])
        except Exception as e:
            return {"ok": False, "msg": f"Файл не прочитан: {e}"}
        try:
            data = convert_bytes(name, raw)
        except Exception as e:
            return {"ok": False, "msg": f"Ошибка чтения: {e}"}
        return {
            "ok": True,
            "html": data["html"],
            "title": data["title"],
            "images": data["images"],
            "msg": f"Готово: {name} (изображений: {data['images']})",
        }


def _build_top_bar_js() -> str:
    """Top bar shown on every vc.ru page. All UI work stays in JS."""
    import json
    editor_url = json.dumps(config.EDITOR_URL)
    login_url = json.dumps(config.LOGIN_URL)
    return r"""
(function(){
  if (document.getElementById('vcph-bar')) return;
  var EDITOR_URL = __EDITOR__;
  var LOGIN_URL  = __LOGIN__;

  var bar = document.createElement('div');
  bar.id = 'vcph-bar';
  bar.style.cssText =
    'position:fixed;top:0;left:0;right:0;height:52px;z-index:2147483647;'+
    'background:#12b869;display:flex;align-items:center;gap:10px;'+
    'padding:0 16px;font-family:Segoe UI,Arial,sans-serif;'+
    'box-shadow:0 2px 10px rgba(0,0,0,.25);';
  function mkBtn(id,text){
    return '<button id="'+id+'" style="background:#fff;color:#0e9a57;'+
      'border:none;border-radius:8px;padding:9px 16px;font-size:14px;'+
      'font-weight:600;cursor:pointer;">'+text+'</button>';
  }
  bar.innerHTML =
    '<span style="color:#fff;font-weight:700;font-size:15px;">VC Paste Helper</span>'+
    '<span style="margin-left:auto"></span>'+
    mkBtn('vcph-login','Войти')+
    mkBtn('vcph-editor','Открыть редактор')+
    mkBtn('vcph-load','Загрузить документ')+
    '<span id="vcph-status" style="color:#eafff3;font-size:13px;max-width:320px;'+
    'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></span>';
  document.body.appendChild(bar);
  document.body.style.paddingTop = '52px';
  var st = document.getElementById('vcph-status');

  // Hidden file input: the page picks the file, so no native dialog from
  // Python and nothing can block.
  var fi = document.createElement('input');
  fi.type = 'file';
  fi.accept = '.docx,.html,.htm,.txt,.md';
  fi.style.display = 'none';
  document.body.appendChild(fi);

  function handleFile(f){
    if (!f) return;
    st.textContent = 'Читаю: ' + f.name;
    var fr = new FileReader();
    fr.onerror = function(){ st.textContent = 'Не удалось прочитать файл'; };
    fr.onload = function(){
      var b64 = String(fr.result).split(',').pop();
      st.textContent = 'Обрабатываю...';
      if (!(window.pywebview && window.pywebview.api)){
        st.textContent = 'Мост с программой недоступен';
        return;
      }
      window.pywebview.api.convert_document(f.name, b64).then(function(r){
        if (!r || !r.ok){ st.textContent = (r && r.msg) || 'Ошибка'; return; }
        st.textContent = r.msg || '';
        if (typeof window.__vcphInsert !== 'function'){
          st.textContent = 'Вставка недоступна, обновите страницу';
          return;
        }
        // Editor open already? Insert now. Otherwise stash and go there.
        if (location.pathname.indexOf('/new') !== -1){
          window.__vcphInsert(r.html, r.title);
        } else {
          try {
            sessionStorage.setItem('vcphPending',
              JSON.stringify({html:r.html, title:r.title}));
          } catch(e){}
          st.textContent = 'Открываю редактор...';
          window.location.href = EDITOR_URL;
        }
      })['catch'](function(e){
        st.textContent = 'Ошибка обработки: ' + e;
      });
    };
    fr.readAsDataURL(f);
  }

  fi.onchange = function(){ handleFile(fi.files && fi.files[0]); fi.value=''; };
  document.getElementById('vcph-load').onclick = function(){ fi.click(); };

  document.getElementById('vcph-editor').onclick = function(){
    st.textContent = 'Открываю редактор...';
    window.location.href = EDITOR_URL;
  };
  document.getElementById('vcph-login').onclick = function(){
    st.textContent = 'Открываю вход...';
    window.location.href = LOGIN_URL;
  };

  // Drag & drop straight into the window - same path, no file dialog.
  window.addEventListener('dragover', function(e){ e.preventDefault(); }, false);
  window.addEventListener('drop', function(e){
    e.preventDefault();
    var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, false);

  // Article converted on a previous page? Insert it here.
  try {
    var pend = sessionStorage.getItem('vcphPending');
    if (pend){
      sessionStorage.removeItem('vcphPending');
      var d = JSON.parse(pend);
      var wait = setInterval(function(){
        if (typeof window.__vcphInsert === 'function'){
          clearInterval(wait);
          window.__vcphInsert(d.html, d.title);
        }
      }, 200);
      setTimeout(function(){ clearInterval(wait); }, 20000);
    }
  } catch(e){}
})();
""".replace("__EDITOR__", editor_url).replace("__LOGIN__", login_url)


def _on_loaded(api: "Api"):
    """Fires after each navigation. Injects insert helper, bar, autofill."""
    try:
        url = api.window.get_current_url() or ""
    except Exception:
        url = ""
    if "vc.ru" not in url:
        return

    # Order matters: __vcphInsert must exist before the bar looks for it.
    for js in (
        build_insert_js(config.EDITOR_AREA_SELECTORS,
                        config.EDITOR_TITLE_SELECTORS),
        _build_top_bar_js(),
    ):
        try:
            api.window.evaluate_js(js)
        except Exception:
            pass

    profiles = storage.load_profiles()
    email = profiles[0]["email"] if profiles else ""
    pw = profiles[0]["password"] if profiles else ""
    try:
        api.window.evaluate_js(build_autofill_js(
            email, pw,
            config.LOGIN_EMAIL_SELECTORS,
            config.LOGIN_PASSWORD_SELECTORS,
            config.LOGIN_SUBMIT_SELECTORS,
            config.LOGIN_SUBMIT_TEXTS,
        ))
    except Exception:
        pass


def main():
    api = Api()
    window = webview.create_window(
        config.WINDOW_TITLE,
        url=config.HOME_URL,
        js_api=api,
        width=config.WINDOW_W,
        height=config.WINDOW_H,
        min_size=(900, 600),
    )
    api.window = window
    window.events.loaded += lambda: _on_loaded(api)

    # private_mode=False keeps cookies/session on disk -> login only once.
    webview.start(
        private_mode=False,
        storage_path=_storage_dir(),
    )


if __name__ == "__main__":
    main()
