/*
 * Headless self-test for the injected JavaScript.
 *
 * Runs the real top-bar and insert scripts against a jsdom mock of vc.ru,
 * with window.pywebview.api stubbed. Catches selector/logic regressions
 * without a Windows machine.
 *
 * Cannot cover: WebView2 itself (native dialogs, navigation, the bridge).
 * That part is only reproducible on the user's Windows install.
 *
 * Usage:  node tests/selftest.js   (expects prepared fixtures in tests/build/)
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const B = path.join(__dirname, 'build');
const insertJs = fs.readFileSync(path.join(B, 'insert.js'), 'utf8');
const barJs = fs.readFileSync(path.join(B, 'bar.js'), 'utf8');
const autofillJs = fs.readFileSync(path.join(B, 'autofill.js'), 'utf8');
const article = JSON.parse(fs.readFileSync(path.join(B, 'article.json'), 'utf8'));

let failed = 0;
function check(name, cond, extra) {
  console.log((cond ? 'PASS  ' : 'FAIL  ') + name +
              (cond ? '' : '   <- ' + JSON.stringify(extra)));
  if (!cond) failed++;
}

function mkWindow(pathname, body) {
  const dom = new JSDOM('<!DOCTYPE html><body>' + body + '</body>', {
    runScripts: 'outside-only', pretendToBeVisual: true,
    url: 'https://vc.ru' + pathname,
  });
  const w = dom.window;
  w.HTMLElement.prototype.getBoundingClientRect = () =>
    ({ width: 200, height: 40, top: 0, left: 0, right: 200, bottom: 40 });
  Object.defineProperty(w.HTMLElement.prototype, 'offsetParent',
    { get() { return w.document.body; } });
  w.document.execCommand = () => false;

  // jsdom performs no real navigation and forbids replacing window.location
  // outright. Instead each script runs inside a wrapper whose `window` and
  // `location` are locals: a Proxy that forwards everything to the real
  // window except location, which is a stub recording navigation attempts.
  const nav = [];
  const loc = { pathname: pathname, hash: '', reload() { nav.push('reload'); } };
  Object.defineProperty(loc, 'href', {
    get() { return 'https://vc.ru' + pathname; },
    set(v) { nav.push(v); },
  });

  // Functions must keep their identity as constructors: bind() strips
  // .prototype, and the injected code reads HTMLInputElement.prototype.
  // So wrap in a Proxy that only fixes `this` on plain calls.
  const wrapped = new WeakMap();
  function wrap(fn, self) {
    if (wrapped.has(fn)) return wrapped.get(fn);
    const p = new Proxy(fn, {
      apply(t, thisArg, args) {
        return Reflect.apply(t, (thisArg === undefined || thisArg === proxy)
          ? self : thisArg, args);
      },
    });
    wrapped.set(fn, p);
    return p;
  }

  const proxy = new Proxy(w, {
    get(t, k) {
      if (k === 'location') return loc;
      const v = Reflect.get(t, k);
      return typeof v === 'function' ? wrap(v, t) : v;
    },
    set(t, k, v) {
      if (k === 'location') { nav.push(String(v)); return true; }
      t[k] = v; return true;
    },
    has(t, k) { return k === 'location' ? true : Reflect.has(t, k); },
  });

  w.__nav = nav;
  w.__eval = (code) =>
    w.eval('(function(window, location){' + code + '\n})')(proxy, loc);
  return w;
}

const EDITOR_DOM =
  '<textarea placeholder="Заголовок"></textarea>' +
  '<div contenteditable="true"></div>';

/* --- 1. document -> editor, already on /new --- */
function testInsertHere(done) {
  const w = mkWindow('/new', EDITOR_DOM);
  const sent = [];
  w.pywebview = { api: { convert_document(name, b64) {
    sent.push(name);
    return Promise.resolve({ ok: true, html: article.html,
      title: article.title, images: article.images, msg: 'Готово: ' + name });
  } } };
  w.__eval(insertJs); w.__eval(barJs);

  const fi = w.document.querySelector('input[type=file]');
  const blob = new w.Blob([Buffer.from('x')], { type: 'text/plain' });
  Object.defineProperty(fi, 'files',
    { value: [Object.assign(blob, { name: 'Статья.docx' })], configurable: true });
  fi.onchange();

  setTimeout(() => {
    const d = w.document;
    check('файл ушёл в конвертер', sent[0] === 'Статья.docx', sent);
    check('тело статьи вставлено',
      d.querySelector('[contenteditable]').innerHTML.length > 20);
    check('заголовок заполнен',
      d.querySelector('textarea').value === article.title,
      d.querySelector('textarea').value);
    check('лишней навигации нет', w.__nav.length === 0, w.__nav);
    done();
  }, 2500);
}

