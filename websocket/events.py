"""
WebSocket 事件处理模块
与前端 main.js 事件完全对齐
所有 emit 统一用 socketio.emit() 以支持 Timer 回调
"""
from flask_socketio import join_room as sio_join, leave_room as sio_leave
from flask import request
from game.models import GamePhase
from game.skills import SKILL_CARDS
import random
import threading

# 运行时由 init_socket_events 注入
socketio = None
room_manager = None


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

        if len(room.players) < 2:
            _emit('error_msg', {'message': '至少需要2名玩家'})
            return

        ok = room_manager.start_game(room_id, player_id)
        if not ok:
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

    @socketio.on('leave_game')
    def on_leave_game(data):
        """玩家退出游戏，重置玩家状态和房间状态"""
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')

        room = room_manager.get_room(room_id)
        if not room or player_id not in room.players:
            return

        # 重置所有玩家状态（游戏结束后所有人一起重置）
        for p in room.players.values():
            p.is_alive = True
            p.is_spectator = False
            p.cities = 100
            p.skills = []
            p.alliance_with = None
            p.alliance_benefits = 0
            p.alliance_damages = 0
            p.repair_active = False
            p.status_effects = {}
            p.action = None

        # 重置房间游戏状态，使房间可以重新开始
        room.game_state = None

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
        _emit('game_state', _build_game_state(room))

    @socketio.on('submit_action')
    def on_submit_action(data):
        room_id = str(data.get('room_id', '')).strip()
        player_id = data.get('player_id', '')
        action_type = data.get('action_type', '')
        target_id = data.get('target_id')
        bet = data.get('bet', 0)
        gesture = data.get('gesture')

        room = room_manager.get_room(room_id)
        if not room:
            _emit('error_msg', {'message': '房间不存在'})
            return

        player = room.players.get(player_id)
        if not player or not player.is_alive:
            _emit('error_msg', {'message': '无法操作'})
            return

        ok = room_manager.submit_action(room_id, player_id, action_type,
                                         target_id, bet, gesture)
        if not ok:
            _emit('error_msg', {'message': '行动无效'})
            return

        action_detail = {
            'type': action_type,
            'target_id': target_id,
            'bet': bet,
            'gesture': gesture,
        }
        # 补充目标玩家名称
        if target_id and target_id in room.players:
            action_detail['target_name'] = room.players[target_id].name

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

        # 检查是否所有存活玩家都已提交
        alive = [p for p in room.players.values() if p.is_alive]
        if len(room.game_state.actions) >= len(alive):
            _process_round(room_id)

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

        room = room_manager.get_room(room_id)
        if not room or not room.game_state:
            _emit('error_msg', {'message': '无法使用技能卡'})
            return

        # 仅在行动阶段允许使用技能卡
        if room.game_state.phase != GamePhase.ACTION:
            _emit('error_msg', {'message': '当前阶段无法使用技能卡'})
            return

        player = room.players.get(player_id)
        if not player or not player.is_alive:
            _emit('error_msg', {'message': '无法使用技能卡'})
            return

        # 检查玩家是否拥有该技能卡
        skill_card = None
        for s in player.skills:
            if s.get('skill_type') == skill_id or s.get('id') == skill_id:
                skill_card = s
                break

        if not skill_card:
            _emit('error_msg', {'message': '没有这张技能卡'})
            return

        # 处理技能卡效果
        skill_type = skill_card.get('type', '')
        effect = skill_card.get('effect', {})
        result_msg = player.name + ' 使用了【' + skill_card.get('name', '技能卡') + '】'

        # 攻击类 - 需要目标
        if skill_type == 'attack' and target_id:
            target = room.players.get(target_id)
            if not target or not target.is_alive:
                _emit('error_msg', {'message': '目标无效'})
                return
            damage = effect.get('damage', 0)
            target.change_cities(-damage)
            result_msg += '，对 ' + target.name + ' 造成 ' + str(damage) + ' 伤害'

            # 破城卡：自身损失
            if effect.get('self_damage'):
                player.change_cities(-effect['self_damage'])
                result_msg += '，自身损失 ' + str(effect['self_damage']) + ' 城池'

            # 奇袭卡：标记无视守城
            if effect.get('ignore_defend'):
                player.status_effects['ignore_defend'] = True
                result_msg += '（无视守城）'

            # 连弩卡：对第二名目标造成伤害
            if effect.get('multi_target'):
                # 寻找另一个存活玩家（非目标、非自己）
                other_targets = [pid for pid, p in room.players.items()
                                 if p.is_alive and not p.is_spectator
                                 and pid != target_id and pid != player_id]
                if other_targets:
                    second_id = random.choice(other_targets)
                    second = room.players[second_id]
                    second_damage = effect.get('damage', 0)
                    second.change_cities(-second_damage)
                    result_msg += '，对 ' + second.name + ' 造成 ' + str(second_damage) + ' 伤害'

            # 毒计卡：标记眩晕
            if effect.get('stun'):
                target.status_effects['stun'] = True
                result_msg += '，' + target.name + ' 下回合无法行动'

        # 防御类 - 自身buff
        elif skill_type == 'defense':
            heal = effect.get('heal', 0)
            if heal:
                player.change_cities(heal)
                result_msg += '，恢复 ' + str(heal) + ' 城池'

            if effect.get('damage_reduction'):
                player.status_effects['damage_reduction'] = effect['damage_reduction']
                result_msg += '，下回合伤害减半'

            if effect.get('reflect'):
                player.status_effects['reflect'] = effect['reflect']
                result_msg += '，下回合被攻击时反弹 ' + str(effect['reflect']) + ' 伤害'

            if effect.get('immune'):
                player.status_effects['immune'] = True
                result_msg += '，下回合免疫攻击'

            if effect.get('untargetable'):
                player.status_effects['untargetable'] = True
                result_msg += '，下回合无法被选中'

        # 资源类 - 即时效果
        elif skill_type == 'resource':
            heal = effect.get('heal', 0)
            if heal:
                player.change_cities(heal)
                result_msg += '，获得 ' + str(heal) + ' 城池'
            percent = effect.get('percent', 0)
            if percent:
                gain = int(player.cities * percent)
                player.change_cities(gain)
                result_msg += '，获得 ' + str(gain) + ' 城池'
            steal = effect.get('steal', 0)
            if steal and steal > 0:
                total = 0
                for pid, p in room.players.items():
                    if pid != player_id and p.is_alive and not p.is_spectator:
                        p.change_cities(-steal)
                        total += steal
                player.change_cities(total)
                result_msg += '，从其他玩家处掠夺 ' + str(total) + ' 城池'

            # 屯田卡：持续回城
            if effect.get('recurring'):
                rounds = effect.get('recurring', 0)
                amount = effect.get('amount', 0)
                player.status_effects['recurring'] = {'rounds': rounds, 'amount': amount}
                result_msg += '，接下来 ' + str(rounds) + ' 回合每回合获得 ' + str(amount) + ' 城池'

            # 募兵卡：强制攻城
            if effect.get('force_attack'):
                player.status_effects['force_attack'] = True
                result_msg += '，下回合必须攻城'

            # 丰收卡：跳过回合
            if effect.get('skip_turn'):
                player.status_effects['skip_turn'] = True
                result_msg += '，下回合跳过行动'

        # 特殊类
        elif skill_type == 'special':
            # 逆转卡 - 需要目标
            if effect.get('swap'):
                if not target_id:
                    _emit('error_msg', {'message': '请选择目标玩家'})
                    return
                target = room.players.get(target_id)
                if not target or not target.is_alive:
                    _emit('error_msg', {'message': '目标无效'})
                    return
                min_c = effect.get('min_cities', 0)
                if player.cities > min_c and target.cities > min_c:
                    player.cities, target.cities = target.cities, player.cities
                    result_msg += '，与 ' + target.name + ' 交换了城池数'
                else:
                    _emit('error_msg', {'message': '双方城池需超过' + str(min_c) + '才能交换'})
                    return

            # 侦查卡 - 需要目标，揭示信息
            elif effect.get('reveal'):
                if not target_id:
                    _emit('error_msg', {'message': '请选择侦查目标'})
                    return
                target = room.players.get(target_id)
                if not target:
                    _emit('error_msg', {'message': '目标无效'})
                    return
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

            # 离间卡 - 需要目标，阻止目标攻击自己
            elif effect.get('prevent_attack'):
                if not target_id:
                    _emit('error_msg', {'message': '请选择离间目标'})
                    return
                target = room.players.get(target_id)
                if not target or not target.is_alive:
                    _emit('error_msg', {'message': '目标无效'})
                    return
                rounds = effect.get('prevent_attack', 1)
                target.status_effects['blocked_attack'] = {'target': player_id, 'rounds': rounds}
                player.status_effects['blocked_attack'] = {'target': target_id, 'rounds': rounds}
                result_msg += '，' + player.name + ' 与 ' + target.name + ' 下回合无法互相攻击'

            # 伪装卡 - 不需要目标
            elif effect.get('disguise'):
                player.status_effects['disguise'] = True
                result_msg += '，下回合行动将显示为随机行动'

            # 急救卡 - 不需要目标
            elif effect.get('emergency_heal'):
                heal_amount = effect['emergency_heal']
                player.change_cities(heal_amount)
                result_msg += '，紧急恢复 ' + str(heal_amount) + ' 城池'
                if not player.is_alive and player.cities >= 0:
                    player.is_alive = True
                    player.is_spectator = False

            else:
                _emit('error_msg', {'message': '无法使用该技能卡'})
                return

        else:
            _emit('error_msg', {'message': '无法使用该技能卡，可能缺少目标'})
            return

        # 移除技能卡
        player.skills.remove(skill_card)

        # 检查是否有人阵亡
        for p in room.players.values():
            if not p.is_alive and not p.is_spectator:
                p.is_spectator = True

        # 移除死亡玩家的已提交行动
        dead_player_ids = [pid for pid, p in room.players.items() if not p.is_alive]
        for dead_id in dead_player_ids:
            room.game_state.actions.pop(dead_id, None)

        # 仅向使用者发送技能卡详情
        _emit('skill_used', {
            'player_id': player_id,
            'player_name': player.name,
            'skill_name': skill_card.get('name', '技能卡'),
            'message': result_msg,
            'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
        }, room=player_id)

        # 向全房间发送玩家状态更新（不含技能卡细节）
        _emit('players_update', {
            'players': {pid: p.to_dict(is_spectator=False, is_self=(pid == player_id)) for pid, p in room.players.items()}
        }, room=room_id)

        # 技能卡可能杀死玩家，重新检查是否所有存活玩家都已提交行动
        alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
        if len(room.game_state.actions) >= len(alive):
            _process_round(room_id)

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
        if not hasattr(gs, 'ready_players'):
            gs.ready_players = set()
        gs.ready_players.add(player_id)

        # 只有存活玩家才算"全部准备好"
        alive = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
        alive_ready = [pid for pid in gs.ready_players if pid in {p.id for p in alive}]
        if len(alive_ready) >= len(alive):
            gs.ready_players = set()

            # 检查拍卖（每回合只触发一次）
            if gs.round >= 6 and (gs.round - 6) % 2 == 0 and not getattr(gs, '_auction_done_this_round', False):
                gs._auction_done_this_round = True
                _start_auction(room_id)
            else:
                _start_next_round(room_id)


