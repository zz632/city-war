#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
城池战争游戏 - Flask 主应用
CityWar Game - Flask Main Application
"""

import os
import uuid
import hashlib
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'citywar-secret-key-2024')
app.config['DEBUG'] = False
app.config['PREFERRED_URL_SCHEME'] = 'http'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60, ping_interval=25)

from game.manager import RoomManager
from game.models import Player, Room, GameState
from websocket.events import init_socket_events

room_manager = RoomManager()

init_socket_events(socketio, room_manager)

# ===== 在线模式 & 用户系统 =====
ONLINE_MODE = os.environ.get('ONLINE_MODE', '').lower() in ('1', 'true', 'yes')
users = {}  # username -> {password_hash, display_name}
sessions = {}  # session_token -> username


def _hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def _check_login():
    """检查是否已登录，返回 username 或 None"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '')
    if token and token in sessions:
        return sessions[token]
    return None


@app.before_request
def require_login_online():
    """在线模式下，未登录用户只能访问登录相关页面"""
    if not ONLINE_MODE:
        return
    # 允许的路径（无需登录）
    path = request.path
    if path.startswith('/api/auth/'):
        return
    if path.startswith('/static/'):
        return
    # 检查登录状态
    username = _check_login()
    if username:
        return
    # 未登录：页面请求返回首页（让前端显示登录），API 请求返回 401
    if path.startswith('/api/'):
        return jsonify({'success': False, 'message': '请先登录'}), 401
    # 页面请求放行，由前端判断显示登录界面
    return None


@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    display_name = data.get('display_name', '').strip() or username

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
    if len(username) < 2 or len(username) > 12:
        return jsonify({'success': False, 'message': '用户名需要2-12个字符'}), 400
    if len(password) < 4:
        return jsonify({'success': False, 'message': '密码至少4个字符'}), 400
    if username in users:
        return jsonify({'success': False, 'message': '用户名已被占用'}), 400

    users[username] = {
        'password_hash': _hash_password(password),
        'display_name': display_name,
    }
    # 自动登录
    token = uuid.uuid4().hex
    sessions[token] = username
    return jsonify({'success': True, 'token': token, 'username': username, 'display_name': display_name})


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    user = users.get(username)
    if not user or user['password_hash'] != _hash_password(password):
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    token = uuid.uuid4().hex
    sessions[token] = username
    return jsonify({'success': True, 'token': token, 'username': username, 'display_name': user['display_name']})


@app.route('/api/auth/check', methods=['GET'])
def api_auth_check():
    username = _check_login()
    if username and username in users:
        return jsonify({'success': True, 'username': username, 'display_name': users[username]['display_name']})
    return jsonify({'success': False})


@app.route('/api/auth/online_mode', methods=['GET'])
def api_online_mode():
    return jsonify({'online': ONLINE_MODE})

ERROR_PAGE_STYLE = '''
<style>
:root {
    --bg: #0c1222;
    --bg-card: #151d30;
    --border: #243050;
    --text: #e8ecf4;
    --text-dim: #7a8baa;
    --primary: #3b82f6;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Noto Sans SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
}
.card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 48px 40px;
    text-align: center;
    max-width: 420px;
    width: 90%;
}
.error-code {
    font-size: 64px;
    font-weight: 800;
    color: var(--primary);
    line-height: 1;
    margin-bottom: 16px;
}
.error-title {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 8px;
}
.error-desc {
    font-size: 14px;
    color: var(--text-dim);
    line-height: 1.6;
}
</style>
'''


def _error_html(code, title, desc):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{code} - {title}</title>{ERROR_PAGE_STYLE}</head>
<body>
<div class="card">
    <div class="error-code">{code}</div>
    <div class="error-title">{title}</div>
    <div class="error-desc">{desc}</div>
</div>
</body>
</html>'''


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/lobby/<room_id>')
def lobby(room_id):
    return render_template('lobby.html', room_id=room_id)


@app.route('/game/<room_id>')
def game(room_id):
    return render_template('game.html', room_id=room_id)


@app.route('/api/rooms', methods=['GET', 'POST'])
def api_rooms():
    if request.method == 'GET':
        return jsonify({'success': True, 'rooms': room_manager.get_public_rooms()})

    data = request.get_json() or {}
    player_name = data.get('player_name', '').strip()
    if not player_name:
        return jsonify({'success': False, 'message': '名字不能为空'}), 400

    client_ip = request.remote_addr
    result = room_manager.create_room(player_name, 'p_' + uuid.uuid4().hex[:12], client_ip)
    if result[0] is None:
        return jsonify({'success': False, 'message': result[1]}), 403

    room_id, player = result
    return jsonify({
        'success': True,
        'room': {'id': room_id, 'name': room_manager.rooms[room_id].name},
        'player': player.to_dict()
    })


@app.route('/api/rooms/<room_id>/join', methods=['POST'])
def api_join_room(room_id):
    data = request.get_json() or {}
    player_name = data.get('player_name', '').strip()
    if not player_name:
        return jsonify({'success': False, 'message': '名字不能为空'}), 400

    client_ip = request.remote_addr
    player = room_manager.join_room(room_id, player_name, 'p_' + uuid.uuid4().hex[:12], client_ip)
    if not player:
        return jsonify({'success': False, 'message': '房间不存在、已满或该设备已在此房间中'}), 400

    return jsonify({
        'success': True,
        'room': {'id': room_id},
        'player': player.to_dict(),
        'is_spectator': player.is_spectator
    })


@app.route('/api/room/<room_id>/status', methods=['GET'])
def get_room_status(room_id):
    room = room_manager.get_room(room_id)
    if not room:
        return jsonify({'success': False, 'message': '房间不存在'}), 404

    return jsonify({
        'success': True,
        'room': room.to_dict()
    })


@app.errorhandler(404)
def not_found(error):
    return _error_html(404, '页面未找到', '你访问的页面不存在，请检查地址是否正确。'), 404


@app.errorhandler(500)
def internal_error(error):
    return _error_html(500, '服务器错误', '服务器遇到了问题，请稍后重试。'), 500
