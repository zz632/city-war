# -*- mode: python ; coding: utf-8 -*-
"""城池战争 - PyInstaller 打包配置"""

import os
import sys

block_cipher = None

# 获取项目根目录
ROOT = os.path.abspath('.')

# 需要打包的数据文件
datas = [
    (os.path.join(ROOT, 'templates'), 'templates'),
    (os.path.join(ROOT, 'static'), 'static'),
]

# 隐藏导入（PyInstaller 可能检测不到的模块）
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
    [os.path.join(ROOT, 'app.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
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
    name='citywar',
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
