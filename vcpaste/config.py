"""
Configurable endpoints and selectors for VC.ru.

If VC.ru changes its markup, only THIS file needs editing.
All selectors are lists tried in order until one matches.
"""

# The window opens straight on this page. No local start screen, so there
# is no Python-side navigation at startup (that step used to hang).
HOME_URL = "https://vc.ru/"

# Where the editor for a new post lives.
EDITOR_URL = "https://vc.ru/new"

# Deep link that opens VC.ru's auth modal on the e-mail step, with both
# e-mail and password fields visible at once. Used by the "Войти" button
# in the top bar.
LOGIN_URL = "https://vc.ru/?modal=auth/login/email"

# Caption of the modal's submit button (matched by text in JS, since CSS
# has no text matching). Lowercase comparison.
LOGIN_SUBMIT_TEXTS = ["войти", "log in", "sign in"]

# CSS selectors for the login form fields (tried in order).
# Placeholder-based selectors come FIRST: the real field is labelled
# "Почта" and may be type="text" rather than type="email".
LOGIN_EMAIL_SELECTORS = [
    'input[placeholder*="Почта" i]',
    'input[placeholder*="почт" i]',
    'input[placeholder*="mail" i]',
    '[class*="modal"] input[type="email"]',
    '[class*="auth"] input[type="email"]',
    '[role="dialog"] input[type="email"]',
    'input[type="email"]',
    'input[name="email"]',
    'input[name="login"]',
    'input[autocomplete="username"]',
]
LOGIN_PASSWORD_SELECTORS = [
    'input[type="password"]',
    'input[placeholder*="Пароль" i]',
    'input[placeholder*="парол" i]',
    '[class*="modal"] input[type="password"]',
    '[role="dialog"] input[type="password"]',
    'input[name="password"]',
    'input[autocomplete="current-password"]',
]
# NOTE: ':has-text()' is a Playwright-only selector and throws in a real
# browser, which aborts querySelector loops. Valid CSS only here; button
# captions are matched by text via LOGIN_SUBMIT_TEXTS.
LOGIN_SUBMIT_SELECTORS = [
    '[class*="modal"] button[type="submit"]',
    '[class*="auth"] button[type="submit"]',
    '[role="dialog"] button[type="submit"]',
    'button[type="submit"]',
    'form button',
]

# CSS selectors for the editor's editable area (tried in order).
EDITOR_AREA_SELECTORS = [
    'div[contenteditable="true"]',
    '[data-editor] [contenteditable]',
    '.editor [contenteditable]',
    'article [contenteditable]',
    'textarea',
]

# Title field of the editor (optional).
EDITOR_TITLE_SELECTORS = [
    'textarea[placeholder*="аголов" i]',
    'input[placeholder*="аголов" i]',
    'textarea[placeholder*="итле" i]',
    'h1[contenteditable="true"]',
]

WINDOW_TITLE = "VC Paste Helper"
WINDOW_W = 1280
WINDOW_H = 820
