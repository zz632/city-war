"""
游戏核心逻辑模块
处理回合结算、战斗计算、胜负判定等
"""

import random
from typing import Dict, List, Optional, Tuple
from .models import Player, Room, GameState, Action, SkillCard
from .skills import get_random_skill


class GameLogic:
    """游戏逻辑核心类"""
    
    def __init__(self, room: Room):
        self.room = room
        self.drawn_count = 0
    
    def start_game(self) -> bool:
        """开始游戏"""
        if len(self.room.players) < 2:
            return False
        
        self.room.game_started = True
        self.room.game_state.current_round = 1
        self.room.game_state.phase = 'action'
        
        # 初始化玩家状态
        for player in self.room.players.values():
            player.cities = 100
            player.is_alive = True
            player.skills = []
            player.action = None
            player.pending_alliance = None
            player.alliance_partner = None
            player.alliance_benefits = 0
            player.alliance_damages = 0
            player.has_repaired = False
        
        return True
    
    def submit_action(self, player_id: str, action_type: str, 
                     target_id: str = None, bet: int = None,
                     gesture: str = None) -> Tuple[bool, str]:
        """提交玩家行动"""
        if player_id not in self.room.players:
            return False, "玩家不存在"
        
        player = self.room.players[player_id]
        
        if not player.is_alive:
            return False, "玩家已死亡"
        
        if player.action is not None:
            return False, "本回合已提交行动"
        
        # 验证行动类型
        valid_actions = ['attack', 'defend', 'hunt', 'duel']
        if self.room.game_state.current_round >= 6:
            valid_actions.extend(['repair', 'alliance'])
        
        if action_type not in valid_actions:
            return False, "无效的行动类型"
        
        # 验证目标
        if action_type in ['attack', 'duel', 'alliance']:
            if not target_id or target_id not in self.room.players:
                return False, "无效的目标玩家"
            target = self.room.players[target_id]
            if not target.is_alive:
                return False, "目标玩家已死亡"
            if action_type == 'alliance' and target_id == player_id:
                return False, "不能与自己结盟"
        
        # 验证赌注
        if action_type == 'duel':
            if not bet or bet <= 0:
                return False, "赌注必须大于0"
            target = self.room.players[target_id]
            max_bet = int(min(player.cities, target.cities) * 0.6)
            if bet > max_bet:
                return False, f"赌注不能超过{max_bet}"
        
        # 创建行动
        action = Action(
            player_id=player_id,
            action_type=action_type,
            target_id=target_id,
            bet=bet,
            gesture=gesture
        )
        
        player.action = action
        
        # 处理打野的猜拳
        if action_type == 'hunt':
            result = self._process_hunt(player, gesture)
            return True, result
        
        # 检查是否所有玩家都已提交行动
        if self._all_players_acted():
            self._process_round()
        
        return True, "行动提交成功"
    
    def _all_players_acted(self) -> bool:
        """检查是否所有存活玩家都已提交行动"""
        alive_players = [p for p in self.room.players.values() if p.is_alive]
        return all(p.action is not None for p in alive_players)
    
    def _process_hunt(self, player: Player, gesture: str) -> str:
        """处理打野猜拳"""
        if not gesture:
            return "请选择手势"
        
        gestures = ['rock', 'paper', 'scissors']
        if gesture not in gestures:
            return "无效的手势"
        
        # 系统随机出拳
        system_gesture = random.choice(gestures)
        
        # 判断胜负
        result = self._judge_gesture(gesture, system_gesture)
        
        round_num = self.room.game_state.current_round
        
        if result == 'win':
            # 获胜：抽取技能卡
            skill = get_random_skill()
            if skill:
                player.skills.append(skill)
                self.drawn_count += 1
                return f"猜拳胜利！你出了{self._gesture_name(gesture)}，系统出了{self._gesture_name(system_gesture)}。获得技能卡：{skill['name']}"
            else:
                return f"猜拳胜利！但技能卡已抽完"
        else:
            # 失败：获得城池
            reward = 20 if round_num >= 6 else 10
            player.cities += reward
            return f"猜拳失败！你出了{self._gesture_name(gesture)}，系统出了{self._gesture_name(system_gesture)}。获得{reward}城池"
    
    def _judge_gesture(self, player: str, system: str) -> str:
        """判断猜拳胜负"""
        if player == system:
            return 'win'  # 平局算玩家赢
        
        wins = {
            'rock': 'scissors',
            'scissors': 'paper',
            'paper': 'rock'
        }
        
        if wins[player] == system:
            return 'win'
        return 'lose'
    
    def _gesture_name(self, gesture: str) -> str:
        """手势中文名"""
        names = {'rock': '石头', 'paper': '布', 'scissors': '剪刀'}
        return names.get(gesture, gesture)
    
    def _process_round(self):
        """处理回合结算"""
        self.room.game_state.phase = 'meeting'
        round_num = self.room.game_state.current_round
        
        # 收集所有行动
        actions = []
        for player in self.room.players.values():
            if player.is_alive and player.action:
                actions.append(player.action)
        
        # 处理结盟请求
        self._process_alliances(actions)
        
        # 处理修城
        self._process_repairs(actions)
        
        # 处理攻城（包括守城反击）
        self._process_attacks(actions)
        
        # 处理约战
        self._process_duels(actions)
        
        # 应用技能卡效果
        self._apply_skill_effects()
        
        # 检查死亡
        self._check_deaths()
        
        # 更新技能卡持续时间
        self._update_skill_durations()
        
        # 生成会议报告
        self._generate_meeting_report(actions)
        
        # 检查是否需要拍卖
        if round_num >= 6 and round_num % 2 == 0:
            self._start_auction()
        else:
            # 进入下一回合
            self._next_round()
    
    def _process_alliances(self, actions: List[Action]):
        """处理结盟请求"""
        for action in actions:
            if action.action_type == 'alliance':
                initiator = self.room.players[action.player_id]
                target = self.room.players[action.target_id]
                
                # 标记待确认的结盟请求
                target.pending_alliance = action.player_id
                initiator.pending_alliance = action.target_id
    
    def confirm_alliance(self, player_id: str, accept: bool) -> Tuple[bool, str]:
        """确认或拒绝结盟"""
        player = self.room.players.get(player_id)
        if not player or not player.pending_alliance:
            return False, "没有待处理的结盟请求"
        
        partner_id = player.pending_alliance
        partner = self.room.players.get(partner_id)
        
        if accept:
            # 建立结盟
            player.alliance_partner = partner_id
            partner.alliance_partner = player_id
            player.pending_alliance = None
            partner.pending_alliance = None
            return True, f"与 {partner.name} 结盟成功"
        else:
            # 拒绝结盟
            player.pending_alliance = None
            partner.pending_alliance = None
            return True, f"拒绝了 {partner.name} 的结盟请求"
    
    def dissolve_alliance(self, player_id: str) -> Tuple[bool, str]:
        """解散结盟（通过猜拳）"""
        player = self.room.players.get(player_id)
        if not player or not player.alliance_partner:
            return False, "当前没有结盟"
        
        partner_id = player.alliance_partner
        partner = self.room.players.get(partner_id)
        
        # 进行猜拳
        gestures = ['rock', 'paper', 'scissors']
        player_gesture = random.choice(gestures)
        partner_gesture = random.choice(gestures)
        
        result = self._judge_gesture(player_gesture, partner_gesture)
        
        if result == 'win':
            # 发起方胜利，获得所有奖励，对方承担所有伤害
            player.cities += player.alliance_benefits + partner.alliance_benefits
            partner.cities -= player.alliance_damages + partner.alliance_damages
            msg = f"解盟猜拳胜利！获得结盟期间所有奖励共 {player.alliance_benefits + partner.alliance_benefits} 城池"
        else:
            # 发起方失败，解盟失败
            msg = f"解盟猜拳失败，结盟关系继续"
            return False, msg
        
        # 清除结盟状态
        player.alliance_partner = None
        partner.alliance_partner = None
        player.alliance_benefits = 0
        partner.alliance_benefits = 0
        player.alliance_damages = 0
        partner.alliance_damages = 0
        
        return True, msg
    
    def _process_repairs(self, actions: List[Action]):
        """处理修城"""
        for action in actions:
            if action.action_type == 'repair':
                player = self.room.players[action.player_id]
                player.cities += 60
                player.has_repaired = True
                action.result = {'type': 'repair', 'cities_gained': 60}
    
    def _process_attacks(self, actions: List[Action]):
        """处理攻城和守城"""
        round_num = self.room.game_state.current_round
        base_damage = 40 if round_num >= 6 else 20
        base_counter = 20 if round_num >= 6 else 10
        
        # 收集所有攻城行动
        attacks = {}
        for action in actions:
            if action.action_type == 'attack':
                attacker_id = action.player_id
                target_id = action.target_id
                
                if target_id not in attacks:
                    attacks[target_id] = []
                attacks[target_id].append(attacker_id)
                
                # 检查是否互相攻城
                if target_id in self.room.players:
                    target = self.room.players[target_id]
                    if target.action and target.action.action_type == 'attack':
                        if target.action.target_id == attacker_id:
                            # 互相攻城，伤害减少
                            action.mutual_attack = True
        
        # 计算伤害
        for action in actions:
            if action.action_type == 'attack':
                attacker = self.room.players[action.player_id]
                target = self.room.players[action.target_id]
                
                # 基础伤害
                damage = base_damage
                
                # 互相攻城减伤
                if getattr(action, 'mutual_attack', False):
                    damage = max(0, damage - 100)
                
                # 修城状态伤害翻倍
                if target.has_repaired:
                    damage *= 2
                
                # 检查目标是否守城
                if target.action and target.action.action_type == 'defend':
                    # 守城成功，攻击方受到伤害
                    counter_damage = base_counter
                    if attacker.has_repaired:
                        counter_damage *= 2
                    
                    attacker.cities -= counter_damage
                    action.result = {
                        'type': 'attack_defended',
                        'damage_dealt': 0,
                        'counter_damage': counter_damage
                    }
                else:
                    # 攻城成功
                    target.cities -= damage
                    action.result = {
                        'type': 'attack_success',
                        'damage_dealt': damage
                    }
                
                # 处理结盟分摊
                self._apply_alliance_sharing(attacker, target, 'attack', damage)
    
    def _apply_alliance_sharing(self, player1: Player, player2: Player, 
                                event_type: str, amount: int):
        """应用结盟分摊"""
        # 伤害分摊
        if event_type == 'attack':
            for player in [player1, player2]:
                if player.alliance_partner:
                    partner = self.room.players.get(player.alliance_partner)
                    if partner and partner.is_alive:
                        # 记录结盟期间的伤害和奖励
                        player.alliance_damages += amount // 2
    
    def _process_duels(self, actions: List[Action]):
        """处理约战（俄罗斯轮盘赌）"""
        round_num = self.room.game_state.current_round
        chamber_size = 10 if round_num >= 6 else 6
        
        for action in actions:
            if action.action_type == 'duel':
                initiator = self.room.players[action.player_id]
                target = self.room.players[action.target_id]
                bet = action.bet
                
                # 初始化轮盘
                chamber = [False] * chamber_size
                bullet_pos = random.randint(0, chamber_size - 1)
                chamber[bullet_pos] = True
                
                current_pos = 0
                current_player = initiator
                other_player = target
                
                result = None
                while result is None and current_pos < chamber_size:
                    # 决定开几枪（简化：随机1-3枪，但不超过剩余子弹数）
                    remaining = chamber_size - current_pos
                    shots = min(random.randint(1, 3), remaining)
                    
                    # 开枪
                    for _ in range(shots):
                        if chamber[current_pos]:
                            # 中弹
                            result = {
                                'loser': current_player.id,
                                'winner': other_player.id,
                                'shots_taken': shots,
                                'bullet_position': current_pos
                            }
                            break
                        current_pos += 1
                    
                    if result is None:
                        # 切换玩家
                        current_player, other_player = other_player, current_player
                
                # 处理结果
                if result:
                    winner = self.room.players[result['winner']]
                    loser = self.room.players[result['loser']]
                    
                    winner.cities += bet
                    loser.cities -= bet
                    
                    action.result = {
                        'type': 'duel_result',
                        'winner': winner.id,
                        'loser': loser.id,
                        'bet': bet,
                        'bullet_pos': result['bullet_position']
                    }
                else:
                    # 无人中弹（理论上不会发生）
                    action.result = {'type': 'duel_draw'}
    
    def _check_deaths(self):
        """检查死亡玩家"""
        for player in self.room.players.values():
            if player.is_alive and player.cities < 0:
                player.is_alive = False
                # 解除结盟
                if player.alliance_partner:
                    partner = self.room.players.get(player.alliance_partner)
                    if partner:
                        partner.alliance_partner = None
                    player.alliance_partner = None
    
    def _update_skill_durations(self):
        """更新技能卡持续时间"""
        for player in self.room.players.values():
            expired_skills = []
            for skill in player.skills:
                if isinstance(skill, dict) and skill.get('duration', 0) > 0:
                    skill['duration'] -= 1
                    if skill['duration'] == 0:
                        expired_skills.append(skill)
            
            # 移除过期技能
            for skill in expired_skills:
                player.skills.remove(skill)
    
    def _apply_skill_effects(self):
        """应用技能卡效果（在行动结算后）"""
        # 技能卡效果在玩家主动使用时触发
        pass
    
    def use_skill_card(self, player_id: str, skill_id: str, 
                      target_id: str = None) -> Tuple[bool, str]:
        """使用技能卡"""
        player = self.room.players.get(player_id)
        if not player or not player.is_alive:
            return False, "玩家不存在或已死亡"
        
        # 查找技能卡
        skill = None
        for s in player.skills:
            if isinstance(s, dict) and (s.get('id') == skill_id or s.get('skill_type') == skill_id):
                skill = s
                break
        
        if not skill:
            return False, "技能卡不存在"
        
        # 验证目标（攻击类技能需要目标）
        if skill.get('type') == 'attack':
            if not target_id or target_id not in self.room.players:
                return False, "需要指定有效目标"
            target = self.room.players[target_id]
            if not target.is_alive:
                return False, "目标已死亡"
        
        # 执行技能效果
        effect = skill.get('effect', {})
        damage = effect.get('damage', 0)
        
        if damage > 0 and target_id:
            target = self.room.players[target_id]
            target.cities -= damage
            
            # 破城卡：自身损失
            if effect.get('self_damage'):
                player.cities -= effect['self_damage']
            
            # 移除使用的技能卡
            player.skills.remove(skill)
            return True, f"使用{skill['name']}，造成{damage}伤害"
        
        # 其他类型技能
        heal = effect.get('heal', 0)
        if heal > 0:
            player.cities += heal
            player.skills.remove(skill)
            return True, f"使用{skill['name']}，恢复{heal}城池"
        
        return False, "该技能卡效果未实现"
    
    def _generate_meeting_report(self, actions: List[Action]):
        """生成会议报告"""
        report = {
            'round': self.room.game_state.current_round,
            'player_status': {},
            'actions': [],
            'total_skills_drawn': self.drawn_count
        }
        
        # 玩家状态
        for pid, player in self.room.players.items():
            report['player_status'][pid] = {
                'name': player.name,
                'cities': player.cities,
                'is_alive': player.is_alive,
                'skill_count': len(player.skills)
            }
        
        # 行动摘要
        for action in actions:
            action_summary = {
                'player': self.room.players[action.player_id].name,
                'action': action.action_type,
                'result': action.result
            }
            report['actions'].append(action_summary)
        
        self.room.game_state.meeting_report = report
    
    def _start_auction(self):
        """开始拍卖"""
        # 抽取一张技能卡作为拍卖品
        auction_card = get_random_skill()
        if not auction_card:
            # 没有技能卡可拍卖
            self._next_round()
            return
        
        # 计算起拍价
        alive_players = [p for p in self.room.players.values() if p.is_alive]
        if not alive_players:
            self._next_round()
            return
        
        min_cities = min(p.cities for p in alive_players)
        starting_price = max(min_cities, 10)
        
        self.room.game_state.auction = {
            'card': auction_card,
            'current_price': starting_price,
            'highest_bidder': None,
            'bids': {},
            'active': True,
            'start_time': None  # 由外部设置
        }
        
        self.room.game_state.phase = 'auction'
    
    def place_bid(self, player_id: str, bid_amount: int) -> Tuple[bool, str]:
        """拍卖出价"""
        if not self.room.game_state.auction or not self.room.game_state.auction['active']:
            return False, "当前没有进行中的拍卖"
        
        player = self.room.players.get(player_id)
        if not player or not player.is_alive:
            return False, "玩家不存在或已死亡"
        
        auction = self.room.game_state.auction
        min_increment = 10
        
        if bid_amount < auction['current_price'] + min_increment:
            return False, f"出价必须至少为 {auction['current_price'] + min_increment}"
        
        if bid_amount > player.cities:
            return False, "城池不足"
        
        auction['bids'][player_id] = bid_amount
        auction['current_price'] = bid_amount
        auction['highest_bidder'] = player_id
        
        return True, f"出价成功，当前最高价：{bid_amount}"
    
    def end_auction(self):
        """结束拍卖"""
        auction = self.room.game_state.auction
        if not auction or not auction['active']:
            return
        
        auction['active'] = False
        
        # 处理拍卖结果
        if auction['highest_bidder']:
            winner = self.room.players.get(auction['highest_bidder'])
            if winner:
                # 扣除城池
                winner.cities -= auction['current_price']
                # 给予技能卡
                winner.skills.append(auction['card'])
                auction['winner'] = winner.id
                auction['final_price'] = auction['current_price']
        
        # 进入下一回合
        self._next_round()
    
    def _next_round(self):
        """进入下一回合"""
        self.room.game_state.current_round += 1
        self.room.game_state.phase = 'action'
        
        # 清除玩家行动
        for player in self.room.players.values():
            player.action = None
            player.has_repaired = False
        
        # 检查游戏结束
        alive_players = [p for p in self.room.players.values() if p.is_alive]
        if len(alive_players) <= 1:
            self.room.game_state.phase = 'ended'
            if alive_players:
                self.room.game_state.winner = alive_players[0].id
    
    def check_game_end(self) -> Optional[str]:
        """检查游戏是否结束，返回获胜者ID"""
        alive_players = [p for p in self.room.players.values() if p.is_alive]
        
        if len(alive_players) == 0:
            return 'draw'
        elif len(alive_players) == 1:
            return alive_players[0].id
        
        return None
