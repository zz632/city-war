"""
游戏房间管理器
"""
import uuid
import time
import random
from typing import Dict, List, Optional
from .models import Room, Player, GameState, GamePhase, ActionType
from .skills import get_random_skill


def get_multiplier(round_num):
    """获取回合倍率"""
    if round_num >= 24:
        return 8
    elif round_num >= 16:
        return 4
    elif round_num >= 8:
        return 2
    else:
        return 1


class RoomManager:
    """房间管理器"""
    
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.players: Dict[str, Player] = {}
    
    def create_room(self, player_name: str, player_sid: str, client_ip: str = '',
                     password: str = '', max_players: int = 8) -> tuple:
        """创建新房间"""
        # 生成4位纯数字房间号，方便分享
        room_id = str(random.randint(1000, 9999))
        while room_id in self.rooms:
            room_id = str(random.randint(1000, 9999))
        
        player = Player(
            id=player_sid,
            name=player_name,
            room_id=room_id,
            is_host=True
        )
        
        room = Room(
            id=room_id,
            name=f"房间-{room_id}",
            host_id=player_sid,
            players={player_sid: player},
            max_players=max(2, min(8, max_players)),
            password=password
        )
        
        self.rooms[room_id] = room
        self.players[player_sid] = player
        
        return room_id, player
    
    def join_room(self, room_id: str, player_name: str, player_sid: str,
                  client_ip: str = '', password: str = '') -> Optional[Player]:
        """加入房间，返回Player或None。密码错误返回None（调用方应区分原因）"""
        room_id = str(room_id).strip()
        if room_id not in self.rooms:
            return None

        room = self.rooms[room_id]

        # 检查密码
        if room.password and password != room.password:
            return None

        if len(room.players) >= room.max_players:
            return None

        # 判断是否需要成为观战者
        is_spectator = False
        if room.game_state and room.game_state.phase != GamePhase.WAITING:
            if not room.allow_join_after_start:
                # 游戏已开始且不允许中途加入，成为观战者
                is_spectator = True
            # 允许中途加入时，以正常玩家身份加入

        player = Player(
            id=player_sid,
            name=player_name,
            room_id=room_id,
            is_spectator=is_spectator,
            is_alive=not is_spectator,
            cities=0 if is_spectator else 250
        )

        room.players[player_sid] = player
        self.players[player_sid] = player

        return player
    
    def leave_room(self, player_sid: str) -> Optional[str]:
        """离开房间"""
        if player_sid not in self.players:
            return None
        
        player = self.players[player_sid]
        room_id = player.room_id
        
        if room_id not in self.rooms:
            return None
        
        room = self.rooms[room_id]
        
        # 移除玩家
        if player_sid in room.players:
            del room.players[player_sid]
        
        if player_sid in self.players:
            del self.players[player_sid]
        
        # 如果房间空了，删除房间
        if not room.players:
            del self.rooms[room_id]
            return room_id
        
        # 如果房主离开，转移房主
        if room.host_id == player_sid:
            new_host = list(room.players.values())[0]
            room.host_id = new_host.id
            new_host.is_host = True
        
        return room_id
    
    def start_game(self, room_id: str, player_sid: str) -> bool:
        """开始游戏"""
        if room_id not in self.rooms:
            return False

        room = self.rooms[room_id]

        if room.host_id != player_sid:
            return False

        # 只计算非观战者玩家数
        non_spectator_count = sum(1 for p in room.players.values() if not p.is_spectator)
        if non_spectator_count < 2:
            return False

        if room.game_state and room.game_state.phase != GamePhase.WAITING:
            # 游戏可能未正确结束（如浏览器关闭），重置为等待状态
            room.game_state = None

        # 初始化游戏状态
        room.game_state = GameState(
            round=1,
            phase=GamePhase.ACTION
        )

        # 初始化玩家城池数（观战者保持观战状态）
        for player in room.players.values():
            if player.is_spectator:
                continue
            player.cities = 250
            player.is_alive = True
            player.skills = []
            player.alliance_with = None
            player.alliance_benefits = 0
            player.alliance_damages = 0
            player.repair_active = False
            player.action_history = []
            # 保留AI配置，只清除游戏状态效果
            ai_cfg = player.status_effects.get('ai_config')
            player.status_effects = {}
            if ai_cfg:
                player.status_effects['ai_config'] = ai_cfg
        
        return True
    
    def submit_action(self, room_id: str, player_sid: str, action_type: str,
                     target_id: str = None, bet: int = 0) -> bool:
        """提交行动"""
        if room_id not in self.rooms:
            return False
        
        room = self.rooms[room_id]
        game_state = room.game_state
        
        if not game_state or game_state.phase != GamePhase.ACTION:
            return False
        
        player = room.players.get(player_sid)
        if not player or not player.is_alive or player.is_spectator:
            return False

        # 检查状态效果
        # 眩晕/跳过回合：自动替换为跳过行动（优先于强制攻城）
        if player.status_effects.get('stun') or player.status_effects.get('skip_turn'):
            action_type = 'skip'

        # 强制攻城：只能选择攻城（skip 不受此限制）
        if player.status_effects.get('force_attack') and action_type not in ('attack', 'skip'):
            return False
        
        # 检查同种操作连续不超过5次
        if action_type != 'skip':
            if len(player.action_history) >= 5 and all(a == action_type for a in player.action_history[-5:]):
                return False

        # 验证行动类型
        valid_actions = ['skip', 'attack', 'defend', 'jungle', 'duel']
        if game_state.round >= 3:
            valid_actions.extend(['repair', 'alliance', 'dissolve_alliance'])

        if action_type not in valid_actions:
            return False

        # 验证目标
        if action_type in ['attack', 'duel', 'alliance']:
            if not target_id or target_id not in room.players:
                return False
            target = room.players[target_id]
            if not target.is_alive:
                return False
            # 不可被选为目标
            if target.status_effects.get('untargetable'):
                return False
            if action_type == 'alliance' and target_id == player_sid:
                return False
            # 逆转卡效果：交换后N轮内不能攻击对方
            if action_type in ['attack', 'duel']:
                reverse_no = player.status_effects.get('reverse_no_attack')
                if reverse_no and reverse_no.get('target') == target_id:
                    return False
            # 联盟内成员间攻击无效
            if action_type == 'attack' and player.alliance_with == target_id:
                return False

        # 结盟校验：双方均未结盟；场上仅剩2人时禁止结盟（避免游戏无法分出胜负）
        if action_type == 'alliance':
            # 离间卡效果：不能联盟
            if player.status_effects.get('no_alliance'):
                return False
            alive_count = sum(1 for p in room.players.values() if p.is_alive and not p.is_spectator)
            if alive_count <= 2:
                return False
            if player.alliance_with:
                return False
            if target_id and room.players.get(target_id) and room.players[target_id].alliance_with:
                return False

        # 解盟校验：只有已结盟玩家才能解盟
        if action_type == 'dissolve_alliance':
            if not player.alliance_with:
                return False
        
        # 验证赌注
        multiplier = get_multiplier(game_state.round)
        if action_type == 'duel' and bet > 0:
            target = room.players.get(target_id)
            if target:
                max_bet = int(min(player.cities, target.cities) * 0.6)
                if bet > max_bet:
                    return False
                if bet < 15 * multiplier:
                    return False
        
        # 记录行动历史（跳过也记录，用于打断同种操作的连续计数）
        player.action_history = (player.action_history + [action_type])[-10:]

        # 创建行动
        action = {
            'player_id': player_sid,
            'action_type': action_type,
            'target_id': target_id,
            'bet': bet,
            'timestamp': time.time()
        }
        
        game_state.actions[player_sid] = action
        return True
    
    def process_round(self, room_id: str) -> dict:
        """处理回合"""
        if room_id not in self.rooms:
            return {}
        
        room = self.rooms[room_id]
        game_state = room.game_state
        
        if not game_state:
            return {}
        
        multiplier = get_multiplier(game_state.round)
        
        results = {
            'round': game_state.round,
            'actions': {},
            'city_changes': {},
            'messages': [],
            'skill_cards': [],
            'duels': [],
            'alliances': []
        }
        
        # 初始化城池变化
        for pid in room.players:
            results['city_changes'][pid] = 0

        # 处理持续效果（屯田卡等）—— 先死技能卡不生效
        for pid, player in room.players.items():
            if not player.is_alive:
                continue
            recurring = player.status_effects.get('recurring')
            if recurring and recurring.get('rounds', 0) > 0:
                amount = recurring['amount']
                player.change_cities(amount)
                results['city_changes'][pid] += amount
                recurring['rounds'] -= 1
                if recurring['rounds'] <= 0:
                    del player.status_effects['recurring']

            # 回血卡 - 每轮固定回血
            recurring_heal = player.status_effects.get('recurring_heal')
            if recurring_heal:
                player.change_cities(recurring_heal)
                results['city_changes'][pid] += recurring_heal

            # 撒豆成兵卡 - 延迟回血
            delay_troops = player.status_effects.get('delay_troops')
            if delay_troops:
                delay_troops['rounds_left'] -= 1
                if delay_troops['rounds_left'] <= 0:
                    heal = delay_troops['heal']
                    player.change_cities(heal)
                    results['city_changes'][pid] += heal
                    results['messages'].append(player.name + f' 撒豆成兵生效，恢复{heal}城池')
                    del player.status_effects['delay_troops']

            # 不死图腾后续效果：每轮回血+减伤倒计时
            totem = player.status_effects.get('immortal_totem')
            if totem and totem.get('post_save_rounds', 0) > 0:
                # 触发后才生效（post_save_rounds初始值等于设定值，说明未触发过）
                if totem.get('triggered'):
                    post_heal = totem.get('post_save_heal', 0)
                    if post_heal:
                        player.change_cities(post_heal)
                        results['city_changes'][pid] += post_heal
                    totem['post_save_rounds'] -= 1
                    if totem['post_save_rounds'] <= 0:
                        del player.status_effects['immortal_totem']
        
        # 处理打野——50%概率获10*multiplier城池，50%获技能卡
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'jungle':
                player = room.players[pid]
                if not player.is_alive:
                    continue
                if random.random() < 0.5:
                    # 50%获得城池
                    gain = 10 * multiplier
                    player.change_cities(gain)
                    results['city_changes'][pid] = results['city_changes'].get(pid, 0) + gain
                    results['actions'][pid] = {'type': 'jungle', 'result': 'cities', 'gain': gain}
                    results['messages'].append(player.name + f' 打野获得{gain}城池')
                else:
                    # 50%获得技能卡
                    skill = get_random_skill()
                    player.add_skill(skill)
                    game_state.skill_cards_drawn += 1
                    results['skill_cards'].append({'player_id': pid, 'card': skill, 'result': 'skill_card'})
                    results['actions'][pid] = {'type': 'jungle', 'result': 'skill_card'}
                    results['messages'].append(player.name + ' 打野获得技能卡：' + skill.get('name', ''))
        
        # 处理攻城
        attack_pairs = []
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'attack':
                attacker = room.players[pid]
                target = room.players.get(action.get('target_id'))
                if target and target.is_alive:
                    # 联盟内成员间攻击无效
                    if attacker.alliance_with and attacker.alliance_with == action.get('target_id'):
                        continue
                    # 检查是否互相攻城
                    target_action = game_state.actions.get(action.get('target_id'))
                    if target_action and target_action['action_type'] == 'attack' and target_action.get('target_id') == pid:
                        attack_pairs.append((pid, action.get('target_id')))
        
        # 记录被攻击的玩家（修城时被攻击则修城不生效）
        attacked_players = set()
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'attack':
                target_id = action.get('target_id')
                if target_id:
                    # 联盟内成员间攻击无效
                    attacker = room.players[pid]
                    if attacker.alliance_with and attacker.alliance_with == target_id:
                        continue
                    attacked_players.add(target_id)

        # 处理攻城伤害
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'attack':
                attacker = room.players[pid]
                target = room.players.get(action.get('target_id'))
                if not target or not target.is_alive:
                    continue
                # 联盟内成员间攻击无效
                if attacker.alliance_with and attacker.alliance_with == action.get('target_id'):
                    results['actions'][pid] = {'type': 'attack', 'target': action.get('target_id'), 'damage': 0, 'alliance_blocked': True}
                    results['messages'].append(attacker.name + ' 与 ' + target.name + ' 是联盟，无法攻击')
                    continue

                # 检查是否互相攻城
                is_mutual = any(
                    (pid == p1 and action.get('target_id') == p2) or
                    (pid == p2 and action.get('target_id') == p1)
                    for p1, p2 in attack_pairs
                )

                # 计算伤害：固定25 * multiplier
                damage = 25 * multiplier

                # 攻击者伤害加成（永久buff）
                if attacker.status_effects.get('permanent_damage_bonus'):
                    damage += attacker.status_effects['permanent_damage_bonus']
                # 猛攻卡：下一次攻城伤害×N（单次生效）
                next_atk_mult = attacker.status_effects.get('next_attack_multiplier')
                if next_atk_mult:
                    damage = int(damage * next_atk_mult)
                if attacker.status_effects.get('permanent_attack_bonus'):
                    damage = int(damage * (1 + attacker.status_effects['permanent_attack_bonus']))

                # 修城方受到的伤害翻倍
                if target.repair_active:
                    damage = damage * 2

                # 目标伤害减免（百分比）
                if target.status_effects.get('damage_reduction'):
                    damage = int(damage * (1 - target.status_effects['damage_reduction']))

                # 目标永久减伤（百分比）
                if target.status_effects.get('permanent_reduction'):
                    damage = int(damage * (1 - target.status_effects['permanent_reduction']))

                # 目标定值减伤（磐石堡垒卡）
                if target.status_effects.get('flat_damage_reduction'):
                    damage = max(0, damage - target.status_effects['flat_damage_reduction'])

                # 不死图腾减伤（触发后3轮内）
                totem = target.status_effects.get('immortal_totem')
                if totem and totem.get('triggered') and totem.get('post_save_reduction'):
                    damage = int(damage * (1 - totem['post_save_reduction']))

                # 双方互攻：伤害-100（最低为0），在所有加成计算之后统一扣除，
                # 保证双方同时进攻时判定对称
                if is_mutual:
                    damage = max(0, damage - 100)

                # 目标免疫
                if target.status_effects.get('immune'):
                    damage = 0

                # 检查目标是否守城
                target_action = game_state.actions.get(action.get('target_id'))
                if target_action and target_action['action_type'] == 'defend':
                    # 奇袭卡无视守城
                    if attacker.status_effects.get('ignore_defend'):
                        target.change_cities(-damage)
                        attacker.change_cities(damage)
                        results['city_changes'][action.get('target_id')] -= damage
                        results['city_changes'][pid] += damage
                        results['actions'][pid] = {
                            'type': 'attack',
                            'target': action.get('target_id'),
                            'damage': damage,
                            'ignore_defend': True
                        }
                    else:
                        # 守城反弹：攻击方 -20*multiplier，守城方 +20*multiplier
                        counter_damage = 20 * multiplier
                        attacker.change_cities(-counter_damage)
                        target.change_cities(counter_damage)
                        results['city_changes'][pid] -= counter_damage
                        results['city_changes'][action.get('target_id')] += counter_damage
                else:
                    # 攻城成功，对方损失的城池转移到攻击方
                    actual_damage = damage
                    # 空城卡/诈降卡反弹
                    if target.status_effects.get('reflect'):
                        reflect_dmg = target.status_effects['reflect']
                        attacker.change_cities(-reflect_dmg)
                        target.change_cities(reflect_dmg)
                        results['city_changes'][pid] -= reflect_dmg
                        results['city_changes'][action.get('target_id')] += reflect_dmg
                        # 免疫则不受伤
                        if target.status_effects.get('immune'):
                            actual_damage = 0

                    target.change_cities(-actual_damage)
                    attacker.change_cities(actual_damage)
                    results['city_changes'][action.get('target_id')] -= actual_damage
                    results['city_changes'][pid] += actual_damage
                
                results['actions'][pid] = {
                    'type': 'attack',
                    'target': action.get('target_id'),
                    'damage': damage if not (target_action and target_action['action_type'] == 'defend') else 0
                }

                # 猛攻卡单次加成已生效，消耗之
                if next_atk_mult:
                    attacker.status_effects.pop('next_attack_multiplier', None)

                # 吸血卡：攻击造成伤害后吸取百分比总血量
                if attacker.status_effects.get('lifesteal_percent') and damage > 0:
                    lifesteal = int(damage * attacker.status_effects['lifesteal_percent'])
                    if lifesteal > 0:
                        attacker.change_cities(lifesteal)
                        results['city_changes'][pid] += lifesteal
        
        # 处理守城——无被动加成，仅在被攻击时反弹
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'defend':
                results['actions'][pid] = {'type': 'defend'}

        # 处理跳过行动（眩晕/丰收卡等）
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'skip':
                player = room.players[pid]
                reason = '被眩晕' if player.status_effects.get('stun') else '跳过回合'
                results['actions'][pid] = {'type': 'skip', 'reason': reason}
                results['messages'].append(player.name + ' ' + reason + '，无法行动')

        # 处理修城——增加30*multiplier城池，本轮受伤翻倍；但被攻击时修城不生效
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'repair':
                player = room.players[pid]
                if not player.is_alive:
                    continue
                repair_gain = 30 * multiplier
                if pid in attacked_players:
                    player.repair_active = True
                    results['actions'][pid] = {'type': 'repair_failed'}
                    results['messages'].append(player.name + ' 修城失败（被攻击），本轮受到的伤害翻倍')
                else:
                    player.change_cities(repair_gain)
                    player.repair_active = True
                    results['actions'][pid] = {'type': 'repair'}
                    results.setdefault('city_changes', {})
                    results['city_changes'][pid] = results['city_changes'].get(pid, 0) + repair_gain
                    results['messages'].append(player.name + f' 修城，获得{repair_gain}城池，本轮受到的伤害翻倍')

        # 处理约战
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'duel':
                initiator = room.players[pid]
                target = room.players.get(action.get('target_id'))
                if target and target.is_alive:
                    bet = action.get('bet', 0)
                    min_bet = 15 * multiplier
                    if bet <= 0:
                        bet = max(min_bet, min(initiator.cities, target.cities))
                    bet = min(bet, min(initiator.cities, target.cities))
                    if bet < min_bet:
                        bet = min_bet
                    results['duels'].append({
                        'initiator': pid,
                        'initiator_name': initiator.name,
                        'target': action.get('target_id'),
                        'target_name': target.name,
                        'bet': bet
                    })
                    results['actions'][pid] = {
                        'type': 'duel',
                        'target': action.get('target_id'),
                        'bet': bet
                    }

        # 处理结盟
        alliance_requests = {}
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'alliance':
                target_id = action.get('target_id')
                if target_id:
                    alliance_requests[pid] = target_id

        # 检查双向结盟
        formed_alliances = set()
        for pid, target_id in alliance_requests.items():
            if target_id in alliance_requests and alliance_requests[target_id] == pid:
                pair = tuple(sorted([pid, target_id]))
                if pair not in formed_alliances:
                    formed_alliances.add(pair)
                    p1 = room.players[pair[0]]
                    p2 = room.players[pair[1]]
                    p1.alliance_with = pair[1]
                    p2.alliance_with = pair[0]
                    results['alliances'].append({
                        'players': [pair[0], pair[1]],
                        'player_names': [p1.name, p2.name]
                    })
                    results['actions'][pair[0]] = {'type': 'alliance', 'partner': pair[1]}
                    results['actions'][pair[1]] = {'type': 'alliance', 'partner': pair[0]}

        # 联盟期间奖励/伤害共享均分
        # 收集所有联盟对
        alliance_pairs_processed = set()
        for pid, player in room.players.items():
            if player.alliance_with and player.is_alive:
                pair = tuple(sorted([pid, player.alliance_with]))
                if pair not in alliance_pairs_processed:
                    alliance_pairs_processed.add(pair)
                    p1 = room.players.get(pair[0])
                    p2 = room.players.get(pair[1])
                    if p1 and p2 and p1.is_alive and p2.is_alive:
                        change1 = results['city_changes'].get(pair[0], 0)
                        change2 = results['city_changes'].get(pair[1], 0)
                        total_change = change1 + change2
                        # 均分（去尾法）
                        share = int(total_change / 2)
                        # 调整：让两人都变为share
                        diff1 = share - change1
                        diff2 = share - change2
                        p1.change_cities(diff1)
                        p2.change_cities(diff2)
                        results['city_changes'][pair[0]] = share
                        results['city_changes'][pair[1]] = share

        # 处理解盟
        for pid, action in game_state.actions.items():
            if action['action_type'] == 'dissolve_alliance':
                player = room.players[pid]
                partner_id = player.alliance_with
                if partner_id and partner_id in room.players:
                    partner = room.players[partner_id]
                    player.alliance_with = None
                    partner.alliance_with = None
                    results['messages'].append(player.name + ' 与 ' + partner.name + ' 解除了同盟')
                    results['actions'][pid] = {'type': 'dissolve_alliance', 'partner': partner_id}
                    results['actions'][partner_id] = {'type': 'dissolve_alliance', 'partner': pid}

        # 收益倍率处理（聚宝盆卡/以逸待劳卡）：对正收益额外加成
        for pid, player in room.players.items():
            if not player.is_alive:
                continue
            change = results['city_changes'].get(pid, 0)
            if change > 0:
                bonus_mult = 1
                if player.status_effects.get('income_multiplier'):
                    bonus_mult *= player.status_effects['income_multiplier']
                if player.status_effects.get('double_gain'):
                    bonus_mult *= 2
                if bonus_mult != 1:
                    bonus = int(change * (bonus_mult - 1))
                    player.change_cities(bonus)
                    results['city_changes'][pid] += bonus

        # 检查死亡玩家（持有不死图腾卡的玩家暂不死亡，由事件层发起濒死抉择）
        for pid, player in room.players.items():
            if player.is_alive and not player.is_spectator and player.cities < 0:
                has_totem = any(isinstance(s, dict) and s.get('skill_type') == 'immortal_totem'
                                for s in player.skills)
                if has_totem:
                    results['messages'].append(f"{player.name} 濒死，正在决定是否使用不死图腾...")
                else:
                    player.is_alive = False
                    player.is_spectator = True
                    results['messages'].append(f"{player.name} 城池耗尽，已阵亡")

        # 检查游戏结束
        alive_players = [p for p in room.players.values() if p.is_alive and not p.is_spectator]
        if len(alive_players) <= 1:
            game_state.phase = GamePhase.FINISHED
            if alive_players:
                results['messages'].append(f"🎉 游戏结束！{alive_players[0].name} 获得胜利！")
            else:
                results['messages'].append("🎉 游戏结束！平局！")
        
        # 如果没有任何变化，提示无事发生
        has_changes = any(v != 0 for v in results['city_changes'].values())
        has_activity = (results['skill_cards'] or results['messages']
                        or results['duels'] or results['alliances']
                        or results['actions'])
        if not has_changes and not has_activity:
            results['messages'].append("无事发生")
        
        # 清空行动
        game_state.actions = {}
        
        return results
    
    def get_room(self, room_id: str) -> Optional[Room]:
        """获取房间"""
        return self.rooms.get(room_id.upper())
    
    def get_player(self, player_sid: str) -> Optional[Player]:
        """获取玩家"""
        return self.players.get(player_sid)
    
    def room_to_dict(self, room_id: str, player_id: str = None) -> dict:
        """将房间转换为字典"""
        room = self.rooms.get(room_id.upper() if not room_id.isdigit() else room_id)
        if not room:
            return {}
        
        return room.to_dict(player_id)

    def get_public_rooms(self) -> list:
        """获取公开房间列表"""
        return [{'id': r.id, 'name': r.name, 'player_count': len(r.players)} 
                for r in self.rooms.values()]


# 全局房间管理器实例
room_manager = RoomManager()
