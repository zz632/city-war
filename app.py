#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
城池战争游戏 - Flask 主应用
CityWar Game - Flask Main Application
"""

import os
import uuid
import hashlib
import smtplib
import ssl
import random
import time
import json
import functools
from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for
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
users = {}  # username -> {password_hash, display_name, email}
sessions = {}  # session_token -> username

# ===== 验证码存储 =====
verification_codes = {}  # email -> {code, expires, last_sent}

# ===== 用户数据持久化 =====
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')


def _load_users():
    """启动时从 data/users.json 加载用户数据"""
    global users
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except (json.JSONDecodeError, IOError):
            users = {}


def _save_users():
    """用户数据变更时自动保存到 data/users.json"""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


# 启动时加载用户数据
_load_users()

# ===== 管理员配置 =====
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'zz632')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Qiqi130102')
admin_sessions = {}  # admin_token -> True


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


def admin_required(f):
    """管理员权限验证装饰器"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        admin_token = request.cookies.get('admin_token', '')
        if not admin_token or admin_token not in admin_sessions:
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated


@app.before_request
def require_login_online():
    """在线模式下，未登录用户只能访问登录相关页面"""
    if not ONLINE_MODE:
        return
    # 允许的路径（无需登录）
    path = request.path
    if path.startswith('/api/auth/'):
        return
    if path.startswith('/admin/'):
        return
    if path.startswith('/static/'):
        return
    # Socket.IO 握手和 polling 请求放行（WebSocket 本身无法带 Authorization）
    if path.startswith('/socket.io/'):
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


@app.route('/api/auth/send_code', methods=['POST'])
def api_send_code():
    """发送邮箱验证码"""
    data = request.get_json() or {}
    email = data.get('email', '').strip()

    if not email:
        return jsonify({'success': False, 'message': '邮箱不能为空'}), 400

    # 60秒防刷
    now = time.time()
    if email in verification_codes:
        last_sent = verification_codes[email].get('last_sent', 0)
        if now - last_sent < 60:
            remaining = int(60 - (now - last_sent))
            return jsonify({'success': False, 'message': f'请{remaining}秒后再试'}), 429

    # 生成6位随机验证码
    code = str(random.randint(100000, 999999))
    verification_codes[email] = {
        'code': code,
        'expires': now + 300,  # 5分钟有效期
        'last_sent': now
    }

    # SMTP配置
    smtp_server = os.environ.get('SMTP_SERVER', '')
    smtp_port = int(os.environ.get('SMTP_PORT', '465'))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_password = os.environ.get('SMTP_PASSWORD', '')
    smtp_from = os.environ.get('SMTP_FROM', smtp_user)

    if not smtp_server or not smtp_user or not smtp_password:
        # SMTP未配置，开发模式：验证码直接在响应中返回
        return jsonify({'success': True, 'message': '验证码已发送（开发模式）', 'dev_code': code})

    # 发送邮件
    try:
        msg = f"Subject: 城池战争 - 邮箱验证码\n\n您的验证码是：{code}\n\n验证码5分钟内有效，请勿泄露给他人。"
        if smtp_port == 465:
            # SSL连接
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, email, msg.encode('utf-8'))
        else:
            # STARTTLS连接
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_from, email, msg.encode('utf-8'))
        return jsonify({'success': True, 'message': '验证码已发送到您的邮箱'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'邮件发送失败：{str(e)}'}), 500


@app.route('/api/auth/check_email', methods=['POST'])
def api_check_email():
    """检查邮箱是否已注册"""
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'success': False, 'message': '邮箱不能为空'}), 400
    # 遍历用户检查邮箱是否已注册
    for u in users.values():
        if u.get('email') == email:
            return jsonify({'success': True, 'registered': True})
    return jsonify({'success': True, 'registered': False})


