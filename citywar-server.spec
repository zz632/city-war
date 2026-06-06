# -*- mode: python ; coding: utf-8 -*-
"""城池战争 - 服务器打包配置"""

import os

block_cipher = None

ROOT = os.path.abspath('.')

datas = [
    (os.path.join(ROOT, 'templates'), 'templates'),
    (os.path.join(ROOT, 'static'), 'static'),
]

hiddenimports = [
    'flask_socketio',
    'engineio',
    'engineio.async_drivers.threading',
    'socketio',
    'simple_websocket',
    'wsproto',
    'h11',
    'dnspython',
    'bidict',
]

a = Analysis(
    [os.path.join(ROOT, 'server.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['webview'],
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
    name='citywar-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
