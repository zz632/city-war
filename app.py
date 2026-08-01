#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
城池战争游戏 - Flask 主应用
CityWar Game - Flask Main Application
"""

import os
import uuid
import hashlib
import time
import json
import functools
import urllib.request
import urllib.parse
from datetime import datetime, timezone
import bcrypt
import pymongo
from cryptography.fernet import Fernet
import base64
from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'citywar-secret-key-2024')
app.config['DEBUG'] = False
app.config['PREFERRED_URL_SCHEME'] = 'http'

# 本地模式用 threading（兼容 pywebview），服务器部署用 eventlet（生产级）
_async_mode = 'eventlet' if os.environ.get('ONLINE_MODE', '').lower() in ('1', 'true', 'yes') else 'threading'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=_async_mode, ping_timeout=60, ping_interval=25)

from game.manager import RoomManager
from game.models import Player, Room, GameState
from websocket.events import init_socket_events

room_manager = RoomManager()

init_socket_events(socketio, room_manager)

# ===== 在线模式 & 用户系统 =====
ONLINE_MODE = os.environ.get('ONLINE_MODE', '').lower() in ('1', 'true', 'yes')

# OAuth 回调地址（必须与 OAuth 应用中配置的完全一致）
OAUTH_CALLBACK_URL = os.environ.get('OAUTH_CALLBACK_URL', '')
if not OAUTH_CALLBACK_URL and ONLINE_MODE:
    # HF Spaces 默认回调地址
    OAUTH_CALLBACK_URL = 'https://zz632-city-war.hf.space/api/auth/oauth/callback'
users = {}  # username -> {password_hash, display_name, ...} (内存缓存)
sessions = {}  # session_token -> username

# ===== 用户数据持久化 =====
MONGODB_URI = os.environ.get('MONGODB_URI', '')
_mongo_client = None
_mongo_db = None
_mongo_users = None  # MongoDB collection

# 本地 JSON 文件路径（fallback）
if os.path.exists('/data') and os.access('/data', os.W_OK):
    DATA_DIR = '/data'
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')


def _use_mongodb():
    """判断是否使用 MongoDB"""
    return MONGODB_URI and _mongo_users is not None


def _init_mongodb():
    """初始化 MongoDB 连接"""
    global _mongo_client, _mongo_db, _mongo_users
    if not MONGODB_URI:
        return
    try:
        _mongo_client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # 测试连接
        _mongo_client.admin.command('ping')
        _mongo_db = _mongo_client['citywar']
        _mongo_users = _mongo_db['users']
        # 确保 username 字段有唯一索引
        _mongo_users.create_index('username', unique=True)
        print('[MongoDB] 连接成功')
    except Exception as e:
        print(f'[MongoDB] 连接失败，回退到本地 JSON: {e}')
        _mongo_client = None
        _mongo_db = None
        _mongo_users = None


def _load_users():
    """启动时加载用户数据（从 MongoDB 或本地 JSON）"""
    global users
    if _use_mongodb():
        # 从 MongoDB 加载
        users = {}
        for doc in _mongo_users.find():
            uname = doc.get('username')
            if uname:
                users[uname] = {k: v for k, v in doc.items() if k != '_id' and k != 'username'}
        # 清除游客数据
        for uname in list(users.keys()):
            if users[uname].get('is_guest'):
                _mongo_users.delete_one({'username': uname})
                del users[uname]
    else:
        # 从本地 JSON 文件加载
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    users = json.load(f)
                # 清除游客数据
                dirty = False
                for uname in list(users.keys()):
                    if users[uname].get('is_guest'):
                        del users[uname]
                        dirty = True
                if dirty:
                    _save_users()
            except (json.JSONDecodeError, IOError):
                users = {}


def _save_users():
    """保存用户数据到本地 JSON（仅在非 MongoDB 模式下使用）"""
    if _use_mongodb():
        return  # MongoDB 模式下通过单独操作写入，不需要全量保存
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def _mongo_upsert_user(username, user_data):
    """向 MongoDB 插入或更新单个用户"""
    if not _use_mongodb():
        return
    doc = {'username': username}
    doc.update(user_data)
    _mongo_users.replace_one({'username': username}, doc, upsert=True)


def _mongo_delete_user(username):
    """从 MongoDB 删除单个用户"""
    if not _use_mongodb():
        return
    _mongo_users.delete_one({'username': username})


def _mongo_update_field(username, field, value):
    """更新 MongoDB 中用户的单个字段"""
    if not _use_mongodb():
        return
    _mongo_users.update_one({'username': username}, {'$set': {field: value}})


# ===== AI 配置加密 =====
def _get_fernet_key():
    """从 SECRET_KEY 派生 Fernet 加密密钥"""
    secret = app.config.get('SECRET_KEY', 'citywar-secret-key-2024')
    # SHA256 取前32字节，base64编码为Fernet所需格式
    key = hashlib.sha256(secret.encode('utf-8')).digest()[:32]
    # Fernet需要32字节url-safe base64编码的key，但实际Fernet key是32字节
    # 使用 base64 url-safe 编码
    return base64.urlsafe_b64encode(key)


def _encrypt_api_key(api_key):
    """加密 API Key"""
    if not api_key:
        return ''
    try:
        f = Fernet(_get_fernet_key())
        return f.encrypt(api_key.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''


def _decrypt_api_key(encrypted):
    """解密 API Key"""
    if not encrypted:
        return ''
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(encrypted.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''


# 初始化 MongoDB 并加载用户数据
_init_mongodb()
_load_users()

# ===== 管理员配置 =====
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'zz632')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
admin_sessions = {}  # admin_token -> True

# ===== IP 限流 =====
IP_RATE_LIMIT = {}  # ip -> {count, reset_time}
IP_RATE_LIMIT_MAX = 10  # 每IP每分钟最多10次请求
IP_RATE_LIMIT_WINDOW = 60  # 限流窗口（秒）

# ===== OAuth 配置 =====
OAUTH_PROVIDERS = {
    'github': {
        'client_id': os.environ.get('GITHUB_CLIENT_ID', ''),
        'client_secret': os.environ.get('GITHUB_CLIENT_SECRET', ''),
        'auth_url': 'https://github.com/login/oauth/authorize',
        'token_url': 'https://github.com/login/oauth/access_token',
        'api_url': 'https://api.github.com/user',
        'scope': 'read:user,user:email',
    },
    'google': {
        'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
        'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
        'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token_url': 'https://oauth2.googleapis.com/token',
        'api_url': 'https://www.googleapis.com/oauth2/v2/userinfo',
        'scope': 'openid profile email',
    },
    'discord': {
        'client_id': os.environ.get('DISCORD_CLIENT_ID', ''),
        'client_secret': os.environ.get('DISCORD_CLIENT_SECRET', ''),
        'auth_url': 'https://discord.com/api/oauth2/authorize',
        'token_url': 'https://discord.com/api/oauth2/token',
        'api_url': 'https://discord.com/api/users/@me',
        'scope': 'identify email',
    },
    'twitch': {
        'client_id': os.environ.get('TWITCH_CLIENT_ID', ''),
        'client_secret': os.environ.get('TWITCH_CLIENT_SECRET', ''),
        'auth_url': 'https://id.twitch.tv/oauth2/authorize',
        'token_url': 'https://id.twitch.tv/oauth2/token',
        'api_url': 'https://api.twitch.tv/helix/users',
        'scope': 'user:read:email',
    },
    'gitee': {
        'client_id': os.environ.get('GITEE_CLIENT_ID', ''),
        'client_secret': os.environ.get('GITEE_CLIENT_SECRET', ''),
        'auth_url': 'https://gitee.com/oauth/authorize',
        'token_url': 'https://gitee.com/oauth/token',
        'api_url': 'https://gitee.com/api/v5/user',
        'scope': 'user_info',
    },
}
# OAuth state 存储: state -> {provider, redirect}
oauth_states = {}


def _check_rate_limit(ip):
    """检查IP限流，返回True表示允许，False表示超限"""
    now = time.time()
    info = IP_RATE_LIMIT.get(ip)
    if not info or now > info['reset_time']:
        IP_RATE_LIMIT[ip] = {'count': 1, 'reset_time': now + IP_RATE_LIMIT_WINDOW}
        return True
    info['count'] += 1
    return info['count'] <= IP_RATE_LIMIT_MAX


def _hash_password(password):
    """使用 bcrypt 对密码进行哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _check_password(password, stored_hash):
    """验证密码，支持 bcrypt 和旧 SHA-256 自动迁移"""
    if not stored_hash:
        return False
    # bcrypt 哈希以 $2b$ 开头
    if stored_hash.startswith('$2b$') or stored_hash.startswith('$2a$') or stored_hash.startswith('$2y$'):
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
        except Exception:
            return False
    else:
        # 旧 SHA-256 哈希：验证后自动升级为 bcrypt
        sha256_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        if sha256_hash == stored_hash:
            return True  # 调用方负责升级哈希
        return False


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
            return redirect('/admin.html')
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
    if path.startswith('/admin/') or path == '/admin.html':
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


