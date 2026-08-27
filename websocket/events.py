"""
WebSocket 事件处理模块
与前端 main.js 事件完全对齐
所有 emit 统一用 socketio.emit() 以支持 Timer 回调
"""
from flask_socketio import join_room as sio_join, leave_room as sio_leave
from flask import request
from game.models import GamePhase, Player
from game.skills import SKILL_CARDS
import random
import threading
import uuid

# 运行时由 init_socket_events 注入
socketio = None
room_manager = None
ws_player_map = {}  # request.sid -> player_id


def init_socket_events(sio, rm):
    global socketio, room_manager
    socketio = sio
    room_manager = rm
    _register()


def _emit(event, data, room=None):
    """统一发送，兼容请求上下文内外"""
    socketio.emit(event, data, room=room)


def _register():
    # ---- 连接 / 断开 ----

    @socketio.on('connect')
    def on_connect():
        print(f'[WS] 连接: {request.sid}')

    @socketio.on('disconnect')
    def on_disconnect():
        print(f'[WS] 断开: {request.sid}')
        player_id = ws_player_map.pop(request.sid, None)
        if not player_id:
            return
        player = room_manager.get_player(player_id)
        if not player:
            return
        # 游戏进行中不移除玩家，等待重新连接
        room = room_manager.get_room(player.room_id)
        if room and room.game_state and room.game_state.phase != GamePhase.WAITING:
            return
        # 延迟移除：页面跳转会导致短暂断连，等5秒看是否重连
        def _delayed_leave():
            # 检查是否已重连（ws_player_map中有新sid映射到该player_id）
            for sid, pid in ws_player_map.items():
                if pid == player_id:
                    return  # 已重连，不移除
            # 确认玩家还在
            p = room_manager.get_player(player_id)
            if not p:
                return
            r = room_manager.get_room(p.room_id)
            # 如果游戏在进行中，也不移除
            if r and r.game_state and r.game_state.phase != GamePhase.WAITING:
                return
            room_manager.leave_room(player_id)
            print(f'[WS] 延迟移除玩家: {player_id}')
        threading.Timer(5.0, _delayed_leave).start()

    # ---- 大厅 ----

    @socketio.on('lobby_join')
    def on_lobby_join(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            _emit('error_msg', {'message': '房间或玩家不存在'})
            return

        sio_join(room_id)
        sio_join(player_id)  # 加入私人房间，用于接收定向消息
        ws_player_map[request.sid] = player_id
        _emit('lobby_update', {
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)

    @socketio.on('start_game')
    def on_start_game(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room:
            _emit('error_msg', {'message': '房间不存在'})
            return

        if room.host_id != player_id:
            _emit('error_msg', {'message': '只有房主可以开始游戏'})
            return

        # 只计算非观战者玩家数
        non_spectator_count = sum(1 for p in room.players.values() if not p.is_spectator)
        if non_spectator_count < 2:
            _emit('error_msg', {'message': '至少需要2名玩家'})
            return

        ok = room_manager.start_game(room_id, player_id)
        if not ok:
            gs = room.game_state
            print(f'[START_GAME] failed: room={room_id}, host={room.host_id}, player={player_id}, '
                  f'players={len(room.players)}, game_state={gs.phase.value if gs else "None"}')
            _emit('error_msg', {'message': '无法开始游戏'})
            return

        _emit('game_started', {
            'room_id': room_id,
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)

    @socketio.on('urge_start')
    def on_urge_start(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room:
            return

        player = room.players.get(player_id)
        if not player:
            return

        _emit('urge_received', {'player_name': player.name}, room=room_id)

    @socketio.on('spectate_join')
    def on_spectate_join(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            return
        player = room.players[player_id]
        # 房主不能观战
        if player.is_host:
            return
        # 游戏进行中不能从玩家变为观战者
        if room.game_state and room.game_state.phase != GamePhase.WAITING:
            return
        player.is_spectator = True
        player.is_alive = False
        player.cities = 0
        _emit('lobby_update', {
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)

    @socketio.on('unspectate_join')
    def on_unspectate_join(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            return
        player = room.players[player_id]
        if not player.is_spectator:
            return
        if room.game_state and room.game_state.phase != GamePhase.WAITING:
            return
        player.is_spectator = False
        player.is_alive = True
        player.cities = 250
        _emit('lobby_update', {
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)

    @socketio.on('add_ai_bot')
    def on_add_ai_bot(data):
        """添加AI人机到房间"""
        import json
        from game.models import Player
        from app import _decrypt_api_key, users

        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            _emit('error_msg', {'message': '房间或玩家不存在'}, room=request.sid)
            return

        # 检查房间人数上限
        if len(room.players) >= room.max_players:
            _emit('error_msg', {'message': '房间已满'}, room=request.sid)
            return

        # 检查AI数量上限（每房间最多4个）
        ai_count = sum(1 for p in room.players.values() if p.is_ai)
        if ai_count >= 4:
            _emit('error_msg', {'message': 'AI人机已达上限（4个）'}, room=request.sid)
            return

        # 获取AI配置：优先从服务器端取（加密），fallback到前端传入
        config = {}
        caller = room.players.get(player_id)
        if caller and caller.username and caller.username in users:
            # 登录用户：从服务器解密获取
            u = users[caller.username]
            ai_cfg = u.get('ai_config', {})
            api_key = _decrypt_api_key(ai_cfg.get('api_key_encrypted', ''))
            if api_key:
                config = {
                    'base_url': ai_cfg.get('base_url', 'https://api.openai.com/v1'),
                    'api_key': api_key,
                    'model': ai_cfg.get('model', 'gpt-4o-mini'),
                }
        # 服务器端取不到，尝试前端传入的配置（本地模式或username未关联的fallback）
        if not config.get('api_key'):
            config = data.get('config', {})
        if not config.get('api_key'):
            _emit('error_msg', {'message': '请先在设置中配置 API Key'}, room=request.sid)
            return

        # 生成AI玩家
        ai_num = ai_count + 1
        ai_id = 'ai_' + str(uuid.uuid4())[:8]
        ai_name = '🤖 AI-' + str(ai_num)

        ai_player = Player(
            id=ai_id,
            name=ai_name,
            room_id=room_id,
            is_ai=True,
            is_alive=True,
            cities=250
        )

        room.players[ai_id] = ai_player
        room_manager.players[ai_id] = ai_player

        # 保存AI配置到玩家对象（供后续AI决策使用）
        ai_player.status_effects['ai_config'] = config

        _emit('lobby_update', {
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)

    @socketio.on('room_settings')
    def on_room_settings(data):
        """房主修改房间设置"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            return
        if room.host_id != player_id:
            return

        changed = False
        if 'allow_join_after_start' in data:
            room.allow_join_after_start = bool(data['allow_join_after_start'])
            changed = True
        if 'password' in data:
            room.password = str(data['password']).strip()
            changed = True
        if 'max_players' in data:
            new_max = int(data['max_players'])
            # 不能小于当前人数，不能小于2，不能大于8
            new_max = max(len(room.players), max(2, min(8, new_max)))
            room.max_players = new_max
            changed = True

        if changed:
            _emit('lobby_update', {
                'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()},
                'allow_join_after_start': room.allow_join_after_start,
                'has_password': bool(room.password),
                'max_players': room.max_players,
            }, room=room_id)

    @socketio.on('transfer_host')
    def on_transfer_host(data):
        """房主转让"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        target_id = data.get('target_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            return
        if room.host_id != player_id:
            return
        if target_id not in room.players or target_id == player_id:
            return

        target = room.players[target_id]
        if target.is_ai or target.is_spectator:
            return

        # 转让房主
        room.players[player_id].is_host = False
        room.host_id = target_id
        target.is_host = True

        _emit('lobby_update', {
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()},
        }, room=room_id)
        _emit('host_transferred', {
            'new_host_name': target.name,
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()},
        }, room=room_id)

    @socketio.on('kick_player')
    def on_kick_player(data):
        """房主踢人"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        target_id = data.get('target_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            return
        if room.host_id != player_id:
            return
        if target_id not in room.players or target_id == player_id:
            return

        target = room.players[target_id]
        if target.is_ai:
            return

        target_name = target.name
        # 从房间移除
        if target_id in room.players:
            del room.players[target_id]
        if target_id in room_manager.players:
            del room_manager.players[target_id]

        # 通知被踢的玩家
        _emit('kicked', {'message': '你已被房主踢出房间'}, room=target_id)
        # 通知房间内其他人
        _emit('lobby_update', {
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()},
        }, room=room_id)
        _emit('player_kicked', {
            'kicked_name': target_name,
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()},
        }, room=room_id)

    @socketio.on('leave_game')
    def on_leave_game(data):
        """玩家退出游戏：重置房间回大厅状态，中途观战者自动变玩家"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            return

        # 重置所有玩家状态
        for p in room.players.values():
            p.is_alive = True
            p.is_spectator = False
            p.cities = 250
            p.skills = []
            p.alliance_with = None
            p.alliance_benefits = 0
            p.alliance_damages = 0
            p.repair_active = False
            p.status_effects = {}
            p.action = None
            p.action_history = []

        # 重置房间游戏状态
        room.game_state = None

        # 移除AI玩家（AI不回到大厅）
        ai_ids = [pid for pid, p in room.players.items() if p.is_ai]
        for aid in ai_ids:
            if aid in room.players:
                del room.players[aid]
            if aid in room_manager.players:
                del room_manager.players[aid]

        # 通知所有人回到大厅
        _emit('back_to_lobby', {
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)

    # ---- 聊天 ----

    @socketio.on('chat_message')
    def on_chat_message(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        message = str(data.get('message', '')).strip()

        if not message:
            return

        room = room_manager.get_room(room_id)
        if not room:
            return

        player = room.players.get(player_id)
        if not player:
            return

        _emit('chat_message', {
            'player_id': player.id,
            'player_name': player.name,
            'message': message,
            'is_dead': not player.is_alive,
            'is_spectator': player.is_spectator or not player.is_alive
        }, room=room_id)

    # ---- 游戏 ----

    @socketio.on('game_join')
    def on_game_join(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            _emit('error_msg', {'message': '房间或玩家不存在'})
            return

        sio_join(room_id)
        sio_join(player_id)  # 加入私人房间，用于接收定向消息
        ws_player_map[request.sid] = player_id
        _emit('game_state', _build_game_state(room))

        # 游戏进行中且为行动阶段时，触发AI自动行动
        if room.game_state and room.game_state.phase == GamePhase.ACTION:
            print(f'[AI] game_join triggers ai_actions, room={room_id}')
            _trigger_ai_actions(room_id)

    @socketio.on('submit_action')
    def on_submit_action(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        action_type = data.get('action_type', '')
        target_id = data.get('target_id')
        bet = data.get('bet', 0)

        room = room_manager.get_room(room_id)
        if not room:
            _emit('error_msg', {'message': '房间不存在'})
            return

        player = room.players.get(player_id)
        if not player or not player.is_alive or player.is_spectator:
            _emit('error_msg', {'message': '无法操作'})
            return

        ok = room_manager.submit_action(room_id, player_id, action_type,
                                         target_id, bet)
        if not ok:
            _emit('error_msg', {'message': '行动无效'})
            return

        action_detail = {
            'type': action_type,
            'target_id': target_id,
            'bet': bet,
        }
        # 补充目标玩家名称
        if target_id and target_id in room.players:
            action_detail['target_name'] = room.players[target_id].name

        # 二般人第二行动提示
        is_extra = player_id in room.game_state.extra_actions
        if is_extra:
            action_detail['extra'] = True

        _emit('player_action_ready', {
            'player_id': player_id,
            'player_name': player.name,
            'action_type': action_type,
            'action_detail': action_detail
        }, room=room_id)

        # 结盟请求：仅通知目标玩家
        if action_type == 'alliance' and target_id:
            target_sid = target_id  # 在本系统中 player_id 就是 sid
            _emit('alliance_request', {
                'from_player_id': player_id,
                'from_player_name': player.name,
                'to_player_id': target_id
            }, room=target_sid)

        # 检查是否所有存活玩家都已提交（二般人玩家还需提交第二行动，暂不结算）
        alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
        pending_extra = any(
            p.is_alive and not p.is_spectator
            and p.status_effects.get('extra_action')
            and p.id in room.game_state.actions
            for p in room.players.values()
        )
        if len(room.game_state.actions) >= len(alive) and not pending_extra:
            _process_round(room_id)
        elif pending_extra and len(room.game_state.actions) >= len(alive):
            # 所有人主行动已交齐，仅剩二般人玩家的第二行动：30秒后自动跳过，防止卡死
            pending_ids = [p.id for p in room.players.values()
                           if p.is_alive and not p.is_spectator
                           and p.status_effects.get('extra_action')
                           and p.id in room.game_state.actions]

            def _force_extra(r_id, p_id):
                r = room_manager.get_room(r_id)
                if not r or not r.game_state:
                    return
                if r.game_state.phase != GamePhase.ACTION:
                    return
                pp = r.players.get(p_id)
                if pp and pp.status_effects.get('extra_action') and p_id in r.game_state.actions:
                    room_manager.submit_action(r_id, p_id, 'skip', None, 0)
                    alive2 = [q for q in r.players.values() if q.is_alive and not q.is_spectator]
                    if len(r.game_state.actions) >= len(alive2):
                        _process_round(r_id)

            for ep_id in pending_ids:
                threading.Timer(30, _force_extra, args=(room_id, ep_id)).start()

    @socketio.on('auction_bid')
    def on_auction_bid(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        bid = data.get('bid', 0)

        room = room_manager.get_room(room_id)
        if not room or not room.game_state or not room.game_state.auction:
            return

        auction = room.game_state.auction
        player = room.players.get(player_id)
        if not player:
            return

        if bid < auction['current_bid'] + 10:
            _emit('error_msg', {'message': '出价至少比当前价高10'})
            return
        if bid > player.cities:
            _emit('error_msg', {'message': '城池不足'})
            return

        auction['current_bid'] = bid
        auction['highest_bidder'] = player_id

        _emit('auction_updated', {
            'current_bid': bid,
            'highest_bidder_name': player.name
        }, room=room_id)

    @socketio.on('auction_pass')
    def on_auction_pass(data):
        """玩家选择跳过拍卖"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or not room.game_state or not room.game_state.auction:
            return

        auction = room.game_state.auction

        # 已有人出价：一人跳过即结束拍卖（出价者获得）
        if auction['highest_bidder']:
            _end_auction(room_id)
            return

        # 无人出价：记录跳过的玩家，所有存活玩家都跳过才流拍
        if player_id not in auction['passed_players']:
            auction['passed_players'].append(player_id)

        alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
        if len(auction['passed_players']) >= len(alive):
            _end_auction(room_id)

    @socketio.on('use_skill')
    def on_use_skill(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        skill_id = data.get('skill_id', '')
        target_id = data.get('target_id')
        upgrade_target = data.get('upgrade_target')

        room = room_manager.get_room(room_id)
        if not room or not room.game_state:
            _emit('error_msg', {'message': '无法使用技能卡'})
            return

        if room.game_state.phase != GamePhase.ACTION:
            _emit('error_msg', {'message': '当前阶段无法使用技能卡'})
            return

        player = room.players.get(player_id)
        if not player or not player.is_alive:
            _emit('error_msg', {'message': '无法使用技能卡'})
            return

        success, result_msg = _apply_skill_card(room_id, player_id, skill_id, target_id,
                                                upgrade_target=upgrade_target)
        if not success:
            _emit('error_msg', {'message': result_msg or '技能卡使用失败'})

    @socketio.on('duel_shot')
    def on_duel_shot(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        shots = data.get('shots', 1)

        room = room_manager.get_room(room_id)
        if not room or not room.game_state or not room.game_state.duel:
            return

        duel = room.game_state.duel
        if duel['current_turn'] != player_id:
            _emit('error_msg', {'message': '不是你的回合'})
            return

        _do_duel_shot(room_id, player_id, shots)

    @socketio.on('duel_accept')
    def on_duel_accept(data):
        """被约战方接受约战，开始轮盘赌"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        room = room_manager.get_room(room_id)
        if not room or not room.game_state or not room.game_state.duel:
            return
        duel = room.game_state.duel
        # 只有被约战方才能接受
        if duel.get('target') != player_id:
            return
        duel_info = {
            'initiator': duel['initiator'],
            'initiator_name': duel['initiator_name'],
            'target': duel['target'],
            'target_name': duel['target_name'],
            'bet': duel['bet'],
        }
        _accept_duel(room_id, duel_info)

    @socketio.on('duel_reject')
    def on_duel_reject(data):
        """被约战方拒绝约战，交50%赌注"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        room = room_manager.get_room(room_id)
        if not room or not room.game_state or not room.game_state.duel:
            return
        duel = room.game_state.duel
        # 只有被约战方才能拒绝
        if duel.get('target') != player_id:
            return
        _reject_duel(room_id)

    @socketio.on('death_choice')
    def on_death_choice(data):
        """玩家濒死时决定是否使用不死图腾"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        use = bool(data.get('use'))

        room = room_manager.get_room(room_id)
        if not room or not room.game_state:
            return

        pending = getattr(room.game_state, 'pending_totem', [])
        if player_id not in pending:
            return

        _resolve_totem_choice(room_id, player_id, use)

    @socketio.on('ready_next_round')
    def on_ready_next_round(data):
        """玩家点击继续行动后通知服务器"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or not room.game_state:
            return

        player = room.players.get(player_id)
        if not player:
            return

        gs = room.game_state

        # 有濒死抉择未完成时，暂不允许进入下一轮
        if getattr(gs, 'pending_totem', None):
            _emit('error_msg', {'message': '有玩家正在做濒死抉择，请稍候'}, room=room_id)
            return

        if not hasattr(gs, 'ready_players'):
            gs.ready_players = set()
        gs.ready_players.add(player_id)

        # 只有存活玩家才算"全部准备好"
        alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
        alive_ready = [pid for pid in gs.ready_players if pid in {p.id for p in alive}]
        if len(alive_ready) >= len(alive):
            gs.ready_players = set()

            # 检查拍卖（第10轮起每5轮触发一次）
            if gs.round >= 10 and (gs.round - 10) % 5 == 0 and not getattr(gs, '_auction_done_this_round', False):
                gs._auction_done_this_round = True
                _start_auction(room_id)
            else:
                _start_next_round(room_id)


# ===== 技能卡公共逻辑 =====

# 需要目标的技能卡类型
_SKILL_NEEDS_TARGET = {'attack', 'special'}
# 攻击类/特殊类中不需要目标的卡ID
_SKILL_NO_TARGET_IDS = {
    'first_aid',                     # 原有
    'plus_damage', 'fierce_attack',  # 攻击类自身buff
    'lifesteal', 'damage_boost',     # 攻击类自身buff
    'arrow_rain',                    # 攻击类AOE，无需指定目标
    'double_action', 'upgrade',      # 特殊类自身buff
}


def _apply_skill_card(room_id, player_id, skill_id, target_id=None, upgrade_target=None):
    """使用技能卡（公共逻辑，供 on_use_skill 和 AI 调用）
    返回 (success: bool, result_msg: str)
    """
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return False, ''

    player = room.players.get(player_id)
    if not player or not player.is_alive:
        return False, ''

    # 查找技能卡
    skill_card = None
    for s in player.skills:
        if s.get('skill_type') == skill_id or s.get('id') == skill_id:
            skill_card = s
            break

    if not skill_card:
        return False, ''

    skill_type_key = skill_card.get('skill_type', skill_id)
    skill_type = skill_card.get('type', '')
    effect = skill_card.get('effect', {})
    result_msg = player.name + ' 使用了【' + skill_card.get('name', '技能卡') + '」'

    # 计算回合倍率（数值翻倍：第8/16/24轮 ×2/×4/×8）
    from game.manager import get_multiplier
    multiplier = get_multiplier(room.game_state.round)

    # 不死图腾卡改为濒死时自动询问，无需主动使用
    if skill_type_key == 'immortal_totem':
        return False, '不死图腾无需主动使用：当你濒死时会自动询问是否使用'

    # 无懈可击拦截：有害技能卡针对有 invulnerable 状态的玩家时，抵消效果
    _HARMFUL_SKILL_IDS = {'fire_attack', 'surprise_attack', 'crossbow', 'siege', 'poison', 'freeze',
                          'steal_card', 'tribute', 'reverse', 'arrow_rain'}
    if target_id and skill_type_key in _HARMFUL_SKILL_IDS:
        target_for_check = room.players.get(target_id)
        if target_for_check and target_for_check.is_alive and target_for_check.status_effects.get('invulnerable'):
            # 抵消技能效果，消耗无懈可击状态
            target_for_check.status_effects.pop('invulnerable', None)
            if skill_card in player.skills:
                player.skills.remove(skill_card)
            result_msg += '，但被' + target_for_check.name + '的无懈可击卡抵消！'
            _emit('skill_used', {
                'player_id': player_id,
                'player_name': player.name,
                'skill_name': skill_card.get('name', '技能卡'),
                'message': result_msg,
                'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
            }, room=room_id)
            return True, result_msg

    # ===== 攻击类 =====
    if skill_type == 'attack':
        # --- 需要目标的攻击效果 ---
        if target_id:
            target = room.players.get(target_id)
            if not target or not target.is_alive:
                return False, ''

            damage = effect.get('damage', 0) * multiplier
            if damage:
                target.change_cities(-damage)
                result_msg += '，对 ' + target.name + ' 造成 ' + str(damage) + ' 伤害'

            if effect.get('self_damage'):
                sd = effect['self_damage'] * multiplier
                player.change_cities(-sd)
                result_msg += '，自身损失 ' + str(sd) + ' 城池'

            if effect.get('ignore_defend'):
                player.status_effects['ignore_defend'] = True
                result_msg += '（无视守城）'

            if effect.get('multi_target'):
                other_targets = [pid for pid, p in room.players.items()
                                 if p.is_alive and not p.is_spectator
                                 and pid != target_id and pid != player_id]
                if other_targets:
                    second_id = random.choice(other_targets)
                    second = room.players[second_id]
                    second_damage = effect.get('damage', 0) * multiplier
                    second.change_cities(-second_damage)
                    result_msg += '，对 ' + second.name + ' 造成 ' + str(second_damage) + ' 伤害'

            if effect.get('stun'):
                target.status_effects['stun'] = 2
                if target_id in room.game_state.actions:
                    room.game_state.actions[target_id] = {
                        'player_id': target_id,
                        'action_type': 'skip',
                        'target_id': None,
                        'bet': 0,
                        'timestamp': room.game_state.actions[target_id].get('timestamp', 0)
                    }
                result_msg += '，' + target.name + ' 下回合无法行动'

        # --- 自身buff攻击效果（无需目标）---
        if effect.get('permanent_damage_bonus'):
            bonus = effect['permanent_damage_bonus'] * multiplier
            player.status_effects['permanent_damage_bonus'] = player.status_effects.get('permanent_damage_bonus', 0) + bonus
            result_msg += '，每轮伤害永久+' + str(bonus)

        if effect.get('one_attack_multiplier'):
            mult = effect['one_attack_multiplier']
            player.status_effects['next_attack_multiplier'] = mult
            result_msg += '，下一次攻城伤害×' + str(mult) + '（单次生效）'

        if effect.get('lifesteal_percent'):
            pct = effect['lifesteal_percent']
            player.status_effects['lifesteal_percent'] = player.status_effects.get('lifesteal_percent', 0) + pct
            result_msg += '，攻击时永久吸取' + str(int(pct * 100)) + '%总血量'

        if effect.get('permanent_attack_bonus'):
            bonus = effect['permanent_attack_bonus']
            player.status_effects['permanent_attack_bonus'] = player.status_effects.get('permanent_attack_bonus', 0) + bonus
            result_msg += '，攻击伤害永久+' + str(int(bonus * 100)) + '%'

        if effect.get('aoe_damage'):
            base_dmg = effect.get('aoe_damage', 0) * multiplier
            per_player = effect.get('aoe_per_player', 0) * multiplier
            n_other = sum(1 for pid, p in room.players.items() if pid != player_id and p.is_alive and not p.is_spectator)
            total_dmg = base_dmg + per_player * n_other
            total_dealt = 0
            for pid, p in room.players.items():
                if pid != player_id and p.is_alive and not p.is_spectator:
                    p.change_cities(-total_dmg)
                    total_dealt += total_dmg
            gain = total_dealt // 3
            player.change_cities(gain)
            result_msg += '，对其他' + str(n_other) + '名玩家各造成' + str(total_dmg) + '伤害，获得' + str(gain) + '城池'

    # ===== 防御类 =====
    elif skill_type == 'defense':
        heal = effect.get('heal', 0) * multiplier
        if heal:
            player.change_cities(heal)
            result_msg += '，恢复 ' + str(heal) + ' 城池'

        if effect.get('damage_reduction'):
            player.status_effects['damage_reduction'] = effect['damage_reduction']
            result_msg += '，下回合伤害减半'

        if effect.get('reflect'):
            reflect_val = effect['reflect'] * multiplier
            player.status_effects['reflect'] = reflect_val
            result_msg += '，下回合被攻击时反弹 ' + str(reflect_val) + ' 伤害'

        if effect.get('immune'):
            player.status_effects['immune'] = True
            result_msg += '，下回合免疫攻击'

        if effect.get('untargetable'):
            player.status_effects['untargetable'] = True
            result_msg += '，下回合无法被选中'

        if effect.get('counter_skill'):
            player.status_effects['invulnerable'] = True
            result_msg += '，对有害技能卡免疫'

        if effect.get('flat_damage_reduction'):
            reduction = effect['flat_damage_reduction'] * multiplier
            player.status_effects['flat_damage_reduction'] = player.status_effects.get('flat_damage_reduction', 0) + reduction
            result_msg += '，永久减伤' + str(reduction)

        if effect.get('recurring_heal'):
            amt = effect['recurring_heal'] * multiplier
            player.status_effects['recurring_heal'] = player.status_effects.get('recurring_heal', 0) + amt
            result_msg += '，每轮+' + str(amt) + '血'

        if effect.get('permanent_reduction'):
            red = effect['permanent_reduction']
            player.status_effects['permanent_reduction'] = player.status_effects.get('permanent_reduction', 0) + red
            result_msg += '，永久减伤' + str(int(red * 100)) + '%'

    # ===== 资源类 =====
    elif skill_type == 'resource':
        heal = effect.get('heal', 0) * multiplier
        if heal:
            player.change_cities(heal)
            result_msg += '，获得 ' + str(heal) + ' 城池'
        percent = effect.get('percent', 0)
        if percent:
            gain = int(player.cities * percent)
            player.change_cities(gain)
            result_msg += '，获得 ' + str(gain) + ' 城池'
        steal = effect.get('steal', 0) * multiplier
        if steal and steal > 0:
            total = 0
            for pid, p in room.players.items():
                if pid != player_id and p.is_alive and not p.is_spectator:
                    p.change_cities(-steal)
                    total += steal
            player.change_cities(total)
            result_msg += '，从其他玩家处掠夺 ' + str(total) + ' 城池'

        if effect.get('recurring'):
            rounds = effect.get('recurring', 0)
            amount = effect.get('amount', 0) * multiplier
            player.status_effects['recurring'] = {'rounds': rounds, 'amount': amount}
            result_msg += '，接下来 ' + str(rounds) + ' 回合每回合获得 ' + str(amount) + ' 城池'

        if effect.get('force_attack'):
            player.status_effects['force_attack'] = True
            result_msg += '，下回合必须攻城'

        if effect.get('skip_turn'):
            player.status_effects['skip_turn'] = True
            result_msg += '，下回合跳过行动'

        # 撒豆成兵卡 - 城池-cost，delay_rounds轮后+delayed_heal
        if effect.get('delayed_heal'):
            cost = effect.get('cost', 0) * multiplier
            delayed_heal = effect['delayed_heal'] * multiplier
            delay_rounds = effect.get('delay_rounds', 3)
            if cost:
                player.change_cities(-cost)
            player.status_effects['delay_troops'] = {
                'heal': delayed_heal,
                'rounds_left': delay_rounds
            }
            result_msg += '，消耗' + str(cost) + '城池，' + str(delay_rounds) + '轮后恢复' + str(delayed_heal) + '城池'

        # 聚宝盆卡 - 城池收益永久×1.25
        if effect.get('income_multiplier'):
            mult = effect['income_multiplier']
            player.status_effects['income_multiplier'] = player.status_effects.get('income_multiplier', 1) * mult
            result_msg += '，城池收益永久×' + str(mult)

        # 等价交换卡 - -cost城获得bonus_cards张技能卡
        if effect.get('bonus_cards'):
            cost = effect.get('cost', 0) * multiplier
            bonus_cards = effect['bonus_cards']
            if player.cities >= cost:
                player.change_cities(-cost)
                from game.skills import get_random_skill
                for _ in range(bonus_cards):
                    new_card = get_random_skill()
                    player.skills.append(new_card)
                result_msg += '，消耗' + str(cost) + '城池获得' + str(bonus_cards) + '张技能卡'
            else:
                return False, '城池不足，需要' + str(cost) + '城池'

        # 以逸待劳卡 - 获得收益时×2
        if effect.get('double_gain'):
            player.status_effects['double_gain'] = True
            result_msg += '，获得收益时×2'

    # ===== 特殊类 =====
    elif skill_type == 'special':
        if effect.get('swap'):
            if not target_id:
                return False, ''
            target = room.players.get(target_id)
            if not target or not target.is_alive:
                return False, ''
            max_diff = effect.get('max_diff', 100) * multiplier
            if abs(player.cities - target.cities) > max_diff:
                return False, f'城池差超过{max_diff}，无法使用逆转卡'
            player.cities, target.cities = target.cities, player.cities
            # 交换后3轮内双方不能攻击对方
            player.status_effects['reverse_no_attack'] = {'target': target_id, 'rounds': 3}
            target.status_effects['reverse_no_attack'] = {'target': player_id, 'rounds': 3}
            result_msg += '，与 ' + target.name + ' 交换了城池数，3轮内不能互相攻击'

        elif effect.get('reveal'):
            if not target_id:
                return False, ''
            target = room.players.get(target_id)
            if not target:
                return False, ''
            skill_names = '、'.join([s.get('name', '?') for s in target.skills]) if target.skills else '无'
            target_action = room.game_state.actions.get(target_id)
            if target_action:
                action_names = {'attack': '攻城', 'defend': '守城', 'jungle': '打野', 'duel': '约战', 'repair': '修城', 'alliance': '结盟', 'skip': '跳过'}
                action_info = action_names.get(target_action['action_type'], target_action['action_type'])
                if target_action.get('target_id') and target_action['target_id'] in room.players:
                    action_info += ' → ' + room.players[target_action['target_id']].name
            else:
                action_info = '未提交'
            result_msg += '，侦查 ' + target.name + '：手牌【' + skill_names + '】行动：' + action_info

        elif effect.get('dissolve_all_alliances'):
            # 离间卡 - 解散所有联盟，3轮内不能联盟
            for pid, p in room.players.items():
                p.alliance_with = None
                p.status_effects['no_alliance'] = 3
            result_msg += '，解散了所有联盟，3轮内不能联盟'

        elif effect.get('emergency_heal'):
            # 急救卡 - 城池<0时使用
            heal_amount = effect['emergency_heal'] * multiplier
            if player.cities < 0 or not player.is_alive:
                player.cities += heal_amount
                if player.cities >= 0:
                    player.is_alive = True
                    player.is_spectator = False
                    result_msg += '，紧急恢复 ' + str(heal_amount) + ' 城池，已复活！'
                else:
                    result_msg += '，紧急恢复 ' + str(heal_amount) + ' 城池'
            else:
                result_msg += '，城池数正常，急救卡效果未触发'

        elif effect.get('steal_card'):
            # 瞒天过海卡 - 消耗cost城池偷走指定玩家一张卡
            cost = effect.get('cost', 30) * multiplier
            if player.cities < cost:
                return False, '城池不足，需要' + str(cost) + '城池'
            if not target_id:
                return False, ''
            target = room.players.get(target_id)
            if not target or not target.is_alive or not target.skills:
                return False, '目标玩家没有可偷的卡'
            player.change_cities(-cost)
            stolen = random.choice(target.skills)
            target.remove_skill(stolen.get('id', ''))
            player.skills.append(stolen)
            result_msg += '，消耗' + str(cost) + '城池偷走' + target.name + '的【' + stolen.get('name', '技能卡') + '】'

        elif effect.get('demand_card'):
            # 顺手牵羊卡 - 让对方给你一张技能卡
            if not target_id:
                return False, ''
            target = room.players.get(target_id)
            if not target or not target.is_alive or not target.skills:
                return False, '目标玩家没有可给的卡'
            given = random.choice(target.skills)
            target.remove_skill(given.get('id', ''))
            player.skills.append(given)
            result_msg += '，从' + target.name + '处获得一张【' + given.get('name', '技能卡') + '】'

        elif effect.get('extra_action'):
            # 二般人卡 - 一轮可行动两次
            player.status_effects['extra_action'] = 1
            result_msg += '，本轮可行动两次'

        elif effect.get('upgrade_skill'):
            # 升级卡 - 自主选择一张技能卡，效果数值×2（未指定时随机，供AI使用）
            target_skill = None
            if upgrade_target:
                for s in player.skills:
                    if s is not skill_card and (s.get('skill_type') == upgrade_target or s.get('id') == upgrade_target):
                        target_skill = s
                        break
            if not target_skill:
                other_skills = [s for s in player.skills if s is not skill_card]
                if other_skills:
                    target_skill = random.choice(other_skills)
            if target_skill:
                # 效果数值×2（百分比类封顶0.95，避免数值越界）
                _PCT_KEYS = {'percent', 'damage_reduction', 'permanent_reduction', 'post_save_reduction',
                             'lifesteal_percent', 'permanent_attack_bonus'}
                eff = target_skill.get('effect')
                if isinstance(eff, dict):
                    for k, v in list(eff.items()):
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            eff[k] = min(0.95, v * 2) if k in _PCT_KEYS else v * 2
                    target_skill['effect'] = eff
                if not target_skill.get('upgraded'):
                    target_skill['name'] = (target_skill.get('name') or '技能卡') + '（已升级）'
                target_skill['upgraded'] = True
                result_msg += '，升级了【' + target_skill.get('name', '技能卡') + '】效果×2'
            else:
                result_msg += '，没有可升级的技能卡'

        else:
            return False, ''

    else:
        return False, ''

    # 移除技能卡
    if skill_card in player.skills:
        player.skills.remove(skill_card)

    # 检查阵亡
    for p in room.players.values():
        if not p.is_alive and not p.is_spectator:
            p.is_spectator = True

    # 移除死亡玩家的已提交行动
    dead_player_ids = [pid for pid, p in room.players.items() if not p.is_alive]
    for dead_id in dead_player_ids:
        room.game_state.actions.pop(dead_id, None)

    # 广播
    _emit('skill_used', {
        'player_id': player_id,
        'player_name': player.name,
        'skill_name': skill_card.get('name', '技能卡'),
        'message': result_msg,
        'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
    }, room=room_id)

    _emit('players_update', {
        'players': {pid: p.to_dict(is_spectator=False, is_self=(pid == player_id)) for pid, p in room.players.items()}
    }, room=room_id)

    # 技能卡可能杀死玩家，检查是否所有存活玩家都已提交行动（二般人待用则暂不结算）
    alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
    pending_extra = any(
        p.is_alive and not p.is_spectator
        and p.status_effects.get('extra_action')
        and p.id in room.game_state.actions
        for p in room.players.values()
    )
    if len(room.game_state.actions) >= len(alive) and not pending_extra:
        _process_round(room_id)

    return True, result_msg


# ===== 辅助函数（全部用 socketio.emit） =====

def _build_game_state(room, viewer_id=None):
    gs = room.game_state
    return {
        'round': gs.round if gs else 1,
        'phase': gs.phase.value if gs else 'waiting',
        'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()},
        'skill_cards_drawn': gs.skill_cards_drawn if gs else 0,
    }


# ===== 濒死抉择（不死图腾）与统一死亡检查 =====

_TOTEM_TIMEOUT = 15  # 濒死抉择超时秒数


def _totem_card(player):
    """返回玩家手中的不死图腾卡（未使用），无则返回 None"""
    for s in player.skills:
        if isinstance(s, dict) and s.get('skill_type') == 'immortal_totem':
            return s
    return None


def _begin_totem_choice(room_id, player):
    """玩家濒死且持有不死图腾：AI立即决策，真人弹窗选择（超时视为放弃）"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    gs = room.game_state
    if not hasattr(gs, 'pending_totem'):
        gs.pending_totem = []
    if player.id in gs.pending_totem:
        return
    gs.pending_totem.append(player.id)

    if player.is_ai:
        card = _totem_card(player)
        from game.manager import get_multiplier
        heal = card['effect'].get('emergency_heal', 50) * get_multiplier(gs.round) if card else 0
        use = bool(card) and (player.cities + heal) >= 0
        _resolve_totem_choice(room_id, player.id, use)
    else:
        _emit('death_choice', {
            'player_id': player.id,
            'player_name': player.name,
            'cities': player.cities,
            'timeout': _TOTEM_TIMEOUT,
        }, room=player.id)

        def _timeout(pid=player.id):
            r = room_manager.get_room(room_id)
            if not r or not r.game_state:
                return
            if pid in getattr(r.game_state, 'pending_totem', []):
                _resolve_totem_choice(room_id, pid, False, timeout=True)

        threading.Timer(_TOTEM_TIMEOUT, _timeout).start()


def _resolve_totem_choice(room_id, player_id, use, timeout=False):
    """处理玩家的濒死抉择结果"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    gs = room.game_state
    pending = getattr(gs, 'pending_totem', [])
    if player_id not in pending:
        return
    pending.remove(player_id)

    player = room.players.get(player_id)
    if not player:
        return

    from game.manager import get_multiplier
    multiplier = get_multiplier(gs.round)

    if use:
        card = _totem_card(player)
        if card:
            effect = card.get('effect', {})
            heal = effect.get('emergency_heal', 50) * multiplier
            player.skills.remove(card)
            player.cities += heal
            player.status_effects['immortal_totem'] = {
                'triggered': True,
                'post_save_reduction': effect.get('post_save_reduction', 0.2),
                'post_save_heal': effect.get('post_save_heal', 5) * multiplier,
                'post_save_rounds': effect.get('post_save_rounds', 3),
            }
            if player.cities >= 0:
                msg = f"{player.name} 使用不死图腾，恢复{heal}城池，继续战斗！"
            else:
                player.is_alive = False
                player.is_spectator = True
                msg = f"{player.name} 使用不死图腾恢复{heal}城池，但仍不足，已阵亡"
        else:
            player.is_alive = False
            player.is_spectator = True
            msg = f"{player.name} 已无不死图腾，已阵亡"
    else:
        player.is_alive = False
        player.is_spectator = True
        msg = f"{player.name} {'超时未决定，' if timeout else ''}放弃使用不死图腾，已阵亡"

    _emit('death_resolved', {
        'message': msg,
        'player_id': player_id,
        'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
    }, room=room_id)

    # 所有抉择处理完毕后检查游戏是否结束
    _check_game_end(room_id)
    # 若其余玩家均已ready（濒死者阵亡后无人再点继续），由AI ready流程接管推进
    if room.game_state.phase != GamePhase.FINISHED:
        _auto_ready_ai(room_id)


def _check_deaths(room_id):
    """统一死亡检查：城池<0的存活玩家 → 持不死图腾则发起濒死抉择，否则直接阵亡"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    messages = []
    for pid, p in list(room.players.items()):
        if p.is_alive and not p.is_spectator and p.cities < 0:
            if _totem_card(p):
                _begin_totem_choice(room_id, p)
            else:
                p.is_alive = False
                p.is_spectator = True
                messages.append(f"{p.name} 城池耗尽，已阵亡")
    if messages:
        _emit('death_resolved', {
            'messages': messages,
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)
    _check_game_end(room_id)


def _check_game_end(room_id):
    """检查游戏是否结束（有濒死抉择未完成时不判定）"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    gs = room.game_state
    if getattr(gs, 'pending_totem', None):
        return
    if gs.phase == GamePhase.FINISHED:
        return
    alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
    if len(alive) <= 1:
        gs.phase = GamePhase.FINISHED
        _emit('game_ended', {'winner': alive[0].to_dict() if alive else None}, room=room_id)


def _process_round(room_id):
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    results = room_manager.process_round(room_id)

    # 统一死亡检查（含不死图腾濒死抉择），可能直接触发游戏结束
    _check_deaths(room_id)

    # 设置会议阶段（游戏已结束时保持FINISHED）
    if room.game_state.phase != GamePhase.FINISHED:
        room.game_state.phase = GamePhase.MEETING

    # 保存约战信息
    duels = results.get('duels', [])

    # 构建回合结果数据
    round_result_data = {
        'round': results.get('round', room.game_state.round),
        'messages': results.get('messages', []),
        'city_changes': results.get('city_changes', {}),
        'skill_cards': results.get('skill_cards', []),
        'actions': results.get('actions', {}),
        'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
    }

    # 保存回合历史供AI决策使用（保留最近3轮）
    if not hasattr(room.game_state, 'round_history'):
        room.game_state.round_history = []
    room.game_state.round_history.append({
        'round': round_result_data['round'],
        'messages': round_result_data['messages'],
        'city_changes': round_result_data['city_changes'],
        'actions': {pid: act for pid, act in round_result_data.get('actions', {}).items()
                    if not room.players.get(pid, Player(id='', name='', room_id='')).is_ai}  # AI不关心其他AI的行动
    })
    # 只保留最近3轮
    room.game_state.round_history = room.game_state.round_history[-3:]

    alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
    if len(alive) <= 1 and room.game_state.phase == GamePhase.FINISHED:
        # 游戏结束（game_ended 已在 _check_deaths 中发出）
        _emit('round_result', round_result_data, room=room_id)
        return

    gs = room.game_state
    if not hasattr(gs, 'ready_players'):
        gs.ready_players = set()

    # 如果有约战，先启动约战流程，延迟显示小结
    if duels:
        gs._pending_duels = duels
        gs._pending_round_result = round_result_data
        # 立即启动第一场约战
        duel_info = gs._pending_duels.pop(0)
        _start_duel(room_id, duel_info)
        return

    # 无约战，直接显示小结
    _emit('round_result', round_result_data, room=room_id)

    # AI预请求：在本轮小结时就发送API请求，下回合直接用缓存结果
    _prefetch_ai_decisions(room_id)

    # AI玩家自动ready（不需要点击继续按钮）
    _auto_ready_ai(room_id)

    # 拍卖由 on_ready_next_round 触发（玩家点击继续后）


def _start_duel(room_id, duel_info):
    """发起约战请求：先询问被约战方是否接受"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    initiator = duel_info['initiator']
    target = duel_info['target']
    bet = duel_info['bet']

    # 保存待处理的约战信息
    room.game_state.duel = {
        'initiator': initiator,
        'initiator_name': duel_info['initiator_name'],
        'target': target,
        'target_name': duel_info['target_name'],
        'bet': bet,
    }
    room.game_state.phase = GamePhase.DUEL

    # 通知双方：被约战方需要选择接受/拒绝
    _emit('duel_request', {
        'initiator': initiator,
        'initiator_name': duel_info['initiator_name'],
        'target': target,
        'target_name': duel_info['target_name'],
        'bet': bet,
    }, room=room_id)

    # 如果被约战方是AI，自动决策
    target_player = room.players.get(target)
    if target_player and target_player.is_ai:
        # AI策略：城池>bet*1.5时有70%概率接受，否则50%接受
        accept_chance = 0.7 if target_player.cities > bet * 1.5 else 0.5
        if random.random() < accept_chance:
            # 延迟1秒后自动接受
            threading.Timer(1.0, lambda: _accept_duel(room_id, duel_info)).start()
        else:
            # 延迟1秒后自动拒绝
            threading.Timer(1.0, lambda: _reject_duel(room_id)).start()


def _accept_duel(room_id, duel_info):
    """被约战方接受，开始轮盘赌"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state or not room.game_state.duel:
        return
    if room.game_state.phase != GamePhase.DUEL:
        return

    # 统一10发转轮，前三枪空包弹
    chambers = 10
    bullet_pos = random.randint(3, 9)

    duel = room.game_state.duel
    duel['chambers'] = chambers
    duel['bullet_pos'] = bullet_pos
    duel['fired'] = 0
    duel['current_turn'] = duel['initiator']  # 发起者先开枪

    _emit('duel_started', {
        'initiator': duel['initiator'],
        'initiator_name': duel['initiator_name'],
        'target': duel['target'],
        'target_name': duel['target_name'],
        'bet': duel['bet'],
        'chambers': chambers,
        'bullet_pos': bullet_pos,
        'current_turn': duel['initiator']
    }, room=room_id)
    # 如果发起者是AI，自动开枪
    _auto_duel_shot(room_id)


def _reject_duel(room_id):
    """被约战方拒绝，交50%赌注"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state or not room.game_state.duel:
        return
    if room.game_state.phase != GamePhase.DUEL:
        return

    duel = room.game_state.duel
    bet = duel['bet']
    tribute = int(bet * 0.5)
    rejecter = room.players.get(duel['target'])
    other = room.players.get(duel['initiator'])
    if rejecter and other and tribute > 0:
        rejecter.change_cities(-tribute)
        other.change_cities(tribute)
    room.game_state.duel = None

    reject_data = {
        'rejecter_name': rejecter.name if rejecter else '',
        'other_name': other.name if other else '',
        'tribute': tribute,
        'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
    }
    _emit('duel_rejected', reject_data, room=room_id)

    # 继续处理下一个约战或回到正常流程
    _after_duel_end(room_id)


def _after_duel_end(room_id):
    """约战结束后的统一处理：检查下一个约战或回到正常流程"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    # 检查是否有人因约战死亡（统一死亡检查，含不死图腾濒死抉择）
    _check_deaths(room_id)
    if room.game_state.phase == GamePhase.FINISHED:
        return

    if hasattr(room.game_state, '_pending_duels') and room.game_state._pending_duels:
        next_duel = room.game_state._pending_duels.pop(0)
        _start_duel(room_id, next_duel)
    else:
        if hasattr(room.game_state, '_pending_round_result') and room.game_state._pending_round_result:
            pending = room.game_state._pending_round_result
            pending['players'] = {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
            _emit('round_result', pending, room=room_id)
            room.game_state._pending_round_result = None
            _prefetch_ai_decisions(room_id)
            _auto_ready_ai(room_id)
        room.game_state.phase = GamePhase.MEETING
        if hasattr(room.game_state, 'ready_players'):
            room.game_state.ready_players = set()


def _start_auction(room_id):
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
    if not alive:
        _start_next_round(room_id)
        return

    skill_id = random.choice(list(SKILL_CARDS.keys()))
    skill = SKILL_CARDS[skill_id].copy()
    skill['id'] = str(uuid.uuid4())
    skill['skill_type'] = skill_id
    starting_price = max(10, min(p.cities for p in alive) // 4)

    room.game_state.auction = {
        'skill_card': skill,
        'starting_price': starting_price,
        'current_bid': starting_price,
        'highest_bidder': None,
        'passed_players': []
    }
    room.game_state.phase = GamePhase.AUCTION

    _emit('auction_started', {
        'round': room.game_state.round,
        'skill_card': skill,
        'starting_price': starting_price,
        'time_limit': 30
    }, room=room_id)

    # AI玩家拍卖决策：根据城池和技能卡数量决定是否竞价
    ai_players = [p for p in alive if p.is_ai and not p.is_spectator]
    for ai in ai_players:
        # AI策略：城池>50且技能卡<2张时，有50%概率竞价；否则pass
        will_bid = (ai.cities > 50 and len(ai.skills) < 2 and random.random() < 0.5)
        if will_bid:
            bid_amount = min(ai.cities, room.game_state.auction['current_bid'] + 10)
            room.game_state.auction['current_bid'] = bid_amount
            room.game_state.auction['highest_bidder'] = ai.id
            _emit('auction_updated', {
                'current_bid': bid_amount,
                'highest_bidder_name': ai.name
            }, room=room_id)
        else:
            room.game_state.auction['passed_players'].append(ai.id)
    # 如果所有存活玩家都pass了，直接结束拍卖
    alive_non_spectator = [p for p in alive if not p.is_spectator]
    if len(room.game_state.auction['passed_players']) >= len(alive_non_spectator):
        threading.Timer(2.0, _end_auction, args=(room_id,)).start()
    else:
        threading.Timer(30.0, _end_auction, args=(room_id,)).start()


def _end_auction(room_id):
    room = room_manager.get_room(room_id)
    if not room or not room.game_state or not room.game_state.auction:
        return

    auction = room.game_state.auction
    players_data = {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
    if auction['highest_bidder']:
        winner = room.players.get(auction['highest_bidder'])
        if winner:
            winner.cities -= auction['current_bid']
            winner.add_skill(auction['skill_card'])
            _emit('auction_ended', {
                'passed': False,
                'winner_name': winner.name,
                'bid': auction['current_bid'],
                'skill_card': auction['skill_card'],
                'players': players_data
            }, room=room_id)
    else:
        _emit('auction_ended', {'passed': True, 'players': players_data}, room=room_id)

    room.game_state.auction = None
    _start_next_round(room_id)


def _start_next_round(room_id):
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
    if len(alive) <= 1:
        winner = alive[0] if alive else None
        _emit('game_ended', {'winner': winner.to_dict() if winner else None}, room=room_id)
        return

    # 重置每轮标志
    for p in room.players.values():
        p.repair_active = False
        # 清除单回合状态效果
        for key in ['skip_turn', 'force_attack', 'ignore_defend',
                     'damage_reduction', 'reflect', 'immune', 'untargetable',
                     'invulnerable', 'extra_action']:
            p.status_effects.pop(key, None)
        # 眩晕：支持计数器，递减而非直接清除
        stun = p.status_effects.get('stun')
        if stun:
            if isinstance(stun, int) and stun > 1:
                p.status_effects['stun'] = stun - 1
            else:
                p.status_effects.pop('stun', None)
        # 离间效果递减
        blocked = p.status_effects.get('blocked_attack')
        if blocked:
            blocked['rounds'] = blocked.get('rounds', 1) - 1
            if blocked['rounds'] <= 0:
                del p.status_effects['blocked_attack']
        # 逆转卡效果递减：交换后不能攻击对方
        reverse_no = p.status_effects.get('reverse_no_attack')
        if reverse_no:
            reverse_no['rounds'] = reverse_no.get('rounds', 1) - 1
            if reverse_no['rounds'] <= 0:
                del p.status_effects['reverse_no_attack']
        # 离间卡效果递减：不能联盟
        no_ally = p.status_effects.get('no_alliance')
        if no_ally:
            if isinstance(no_ally, int) and no_ally > 1:
                p.status_effects['no_alliance'] = no_ally - 1
            else:
                p.status_effects.pop('no_alliance', None)

    room.game_state.next_round()
    room.game_state._auction_done_this_round = False
    _emit('next_round', _build_game_state(room), room=room_id)
    # AI玩家自动行动
    _trigger_ai_actions(room_id)


def _prefetch_ai_decisions(room_id):
    """本轮小结时预请求AI决策，结果缓存到玩家对象，下回合直接使用"""
    import random as _random
    from game.ai_player import ai_decide

    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    ai_players = [p for p in room.players.values() if p.is_ai and p.is_alive and not p.is_spectator]
    if not ai_players:
        return

    # 标记预请求进行中
    room.game_state._ai_prefetch_pending = len(ai_players)

    for i, ai_player in enumerate(ai_players):
        # 错开请求时间，避免429限流
        delay = 0.3 + i * 1.5 + _random.uniform(0, 0.3)
        pid = ai_player.id

        def _prefetch(pid=pid, d=delay):
            r = room_manager.get_room(room_id)
            if not r or not r.game_state:
                return
            p = r.players.get(pid)
            if not p or not p.is_alive:
                # 减少pending计数
                if hasattr(r.game_state, '_ai_prefetch_pending'):
                    r.game_state._ai_prefetch_pending = max(0, r.game_state._ai_prefetch_pending - 1)
                return

            config = p.status_effects.get('ai_config', {})
            if not config.get('api_key'):
                if hasattr(r.game_state, '_ai_prefetch_pending'):
                    r.game_state._ai_prefetch_pending = max(0, r.game_state._ai_prefetch_pending - 1)
                return

            print(f'[AI] prefetch: {p.name} 开始预请求决策')
            decision = ai_decide(r, pid, config)
            print(f'[AI] prefetch: {p.name} 预请求完成: {decision}')

            # 缓存决策到玩家对象，减少pending计数
            p = r.players.get(pid)
            if p:
                p.status_effects['_ai_cached_decision'] = decision
            if r and hasattr(r.game_state, '_ai_prefetch_pending'):
                r.game_state._ai_prefetch_pending = max(0, r.game_state._ai_prefetch_pending - 1)

        threading.Timer(delay, _prefetch).start()


def _auto_ready_ai(room_id):
    """AI玩家自动发送ready_next_round（不需要点击继续按钮）"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    gs = room.game_state
    if not hasattr(gs, 'ready_players'):
        gs.ready_players = set()
    ai_players = [p for p in room.players.values() if p.is_ai and p.is_alive and not p.is_spectator]
    for ai in ai_players:
        gs.ready_players.add(ai.id)
    # 有濒死抉择未完成时不进入下一轮
    if getattr(gs, 'pending_totem', None):
        return
    # 检查是否所有存活玩家都ready了
    alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
    alive_ready = [pid for pid in gs.ready_players if pid in {p.id for p in alive}]
    if len(alive_ready) >= len(alive):
        gs.ready_players = set()
        # 检查拍卖（第10轮起每5轮）
        if gs.round >= 10 and (gs.round - 10) % 5 == 0 and not getattr(gs, '_auction_done_this_round', False):
            gs._auction_done_this_round = True
            _start_auction(room_id)
        else:
            _start_next_round(room_id)


def _trigger_ai_actions(room_id):
    """触发AI玩家的自动行动"""
    import random as _random
    from game.ai_player import ai_decide

    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return
    if room.game_state.phase != GamePhase.ACTION:
        return

    # 只触发尚未提交行动的AI玩家（检查 game_state.actions 而非 p.action）
    ai_players = [p for p in room.players.values() if p.is_ai and p.is_alive and not p.is_spectator and p.id not in room.game_state.actions]
    print(f'[AI] trigger_ai_actions: room={room_id}, phase={room.game_state.phase.value}, ai_count={len(ai_players)}, all_players={[(p.id, p.is_ai, p.action) for p in room.players.values()]}')
    if not ai_players:
        return

    for i, ai_player in enumerate(ai_players):
        # 检查是否有预请求缓存的决策
        cached = ai_player.status_effects.pop('_ai_cached_decision', None)
        pid = ai_player.id

        def _apply_ai_decision(pid, decision, r, p):
            """执行AI决策（技能卡+提交行动），返回是否成功"""
            # API调用失败时通知房间内玩家
            ai_error = decision.pop('_ai_error', None)
            ai_raw = decision.pop('_ai_raw', None)
            ai_raw_resp = decision.pop('_ai_raw_response', None)
            if ai_error:
                _emit('ai_api_error', {
                    'ai_name': p.name,
                    'error': ai_error,
                    'raw_content': ai_raw or '',
                    'raw_response': ai_raw_resp or ''
                }, room=room_id)

            # AI使用技能卡
            if decision.get('use_skill') and p.skills:
                skill_name = decision.get('skill_name', '')
                skill_to_use = None
                if skill_name:
                    for s in p.skills:
                        if s.get('name') == skill_name:
                            skill_to_use = s
                            break
                if not skill_to_use:
                    skill_to_use = p.skills[0]

                skill_id = skill_to_use.get('skill_type') or skill_to_use.get('id')
                skill_target_id = decision.get('skill_target_id')

                skill_type = skill_to_use.get('type', '')
                needs_target = skill_type in _SKILL_NEEDS_TARGET and skill_id not in _SKILL_NO_TARGET_IDS

                if needs_target and not skill_target_id:
                    alive_targets = [tid for tid, tp in r.players.items()
                                    if tp.is_alive and not tp.is_spectator and tid != pid]
                    if alive_targets:
                        skill_target_id = _random.choice(alive_targets)
                    else:
                        skill_target_id = None

                if not needs_target or skill_target_id:
                    _apply_skill_card(room_id, pid, skill_id, skill_target_id)
                    p = r.players.get(pid)
                    if not p or not p.is_alive:
                        return False

            action_type = decision.get('action', 'defend')
            target_id = decision.get('target_id')
            bet = decision.get('bet', 0) or 0

            valid_actions = ['attack', 'defend', 'jungle', 'repair', 'alliance', 'dissolve_alliance', 'duel', 'skip']
            if action_type not in valid_actions:
                action_type = 'defend'
            if action_type in ['repair', 'alliance', 'dissolve_alliance', 'duel'] and r.game_state.round < 3:
                action_type = 'defend'
            if action_type in ['attack', 'alliance'] and target_id:
                target = r.players.get(target_id)
                if not target or not target.is_alive or target.is_spectator:
                    action_type = 'defend'
                    target_id = None

            ok = room_manager.submit_action(room_id, pid, action_type, target_id, bet)
            print(f'[AI] {p.name} submit_action({action_type}, target={target_id}) => ok={ok}')
            if ok:
                action_detail = {
                    'type': action_type,
                    'target_id': target_id,
                    'bet': bet,
                }
                if target_id and target_id in r.players:
                    action_detail['target_name'] = r.players[target_id].name
                _emit('player_action_ready', {
                    'player_id': pid,
                    'player_name': p.name,
                    'action_type': action_type,
                    'action_detail': action_detail
                }, room=room_id)

                # 二般人卡：AI 自动提交第二行动（攻击随机目标或打野）
                p_now = r.players.get(pid)
                if p_now and p_now.status_effects.get('extra_action') and pid in r.game_state.actions:
                    alive_targets = [tid for tid, tp in r.players.items()
                                     if tp.is_alive and not tp.is_spectator and tid != pid]
                    if alive_targets and _random.random() < 0.7:
                        extra_type, extra_target = 'attack', _random.choice(alive_targets)
                    else:
                        extra_type, extra_target = 'jungle', None
                    ok2 = room_manager.submit_action(room_id, pid, extra_type, extra_target, 0)
                    if ok2:
                        _emit('player_action_ready', {
                            'player_id': pid,
                            'player_name': p_now.name,
                            'action_type': extra_type,
                            'action_detail': {'type': extra_type, 'target_id': extra_target, 'bet': 0, 'extra': True}
                        }, room=room_id)

                alive = [pp for pp in r.players.values() if pp.is_alive and not pp.is_spectator]
                pending_extra = any(
                    pp.is_alive and not pp.is_spectator
                    and pp.status_effects.get('extra_action')
                    and pp.id in r.game_state.actions
                    for pp in r.players.values()
                )
                if len(r.game_state.actions) >= len(alive) and not pending_extra:
                    _process_round(room_id)
            return ok

        if cached:
            # 有缓存决策，立即使用，无需等待
            print(f'[AI] {ai_player.name} 使用缓存决策: {cached}')
            r = room_manager.get_room(room_id)
            if r and r.game_state and r.game_state.phase == GamePhase.ACTION:
                p = r.players.get(pid)
                if p and p.is_alive:
                    _apply_ai_decision(pid, cached, r, p)
        else:
            # 无缓存：检查是否有预请求正在进行
            prefetch_pending = getattr(room.game_state, '_ai_prefetch_pending', 0)

            if prefetch_pending > 0:
                # 有预请求在进行中，等它完成再检查，超时后fallback到直接请求
                def _wait_for_cache(pid=pid, attempt=0):
                    r = room_manager.get_room(room_id)
                    if not r or not r.game_state or r.game_state.phase != GamePhase.ACTION:
                        return
                    p = r.players.get(pid)
                    if not p or not p.is_alive:
                        return

                    # 检查缓存是否已到达
                    cached_now = p.status_effects.pop('_ai_cached_decision', None)
                    if cached_now:
                        print(f'[AI] {p.name} 等到缓存决策: {cached_now}')
                        _apply_ai_decision(pid, cached_now, r, p)
                    elif attempt < 6:
                        # 预请求还在进行中，500ms后重试（最多等3秒）
                        print(f'[AI] {p.name} 等待预请求缓存... (attempt={attempt+1})')
                        threading.Timer(0.5, _wait_for_cache, args=(pid, attempt+1)).start()
                    else:
                        # 超时，fallback到直接API请求
                        config = p.status_effects.get('ai_config', {})
                        if not config.get('api_key'):
                            print(f'[AI] {p.name} 无API配置，跳过')
                            return
                        print(f'[AI] {p.name} 预请求超时，fallback直接请求')
                        decision = ai_decide(r, pid, config)
                        print(f'[AI] {p.name} 决策完成: {decision}')
                        _apply_ai_decision(pid, decision, r, p)

                _wait_for_cache()
            else:
                # 没有预请求（第一轮或预请求未触发），直接调用API
                config = ai_player.status_effects.get('ai_config', {})
                if config.get('api_key'):
                    print(f'[AI] {ai_player.name} 无预请求缓存，直接请求API')

                    def _direct_request(pid=pid):
                        r = room_manager.get_room(room_id)
                        if not r or not r.game_state or r.game_state.phase != GamePhase.ACTION:
                            return
                        p = r.players.get(pid)
                        if not p or not p.is_alive:
                            return
                        decision = ai_decide(r, pid, config)
                        print(f'[AI] {p.name} 决策完成: {decision}')
                        _apply_ai_decision(pid, decision, r, p)

                    threading.Timer(0.3, _direct_request).start()
                else:
                    print(f'[AI] {ai_player.name} 无API配置，跳过')


def _auto_duel_shot(room_id):
    """AI约战时自动开一枪"""
    import threading, random
    room = room_manager.get_room(room_id)
    if not room or not room.game_state or not room.game_state.duel:
        return
    duel = room.game_state.duel
    current_turn = duel.get('current_turn')
    if not current_turn:
        return
    player = room.players.get(current_turn)
    if player and player.is_ai:
        # 延迟0.5-1秒后自动开1枪，避免同步调用问题
        def _shoot():
            _do_duel_shot(room_id, current_turn, 1)
        threading.Timer(random.uniform(0.5, 1.0), _shoot).start()


def _do_duel_shot(room_id, player_id, shots):
    room = room_manager.get_room(room_id)
    if not room or not room.game_state or not room.game_state.duel:
        return

    duel = room.game_state.duel
    chambers = duel['chambers']
    bullet_pos = duel['bullet_pos']
    fired = duel['fired']

    hit = False
    for i in range(shots):
        pos = fired
        fired += 1
        if pos == bullet_pos:
            hit = True
            break

    duel['fired'] = fired

    _emit('duel_shot_result', {
        'player_id': player_id,
        'player_name': room.players[player_id].name if player_id in room.players else '',
        'shots': shots,
        'hit': hit,
        'fired': fired,
        'total': chambers
    }, room=room_id)

    if hit:
        initiator_id = duel['initiator']
        bet = duel['bet']

        if player_id == initiator_id:
            loser = room.players[player_id]
            winner_id = duel['target']
            winner = room.players.get(winner_id)
        else:
            loser = room.players[player_id]
            winner_id = initiator_id
            winner = room.players.get(winner_id)

        if loser and winner:
            loser.change_cities(-bet)
            winner.change_cities(bet)

        room.game_state.duel = None

        # 将约战结果累积到待发送的回合小结中
        if hasattr(room.game_state, '_pending_round_result') and room.game_state._pending_round_result:
            pending = room.game_state._pending_round_result
            duel_msg = '约战结束：' + (loser.name if loser else '') + ' 落败，' + (winner.name if winner else '') + ' 赢得 ' + str(bet) + ' 城池'
            pending['messages'] = [m for m in pending.get('messages', []) if m != '无事发生'] + [duel_msg]
            if loser and winner:
                if 'city_changes' not in pending:
                    pending['city_changes'] = {}
                pending['city_changes'][loser.id] = pending['city_changes'].get(loser.id, 0) - bet
                pending['city_changes'][winner.id] = pending['city_changes'].get(winner.id, 0) + bet

        # 更新玩家状态
        _emit('duel_ended', {
            'loser_name': loser.name if loser else '',
            'winner_name': winner.name if winner else '',
            'bet': bet,
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=room_id)

        # 统一死亡检查（含不死图腾濒死抉择）
        _check_deaths(room_id)
        if room.game_state.phase == GamePhase.FINISHED:
            return

        # 如果还有待处理的约战，继续下一场
        _after_duel_end(room_id)
    else:
        duel['current_turn'] = duel['target'] if player_id == duel['initiator'] else duel['initiator']
        _emit('duel_next_turn', {
            'current_turn': duel['current_turn'],
            'current_turn_name': room.players[duel['current_turn']].name if duel['current_turn'] in room.players else '',
            'fired': fired,
            'remaining': chambers - fired
        }, room=room_id)
        # AI轮到开枪时自动开一枪
        _auto_duel_shot(room_id)