# ===== 辅助函数（全部用 socketio.emit） =====

def _build_game_state(room, viewer_id=None):
    gs = room.game_state
    return {
        'round': gs.round if gs else 1,
        'phase': gs.phase.value if gs else 'waiting',
        'players': {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()},
        'skill_cards_drawn': gs.skill_cards_drawn if gs else 0,
    }


def _process_round(room_id):
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    results = room_manager.process_round(room_id)

    # 设置会议阶段
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

    alive = [p for p in room.players.values() if p.is_alive]
    if len(alive) <= 1:
        winner = alive[0] if alive else None
        _emit('round_result', round_result_data, room=room_id)
        _emit('game_ended', {'winner': winner.to_dict() if winner else None}, room=room_id)
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

    # 拍卖由 on_ready_next_round 触发（玩家点击继续后）


def _start_duel(room_id, duel_info):
    """启动约战"""
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    initiator = duel_info['initiator']
    target = duel_info['target']
    bet = duel_info['bet']

    # 第6轮后10发转轮，之前6发；前两枪不能有子弹
    chambers = 10 if room.game_state.round >= 6 else 6
    bullet_pos = random.randint(2, chambers - 1)

    room.game_state.duel = {
        'initiator': initiator,
        'initiator_name': duel_info['initiator_name'],
        'target': target,
        'target_name': duel_info['target_name'],
        'bet': bet,
        'chambers': chambers,
        'bullet_pos': bullet_pos,
        'fired': 0,
        'current_turn': initiator  # 发起者先开枪
    }
    room.game_state.phase = GamePhase.DUEL

    _emit('duel_started', {
        'initiator': initiator,
        'initiator_name': duel_info['initiator_name'],
        'target': target,
        'target_name': duel_info['target_name'],
        'bet': bet,
        'chambers': chambers,
        'bullet_pos': bullet_pos,
        'current_turn': initiator
    }, room=room_id)