@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    display_name = data.get('display_name', '').strip() or username
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
    if len(username) < 2 or len(username) > 12:
        return jsonify({'success': False, 'message': '用户名需要2-12个字符'}), 400
    if len(password) < 4:
        return jsonify({'success': False, 'message': '密码至少4个字符'}), 400
    if username in users:
        return jsonify({'success': False, 'message': '用户名已被占用'}), 400

    # 在线模式下必须验证邮箱验证码
    if ONLINE_MODE:
        if not email or not code:
            return jsonify({'success': False, 'message': '邮箱和验证码不能为空'}), 400
        # 检查邮箱是否已被注册
        for u in users.values():
            if u.get('email') == email:
                return jsonify({'success': False, 'message': '该邮箱已被注册'}), 400
        # 验证验证码
        if email not in verification_codes:
            return jsonify({'success': False, 'message': '请先发送验证码'}), 400
        stored = verification_codes[email]
        if time.time() > stored['expires']:
            del verification_codes[email]
            return jsonify({'success': False, 'message': '验证码已过期，请重新发送'}), 400
        if stored['code'] != code:
            return jsonify({'success': False, 'message': '验证码错误'}), 400
        # 验证码正确后删除
        del verification_codes[email]

    users[username] = {
        'password_hash': _hash_password(password),
        'display_name': display_name,
        'email': email,
    }
    _save_users()
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


# ===== 后台管理系统 =====

@app.route('/admin/login', methods=['GET'])
def admin_login_page():
    """管理员登录页"""
    # 如果已登录则跳转
    admin_token = request.cookies.get('admin_token', '')
    if admin_token and admin_token in admin_sessions:
        return redirect('/admin/')
    return render_template('admin.html', page='login')


@app.route('/admin/login', methods=['POST'])
def admin_login_submit():
    """管理员登录验证"""
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        admin_token = uuid.uuid4().hex
        admin_sessions[admin_token] = True
        resp = make_response(jsonify({'success': True}))
        resp.set_cookie('admin_token', admin_token, httponly=True, max_age=86400)
        return resp
    return jsonify({'success': False, 'message': '用户名或密码错误'}), 401


@app.route('/admin/')
@admin_required
def admin_panel():
    """管理面板"""
    return render_template('admin.html', page='panel')


@app.route('/admin/api/users', methods=['GET'])
@admin_required
def admin_api_users():
    """获取所有用户列表"""
    user_list = []
    for username, info in users.items():
        user_list.append({
            'username': username,
            'display_name': info.get('display_name', ''),
            'email': info.get('email', '')
        })
    return jsonify({'success': True, 'users': user_list})


@app.route('/admin/api/rooms', methods=['GET'])
@admin_required
def admin_api_rooms():
    """获取所有房间列表"""
    room_list = []
    for room_id, room in room_manager.rooms.items():
        player_count = len([p for p in room.players.values() if not p.is_spectator])
        room_list.append({
            'id': room_id,
            'name': room.name,
            'player_count': player_count,
            'phase': room.game_state.phase.value if room.game_state else 'waiting'
        })
    return jsonify({'success': True, 'rooms': room_list})


@app.route('/admin/user/<username>/delete', methods=['POST'])
@admin_required
def admin_delete_user(username):
    """删除用户"""
    if username not in users:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    # 删除用户的session
    tokens_to_remove = [t for t, u in sessions.items() if u == username]
    for t in tokens_to_remove:
        del sessions[t]
    del users[username]
    _save_users()
    return jsonify({'success': True, 'message': f'用户 {username} 已删除'})


@app.route('/admin/room/<room_id>/delete', methods=['POST'])
@admin_required
def admin_delete_room(room_id):
    """删除房间"""
    if room_id not in room_manager.rooms:
        return jsonify({'success': False, 'message': '房间不存在'}), 404
    # 直接从 room_manager.rooms 中删除
    del room_manager.rooms[room_id]
    return jsonify({'success': True, 'message': f'房间 {room_id} 已删除'})


@app.errorhandler(404)
def not_found(error):
    return _error_html(404, '页面未找到', '你访问的页面不存在，请检查地址是否正确。'), 404


@app.errorhandler(500)
def internal_error(error):
    return _error_html(500, '服务器错误', '服务器遇到了问题，请稍后重试。'), 500
