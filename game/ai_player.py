"""
AI 玩家决策模块
通过 OpenAI 兼容 API 获取行动决策
"""
import json
import random
import time
import requests
from typing import Dict, Any, Optional, List
from .models import GamePhase
from .skills import SKILL_CARDS


# 游戏规则常量
GAME_RULES = """你是"城池战争"游戏的AI玩家。

## 游戏规则
回合制策略游戏，每回合所有玩家同时提交行动。起始城池250，城池<=0被淘汰，最后存活者获胜。

### 可选行动：
- attack + target_id: 攻击目标，目标-25城池，自己+25城池。目标守城则反弹(攻方-20/守方+20)。互攻则各自伤害-100最低0
- defend: 守城，被攻城时反弹：攻击方-20城池，守城方+20城池
- jungle: 打野，50%获得10城池，50%获得随机技能卡
- repair(第3轮起): 修城+30，被攻击则伤害×2且不增加城池
- alliance + target_id(第3轮起): 结盟，联盟人数≤总存活人数1/2，联盟期间奖励/伤害共享均分，联盟内不受伤害
- dissolve_alliance: 解除已有联盟
- duel + target_id + bet: 约战(轮盘赌)，赌注最小15最大min(双方)×60%，10发转轮1弹(前三枪空包)，可拒绝(交50%赌注贡奉)
- skip: 跳过本轮（当某种行动连续5次达到上限无法再选时可选）

### 数值翻倍
第8轮后所有数值翻倍(×2)，第16轮再翻倍(×4)，第24轮第三次翻倍(×8)。攻城/守城/打野/修城/约战赌注下限等均翻倍，百分比和特殊效果不翻倍。

### 技能卡(持有上限3张，行动阶段使用)：
攻击类: 火攻(30伤), 奇袭(20伤无视守城), 连弩(15伤×2), 破城(50伤自损10), 毒计(眩晕1轮), +5伤(每轮+5伤), 呆若木鸡(对方无法行动), 万箭齐发(对其他人15+3n伤), 猛攻(攻击×3), 吸血(吸取5%血), 加伤(攻击永久+25%)
防御类: 铁壁(伤害减半), 空城(反弹20), 援军(+25), 诈降(免疫+反弹15), 迁都(+15+不可选), 无懈可击(免除有害技能), 不死图腾(血<0时+50+3局减伤20%), 磐石堡垒(减伤10), 退退退(免疫+反弹50), 回血(每轮+5), 主角光环(永久减伤20%)
资源类: 屯田(3回合每回合+10), 商路(每人掠夺5), 征税(+20%), 募兵(+20下回合必须攻城), 丰收(+30跳过下回合), 撒豆成兵(-20城3轮后+80), 聚宝盆(收益永久×1.25), 等价交换(-75城获2卡), 以逸待劳(收益×2)
特殊类: 瞒天过海(-30城偷1卡), 二般人(行动两次), 升级(技能×2), 顺手牵羊(要1卡), 侦查(查看目标), 急救(城<0时+20), 逆转(交换城池差≤100+3轮不攻), 离间(解散所有联盟+3轮不能联盟)

### 其他规则
- 同种操作不可连续超过5次
- 拍卖: 第10轮起每5轮一次，随机技能卡拍卖
- 人先死亡则技能卡不生效(全场影响类仍生效)

## 返回格式
你必须返回JSON(不要任何其他文字)：
{"action": "attack|defend|jungle|repair|alliance|dissolve_alliance|duel|skip", "target_id": "player_id或null", "bet": 数字或0, "use_skill": true/false, "skill_name": "技能卡名称或null", "skill_target_id": "player_id或null"}

如果use_skill为true，你必须通过skill_name指定要使用哪张技能卡（必须是你持有的卡）。需要目标的技能卡还需指定skill_target_id。
"""


