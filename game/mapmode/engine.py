# -*- coding: utf-8 -*-
"""
地图模式引擎（一期核心循环）：选地出生 → 殖民 → 征兵 → 建造 → 行军 → 陆战
规则依据：/Users/sha/Downloads/city-war/地图模式规则.md（2026-11-07 修订版）

实时结算：服务器每秒 tick 一次（收入/兵耗/建造/农场人口/行军/战斗）。
战斗公式为占位实现（规则文档第 9 节待定项 P1/P2/P3，用户后续提供），
参数集中在下方常量区，调整无需动逻辑。
"""
import threading
import time

from . import data as mdata

# ================= 数值常量（全部来自规则文档） =================
START_MONEY_AREA = 5000          # 启动资金锚点面积
START_MONEY_BASE = 10000         # 锚点金额
START_MONEY_MIN = 500            # 保底
POP_PER_KM2 = 2                  # 初始/殖民附带人口
INCOME_DIVISOR = 600             # 收入 = 人口/600 元/秒
SPEED_LAND = 83                  # 行军 km/s
UPKEEP_SOLDIER = 1 / 300         # 兵耗 元/兵/秒
UPKEEP_SOLDIER_CAMP = 1 / 600    # 营地减半
MAX_RECRUIT_PCT = 0.2            # 单块地征兵上限 = 人口 × 20%
WAR_LOOT_PCT = 0.2               # 战利品 = 开战前对方军队 × 1/5

# 建筑（名称/各等级花费/建造秒数(已减半)/效果）
BUILDINGS = {
    'fort':    {'name': '堡垒',   'cost': [3000, 16000, 20000],        'time': [60, 90, 120],   'max': 3},
    'tower':   {'name': '瞭望塔', 'cost': [3000, 7000, 15000],         'time': [30, 60, 90],    'max': 3},
    'farm':    {'name': '农场',   'cost': [2000, 3000, 5000, 7500, 10000], 'time': [30, 60, 60, 90, 120], 'max': 5},
    'factory': {'name': '工厂',   'cost': [3000, 7500, 20000],         'time': [60, 90, 120],   'max': 3},
    'port':    {'name': '港口',   'cost': [5000],                      'time': [0],             'max': 1},
    'camp':    {'name': '营地',   'cost': [7500],                      'time': [0],             'max': 1},
    'lab':     {'name': '研究院', 'cost': [20000, 30000, 50000],       'time': [90, 120, 150],  'max': 3},
}
FARM_POP_PER_MIN = [2000, 2500, 3500, 4000, 5000]            # 农场每分钟加人口
FACTORY_INCOME_PER_MIN = [0.2, 0.4, 1.0]                     # 工厂人均收入（元/人/分钟）
FORT_DEF_BONUS = [0.5, 1.0, 2.0]                             # 堡垒防御加成
LAB_COLONIZE_PRICE = [1.0, 0.8, 0.4]                         # 殖民价 元/km²（按研究院最高等级）
LAB_COMBAT_BONUS = [0.0, 0.25, 0.25, 0.5]                    # 研究院战斗力加成（占位，见规则 P2）
LAB_INCOME_MULT = [1.0, 1.25, 1.25, 1.5]                     # 研究院收入加成（占位）

# 战斗占位参数（规则 P3：按比例损耗，公式待用户确认）
BATTLE_K = 0.03              # 每秒损耗速率：双方兵力损失 = 对方有效兵力 × K

TICK_SECONDS = 1.0

# 国际主题色池（高对比度；不含蓝色/白色——海洋与无主地专用）
THEME_COLORS = [
    '#d32f2f',  # 红
    '#f57c00',  # 橙
    '#fbc02d',  # 黄
    '#388e3c',  # 绿
    '#00896b',  # 青绿
    '#7b1fa2',  # 紫
    '#c2185b',  # 品红
    '#e91e63',  # 玫红
    '#795548',  # 棕
    '#455a64',  # 深灰
    '#212121',  # 黑
    '#827717',  # 橄榄
]


def _fuzzy(v):
    """基础情报模糊化：千位以上取整到千，百位取整到十"""
    if v <= 0:
        return 0
    if v < 1000:
        return int(round(v, -1))
    return int(round(v, -3))


