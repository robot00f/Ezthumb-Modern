# -*- mode: python ; coding: utf-8 -*-
import os
import glob
import customtkinter
import tkinterdnd2

customtkinter_path = os.path.dirname(customtkinter.__file__)
tkinterdnd2_path = os.path.dirname(tkinterdnd2.__file__)

bin_dir = 'bin'
if not os.path.exists(bin_dir):
    bin_dir = r'C:\Program Files (x86)\Ezthumb'

binaries = []
if os.path.exists(bin_dir):
    for dll in glob.glob(os.path.join(bin_dir, "*.dll")):
        binaries.append((dll, '.'))
    for exe_name in ["ezthumb.exe", "ffmpeg.exe", "ffprobe.exe"]:
        exe_path = os.path.join(bin_dir, exe_name)
        if os.path.exists(exe_path):
            binaries.append((exe_path, '.'))

a = Analysis(
    ['EzthumbWin_CTk.py'],
    pathex=[],
    binaries=binaries,
    datas=[(customtkinter_path, 'customtkinter/'), (tkinterdnd2_path, 'tkinterdnd2/')],
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
    icon=['favicon.ico'],
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
