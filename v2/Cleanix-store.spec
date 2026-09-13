# -*- mode: python ; coding: utf-8 -*-
# onedir build for the MSIX package: starts faster than onefile and needs no temp extraction
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(ROOT, 'Cleanix.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, 'assets', name), 'assets')
           for name in ('icon.ico', 'logo_44.png', 'logo_66.png', 'logo_88.png')],
    hiddenimports=['send2trash'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['win32ui', 'dde', 'pywin'],
    noarchive=False,
    optimize=0,
)
# pywin32's MFC GUI and Tcl timezone data are never used by the app
a.binaries = [b for b in a.binaries if 'Pythonwin' not in b[0] and 'mfc140' not in b[0].lower()]
a.datas = [d for d in a.datas if 'tzdata' not in d[0] and not d[0].startswith('Pythonwin')]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Cleanix',
    icon=os.path.join(ROOT, 'assets', 'icon.ico'),
    version=os.path.join(SPECPATH, 'version_info.txt'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Cleanix',
)
