"""
城池战争游戏 - 数据模型
"""
import uuid
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class ActionType(Enum):
    """行动类型"""
    ATTACK = "attack"           # 攻城
    DEFEND = "defend"           # 守城
    JUNGLE = "jungle"           # 打野
    DUEL = "duel"               # 约战
    REPAIR = "repair"           # 修城（第6轮后）
    ALLIANCE = "alliance"           # 结盟（第6轮后）
    DISSOLVE_ALLIANCE = "dissolve_alliance"  # 解盟


class GamePhase(Enum):
    """游戏阶段"""
    WAITING = "waiting"         # 等待中
    ACTION = "action"           # 行动阶段
    MEETING = "meeting"         # 会议阶段
    AUCTION = "auction"         # 拍卖阶段
    DUEL = "duel"               # 轮盘赌阶段
    FINISHED = "finished"       # 游戏结束


@dataclass
class Player:
    """玩家模型"""
    id: str
    name: str
    room_id: str
    cities: int = 100
    is_alive: bool = True
    is_host: bool = False
    is_ready: bool = False
    is_spectator: bool = False
    skills: List[Dict] = field(default_factory=list)
    action: Optional[Dict] = None
    alliance_with: Optional[str] = None
    alliance_benefits: int = 0
    alliance_damages: int = 0
    repair_active: bool = False
    status_effects: Dict = field(default_factory=dict)  # 活跃状态效果
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self, is_spectator: bool = False, is_self: bool = False) -> Dict:
        """转换为字典"""
        data = {
            "id": self.id,
            "name": self.name,
            "cities": self.cities,
            "is_alive": self.is_alive,
            "is_host": self.is_host,
            "is_ready": self.is_ready,
            "is_spectator": self.is_spectator,
            "alliance_with": self.alliance_with,
            "repair_active": self.repair_active,
        }

        # 非观战者可以看到技能卡数量
        if is_spectator or self.is_alive:
            data["skills_count"] = len(self.skills)

        # 自己或上帝视角可以看到自己的技能卡详情
        if is_self or is_spectator:
            data["skills"] = self.skills

        # 上帝视角可以看到所有信息
        if is_spectator:
            data["action"] = self.action
            data["alliance_benefits"] = self.alliance_benefits
            data["alliance_damages"] = self.alliance_damages
            data["status_effects"] = self.status_effects

        # 自己可以看到自己的状态效果
        if is_self:
            data["status_effects"] = self.status_effects

        return data
    
    def add_skill(self, skill: Dict):
        """添加技能卡"""
        self.skills.append(skill)
    
    def remove_skill(self, skill_id: str) -> Optional[Dict]:
        """移除技能卡"""
        for i, skill in enumerate(self.skills):
            if skill["id"] == skill_id:
                return self.skills.pop(i)
        return None
    
    def change_cities(self, amount: int):
        """改变城池数"""
        self.cities += amount
        if self.cities < 0:
            self.is_alive = False


@dataclass
class Room:
    """房间模型"""
    id: str
    name: str
    host_id: str
    players: Dict[str, Player] = field(default_factory=dict)
    game_state: Optional['GameState'] = None
    created_at: float = field(default_factory=time.time)
    max_players: int = 8
    
    def to_dict(self, player_id: str = None) -> Dict:
        """转换为字典"""
        is_spectator = False
        if player_id and player_id in self.players:
            p = self.players[player_id]
            is_spectator = p.is_spectator or not p.is_alive

        return {
            "id": self.id,
            "name": self.name,
            "host_id": self.host_id,
            "players": {pid: p.to_dict(is_spectator, is_self=(pid == player_id)) for pid, p in self.players.items()},
            "player_count": len(self.players),
            "max_players": self.max_players,
            "game_state": self.game_state.to_dict(is_spectator) if self.game_state else None,
            "created_at": self.created_at,
        }
    
    def add_player(self, player: Player) -> bool:
        """添加玩家"""
        if len(self.players) >= self.max_players:
            return False
        self.players[player.id] = player
        return True
    
    def remove_player(self, player_id: str):
        """移除玩家"""
        if player_id in self.players:
            del self.players[player_id]
            # 如果房主离开，转移房主身份
            if player_id == self.host_id and self.players:
                self.host_id = next(iter(self.players.keys()))
                self.players[self.host_id].is_host = True
    
    def get_alive_players(self) -> List[Player]:
        """获取存活玩家"""
        return [p for p in self.players.values() if p.is_alive]
    
    def check_game_over(self) -> Optional[str]:
        """检查游戏是否结束，返回获胜者ID"""
        alive_players = self.get_alive_players()
        if len(alive_players) <= 1:
            return alive_players[0].id if alive_players else None
        return None