class MapPlayer:
    def __init__(self, pid, name, color):
        self.pid = pid
        self.name = name
        self.color = color
        self.money = 0.0
        self.alive = True
        self.picked = None    # 选地阶段已选地块 i（保密，广播只给本人）
        self.ready = False

    def to_public(self):
        return {'pid': self.pid, 'name': self.name, 'color': self.color,
                'money': int(self.money), 'alive': self.alive}


class MapGame:
    """一局地图模式对局（属于一个房间）"""

    def __init__(self, room_id, players):
        """players: {pid: {'name':..., 'color':...}}（非观战者）"""
        self.room_id = room_id
        self.phase = 'picking'  # picking → playing → finished
        self.players = {pid: MapPlayer(pid, p['name'], p['color'])
                        for pid, p in players.items()}
        self.regions = {}       # i -> RegionState（仅被占/有驻军的地块）
        self.armies = []        # 行军中的军队
        self.battles = {}       # i -> battle dict
        self.pending_regions = set()  # tick 外的直接操作（殖民/出兵）待广播的地块
        self.next_army_id = 1
        self.lock = threading.RLock()
        self.winner = None
        self.started_at = None
        self._gen = 0           # 状态版本号（增量广播）

    # ---------- 选地 ----------
    def pick(self, pid, region_i):
        """选地（允许重复：房主开局时统一判定冲突）"""
        with self.lock:
            if self.phase != 'picking':
                return False, '已过选地阶段'
            p = self.players.get(pid)
            if not p or not p.alive:
                return False, '玩家不存在'
            if not mdata.exists(region_i):
                return False, '地块不存在'
            p.picked = int(region_i)
            return True, ''

    def add_player(self, pid, name, color=''):
        """选地阶段加入玩家（进房间后 mm_join 时懒注册）"""
        with self.lock:
            if pid in self.players or self.phase != 'picking':
                return
            self.players[pid] = MapPlayer(pid, name, color)

    def set_color(self, pid, color):
        """选主题色（对局内同步；唯一性由房间层校验后调用）"""
        with self.lock:
            p = self.players.get(pid)
            if not p or self.phase != 'picking':
                return False, '无法设置颜色'
            p.color = color
            return True, ''

    def picks_view(self):
        """选地公开视图：谁选了哪块 + 颜色 + 冲突地块"""
        with self.lock:
            picks = {pid: p.picked for pid, p in self.players.items() if p.picked is not None}
            counts = {}
            for i in picks.values():
                counts[i] = counts.get(i, 0) + 1
            conflicts = [i for i, c in counts.items() if c > 1]
            return {'picks': picks,
                    'colors': {pid: p.color for pid, p in self.players.items()},
                    'names': {pid: p.name for pid, p in self.players.items()},
                    'conflicts': conflicts}

    def try_start(self, active_pids):
        """房主点击开始：校验选地完整性。返回 (ok, result)
        失败时 result: {'error': msg} 或 {'conflicts': {i: [pid...]}}"""
        with self.lock:
            if self.phase != 'picking':
                return True, {}
            # 剔除已离开房间的玩家
            for pid in list(self.players.keys()):
                if pid not in active_pids:
                    del self.players[pid]
            alive = list(self.players.values())
            if len(alive) < 2:
                return False, {'error': '至少需要2名玩家'}
            missing = [p.name for p in alive if p.picked is None]
            if missing:
                return False, {'error': '还有玩家未选地：' + '、'.join(missing[:5])}
            counts = {}
            for p in alive:
                counts.setdefault(p.picked, []).append(p.pid)
            conflicts = {i: pids for i, pids in counts.items() if len(pids) > 1}
            if conflicts:
                return False, {'conflicts': conflicts}
            self._start_playing()
            return True, {}

    def _start_playing(self):
        """全部选完 → 初始化出生地与资源"""
        self.phase = 'playing'
        self.started_at = time.time()
        for p in self.players.values():
            meta = mdata.get(p.picked)
            area = meta['a']
            p.money = max(START_MONEY_MIN,
                          START_MONEY_BASE * (START_MONEY_AREA / max(area, 1)) ** 0.5)
            self.regions[p.picked] = {
                'owner': p.pid, 'pop': area * POP_PER_KM2, 'troops': 0,
                'garrison': p.pid, 'conquest': False, 'recruited': 0.0,
                'b': {},        # 建筑: type -> level (port/camp 为 1)
                'queue': [],    # 建造队列 [{type,lvl,left}]
                'public_mil': True,
            }

    # ---------- 内部工具 ----------
    def _player_regions(self, pid):
        return [i for i, r in self.regions.items() if r['owner'] == pid]

    def _lab_level(self, pid):
        lvl = 0
        for i in self._player_regions(pid):
            lvl = max(lvl, self.regions[i]['b'].get('lab', 0))
        return lvl

    def _colonize_price(self, pid, area):
        return area * LAB_COLONIZE_PRICE[self._lab_level(pid)]

    def _income_mult(self, pid):
        return LAB_INCOME_MULT[self._lab_level(pid)]

    def _combat_bonus(self, pid):
        return LAB_COMBAT_BONUS[self._lab_level(pid)]

    # ---------- 殖民 ----------
    def colonize(self, pid, region_i):
        with self.lock:
            if self.phase != 'playing':
                return False, '游戏未开始'
            p = self.players.get(pid)
            if not p or not p.alive:
                return False, '玩家不存在'
            region_i = int(region_i)
            r = self.regions.get(region_i)
            meta = mdata.get(region_i)
            if not meta:
                return False, '地块不存在'
            if r and r['owner'] is not None:
                return False, '该地块已被占领'
            # 范围：相邻或军队到达（有己方驻军）
            has_garrison = r and r['garrison'] == pid and r['troops'] > 0
            near = any(mdata.adjacent(own, region_i) for own in self._player_regions(pid))
            if not near and not has_garrison:
                return False, '只能殖民相邻或军队已到达的无人土地'
            price = self._colonize_price(pid, meta['a'])
            if p.money < price:
                return False, '资金不足（需 %d 元）' % int(price)
            p.money -= price
            if r:
                r['owner'] = pid
                r['conquest'] = False
            else:
                self.regions[region_i] = {
                    'owner': pid, 'pop': meta['a'] * POP_PER_KM2, 'troops': 0,
                    'garrison': pid, 'conquest': False, 'recruited': 0.0,
                    'b': {}, 'queue': [], 'public_mil': True,
                }
            self.pending_regions.add(region_i)
            return True, ''

    # ---------- 征兵 ----------
    def recruit(self, pid, region_i, count):
        with self.lock:
            if self.phase != 'playing':
                return False, '游戏未开始'
            p = self.players.get(pid)
            if not p or not p.alive:
                return False, '玩家不存在'
            r = self.regions.get(int(region_i))
            if not r or r['owner'] != pid:
                return False, '不是你的地块'
            if r['conquest']:
                return False, '攻占得来的地块不能征兵'
            count = int(count)
            if count <= 0:
                return False, '数量无效'
            cap = max(0, r['pop'] * MAX_RECRUIT_PCT - r['recruited'])
            if count > cap:
                return False, '超过征兵上限（该地人口的20%%，还可征 %d 人）' % int(cap)
            if p.money < count:
                return False, '资金不足（需 %d 元）' % count
            p.money -= count
            r['pop'] -= count
            r['recruited'] += count
            r['troops'] += count
            return True, ''

    # ---------- 建造 / 升级 ----------
    def build(self, pid, region_i, btype):
        with self.lock:
            if self.phase != 'playing':
                return False, '游戏未开始'
            p = self.players.get(pid)
            if not p or not p.alive:
                return False, '玩家不存在'
            spec = BUILDINGS.get(btype)
            if not spec:
                return False, '未知设施'
            r = self.regions.get(int(region_i))
            if not r or r['owner'] != pid:
                return False, '不是你的地块'
            cur = r['b'].get(btype, 0)
            if cur >= spec['max']:
                return False, '该设施已满级'
            nxt = cur + 1
            cost = spec['cost'][nxt - 1]
            if p.money < cost:
                return False, '资金不足（需 %d 元）' % cost
            if any(q['type'] == btype for q in r['queue']):
                return False, '该设施正在建造中'
            p.money -= cost
            r['queue'].append({'type': btype, 'lvl': nxt, 'left': spec['time'][cur]})
            return True, ''

    def demolish(self, pid, region_i, btype):
        """拆除（不返钱）"""
        with self.lock:
            r = self.regions.get(int(region_i))
            if not r or r['owner'] != pid:
                return False, '不是你的地块'
            if btype not in r['b']:
                return False, '该地没有此设施'
            del r['b'][btype]
            r['queue'] = [q for q in r['queue'] if q['type'] != btype]
            return True, ''

    # ---------- 调兵（按量拆分） ----------
    def send_troops(self, pid, from_i, to_i, count):
        with self.lock:
            if self.phase != 'playing':
                return False, '游戏未开始'
            from_i, to_i = int(from_i), int(to_i)
            if from_i == to_i:
                return False, '出发地与目的地相同'
            r = self.regions.get(from_i)
            if not r or r['garrison'] != pid or r['troops'] <= 0:
                return False, '该地没有你的驻军'
            count = int(count)
            if count <= 0 or count > r['troops']:
                return False, '兵力数量无效'
            if not mdata.exists(to_i):
                return False, '目的地不存在'
            path = mdata.find_path(from_i, to_i)
            if not path:
                return False, '无陆路可达（跨海需港口，尚未实装）'
            r['troops'] -= count
            self.pending_regions.add(from_i)  # 兵力清零时归属显示需随增量更新
            dist = sum(mdata.segment_km(path[k], path[k + 1]) for k in range(len(path) - 1))
            self.armies.append({
                'id': self.next_army_id, 'pid': pid, 'troops': count,
                'path': path, 'pos_km': 0.0, 'total_km': dist,
            })
            self.next_army_id += 1
            return True, ''

    # ---------- 每秒 tick ----------
    def tick(self, dt):
        """推进一秒结算，返回本 tick 有变更的广播增量"""
        with self.lock:
            if self.phase != 'playing' and self.phase != 'finished':
                return None
            if self.phase == 'finished':
                return None
            dirty_regions = set()
            dirty_players = set()
            # 收拢 tick 外直接操作（殖民/出兵）标记的地块，随本秒增量广播
            if self.pending_regions:
                dirty_regions |= self.pending_regions
                self.pending_regions = set()

            # 1) 收入 + 农场人口 + 兵耗 + 建造进度
            for i, r in self.regions.items():
                owner = self.players.get(r['owner'])
                if not owner or not owner.alive:
                    continue
                # 收入：人口/600 × 工厂倍率 × 研究院倍率
                fac = FACTORY_INCOME_PER_MIN[r['b'].get('factory', 0) - 1] if r['b'].get('factory') else 0.1
                owner.money += r['pop'] / INCOME_DIVISOR * (fac / 0.1) * self._income_mult(r['owner']) * dt
                # 农场：每分钟持续加人口
                farm = r['b'].get('farm', 0)
                if farm:
                    r['pop'] += FARM_POP_PER_MIN[farm - 1] / 60.0 * dt
                    dirty_regions.add(i)
                # 兵耗（营地减半）
                if r['troops'] > 0:
                    rate = UPKEEP_SOLDIER_CAMP if r['b'].get('camp') else UPKEEP_SOLDIER
                    owner.money -= r['troops'] * rate * dt
                    if owner.money < 0:
                        owner.money = 0  # 资金不透支（逃兵机制暂未实装）
                # 建造进度
                for q in r['queue']:
                    q['left'] -= dt
                    if q['left'] <= 0:
                        r['b'][q['type']] = q['lvl']
                        dirty_regions.add(i)
                if r['queue']:
                    r['queue'] = [q for q in r['queue'] if q['left'] > 0]
                    dirty_regions.add(i)
                dirty_players.add(r['owner'])

            # 2) 行军
            arrived = []
            for a in self.armies:
                step = SPEED_LAND * dt
                a['pos_km'] += step
                if a['pos_km'] >= a['total_km']:
                    arrived.append(a)
            if arrived:
                for a in arrived:
                    self.armies.remove(a)
                    self._army_arrive(a, dirty_regions)

            # 3) 战斗结算
            for i in list(self.battles.keys()):
                self._resolve_battle_tick(i, dt)
                dirty_regions.add(i)

            # 4) 出局与胜负
            for pid, p in list(self.players.items()):
                if p.alive and p.picked is not None and not any(
                        r['owner'] == pid for r in self.regions.values()) \
                        and not any(a['pid'] == pid for a in self.armies) \
                        and not any(b['atk_pid'] == pid for b in self.battles.values()):
                    p.alive = False
                    dirty_players.add(pid)
            alive = [p for p in self.players.values() if p.alive]
            if len(alive) <= 1 and self.phase == 'playing':
                self.phase = 'finished'
                self.winner = alive[0].pid if alive else None
                dirty_players = set(self.players.keys())

            self._gen += 1
            return {'dirty_regions': dirty_regions, 'dirty_players': dirty_players}

    def _army_arrive(self, army, dirty_regions):
        """军队抵达目的地：
        - 无人且无驻军 → 驻扎
        - 己方地 → 并入驻军
        - 无主地有他人驻军 / 敌方占领地 → 开战"""
        i = army['path'][-1]
        dirty_regions.add(i)
        r = self.regions.get(i)
        if r is None:
            meta = mdata.get(i)
            r = self.regions[i] = {
                'owner': None, 'pop': meta['a'] * POP_PER_KM2, 'troops': 0,
                'garrison': army['pid'], 'conquest': False, 'recruited': 0.0,
                'b': {}, 'queue': [], 'public_mil': True,
            }
            r['troops'] += army['troops']
            return
        if r['owner'] is None:
            if r['troops'] > 0 and r['garrison'] != army['pid']:
                self._start_battle(i, army)   # 无主地相遇：与驻军开战
            else:
                r['garrison'] = army['pid']
                r['troops'] += army['troops']
            return
        if r['owner'] == army['pid']:
            r['troops'] += army['troops']
            return
        self._start_battle(i, army)

    def _start_battle(self, i, army):
        b = self.battles.get(i)
        if b:
            # 已有战场：并入进攻方（第三方抵达他人的战场时暂时也算进攻方，简化）
            if b['atk_pid'] != army['pid']:
                b['atk_pid'] = b['atk_pid']
            b['atk_troops'] += army['troops']
            b['atk_t0'] += army['troops']
            return
        r = self.regions[i]
        self.battles[i] = {
            'atk_pid': army['pid'], 'atk_troops': army['troops'],
            'atk_t0': army['troops'], 'def_pid': r['garrison'], 'def_troops': r['troops'],
            'def_t0': r['troops'],
        }
        # 守军离开驻军状态，锁定在战斗中
        r['troops'] = 0

    def _resolve_battle_tick(self, i, dt):
        """按比例损耗（占位公式，见规则 P1/P3）：
        每秒双方损失 = 对方有效兵力 × K ÷ (1 + 己方防御加成)
        有效兵力 = 兵力 × (1 + 研究院战斗力加成)（P2 占位）"""
        b = self.battles[i]
        atk, dfn = self.players.get(b['atk_pid']), self.players.get(b['def_pid'])
        r = self.regions.get(i, {})
        def_bonus = FORT_DEF_BONUS[r['b'].get('fort', 0) - 1] if r.get('b', {}).get('fort') else 0.0
        atk_pow = b['atk_troops'] * (1 + (self._combat_bonus(b['atk_pid']) if atk else 0))
        def_pow = b['def_troops'] * (1 + (self._combat_bonus(b['def_pid']) if dfn else 0))
        b['atk_troops'] = max(0.0, b['atk_troops'] - def_pow * BATTLE_K * dt)
        b['def_troops'] = max(0.0, b['def_troops'] - atk_pow * BATTLE_K / (1 + def_bonus) * dt)

        if b['def_troops'] <= 0 or b['atk_troops'] <= 0:
            self._end_battle(i, b)

    def _end_battle(self, i, b):
        del self.battles[i]
        r = self.regions.get(i)
        if not r:
            return
        # 战利品：开战前对方军队 × 1/5
        if b['atk_troops'] <= 0 and b['def_troops'] <= 0:
            winner = None
        elif b['def_troops'] <= 0:
            winner = 'atk'
        else:
            winner = 'def'
        wp = b['atk_pid'] if winner == 'atk' else (b['def_pid'] if winner == 'def' else None)
        lp = b['def_pid'] if winner == 'atk' else (b['atk_pid'] if winner == 'def' else None)
        if wp and lp:
            loot = (b['def_t0'] if winner == 'atk' else b['atk_t0']) * WAR_LOOT_PCT
            w = self.players.get(wp)
            if w:
                w.money += loot
        if winner == 'atk':
            if r['owner'] is None:
                # 无主地战斗胜利：只获驻军权，不占领
                r['garrison'] = wp
                r['troops'] = b['atk_troops']
            else:
                # 进攻方继承地块（保留设施与人口），攻占得来不能征兵
                r['owner'] = wp
                r['garrison'] = wp
                r['troops'] = b['atk_troops']
                r['conquest'] = True
                r['recruited'] = 0.0
        elif winner == 'def':
            # 守方守住：地块归属不变
            r['troops'] = b['def_troops']
        else:
            # 两败俱伤
            r['troops'] = 0
            if r['owner'] is None:
                del self.regions[i]

    # ---------- 视图 ----------
    def my_state(self, pid):
        """发给玩家的个人完整视图（join / 每 10 秒兜底快照）"""
        with self.lock:
            p = self.players.get(pid)
            mine = {}
            for i, r in self.regions.items():
                if r['owner'] == pid or r['garrison'] == pid:
                    mine[i] = self._region_view(i, r)
            return {
                'phase': self.phase,
                'winner': self.winner,
                'me': {'pid': pid,
                       'money': int(p.money) if p else 0,
                       'picked': p.picked if p else None},
                'colors': {q.pid: q.color for q in self.players.values()},
                'colonize_price': LAB_COLONIZE_PRICE[self._lab_level(pid)],
                'mine': mine,
                'armies': self._armies_view(pid),
                'battles': {i: self._battle_view(b) for i, b in self.battles.items()},
            }

    def world_snapshot(self, pid):
        """全量归属快照（客户端 join 时建立底图）：i -> [owner_pid, 驻军归属可见性]"""
        with self.lock:
            out = {}
            for i, r in self.regions.items():
                if r['owner'] is not None:
                    out[i] = [r['owner']]
                elif r['troops'] > 0:
                    out[i] = [None, r['garrison']]
            return out

    def region_info(self, region_i, pid):
        """地块悬停情报：选地阶段=选择者列表；游戏中=他人模糊情报/本人全量"""
        with self.lock:
            region_i = int(region_i)
            meta = mdata.get(region_i)
            if not meta:
                return None
            info = {'i': region_i, 'n': meta['n'], 'a': meta['a'], 'phase': self.phase}
            if self.phase == 'picking':
                info['picks'] = [{'pid': q.pid, 'name': q.name, 'color': q.color}
                                 for q in self.players.values() if q.picked == region_i]
                return info
            r = self.regions.get(region_i)
            if r is None:
                info['owner'] = None
                return info
            info['owner'] = r['owner']
            if pid == r['owner'] or pid == r['garrison']:
                info.update(self._region_view(region_i, r))   # 本人地块：全量
            else:
                # 他人地块：基础情报（模糊数值）
                info['pop_approx'] = _fuzzy(r['pop'])
                info['troops_approx'] = _fuzzy(r['troops']) if r['troops'] > 0 else 0
                info['b_cnt'] = sum(1 for v in r['b'].values() if v)
            return info

    def tick_delta(self, dirty):
        """每秒增量广播（发给全房间）：归属变更 + 玩家资金/存活 + 战场"""
        with self.lock:
            owners = {}
            for i in dirty['dirty_regions']:
                r = self.regions.get(i)
                if not r:
                    owners[i] = None
                elif r['owner'] is not None:
                    owners[i] = [r['owner']]
                elif r['troops'] > 0:
                    owners[i] = [None, r['garrison']]
                else:
                    owners[i] = None
            if not owners and self.phase != 'finished' \
                    and not any(not p.alive for p in self.players.values()):
                return None
            return {
                'gen': self._gen,
                'owners': owners,
                'players': {pid: p.to_public() for pid, p in self.players.items()},
                'armies': self._armies_view(),
                'battles': {i: self._battle_view(b) for i, b in self.battles.items()},
                'phase': self.phase,
                'winner': self.winner,
            }

    def _armies_view(self, pid=None):
        """军队视图：本人的全可见；他人在一期全部可见（视野迷雾二期）"""
        return [{'id': a['id'], 'pid': a['pid'], 'troops': int(a['troops']),
                 'path': a['path'], 'pos_km': int(a['pos_km']), 'total_km': int(a['total_km'])}
                for a in self.armies]

    def _region_view(self, i, r):
        return {'owner': r['owner'], 'pop': int(r['pop']), 'troops': int(r['troops']),
                'garrison': r['garrison'], 'recruited': int(r['recruited']), 'b': dict(r['b']),
                'queue': [dict(q) for q in r['queue']], 'conquest': r['conquest']}

    def _battle_view(self, b):
        return {'atk_pid': b['atk_pid'], 'atk_troops': int(b['atk_troops']),
                'def_pid': b['def_pid'], 'def_troops': int(b['def_troops'])}