/* --- 2. from the home page: stash + navigate --- */
function testInsertViaNav(done) {
  const w = mkWindow('/', '<div></div>');
  w.pywebview = { api: { convert_document(name) {
    return Promise.resolve({ ok: true, html: article.html,
      title: article.title, images: article.images, msg: 'ok' });
  } } };
  w.__eval(insertJs); w.__eval(barJs);
  const fi = w.document.querySelector('input[type=file]');
  const blob = new w.Blob([Buffer.from('x')], { type: 'text/plain' });
  Object.defineProperty(fi, 'files',
    { value: [Object.assign(blob, { name: 'a.docx' })], configurable: true });
  fi.onchange();
  setTimeout(() => {
    check('переход в редактор', w.__nav.indexOf('https://vc.ru/new') !== -1, w.__nav);
    check('статья отложена до редактора',
      !!w.sessionStorage.getItem('vcphPending'));
    done();
  }, 2000);
}

/* --- 3. converter error is surfaced, not swallowed --- */
function testError(done) {
  const w = mkWindow('/new', EDITOR_DOM);
  w.pywebview = { api: { convert_document() {
    return Promise.resolve({ ok: false, msg: 'Ошибка чтения: битый файл' });
  } } };
  w.__eval(insertJs); w.__eval(barJs);
  const fi = w.document.querySelector('input[type=file]');
  const blob = new w.Blob([Buffer.from('x')], { type: 'text/plain' });
  Object.defineProperty(fi, 'files',
    { value: [Object.assign(blob, { name: 'bad.docx' })], configurable: true });
  fi.onchange();
  setTimeout(() => {
    const st = w.document.getElementById('vcph-status').textContent;
    check('ошибка показана пользователю', /Ошибка чтения/.test(st), st);
    check('редактор не испорчен',
      w.document.querySelector('[contenteditable]').innerHTML.length < 20);
    done();
  }, 1200);
}

/* --- 4. buttons never call Python for navigation --- */
function testNavIsPureJs(done) {
  const w = mkWindow('/', '<div></div>');
  let bridgeCalls = 0;
  w.pywebview = { api: new Proxy({}, { get() {
    return () => { bridgeCalls++; return Promise.resolve({ ok: true }); };
  } }) };
  w.__eval(insertJs); w.__eval(barJs);
  const d = w.document;
  d.getElementById('vcph-editor').onclick();
  d.getElementById('vcph-login').onclick();
  setTimeout(() => {
    check('навигация без обращений к программе', bridgeCalls === 0, bridgeCalls);
    check('оба перехода выполнены', w.__nav.length === 2, w.__nav);
    done();
  }, 300);
}

/* --- 5. autofill: fills the modal, spares the search box, no auto-click --- */
function testAutofill(done) {
  const w = mkWindow('/', '<input id="site-search" type="text" placeholder="Поиск"><div id="root"></div>');
  const remembered = [];
  w.pywebview = { api: { remember_login(e, p) {
    remembered.push([e, p]); return Promise.resolve(true);
  } } };
  w.__eval(autofillJs);
  setTimeout(() => {
    w.document.getElementById('root').innerHTML =
      '<div role="dialog"><input id="mail" type="text" placeholder="Почта">' +
      '<input id="pw" type="password" placeholder="Пароль">' +
      '<button id="go">Войти</button></div>';
  }, 800);
  setTimeout(() => {
    const d = w.document;
    check('почта подставлена', d.getElementById('mail').value.indexOf('@') > 0,
      d.getElementById('mail').value);
    check('пароль подставлен', d.getElementById('pw').value.length > 0);
    check('поиск не тронут', d.getElementById('site-search').value === '');
    check('скрипт не нажимает Войти сам', remembered.length === 0, remembered);
    d.getElementById('pw').value = 'NewPass777';
    d.getElementById('go').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    setTimeout(() => {
      check('введённый пароль запомнен',
        remembered.length === 1 && remembered[0][1] === 'NewPass777', remembered);
      done();
    }, 200);
  }, 2200);
}

const queue = [testInsertHere, testInsertViaNav, testError,
               testNavIsPureJs, testAutofill];
(function next() {
  const t = queue.shift();
  if (!t) {
    console.log(failed ? '\nПРОВАЛЕНО проверок: ' + failed : '\nВсе проверки пройдены');
    process.exit(failed ? 1 : 0);
  }
  t(next);
})();
