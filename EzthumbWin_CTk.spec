# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['F:\\EzthumbWin_CTk.py'],
    pathex=[],
    binaries=[('C:\\Program Files (x86)\\Ezthumb\\*.dll', '.'), ('C:\\Program Files (x86)\\Ezthumb\\ezthumb.exe', '.'), ('C:\\Program Files (x86)\\Ezthumb\\ffmpeg.exe', '.'), ('C:\\Program Files (x86)\\Ezthumb\\ffprobe.exe', '.')],
    datas=[('C:\\Users\\Legend\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\customtkinter', 'customtkinter/'), ('C:\\Users\\Legend\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\tkinterdnd2', 'tkinterdnd2/')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EzthumbWin_CTk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['F:\\favicon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EzthumbWin_CTk',
)
