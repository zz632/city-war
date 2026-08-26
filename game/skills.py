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
        "description": "濒死时自动询问是否使用：+50城池，之后3轮减伤20%且每轮+5城池（无需主动使用）",
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
        "description": "下一次攻城伤害×3（单次生效）",
        "effect": {"one_attack_multiplier": 3}
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
        "description": "自主选择一张持有的技能卡，其效果数值×2",
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