def build_ai_prompt(room, player_id: str) -> str:
    """构建 AI 决策 prompt"""
    player = room.players.get(player_id)
    if not player:
        return GAME_RULES

    gs = room.game_state
    round_num = gs.round if gs else 1
    is_late = round_num >= 3

    # 计算数值翻倍倍率
    if round_num >= 24:
        multiplier = 8
    elif round_num >= 16:
        multiplier = 4
    elif round_num >= 8:
        multiplier = 2
    else:
        multiplier = 1

    # 当前局面
    situation = f"\n## 当前局面\n回合: {round_num}\n数值翻倍倍率: ×{multiplier}\n你的ID: {player_id}\n你的城池: {player.cities}\n你的技能卡: "
    if player.skills:
        situation += ', '.join([f"【{s.get('name', '?')}】" for s in player.skills])
    else:
        situation += '无'

    situation += '\n\n所有玩家:\n'
    for pid, p in room.players.items():
        if p.is_spectator:
            continue
        status = '存活' if p.is_alive else '阵亡'
        mark = ' (你)' if pid == player_id else ''
        ai_mark = ' [AI]' if p.is_ai else ''
        situation += f"  - ID:{pid} 名字:{p.name}{ai_mark} 城池:{p.cities} 状态:{status}{mark}\n"

    # 可选行动
    available = ['attack', 'defend', 'jungle']
    if is_late:
        available.extend(['repair', 'alliance', 'duel'])
    if player.alliance_with:
        available.append('dissolve_alliance')
    available.append('skip')

    situation += f'\n你可选的行动: {", ".join(available)} (当前数值倍率: ×{multiplier})\n'

    # 当前联盟
    if player.alliance_with:
        partner = room.players.get(player.alliance_with)
        partner_name = partner.name if partner else player.alliance_with
        situation += f'当前联盟对象: {partner_name} (ID:{player.alliance_with})\n'

    # 可攻击目标
    alive_targets = [pid for pid, p in room.players.items() 
                     if p.is_alive and not p.is_spectator and pid != player_id
                     and pid != player.alliance_with]  # 联盟成员不可攻击
    if alive_targets:
        situation += f'可选目标ID: {", ".join(alive_targets)}\n'

    # 最近回合历史
    history = getattr(gs, 'round_history', [])
    if history:
        situation += '\n## 最近回合记录\n'
        for h in history:
            rnd = h.get('round', '?')
            situation += f'第{rnd}轮: '
            msgs = h.get('messages', [])
            if msgs:
                situation += '; '.join(msgs)
            changes = h.get('city_changes', {})
            if changes:
                change_strs = []
                for pid, delta in changes.items():
                    pname = room.players.get(pid, player).name if room else pid
                    sign = '+' if delta >= 0 else ''
                    change_strs.append(f'{pname}{sign}{delta}')
                situation += f' | 城池变化: {", ".join(change_strs)}'
            situation += '\n'

    return GAME_RULES + situation


def call_ai_api(prompt: str, config: Dict[str, str]) -> Dict[str, Any]:
    """调用 OpenAI 兼容 API，返回 {result, raw_content, error}"""
    base_url = config.get('base_url', 'https://api.openai.com/v1').rstrip('/')
    # 去掉用户可能多填的 /chat/completions 后缀
    if base_url.endswith('/chat/completions'):
        base_url = base_url[:-len('/chat/completions')]
    api_key = config.get('api_key', '')
    model = config.get('model', 'gpt-4o-mini')

    if not api_key:
        return {'result': None, 'raw_content': '', 'error': '未配置API Key'}

    url = f'{base_url}/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': '你是游戏AI，只返回JSON，不返回其他文字。'},
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.7,
        'max_tokens': 4096
    }

    # 429限流重试，最多重试3次，指数退避
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            print(f'[AI] API请求: url={url}, model={model}, attempt={attempt+1}')
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            
            # 429限流：等待后重试
            if resp.status_code == 429 and attempt < max_retries:
                retry_after = int(resp.headers.get('Retry-After', 2 * (attempt + 1)))
                print(f'[AI] 429限流, 等待{retry_after}秒后重试')
                time.sleep(retry_after)
                continue
            
            resp.raise_for_status()
            resp_json = resp.json()
            resp_str = json.dumps(resp_json, ensure_ascii=False)
            # 智谱等API可能content为None（拒绝回答等情况），混合思考模型content在reasoning_content后输出
            msg = resp_json.get('choices', [{}])[0].get('message', {})
            content = (msg.get('content') or '').strip()
            reasoning = (msg.get('reasoning_content') or '').strip()
            print(f'[AI] API响应: model={model}, content_len={len(content)}, reasoning_len={len(reasoning)}, content_preview={content[:200]}')
            if not content and reasoning:
                return {'result': None, 'raw_content': reasoning[:500], 'raw_response': resp_str[:500], 'error': f'模型思考完毕但输出为空(finish_reason=length)，max_tokens不够，请增大max_tokens'}
            if not content:
                return {'result': None, 'raw_content': '', 'raw_response': resp_str[:500], 'error': f'API返回空内容'}
            # 尝试从返回内容中提取JSON
            raw = content
            if content.startswith('```'):
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()
            parsed = json.loads(content)
            return {'result': parsed, 'raw_content': raw, 'raw_response': '', 'error': ''}
        except requests.exceptions.ConnectionError as e:
            err = f'连接失败: {url} - {str(e)[:200]}'
            print(f'[AI] {err}')
            return {'result': None, 'raw_content': '', 'raw_response': '', 'error': err}
        except requests.exceptions.Timeout as e:
            err = f'请求超时(30s): {url}'
            print(f'[AI] {err}')
            return {'result': None, 'raw_content': '', 'raw_response': '', 'error': err}
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            body = ''
            try:
                body = e.response.text[:500] if e.response else ''
            except Exception:
                pass
            if status == 0 and not body:
                err = f'请求失败(无响应): {url}, 原始异常: {str(e)[:200]}'
            else:
                err = f'HTTP {status}: {body[:200]}' if body else f'HTTP {status}'
            print(f'[AI] API调用失败: {err}')
            return {'result': None, 'raw_content': '', 'raw_response': body, 'error': err}
        except json.JSONDecodeError as e:
            print(f'[AI] JSON解析失败: {e}, 原始内容: {raw[:200]}')
            return {'result': None, 'raw_content': raw, 'raw_response': '', 'error': f'JSON解析失败: {str(e)}'}
        except Exception as e:
            err = f'{type(e).__name__}: {str(e)[:300]}'
            print(f'[AI] API调用失败: {err}')
            return {'result': None, 'raw_content': '', 'raw_response': '', 'error': err}
    
    # 重试耗尽
    return {'result': None, 'raw_content': '', 'raw_response': '', 'error': 'API限流(429)，重试多次仍失败'}


