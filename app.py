#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
城池战争游戏 - Flask 主应用
CityWar Game - Flask Main Application
"""

import os
import sys

# 将 vendor 目录加入模块搜索路径（内置依赖，无需 pip 安装）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor'))

import uuid
import socket
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room

# 创建 Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'citywar-secret-key-2024'
app.config['DEBUG'] = False

# 创建 SocketIO 实例（使用 threading 模式，纯 Python 无 C 扩展依赖）
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60, ping_interval=25)

# 导入游戏模块
from game.manager import RoomManager
from game.models import Player, Room, GameState
from websocket.events import init_socket_events

# 创建房间管理器实例
room_manager = RoomManager()

# 注册 Socket.IO 事件
init_socket_events(socketio, room_manager)


@app.route('/')
def index():
    """首页 - 创建/加入房间"""
    return render_template('index.html')


@app.route('/lobby/<room_id>')
def lobby(room_id):
    """游戏大厅"""
    return render_template('lobby.html', room_id=room_id)


@app.route('/game/<room_id>')
def game(room_id):
    """游戏主界面"""
    return render_template('game.html', room_id=room_id)


@app.route('/api/rooms', methods=['GET', 'POST'])
def api_rooms():
    """获取/创建房间"""
    if request.method == 'GET':
        return jsonify({'success': True, 'rooms': room_manager.get_public_rooms()})

    # POST - 创建房间
    data = request.get_json() or {}
    player_name = data.get('player_name', '').strip()
    if not player_name:
        return jsonify({'success': False, 'message': '名字不能为空'}), 400

    room_id, player = room_manager.create_room(player_name, 'p_' + uuid.uuid4().hex[:12])
    return jsonify({
        'success': True,
        'room': {'id': room_id, 'name': room_manager.rooms[room_id].name},
        'player': player.to_dict()
    })


@app.route('/api/rooms/<room_id>/join', methods=['POST'])
def api_join_room(room_id):
    """加入房间"""
    data = request.get_json() or {}
    player_name = data.get('player_name', '').strip()
    if not player_name:
        return jsonify({'success': False, 'message': '名字不能为空'}), 400

    player = room_manager.join_room(room_id, player_name, 'p_' + uuid.uuid4().hex[:12])
    if not player:
        return jsonify({'success': False, 'message': '房间不存在或已满'}), 400

    return jsonify({
        'success': True,
        'room': {'id': room_id},
        'player': player.to_dict(),
        'is_spectator': player.is_spectator
    })


@app.route('/api/room/<room_id>/status', methods=['GET'])
def get_room_status(room_id):
    """获取房间状态"""
    room = room_manager.get_room(room_id)
    if not room:
        return jsonify({'success': False, 'message': '房间不存在'}), 404

    return jsonify({
        'success': True,
        'room': room.to_dict()
    })


@app.errorhandler(404)
def not_found(error):
    """404 错误处理"""
    return jsonify({
        'success': False,
        'message': '页面未找到'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """500 错误处理"""
    return jsonify({
        'success': False,
        'message': '服务器内部错误'
    }), 500


def find_available_port(start_port=5000, max_tries=100):
    """从 start_port 开始寻找可用端口"""
    for port in range(start_port, start_port + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    return start_port  # 找不到就返回默认值


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='城池战争 CityWar - 本地多人策略游戏')
    parser.add_argument('--port', type=int, default=None, help='指定端口号（默认自动选择）')
    args = parser.parse_args()

    # 获取端口，如被占用则自动切换
    preferred_port = args.port or int(os.environ.get('PORT', 5000))
    port = find_available_port(preferred_port)

    print(f"""
╔═════════════════════════════════════════════════════════╗
║                                                         ║
║   城池战争 CityWar - 本地多人策略游戏                   ║
║                                                         ║
║   本地地址: http://localhost:{port}                       ║
║                                                         ║
╚═════════════════════════════════════════════════════════╝
    """)

    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
        log_output=False
    )