def _start_auction(room_id):
    room = room_manager.get_room(room_id)
    if not room or not room.game_state:
        return

    alive = [p for p in room.players.values() if p.is_alive]
    if not alive:
        _start_next_round(room_id)
        return

    skill = random.choice(list(SKILL_CARDS.values())).copy()
    skill['id'] = f"auction_{room.game_state.round}"
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

    alive = [p for p in room.players.values() if p.is_alive]
    if len(alive) <= 1:
        winner = alive[0] if alive else None
        _emit('game_ended', {'winner': winner.to_dict() if winner else None}, room=room_id)
        return

    # 重置每轮标志
    for p in room.players.values():
        p.repair_active = False
        # 清除单回合状态效果
        for key in ['stun', 'skip_turn', 'force_attack', 'ignore_defend',
                     'damage_reduction', 'reflect', 'immune', 'untargetable', 'disguise']:
            p.status_effects.pop(key, None)
        # 离间效果递减
        blocked = p.status_effects.get('blocked_attack')
        if blocked:
            blocked['rounds'] = blocked.get('rounds', 1) - 1
            if blocked['rounds'] <= 0:
                del p.status_effects['blocked_attack']

    room.game_state.next_round()
    room.game_state._auction_done_this_round = False
    _emit('next_round', _build_game_state(room), room=room_id)


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

        # 检查是否有人因约战死亡
        alive = [p for p in room.players.values() if p.is_alive]
        if len(alive) <= 1:
            winner_p = alive[0] if alive else None
            room.game_state.phase = GamePhase.FINISHED
            _emit('game_ended', {'winner': winner_p.to_dict() if winner_p else None}, room=room_id)
            return

        # 如果还有待处理的约战，继续下一场
        if hasattr(room.game_state, '_pending_duels') and room.game_state._pending_duels:
            next_duel = room.game_state._pending_duels.pop(0)
            _start_duel(room_id, next_duel)
        else:
            # 所有约战结束，发送回合小结并回到会议阶段
            if hasattr(room.game_state, '_pending_round_result') and room.game_state._pending_round_result:
                pending = room.game_state._pending_round_result
                pending['players'] = {pid: p.to_dict(is_spectator=True, is_self=True) for pid, p in room.players.items()}
                _emit('round_result', pending, room=room_id)
                room.game_state._pending_round_result = None
            room.game_state.phase = GamePhase.MEETING
            if hasattr(room.game_state, 'ready_players'):
                room.game_state.ready_players = set()
    else:
        duel['current_turn'] = duel['target'] if player_id == duel['initiator'] else duel['initiator']
        _emit('duel_next_turn', {
            'current_turn': duel['current_turn'],
            'current_turn_name': room.players[duel['current_turn']].name if duel['current_turn'] in room.players else '',
            'fired': fired,
            'remaining': chambers - fired
        }, room=room_id)