@app.route('/api/auth/register', methods=['POST'])
def api_register():
    if not _check_rate_limit(request.remote_addr):
        return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429
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
        'auth_method': 'password',
        'is_guest': False,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    _mongo_upsert_user(username, users[username])
    _save_users()
    # 自动登录
    token = uuid.uuid4().hex
    sessions[token] = username
    return jsonify({'success': True, 'token': token, 'username': username, 'display_name': display_name})


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    if not _check_rate_limit(request.remote_addr):
        return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    user = users.get(username)
    if not user or not _check_password(password, user.get('password_hash', '')):
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    # SHA-256 迁移到 bcrypt：如果哈希不是 bcrypt 格式，升级它
    stored_hash = user.get('password_hash', '')
    if stored_hash and not stored_hash.startswith('$2b$') and not stored_hash.startswith('$2a$') and not stored_hash.startswith('$2y$'):
        user['password_hash'] = _hash_password(password)
        _mongo_update_field(username, 'password_hash', user['password_hash'])
        _save_users()

    token = uuid.uuid4().hex
    sessions[token] = username
    return jsonify({'success': True, 'token': token, 'username': username, 'display_name': user['display_name']})


@app.route('/api/auth/guest', methods=['POST'])
def api_guest_login():
    """游客登录：输入昵称"""
    if not _check_rate_limit(request.remote_addr):
        return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429
    data = request.get_json() or {}
    display_name = data.get('display_name', '').strip()

    if not display_name:
        return jsonify({'success': False, 'message': '请输入昵称'}), 400
    if len(display_name) < 1 or len(display_name) > 12:
        return jsonify({'success': False, 'message': '昵称需要1-12个字符'}), 400

    # 生成游客用户名（guest_ + 随机数）
    guest_id = str(uuid.uuid4())[:8]
    username = f'guest_{guest_id}'

    users[username] = {
        'password_hash': '',
        'display_name': display_name,
        'is_guest': True,
        'auth_method': 'guest',
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    # 游客不持久化，仅存在内存中，重启后丢失

    token = uuid.uuid4().hex
    sessions[token] = username
    return jsonify({'success': True, 'token': token, 'username': username, 'display_name': display_name})


@app.route('/api/auth/check', methods=['GET'])
def api_auth_check():
    username = _check_login()
    if username and username in users:
        return jsonify({'success': True, 'username': username, 'display_name': users[username]['display_name']})
    return jsonify({'success': False})


@app.route('/api/auth/online_mode', methods=['GET'])
def api_online_mode():
    return jsonify({'online': ONLINE_MODE})


@app.route('/api/auth/oauth/<provider>', methods=['GET'])
def oauth_redirect(provider):
    """跳转到 OAuth 提供方授权页面"""
    if provider not in OAUTH_PROVIDERS:
        return redirect('/?oauth_error=unsupported')

    cfg = OAUTH_PROVIDERS[provider]
    if not cfg['client_id']:
        return redirect('/?oauth_error=not_configured')

    state = uuid.uuid4().hex
    redirect_url = request.args.get('redirect', '/')
    oauth_states[state] = {'provider': provider, 'redirect': redirect_url}

    params = {
        'client_id': cfg['client_id'],
        'redirect_uri': OAUTH_CALLBACK_URL,
        'response_type': 'code',
        'scope': cfg['scope'],
        'state': state,
    }
    auth_url = f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)


