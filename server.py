#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
城池战争 - 服务器启动器
负责查找端口、启动 Flask-SocketIO 服务器
可被 run.py 在后台线程中调用，也可独立运行
"""

import os
import socket
import threading
import time


def get_lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = info[4][0]
            if addr not in ips and not addr.startswith('127.'):
                ips.append(addr)
    except Exception:
        pass
    return ips


def find_available_port(start_port=5000, max_tries=100):
    for port in range(start_port, start_port + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    return start_port


def wait_for_server(host, port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.3)
    return False


def is_game_server(host, port):
    try:
        import urllib.request
        resp = urllib.request.urlopen(f'http://{host}:{port}/', timeout=3)
        html = resp.read().decode('utf-8', errors='ignore')
        return '城池战争' in html
    except Exception:
        return False


def start_server(port, block=False):
    from app import app, socketio

    if block:
        socketio.run(
            app,
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False,
            log_output=True,
            allow_unsafe_werkzeug=True,
        )
    else:
        t = threading.Thread(
            target=socketio.run,
            args=(app,),
            kwargs={
                'host': '0.0.0.0',
                'port': port,
                'debug': False,
                'use_reloader': False,
                'log_output': False,
                'allow_unsafe_werkzeug': True,
            },
            daemon=True,
        )
        t.start()
        return t


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='城池战争 CityWar - 服务器启动器')
    parser.add_argument('--port', type=int, default=None, help='指定端口号（默认自动选择）')
    args = parser.parse_args()

    preferred_port = args.port or int(os.environ.get('PORT', 5000))
    # Render 等云平台要求绑定到指定端口，不允许递增
    if os.environ.get('PORT'):
        port = preferred_port
    else:
        port = find_available_port(preferred_port)

    lan_ips = get_lan_ips()

    lines = [
        '╔═════════════════════════════════════════════════════════╗',
        '║                                                         ║',
        '║   城池战争 CityWar - 服务器已启动                       ║',
        '║                                                         ║',
        f'║   本机访问: http://localhost:{port:<24}║',
    ]
    for ip in lan_ips:
        lines.append(f'║   局域网:   http://{ip}:{port:<{27 - len(ip)}}║')
    lines += [
        '║                                                         ║',
        '╚═════════════════════════════════════════════════════════╝',
    ]
    print('\n'.join(lines))

    start_server(port, block=True)
