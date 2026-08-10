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
        "description": "解散所有联盟，3轮内不能联盟",
        "effect": {"dissolve_all_alliances": True, "no_alliance_rounds": 3}
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
        "description": "与一名玩家交换城池数（城池差不超过100），交换后3轮内不能攻击对方",
        "effect": {"swap": True, "max_diff": 100}
    },

    # ===== 新增技能卡（第二批） =====

    # 攻击类
    "plus_damage": {
        "name": "+5伤卡",
        "type": "attack",
        "description": "使用后每轮伤害增加5",
        "effect": {"permanent_damage_bonus": 5}
    },
    "invulnerable": {
        "name": "无懈可击卡",
        "type": "defense",
        "description": "当有玩家对你使用有害技能卡时，可免除效果",
        "effect": {"counter_skill": True}
    },
    "steal_card": {
        "name": "瞒天过海卡",
        "type": "special",
        "description": "消耗30城池偷走指定玩家一张卡",
        "effect": {"steal_card": True, "cost": 30}
    },
    "immortal_totem": {
        "name": "不死图腾卡",
        "type": "defense",
        "description": "血量<0时+50血，3局内减伤20%+每轮+5",
        "effect": {"emergency_heal": 50, "post_save_reduction": 0.2, "post_save_heal": 5, "post_save_rounds": 3}
    },
    "fortress": {
        "name": "磐石堡垒卡",
        "type": "defense",
        "description": "定值减伤10",
        "effect": {"flat_damage_reduction": 10}
    },
    "freeze": {
        "name": "呆若木鸡卡",
        "type": "attack",
        "description": "对方这回合无法行动",
        "effect": {"stun": True}
    },
    "arrow_rain": {
        "name": "万箭齐发卡",
        "type": "attack",
        "description": "对其他所有人造成15+3n伤害，获得伤害1/3城池",
        "effect": {"aoe_damage": 15, "aoe_per_player": 3}
    },
    "delay_troops": {
        "name": "撒豆成兵卡",
        "type": "resource",
        "description": "城池-20，3轮后+80",
        "effect": {"cost": 20, "delayed_heal": 80, "delay_rounds": 3}
    },
    "retreat": {
        "name": "退退退卡",
        "type": "defense",
        "description": "本轮无法受攻击伤害且反弹50",
        "effect": {"immune": True, "reflect": 50}
    },
    "fierce_attack": {
        "name": "猛攻卡",
        "type": "attack",
        "description": "攻击时单次伤害×3",
        "effect": {"attack_multiplier": 3}
    },
    "regen": {
        "name": "回血卡",
        "type": "defense",
        "description": "每轮+5血",
        "effect": {"recurring_heal": 5}
    },
    "double_action": {
        "name": "二般人卡",
        "type": "special",
        "description": "一轮可行动两次",
        "effect": {"extra_action": True}
    },
    "lifesteal": {
        "name": "吸血卡",
        "type": "attack",
        "description": "每次攻击吸取5%总血量",
        "effect": {"lifesteal_percent": 0.05}
    },
    "upgrade": {
        "name": "升级卡",
        "type": "special",
        "description": "升级一次技能(×2)",
        "effect": {"upgrade_skill": True}
    },
    "treasure": {
        "name": "聚宝盆卡",
        "type": "resource",
        "description": "城池收益永久×1.25",
        "effect": {"income_multiplier": 1.25}
    },
    "equal_trade": {
        "name": "等价交换卡",
        "type": "resource",
        "description": "-75城获得两张技能卡",
        "effect": {"cost": 75, "bonus_cards": 2}
    },
    "damage_boost": {
        "name": "加伤卡",
        "type": "attack",
        "description": "攻击伤害永久+25%",
        "effect": {"permanent_attack_bonus": 0.25}
    },
    "double_gain": {
        "name": "以逸待劳卡",
        "type": "resource",
        "description": "获得收益时×2",
        "effect": {"double_gain": True}
    },
    "tribute": {
        "name": "顺手牵羊卡",
        "type": "special",
        "description": "让对方给你一张技能卡",
        "effect": {"demand_card": True}
    },
    "protagonist": {
        "name": "主角光环卡",
        "type": "defense",
        "description": "永久减伤20%",
        "effect": {"permanent_reduction": 0.2}
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
            if pid != player_id and p.is_alive and not p.is_spectator:
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
        # 离间卡 - 解散所有联盟，3轮内不能联盟
        for pid, p in game_state.players.items():
            p.alliance_with = None
            p.status_effects['no_alliance'] = 3
        result["effects"].append({
            "type": "dissolve_all_alliances",
            "no_alliance_rounds": 3
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
        # 逆转卡 - 交换城池数（城池差不超过100），交换后3轮内不能攻击对方
        if target_id:
            target = game_state.get_player(target_id)
            max_diff = effect.get('max_diff', 100)
            if target:
                if abs(player.cities - target.cities) <= max_diff:
                    player.cities, target.cities = target.cities, player.cities
                    # 交换后3轮内双方不能攻击对方
                    player.status_effects['reverse_no_attack'] = {'target': target_id, 'rounds': 3}
                    target.status_effects['reverse_no_attack'] = {'target': player_id, 'rounds': 3}
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
                    "message": "目标玩家不存在"
                })

    # ===== 新增技能卡执行逻辑（第二批） =====

    elif skill_type_key == "plus_damage":
        # +5伤卡 - 每轮伤害永久+5
        player.status_effects["permanent_damage_bonus"] = player.status_effects.get("permanent_damage_bonus", 0) + 5
        result["effects"].append({
            "type": "permanent_buff",
            "status": "permanent_damage_bonus",
            "value": 5
        })

    elif skill_type_key == "invulnerable":
        # 无懈可击卡 - 被动：对有害技能卡免疫（标记，实际触发在 manager.py 的 process_round 中处理）
        player.status_effects["invulnerable"] = True
        result["effects"].append({
            "type": "buff",
            "status": "invulnerable"
        })

    elif skill_type_key == "steal_card":
        # 瞒天过海卡 - 消耗30城池偷走指定玩家一张卡
        cost = skill["effect"].get("cost", 30)
        if player.cities >= cost:
            player.cities -= cost
            if target_id:
                target = game_state.get_player(target_id)
                if target and target.skills:
                    import random
                    stolen = random.choice(target.skills)
                    target.remove_skill(stolen.get('id', ''))
                    player.skills.append(stolen)
                    result["effects"].append({
                        "type": "steal_card",
                        "target": target_id,
                        "cost": cost
                    })
                else:
                    result["effects"].append({
                        "type": "message",
                        "message": "目标玩家没有可偷的卡"
                    })
            else:
                result["effects"].append({
                    "type": "message",
                    "message": "未指定目标玩家"
                })
        else:
            result["effects"].append({
                "type": "message",
                "message": "城池不足，需要{}城池".format(cost)
            })

    elif skill_type_key == "immortal_totem":
        # 不死图腾卡 - 血量<0时+50血，3局内减伤20%+每轮+5（被动触发，标记）
        player.status_effects["immortal_totem"] = {
            "emergency_heal": 50,
            "post_save_reduction": 0.2,
            "post_save_heal": 5,
            "post_save_rounds": 3
        }
        result["effects"].append({
            "type": "buff",
            "status": "immortal_totem",
            "duration": 3
        })

    elif skill_type_key == "fortress":
        # 磐石堡垒卡 - 定值减伤10（永久）
        player.status_effects["flat_damage_reduction"] = player.status_effects.get("flat_damage_reduction", 0) + 10
        result["effects"].append({
            "type": "permanent_buff",
            "status": "flat_damage_reduction",
            "value": 10
        })

    elif skill_type_key == "freeze":
        # 呆若木鸡卡 - 对方这回合无法行动
        if target_id:
            target = game_state.get_player(target_id)
            if target:
                target.status_effects["stun"] = 2
                result["effects"].append({
                    "type": "status",
                    "target": target_id,
                    "status": "stun"
                })

    elif skill_type_key == "arrow_rain":
        # 万箭齐发卡 - 对其他所有人造成15+3n伤害，获得伤害1/3城池
        base_dmg = skill["effect"].get("aoe_damage", 15)
        per_player = skill["effect"].get("aoe_per_player", 3)
        n_other = sum(1 for pid, p in game_state.players.items() if pid != player_id and p.is_alive and not p.is_spectator)
        total_dmg = base_dmg + per_player * n_other
        total_dealt = 0
        for pid, p in game_state.players.items():
            if pid != player_id and p.is_alive and not p.is_spectator:
                p.cities -= total_dmg
                total_dealt += total_dmg
        player.cities += total_dealt // 3
        result["effects"].append({
            "type": "aoe_damage",
            "damage_per_target": total_dmg,
            "targets_hit": n_other,
            "cities_gained": total_dealt // 3
        })

    elif skill_type_key == "delay_troops":
        # 撒豆成兵卡 - 城池-20，3轮后+80
        cost = skill["effect"].get("cost", 20)
        delayed_heal = skill["effect"].get("delayed_heal", 80)
        delay_rounds = skill["effect"].get("delay_rounds", 3)
        player.cities -= cost
        player.status_effects["delay_troops"] = {
            "heal": delayed_heal,
            "rounds_left": delay_rounds
        }
        result["effects"].append({
            "type": "delayed_effect",
            "cost": cost,
            "delayed_heal": delayed_heal,
            "delay_rounds": delay_rounds
        })

    elif skill_type_key == "retreat":
        # 退退退卡 - 本轮无法受攻击伤害且反弹50
        player.status_effects["retreat"] = 1
        result["effects"].append({
            "type": "buff",
            "status": "retreat"
        })

    elif skill_type_key == "fierce_attack":
        # 猛攻卡 - 攻击时单次伤害×3
        player.status_effects["attack_multiplier"] = player.status_effects.get("attack_multiplier", 1) * 3
        result["effects"].append({
            "type": "permanent_buff",
            "status": "attack_multiplier",
            "value": 3
        })

    elif skill_type_key == "regen":
        # 回血卡 - 每轮+5血（永久）
        player.status_effects["recurring_heal"] = player.status_effects.get("recurring_heal", 0) + 5
        result["effects"].append({
            "type": "permanent_buff",
            "status": "recurring_heal",
            "value": 5
        })

    elif skill_type_key == "double_action":
        # 二般人卡 - 一轮可行动两次
        player.status_effects["extra_action"] = 1
        result["effects"].append({
            "type": "buff",
            "status": "extra_action"
        })

    elif skill_type_key == "lifesteal":
        # 吸血卡 - 每次攻击吸取5%总血量（永久标记）
        lifesteal_pct = skill["effect"].get("lifesteal_percent", 0.05)
        player.status_effects["lifesteal_percent"] = player.status_effects.get("lifesteal_percent", 0) + lifesteal_pct
        result["effects"].append({
            "type": "permanent_buff",
            "status": "lifesteal_percent",
            "value": lifesteal_pct
        })

    elif skill_type_key == "upgrade":
        # 升级卡 - 升级一次技能(×2)
        target_skill = kwargs.get("upgrade_target")
        if target_skill:
            # 对指定技能效果翻倍（通过 status_effects 标记）
            player.status_effects["upgrade_target"] = target_skill
            player.status_effects["upgrade_multiplier"] = 2
            result["effects"].append({
                "type": "upgrade",
                "target_skill": target_skill,
                "multiplier": 2
            })
        else:
            result["effects"].append({
                "type": "message",
                "message": "未指定要升级的技能"
            })

    elif skill_type_key == "treasure":
        # 聚宝盆卡 - 城池收益永久×1.25
        player.status_effects["income_multiplier"] = player.status_effects.get("income_multiplier", 1) * 1.25
        result["effects"].append({
            "type": "permanent_buff",
            "status": "income_multiplier",
            "value": 1.25
        })

    elif skill_type_key == "equal_trade":
        # 等价交换卡 - -75城获得两张技能卡
        cost = skill["effect"].get("cost", 75)
        bonus_cards = skill["effect"].get("bonus_cards", 2)
        if player.cities >= cost:
            player.cities -= cost
            for _ in range(bonus_cards):
                new_card = get_random_skill()
                player.skills.append(new_card)
            result["effects"].append({
                "type": "trade",
                "cost": cost,
                "cards_gained": bonus_cards
            })
        else:
            result["effects"].append({
                "type": "message",
                "message": "城池不足，需要{}城池".format(cost)
            })

    elif skill_type_key == "damage_boost":
        # 加伤卡 - 攻击伤害永久+25%
        bonus = skill["effect"].get("permanent_attack_bonus", 0.25)
        player.status_effects["permanent_attack_bonus"] = player.status_effects.get("permanent_attack_bonus", 0) + bonus
        result["effects"].append({
            "type": "permanent_buff",
            "status": "permanent_attack_bonus",
            "value": bonus
        })

    elif skill_type_key == "double_gain":
        # 以逸待劳卡 - 获得收益时×2（永久标记）
        player.status_effects["double_gain"] = True
        result["effects"].append({
            "type": "permanent_buff",
            "status": "double_gain"
        })

    elif skill_type_key == "tribute":
        # 顺手牵羊卡 - 让对方给你一张技能卡
        if target_id:
            target = game_state.get_player(target_id)
            if target and target.skills:
                import random
                given = random.choice(target.skills)
                target.remove_skill(given.get('id', ''))
                player.skills.append(given)
                result["effects"].append({
                    "type": "demand_card",
                    "target": target_id
                })
            else:
                result["effects"].append({
                    "type": "message",
                    "message": "目标玩家没有可给的卡"
                })
        else:
            result["effects"].append({
                "type": "message",
                "message": "未指定目标玩家"
            })

    elif skill_type_key == "protagonist":
        # 主角光环卡 - 永久减伤20%
        reduction = skill["effect"].get("permanent_reduction", 0.2)
        player.status_effects["permanent_reduction"] = player.status_effects.get("permanent_reduction", 0) + reduction
        result["effects"].append({
            "type": "permanent_buff",
            "status": "permanent_reduction",
            "value": reduction
        })

    return result