@app.route('/api/auth/oauth/callback', methods=['GET'])
def oauth_callback():
    """OAuth 回调：用 code 换 token，获取用户信息，登录/注册"""
    code = request.args.get('code', '')
    state = request.args.get('state', '')

    if not code or not state or state not in oauth_states:
        return redirect('/?oauth_error=invalid_request')

    state_data = oauth_states.pop(state)
    provider = state_data['provider']
    redirect_to = state_data.get('redirect', '/')
    cfg = OAUTH_PROVIDERS.get(provider)
    if not cfg:
        return redirect('/?oauth_error=unknown_provider')

    # 用 code 换 access_token
    try:
        token_data = urllib.parse.urlencode({
            'client_id': cfg['client_id'],
            'client_secret': cfg['client_secret'],
            'code': code,
            'redirect_uri': OAUTH_CALLBACK_URL,
            'grant_type': 'authorization_code',
        }).encode()
        headers = {'Accept': 'application/json'}
        req = urllib.request.Request(cfg['token_url'], data=token_data, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_resp = json.loads(resp.read())
        access_token = token_resp.get('access_token', '')
        if not access_token:
            return redirect('/?oauth_error=no_token')
    except Exception:
        return redirect('/?oauth_error=token_failed')

    # 获取用户信息
    try:
        api_headers = {'Authorization': f'Bearer {access_token}'}
        if provider == 'twitch':
            api_headers['Client-Id'] = cfg['client_id']
        req = urllib.request.Request(cfg['api_url'], headers=api_headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            user_info = json.loads(resp.read())
    except Exception:
        return redirect('/?oauth_error=api_failed')

    # 提取 OAuth ID 和显示名
    if provider == 'github':
        oauth_id = str(user_info.get('id', ''))
        display_name = user_info.get('login', '') or user_info.get('name', '')
        email = user_info.get('email', '')
    elif provider == 'google':
        oauth_id = str(user_info.get('id', ''))
        display_name = user_info.get('name', '') or user_info.get('given_name', '')
        email = user_info.get('email', '')
    elif provider == 'discord':
        oauth_id = str(user_info.get('id', ''))
        display_name = user_info.get('username', '') or user_info.get('global_name', '')
        email = user_info.get('email', '')
    elif provider == 'twitch':
        # Twitch API 返回 {"data": [{...}]}
        twitch_user = {}
        if isinstance(user_info.get('data'), list) and user_info['data']:
            twitch_user = user_info['data'][0]
        oauth_id = str(twitch_user.get('id', ''))
        display_name = twitch_user.get('display_name', '') or twitch_user.get('login', '')
        email = twitch_user.get('email', '')
    elif provider == 'gitee':
        oauth_id = str(user_info.get('id', ''))
        display_name = user_info.get('login', '') or user_info.get('name', '')
        email = user_info.get('email', '')
    else:
        return redirect('/?oauth_error=unknown_provider')

    if not oauth_id:
        return redirect('/?oauth_error=no_id')

    return _oauth_login_or_register(provider, oauth_id, display_name, email, redirect_to)


def _oauth_login_or_register(provider, oauth_id, display_name, email, redirect_to):
    """OAuth 登录或注册的通用逻辑"""
    oauth_key = f'{provider}_{oauth_id}'
    for uname, udata in users.items():
        if udata.get('oauth_id') == oauth_key:
            # 已绑定，直接登录
            token = uuid.uuid4().hex
            sessions[token] = uname
            resp = make_response(redirect(redirect_to))
            resp.set_cookie('auth_token', token, httponly=True, max_age=86400 * 30)
            return resp

    # 未绑定，创建新账号
    username = f'{provider}_{oauth_id}'
    if username not in users:
        users[username] = {
            'password_hash': '',
            'display_name': display_name,
            'auth_method': provider,
            'oauth_id': oauth_key,
            'oauth_provider': provider,
            'email': email,
            'is_guest': False,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        _mongo_upsert_user(username, users[username])
        _save_users()

    token = uuid.uuid4().hex
    sessions[token] = username
    resp = make_response(redirect(redirect_to))
    resp.set_cookie('auth_token', token, httponly=True, max_age=86400 * 30)
    return resp


@app.route('/api/auth/oauth_providers', methods=['GET'])
def api_oauth_providers():
    """返回已配置的 OAuth 提供方列表"""
    providers = []
    for name, cfg in OAUTH_PROVIDERS.items():
        if cfg['client_id']:
            providers.append({'name': name, 'label': name.capitalize()})
    return jsonify({'providers': providers})


# ===== 账号设置 =====

@app.route('/api/auth/profile', methods=['GET'])
def api_get_profile():
    """获取当前用户信息"""
    username = _check_login()
    if not username or username not in users:
        return jsonify({'success': False, 'message': '未登录'}), 401
    u = users[username]
    return jsonify({
        'success': True,
        'username': username,
        'display_name': u.get('display_name', ''),
        'email': u.get('email', ''),
        'is_guest': u.get('is_guest', False),
        'oauth_provider': u.get('oauth_provider', ''),
    })


@app.route('/api/auth/profile', methods=['POST'])
def api_update_profile():
    """更新用户信息（昵称、密码）"""
    username = _check_login()
    if not username or username not in users:
        return jsonify({'success': False, 'message': '未登录'}), 401

    u = users[username]
    if u.get('is_guest'):
        return jsonify({'success': False, 'message': '游客账号不支持修改'}), 400

    data = request.get_json() or {}
    display_name = data.get('display_name', '').strip()
    new_password = data.get('new_password', '')
    old_password = data.get('old_password', '')

    if display_name:
        u['display_name'] = display_name
        _mongo_update_field(username, 'display_name', display_name)
        _save_users()

    if new_password:
        if not old_password:
            return jsonify({'success': False, 'message': '请输入旧密码'}), 400
        if u.get('password_hash') and not _check_password(old_password, u['password_hash']):
            return jsonify({'success': False, 'message': '旧密码错误'}), 400
        if len(new_password) < 4:
            return jsonify({'success': False, 'message': '新密码至少4个字符'}), 400
        u['password_hash'] = _hash_password(new_password)
        _mongo_update_field(username, 'password_hash', u['password_hash'])
        _save_users()

    return jsonify({'success': True, 'message': '修改成功', 'display_name': u['display_name']})


@app.route('/api/ai/config', methods=['GET'])
def api_get_ai_config():
    """获取当前用户的AI配置"""
    username = _check_login()
    if not username or username not in users:
        return jsonify({'success': False, 'message': '未登录'}), 401
    u = users[username]
    if u.get('is_guest'):
        return jsonify({'success': False, 'message': '游客账号不支持AI配置'}), 400

    ai_config = u.get('ai_config', {})
    # 解密 API Key
    encrypted_key = ai_config.get('api_key_encrypted', '')
    api_key = _decrypt_api_key(encrypted_key)

    return jsonify({
        'success': True,
        'config': {
            'base_url': ai_config.get('base_url', 'https://api.openai.com/v1'),
            'api_key': api_key,
            'model': ai_config.get('model', 'gpt-4o-mini'),
        }
    })


@app.route('/api/ai/config', methods=['POST'])
def api_update_ai_config():
    """更新当前用户的AI配置"""
    username = _check_login()
    if not username or username not in users:
        return jsonify({'success': False, 'message': '未登录'}), 401
    u = users[username]
    if u.get('is_guest'):
        return jsonify({'success': False, 'message': '游客账号不支持AI配置'}), 400

    data = request.get_json() or {}
    base_url = data.get('base_url', 'https://api.openai.com/v1').strip()
    api_key = data.get('api_key', '').strip()
    model = data.get('model', 'gpt-4o-mini').strip()

    # 加密存储 API Key
    encrypted_key = _encrypt_api_key(api_key) if api_key else ''

    ai_config = {
        'base_url': base_url,
        'api_key_encrypted': encrypted_key,
        'model': model,
    }

    u['ai_config'] = ai_config
    _mongo_update_field(username, 'ai_config', ai_config)
    _save_users()

    return jsonify({'success': True, 'message': 'AI配置已保存'})


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


@app.route('/settings')
def settings_page():
    return render_template('settings.html')


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
    # 关联登录用户名
    login_user = _check_login()
    if login_user:
        player.username = login_user
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
        return jsonify({'success': False, 'message': '房间不存在或已满'}), 400

    # 关联登录用户名
    login_user = _check_login()
    if login_user:
        player.username = login_user

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

@app.route('/admin.html', methods=['GET'])
def admin_page():
    """管理员页面（登录+管理面板）"""
    admin_token = request.cookies.get('admin_token', '')
    if admin_token and admin_token in admin_sessions:
        return render_template('admin.html', page='panel')
    return render_template('admin.html', page='login')


@app.route('/admin/login', methods=['POST'])
def admin_login_submit():
    """管理员登录验证"""
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')

    if username == ADMIN_USERNAME and ADMIN_PASSWORD and password == ADMIN_PASSWORD:
        admin_token = uuid.uuid4().hex
        admin_sessions[admin_token] = True
        resp = make_response(jsonify({'success': True}))
        resp.set_cookie('admin_token', admin_token, httponly=True, max_age=86400)
        return resp
    return jsonify({'success': False, 'message': '用户名或密码错误'}), 401


@app.route('/admin/')
def admin_panel_redirect():
    """兼容旧链接，重定向到 /admin.html"""
    return redirect('/admin.html')


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
    _mongo_delete_user(username)
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