@dataclass
class GameState:
    """游戏状态"""
    round: int = 1
    phase: GamePhase = GamePhase.WAITING
    actions: Dict[str, Dict] = field(default_factory=dict)
    messages: List[Dict] = field(default_factory=list)
    auction: Optional[Dict] = None
    duel: Optional[Dict] = None
    meeting_results: Optional[Dict] = None
    skill_cards_drawn: int = 0
    
    def to_dict(self, is_spectator: bool = False) -> Dict:
        """转换为字典"""
        data = {
            "round": self.round,
            "phase": self.phase.value,
            "skill_cards_drawn": self.skill_cards_drawn,
        }
        
        if is_spectator:
            data["actions"] = self.actions
            data["messages"] = self.messages
        
        if self.auction:
            data["auction"] = self.auction
        if self.duel:
            data["duel"] = self.duel
        if self.meeting_results:
            data["meeting_results"] = self.meeting_results
        
        return data
    
    def next_round(self):
        """进入下一轮"""
        self.round += 1
        self.actions = {}
        self.meeting_results = None
        self.phase = GamePhase.ACTION
    
    def add_action(self, player_id: str, action: Dict):
        """添加玩家行动"""
        self.actions[player_id] = action
    
    def add_message(self, player_id: str, message: str, msg_type: str = "public"):
        """添加消息"""
        self.messages.append({
            "player_id": player_id,
            "message": message,
            "type": msg_type,
            "timestamp": time.time(),
        })


@dataclass
class Action:
    """玩家行动"""
    player_id: str
    action_type: ActionType
    target_id: Optional[str] = None
    bet: Optional[int] = None
    result: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            "player_id": self.player_id,
            "action_type": self.action_type.value,
            "target_id": self.target_id,
            "bet": self.bet,
            "result": self.result,
        }


# 技能卡定义
SKILL_CARDS = {
    # 攻击类
    "fire_attack": {"name": "火攻卡", "type": "attack", "description": "对目标造成30城池伤害", "effect": {"damage": 30}},
    "surprise": {"name": "奇袭卡", "type": "attack", "description": "对目标造成20城池伤害，无视守城", "effect": {"damage": 20, "ignore_defend": True}},
    "crossbow": {"name": "连弩卡", "type": "attack", "description": "攻击两名不同玩家，各造成15伤害", "effect": {"damage": 15, "multi_target": 2}},
    "siege": {"name": "破城卡", "type": "attack", "description": "对目标造成50伤害，自己损失10", "effect": {"damage": 50, "self_damage": 10}},
    "poison": {"name": "毒计卡", "type": "attack", "description": "使目标下回合无法行动", "effect": {"stun": True}},
    
    # 防御类
    "iron_wall": {"name": "铁壁卡", "type": "defense", "description": "下回合受到的伤害减半", "effect": {"damage_reduction": 0.5}},
    "empty_city": {"name": "空城卡", "type": "defense", "description": "下回合若被攻击，攻击方损失20", "effect": {"reflect": 20}},
    "reinforce": {"name": "援军卡", "type": "defense", "description": "立即获得25城池", "effect": {"heal": 25}},
    "feign": {"name": "诈降卡", "type": "defense", "description": "下回合若被攻击，免疫并反弹15", "effect": {"immune": True, "reflect": 15}},
    "move_capital": {"name": "迁都卡", "type": "defense", "description": "获得15城池，下回合无法被选中", "effect": {"heal": 15, "untargetable": True}},
    
    # 资源类
    "farm": {"name": "屯田卡", "type": "resource", "description": "接下来3回合每回合获得10城池", "effect": {"recurring": 3, "amount": 10}},
    "trade": {"name": "商路卡", "type": "resource", "description": "从所有其他玩家处各获得5城池", "effect": {"steal": 5}},
    "tax": {"name": "征税卡", "type": "resource", "description": "获得当前城池数20%的额外城池", "effect": {"percent": 0.2}},
    "recruit": {"name": "募兵卡", "type": "resource", "description": "立即获得20城池，但下回合必须攻城", "effect": {"heal": 20, "force_attack": True}},
    "harvest": {"name": "丰收卡", "type": "resource", "description": "获得30城池，但跳过下回合", "effect": {"heal": 30, "skip_turn": True}},
    
    # 特殊类
    "alienate": {"name": "离间卡", "type": "special", "description": "指定两名玩家，他们下回合无法互相攻击", "effect": {"prevent_attack": 2}},
    "scout": {"name": "侦查卡", "type": "special", "description": "查看一名玩家的手牌和下回合意图", "effect": {"reveal": True}},
    "disguise": {"name": "伪装卡", "type": "special", "description": "下回合你的行动显示为随机行动", "effect": {"disguise": True}},
    "first_aid": {"name": "急救卡", "type": "special", "description": "城池<0时使用，获得20城池（救命一次）", "effect": {"emergency_heal": 20}},
    "reverse": {"name": "逆转卡", "type": "special", "description": "与一名玩家交换城池数（双方需>50）", "effect": {"swap": True, "min_cities": 50}},
}


def get_random_skill() -> Dict:
    """随机获取一张技能卡"""
    import random
    skill_id = random.choice(list(SKILL_CARDS.keys()))
    skill = SKILL_CARDS[skill_id].copy()
    skill["id"] = str(uuid.uuid4())
    skill["skill_type"] = skill_id
    return skill
