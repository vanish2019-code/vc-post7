# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# --- Collect pythonnet + clr_loader completely ---
# pywebview on Windows uses pythonnet (clr) to talk to WinForms/WebView2.
# PyInstaller must bundle Python.Runtime.dll and the runtimeconfig files,
# otherwise .NET fails with "Failed to resolve Python.Runtime.Loader".
datas = [('vcpaste/assets/app.ico', 'vcpaste/assets'),
         ('vcpaste/assets/app.png', 'vcpaste/assets')]
binaries = []
hiddenimports = ['webview', 'mammoth', 'clr_loader', 'proxy_tools', 'clr',
                 'bottle']

for pkg in ('pythonnet', 'clr_loader'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# pywebview ships platform backends that are imported dynamically.
hiddenimports += collect_submodules('webview')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'PIL', 'test', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='VC Paste Helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can corrupt .NET DLLs (Python.Runtime.dll)
    console=False,
    icon='vcpaste/assets/app.ico',
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name='VC Paste Helper',
)
