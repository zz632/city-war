#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
城池战争 - 游戏窗口启动器
使用 pywebview 将游戏嵌入原生桌面窗口，并阻止多开
支持本机/局域网连接
"""

import os
import sys
import socket
import threading
import webbrowser
import webview

from server import wait_for_server

LOCK_PORT = 15432
ONLINE_URL = 'https://zz632-city-war.hf.space'
WINDOW_TITLE = '城池战争 CityWar'
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 750
WINDOW_MIN_SIZE = (800, 600)


def acquire_single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


_lock = None


def _get_window():
    return webview.windows[0] if webview.windows else None


class GameApi:
    def select_local(self):
        w = _get_window()
        if w:
            w.evaluate_js('showPage("connect")')

    def select_online(self):
        w = _get_window()
        if w:
            w.set_title(WINDOW_TITLE)
            w.load_url(ONLINE_URL)

    def go_back(self):
        w = _get_window()
        if w:
            w.evaluate_js('showPage("mode")')

    def connect(self, host, port):
        t = threading.Thread(target=self._do_connect, args=(host, port), daemon=True)
        t.start()

    def cancel(self):
        w = _get_window()
        if w:
            w.destroy()

    def open_external(self, url):
        """用系统浏览器打开外部链接"""
        if url and url.startswith('http'):
            webbrowser.open(url)

    def _do_connect(self, host, port):
        self._set_status('正在连接...')

        if not wait_for_server(host, port, timeout=10):
            self._set_status('连接超时，请确认服务器是否已启动')
            return

        w = _get_window()
        if w:
            w.set_title(WINDOW_TITLE)
            w.load_url(f'http://{host}:{port}')

    def _set_status(self, text):
        w = _get_window()
        if w:
            try:
                w.evaluate_js(f'document.getElementById("status").innerText = "{text}"')
            except Exception:
                pass


def _on_closing():
    global _lock
    if _lock:
        _lock.close()


def _on_loaded():
    w = _get_window()
    if not w:
        return
    try:
        url = w.get_url()
    except Exception:
        return
    if not url:
        return
    # 拦截 target="_blank" 链接，用系统浏览器打开而不是弹新窗口
    try:
        w.evaluate_js('''
            document.addEventListener('click', function(e) {
                var a = e.target.closest('a');
                if (a && a.target === '_blank') {
                    e.preventDefault();
                    window.pywebview.api.open_external(a.href);
                }
            });
        ''')
    except Exception:
        pass
    if '/lobby/' in url or '/game/' in url:
        w.resize(WINDOW_WIDTH, WINDOW_HEIGHT)


CONNECT_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>城池战争</title>
<style>
:root {
    --bg: #F5F5F7;
    --surface: #FFFFFF;
    --surface-hover: #F8F8FA;
    --border: rgba(0,0,0,0.08);
    --border-strong: rgba(0,0,0,0.15);
    --text: #1D1D1F;
    --text-secondary: #6E6E73;
    --text-tertiary: #AEAEB2;
    --primary: #007AFF;
    --primary-hover: #0062CC;
    --shadow: 0 2px 8px rgba(0,0,0,0.06), 0 0 1px rgba(0,0,0,0.04);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.08), 0 0 1px rgba(0,0,0,0.06);
    --radius: 12px;
    --radius-sm: 8px;
    --radius-lg: 16px;
    --radius-xl: 20px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', 'PingFang SC', sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.47;
    -webkit-font-smoothing: antialiased;
}
.page-wrap { max-width: 480px; margin: 0 auto; padding: 60px 20px 40px; }
.home-header { text-align: center; margin-bottom: 36px; }
.home-header .logo-icon { width: 48px; height: 48px; stroke: var(--primary); fill: none; stroke-width: 1.3; margin-bottom: 14px; }
.page-title { font-size: 32px; font-weight: 700; text-align: center; margin-bottom: 4px; letter-spacing: -.3px; }
.page-subtitle { font-size: 13px; color: var(--text-tertiary); text-align: center; margin-bottom: 32px; letter-spacing: 2px; text-transform: uppercase; }

.card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 24px; margin-bottom: 16px;
    box-shadow: var(--shadow);
}

.field { margin-bottom: 14px; }
.field-label { display: flex; align-items: center; gap: 5px; font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 5px; }
.field-label svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 1.8; flex-shrink: 0; }
.field-input {
    width: 100%; padding: 11px 14px;
    background: var(--surface); border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm); color: var(--text); font-size: 16px; outline: none;
    transition: all .15s;
}
.field-input::placeholder { color: var(--text-tertiary); }
.field-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(0,122,255,.15); }

.btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 11px 22px; border: none; border-radius: var(--radius-sm);
    font-size: 16px; font-weight: 600; cursor: pointer; transition: all .15s; white-space: nowrap;
}
.btn:active { transform: scale(.97); }
.btn svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 1.8; flex-shrink: 0; }
.btn-primary { background: var(--primary); color: #fff; box-shadow: 0 1px 3px rgba(0,122,255,.25); }
.btn-primary:hover { background: var(--primary-hover); }
.btn-block { width: 100%; }
.btn-lg { padding: 14px 28px; font-size: 17px; border-radius: var(--radius); }

.mode-btn {
    width: 100%; padding: 18px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--text); cursor: pointer;
    transition: all .15s; display: flex; align-items: center; gap: 14px;
    font-size: 16px; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,.04);
}
.mode-btn svg { width: 26px; height: 26px; stroke: var(--primary); fill: none; stroke-width: 1.5; flex-shrink: 0; }
.mode-btn-text { text-align: left; }
.mode-btn-desc { font-size: 12px; font-weight: 400; color: var(--text-secondary); margin-top: 2px; }
.mode-btn:hover { background: var(--surface-hover); border-color: var(--border-strong); }
.mode-btn + .mode-btn { margin-top: 10px; }
#status { color: var(--primary); font-size: 13px; margin-top: 12px; min-height: 20px; text-align: center; }

.page-section { display: none; }
.page-section.active { display: block; }
.back-btn {
    position: absolute; top: 12px; left: 12px; width: 34px; height: 34px;
    display: flex; align-items: center; justify-content: center;
    background: var(--surface-hover); border: none; border-radius: 10px;
    cursor: pointer; color: var(--text-secondary); transition: all .15s; padding: 0;
}
.back-btn svg { width: 20px; height: 20px; stroke: currentColor; fill: none; stroke-width: 2; }
.back-btn:hover { color: var(--text); background: var(--border-strong); }
</style>
</head>
<body>
<div class="page-wrap">
    <div class="home-header">
        <svg class="logo-icon" viewBox="0 0 24 24">
            <path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-6a2 2 0 012-2h2a2 2 0 012 2v6"/>
        </svg>
        <div class="page-title">城池战争</div>
        <div class="page-subtitle">CityWar</div>
    </div>
    <div id="page-mode" class="page-section active">
        <div class="card">
            <button class="mode-btn" onclick="window.pywebview.api.select_online()">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10A15.3 15.3 0 0112 2z"/></svg>
                <div class="mode-btn-text">在线游戏<div class="mode-btn-desc">连接远程服务器，与全网玩家对战</div></div>
            </button>
            <button class="mode-btn" onclick="window.pywebview.api.select_local()">
                <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
                <div class="mode-btn-text">本地游戏<div class="mode-btn-desc">局域网或本机对战</div></div>
            </button>
        </div>
    </div>
    <div id="page-connect" class="page-section">
        <div class="card" style="position:relative;padding-top:48px">
            <button class="back-btn" onclick="window.pywebview.api.go_back()">
                <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>
            </button>
            <div class="field">
                <label class="field-label">
                    <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
                    <span>服务器地址</span>
                </label>
                <input type="text" id="host" class="field-input" value="localhost" placeholder="IP 或 localhost">
            </div>
            <div class="field">
                <label class="field-label">
                    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                    <span>端口号</span>
                </label>
                <input type="text" id="port" class="field-input" value="5000" placeholder="5000">
            </div>
            <button class="btn btn-primary btn-block btn-lg" onclick="doConnect()">
                <svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                <span>连接</span>
            </button>
            <p id="status"></p>
        </div>
    </div>
</div>
<script>
function showPage(name) {
    document.querySelectorAll('.page-section').forEach(function(el) { el.classList.remove('active'); });
    document.getElementById('page-' + name).classList.add('active');
}
function doConnect() {
    var host = document.getElementById('host').value.trim() || 'localhost';
    var port = parseInt(document.getElementById('port').value.trim()) || 5000;
    document.getElementById('status').innerText = '正在连接...';
    window.pywebview.api.connect(host, port);
}
document.addEventListener('keydown', function(e) {
    var connectPage = document.getElementById('page-connect');
    if (connectPage.classList.contains('active') && e.key === 'Enter') doConnect();
});
</script>
</body>
</html>'''


def main():
    global _lock
    lock = acquire_single_instance()
    if lock is None:
        print('城池战争已在运行中，不可多开。')
        sys.exit(0)

    _lock = lock

    window = webview.create_window(
        title='城池战争',
        html=CONNECT_HTML,
        width=480,
        height=720,
        min_size=(400, 600),
        resizable=True,
        text_select=False,
        js_api=GameApi(),
    )

    window.events.closing += _on_closing
    window.events.loaded += _on_loaded

    webview.start(debug=False)

    sys.exit(0)


if __name__ == '__main__':
    main()
