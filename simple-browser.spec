# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect data files for QtWebEngine
qt_webengine_datas = []
try:
    qt_webengine_datas = collect_data_files('PyQt6', includes=['QtWebEngine', 'QtWebEngineCore'])
except:
    pass

# Collect all required modules
hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui', 
    'PyQt6.QtWidgets',
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineCore',
    'PyQt6.QtWebEngine',
    'requests',
    'yt_dlp',
    'streamlink',
    'ffmpeg',
    'ffmpeg_python',
    'urllib.parse',
    'json',
    'os',
    're',
    'time',
    'datetime',
    'threading',
    'queue',
    'subprocess',
    'platform',
    'shutil',
    'pathlib',
    'utils'
]

# Add FFmpeg binaries
ffmpeg_binaries = [
    ('ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe', '.'),
    ('ffmpeg-master-latest-win64-gpl/bin/ffplay.exe', '.'),
    ('ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe', '.')
]

# Add streamlink plugins
try:
    streamlink_plugins = collect_submodules('streamlink.plugins')
    hiddenimports.extend(streamlink_plugins)
except:
    pass

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=qt_webengine_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PrivateBrowser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version='version_info.txt' if os.path.exists('version_info.txt') else None
)
