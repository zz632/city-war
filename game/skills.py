"""
技能卡效果实现 - 20张不同的技能卡
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class SkillType(Enum):
    ATTACK = "attack"
    DEFENSE = "defense"
    RESOURCE = "resource"
    SPECIAL = "special"


@dataclass
class SkillCard:
    id: str
    name: str
    type: SkillType
    description: str
    effect_func: Optional[Callable] = None


# 技能卡定义
SKILL_CARDS: Dict[str, Dict] = {
    # 攻击类技能卡
    "fire_attack": {
        "name": "火攻卡",
        "type": "attack",
        "description": "对目标造成 30 城池伤害",
        "effect": {"damage": 30}
    },
    "surprise_attack": {
        "name": "奇袭卡",
        "type": "attack",
        "description": "对目标造成 20 城池伤害，无视守城效果",
        "effect": {"damage": 20, "ignore_defend": True}
    },
    "crossbow": {
        "name": "连弩卡",
        "type": "attack",
        "description": "连续攻击两名不同玩家，各造成 15 城池伤害",
        "effect": {"damage": 15, "multi_target": 2}
    },
    "siege": {
        "name": "破城卡",
        "type": "attack",
        "description": "对目标造成 50 城池伤害，但自己损失 10 城池",
        "effect": {"damage": 50, "self_damage": 10}
    },
    "poison": {
        "name": "毒计卡",
        "type": "attack",
        "description": "使目标下回合无法行动",
        "effect": {"stun": True}
    },
    
    # 防御类技能卡
    "iron_wall": {
        "name": "铁壁卡",
        "type": "defense",
        "description": "下回合受到的所有伤害减半",
        "effect": {"damage_reduction": 0.5}
    },
    "empty_city": {
        "name": "空城卡",
        "type": "defense",
        "description": "下回合若被攻击，攻击方损失 20 城池",
        "effect": {"reflect": 20}
    },
    "reinforcements": {
        "name": "援军卡",
        "type": "defense",
        "description": "立即获得 25 城池",
        "effect": {"heal": 25}
    },
    "feign_surrender": {
        "name": "诈降卡",
        "type": "defense",
        "description": "下回合若被攻击，免疫伤害并反弹 15 城池伤害",
        "effect": {"immune": True, "reflect": 15}
    },
    "relocate": {
        "name": "迁都卡",
        "type": "defense",
        "description": "立即获得 15 城池，下回合无法被选中为攻击目标",
        "effect": {"heal": 15, "untargetable": True}
    },
    
    # 资源类技能卡
    "farm": {
        "name": "屯田卡",
        "type": "resource",
        "description": "接下来 3 回合每回合获得 10 城池",
        "effect": {"recurring": 3, "amount": 10}
    },
    "trade_route": {
        "name": "商路卡",
        "type": "resource",
        "description": "从所有其他玩家处各获得 5 城池",
        "effect": {"steal": 5}
    },
    "tax": {
        "name": "征税卡",
        "type": "resource",
        "description": "获得当前城池数 20% 的额外城池",
        "effect": {"percent": 0.2}
    },
    "recruit": {
        "name": "募兵卡",
        "type": "resource",
        "description": "立即获得 20 城池，但下回合必须选择攻城",
        "effect": {"heal": 20, "force_attack": True}
    },
    "harvest": {
        "name": "丰收卡",
        "type": "resource",
        "description": "获得 30 城池，但跳过下回合行动",
        "effect": {"heal": 30, "skip_turn": True}
    },
    
    # 特殊类技能卡
    "sow_discord": {
        "name": "离间卡",
        "type": "special",
        "description": "指定两名其他玩家，他们下回合无法互相攻击",
        "effect": {"prevent_attack": 2}
    },
    "recon": {
        "name": "侦查卡",
        "type": "special",
        "description": "查看一名玩家的手牌和下回合意图",
        "effect": {"reveal": True}
    },
    "disguise": {
        "name": "伪装卡",
        "type": "special",
        "description": "下回合你的行动对其他玩家显示为随机行动",
        "effect": {"disguise": True}
    },
    "first_aid": {
        "name": "急救卡",
        "type": "special",
        "description": "当城池数小于 0 时使用，立即获得 20 城池（可救命一次）",
        "effect": {"emergency_heal": 20}
    },
    "reverse": {
        "name": "逆转卡",
        "type": "special",
        "description": "与一名玩家交换城池数（双方需>50城池，且城池差不超过30）",
        "effect": {"swap": True, "min_cities": 50, "max_diff": 30}
    }
}


def get_skill_card(skill_id: str) -> Optional[SkillCard]:
    """获取技能卡信息"""
    if skill_id not in SKILL_CARDS:
        return None
    
    skill_data = SKILL_CARDS[skill_id]
    return SkillCard(
        id=skill_id,
        name=skill_data["name"],
        type=skill_data["type"],
        description=skill_data["description"]
    )


def get_random_skill() -> Dict:
    """随机获取一张技能卡"""
    import random
    import uuid
    skill_id = random.choice(list(SKILL_CARDS.keys()))
    skill = SKILL_CARDS[skill_id].copy()
    skill["id"] = str(uuid.uuid4())
    skill["skill_type"] = skill_id
    return skill


def get_all_skills() -> List[SkillCard]:
    """获取所有技能卡"""
    return [get_skill_card(sid) for sid in SKILL_CARDS.keys()]


# 技能效果处理函数
def apply_skill_effect(game_state: Any, player_id: str, skill_id: str, 
                       target_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    应用技能卡效果
    返回效果执行结果
    """
    player = game_state.get_player(player_id)
    if not player:
        return {"success": False, "message": "玩家不存在"}

    # 查找技能卡（兼容 skill_type 和 uuid id）
    skill_card = None
    for s in player.skills:
        if isinstance(s, dict) and (s.get('skill_type') == skill_id or s.get('id') == skill_id):
            skill_card = s
            break

    if not skill_card:
        return {"success": False, "message": "玩家没有这张技能卡"}

    # 获取技能定义
    skill_type_key = skill_card.get('skill_type', skill_id)
    skill = SKILL_CARDS.get(skill_type_key)
    if not skill:
        return {"success": False, "message": "技能卡不存在"}

    # 移除技能卡
    player.remove_skill(skill_card.get('id', skill_id))
    
    result = {
        "success": True,
        "skill_name": skill["name"],
        "player_id": player_id,
        "target_id": target_id,
        "effects": []
    }
    
    # 根据技能类型执行不同效果
    if skill_type_key == "fire_attack":
        # 火攻卡 - 造成30伤害
        if target_id:
            target = game_state.get_player(target_id)
            if target:
                target.cities -= 30
                result["effects"].append({
                    "type": "damage",
                    "target": target_id,
                    "amount": 30
                })

    elif skill_type_key == "surprise_attack":
        # 奇袭卡 - 造成20伤害，无视守城
        if target_id:
            target = game_state.get_player(target_id)
            if target:
                target.cities -= 20
                result["effects"].append({
                    "type": "damage",
                    "target": target_id,
                    "amount": 20,
                    "ignore_defense": True
                })

    elif skill_type_key == "crossbow":
        # 连弩卡 - 攻击两名玩家
        targets = kwargs.get("targets", [])
        for tid in targets[:2]:
            target = game_state.get_player(tid)
            if target:
                target.cities -= 15
                result["effects"].append({
                    "type": "damage",
                    "target": tid,
                    "amount": 15
                })

    elif skill_type_key == "siege":
        # 破城卡 - 造成50伤害，自己损失10
        if target_id:
            target = game_state.get_player(target_id)
            if target:
                target.cities -= 50
                player.cities -= 10
                result["effects"].append({
                    "type": "damage",
                    "target": target_id,
                    "amount": 50
                })
                result["effects"].append({
                    "type": "self_damage",
                    "amount": 10
                })

    elif skill_type_key == "poison":
        # 毒计卡 - 目标下回合无法行动
        if target_id:
            target = game_state.get_player(target_id)
            if target:
                target.status_effects["stun"] = 2  # 与 events.py 一致
                result["effects"].append({
                    "type": "status",
                    "target": target_id,
                    "status": "stun"
                })

    elif skill_type_key == "iron_wall":
        # 铁壁卡 - 下回合伤害减半
        player.status_effects["iron_wall"] = 1
        result["effects"].append({
            "type": "buff",
            "status": "iron_wall"
        })

    elif skill_type_key == "empty_city":
        # 空城卡 - 被攻击时攻击方损失20
        player.status_effects["empty_city"] = 1
        result["effects"].append({
            "type": "buff",
            "status": "empty_city"
        })

    elif skill_type_key == "reinforcements":
        # 援军卡 - 获得25城池
        player.cities += 25
        result["effects"].append({
            "type": "heal",
            "amount": 25
        })

    elif skill_type_key == "feign_surrender":
        # 诈降卡 - 免疫并反弹
        player.status_effects["feign_surrender"] = 1
        result["effects"].append({
            "type": "buff",
            "status": "feign_surrender"
        })

    elif skill_type_key == "relocate":
        # 迁都卡 - 获得15城池，下回合无法被选中
        player.cities += 15
        player.status_effects["relocate"] = 1
        result["effects"].append({
            "type": "heal",
            "amount": 15
        })
        result["effects"].append({
            "type": "buff",
            "status": "relocate"
        })

    elif skill_type_key == "farm":
        # 屯田卡 - 3回合每回合+10
        player.status_effects["farm"] = 3
        result["effects"].append({
            "type": "buff",
            "status": "farm",
            "duration": 3
        })

    elif skill_type_key == "trade_route":
        # 商路卡 - 从其他玩家各获得5城池
        total_gain = 0
        for pid, p in game_state.players.items():
            if pid != player_id and p.is_alive:
                p.cities -= 5
                total_gain += 5
        player.cities += total_gain
        result["effects"].append({
            "type": "heal",
            "amount": total_gain
        })

    elif skill_type_key == "tax":
        # 征税卡 - 获得当前20%城池
        gain = int(player.cities * 0.2)
        player.cities += gain
        result["effects"].append({
            "type": "heal",
            "amount": gain
        })

    elif skill_type_key == "recruit":
        # 募兵卡 - 获得20城池，下回合必须攻城
        player.cities += 20
        player.status_effects["must_attack"] = 1
        result["effects"].append({
            "type": "heal",
            "amount": 20
        })
        result["effects"].append({
            "type": "restriction",
            "restriction": "must_attack"
        })

    elif skill_type_key == "harvest":
        # 丰收卡 - 获得30城池，跳过下回合
        player.cities += 30
        player.status_effects["skip_turn"] = 1
        result["effects"].append({
            "type": "heal",
            "amount": 30
        })
        result["effects"].append({
            "type": "restriction",
            "restriction": "skip_turn"
        })

    elif skill_type_key == "sow_discord":
        # 离间卡 - 两名玩家无法互相攻击
        targets = kwargs.get("targets", [])
        if len(targets) >= 2:
            for tid in targets[:2]:
                target = game_state.get_player(tid)
                if target:
                    target.status_effects["discord"] = 1
            result["effects"].append({
                "type": "status",
                "targets": targets[:2],
                "status": "discord"
            })

    elif skill_type_key == "recon":
        # 侦查卡 - 查看玩家手牌和意图
        if target_id:
            target = game_state.get_player(target_id)
            if target:
                result["effects"].append({
                    "type": "reveal",
                    "target": target_id,
                    "skills": target.skills.copy(),
                    "intention": target.current_action
                })

    elif skill_type_key == "disguise":
        # 伪装卡 - 行动显示为随机
        player.status_effects["disguise"] = 1
        result["effects"].append({
            "type": "buff",
            "status": "disguise"
        })

    elif skill_type_key == "first_aid":
        # 急救卡 - 救命用
        if player.cities < 0:
            player.cities = 20
            result["effects"].append({
                "type": "revive",
                "amount": 20
            })
        else:
            result["effects"].append({
                "type": "message",
                "message": "城池数不为负，急救卡无效"
            })

    elif skill_type_key == "reverse":
        # 逆转卡 - 交换城池数（限制城池差）
        if target_id:
            target = game_state.get_player(target_id)
            max_diff = effect.get('max_diff', 30)
            if target and player.cities > 50 and target.cities > 50:
                if abs(player.cities - target.cities) <= max_diff:
                    player.cities, target.cities = target.cities, player.cities
                    result["effects"].append({
                        "type": "swap",
                        "target": target_id
                    })
                else:
                    result["effects"].append({
                        "type": "message",
                        "message": "双方城池差超过" + str(max_diff) + "，无法交换"
                    })
            else:
                result["effects"].append({
                    "type": "message",
                    "message": "双方城池数均需大于50"
                })
    
    return result