def get_random_action(room, player_id: str) -> Dict[str, Any]:
    """随机选择合法行动（fallback）"""
    gs = room.game_state
    round_num = gs.round if gs else 1
    is_late = round_num >= 3

    # 计算数值翻倍倍率
    if round_num >= 24:
        multiplier = 8
    elif round_num >= 16:
        multiplier = 4
    elif round_num >= 8:
        multiplier = 2
    else:
        multiplier = 1

    actions = ['attack', 'defend', 'jungle']
    if is_late:
        actions.extend(['repair', 'alliance', 'duel'])

    player = room.players.get(player_id)
    if player and player.alliance_with:
        actions.append('dissolve_alliance')

    action = random.choice(actions)
    result = {'action': action, 'target_id': None, 'bet': 0, 'use_skill': False, 'skill_name': None, 'skill_target_id': None}

    alive_targets = [pid for pid, p in room.players.items()
                     if p.is_alive and not p.is_spectator and pid != player_id
                     and pid != (player.alliance_with if player else None)]

    if action in ['attack', 'alliance'] and alive_targets:
        result['target_id'] = random.choice(alive_targets)
    elif action == 'duel' and alive_targets and player:
        target_id = random.choice(alive_targets)
        target = room.players.get(target_id)
        if target:
            result['target_id'] = target_id
            min_bet = 15 * multiplier
            max_bet = int(min(player.cities, target.cities) * 0.6)
            if max_bet >= min_bet:
                result['bet'] = random.randint(min_bet, max_bet)
            else:
                result['bet'] = min_bet

    if player and player.skills and random.random() < 0.3:
        result['use_skill'] = True
        chosen_skill = random.choice(player.skills)
        result['skill_name'] = chosen_skill.get('name')
        if alive_targets:
            result['skill_target_id'] = random.choice(alive_targets)

    return result


def ai_decide(room, player_id: str, config: Dict[str, str]) -> Dict[str, Any]:
    """AI 决策入口：尝试 LLM，失败则 fallback
    返回 dict 包含 action 等决策字段，以及可选的 _ai_error / _ai_raw / _ai_raw_response 字段
    """
    prompt = build_ai_prompt(room, player_id)
    api_result = call_ai_api(prompt, config)
    result = api_result.get('result')
    raw = api_result.get('raw_content', '')
    raw_resp = api_result.get('raw_response', '')
    error = api_result.get('error', '')

    if result and isinstance(result, dict) and 'action' in result:
        # 验证基本格式
        valid_actions = ['attack', 'defend', 'jungle', 'repair', 'alliance', 'dissolve_alliance', 'duel', 'skip']
        if result['action'] in valid_actions:
            return result

    # fallback + 附带错误信息供通知
    fallback = get_random_action(room, player_id)
    if error:
        fallback['_ai_error'] = error
    if raw:
        fallback['_ai_raw'] = raw[:500]
    if raw_resp:
        fallback['_ai_raw_response'] = raw_resp[:1000]
    return fallback
