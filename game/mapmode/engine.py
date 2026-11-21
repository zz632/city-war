# -*- coding: utf-8 -*-
"""
地图模式引擎（一期核心循环）：选地出生 → 殖民 → 征兵 → 建造 → 行军 → 陆战
规则依据：/Users/sha/Downloads/city-war/地图模式规则.md（2026-11-07 修订版）

实时结算：服务器每秒 tick 一次（收入/兵耗/建造/农场人口/行军/战斗）。
战斗公式已定稿：防御减伤型（堡垒减伤 + 研究院增攻），按比例慢速损耗。
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
SPEED_SEA = 166                  # 海上行军 km/s（×2）
SEA_BATTLE_KM = 1000             # 海战触发距离
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
LAB_COMBAT_BONUS = [0.0, 0.25, 0.25, 0.5]                    # 研究院战斗力加成（P2 已定稿：有效兵力增攻）
LAB_INCOME_MULT = [1.0, 1.25, 1.25, 1.5]                     # 研究院收入加成

# 战斗公式（P1/P2/P3 已定稿）：防御减伤型——守方堡垒减少每秒损失，
# 研究院提升输出；慢速损耗，均势约 60 秒分胜负
BATTLE_K = 0.015             # 每秒损耗速率：双方兵力损失 = 对方有效兵力 × K

TICK_SECONDS = 1.0

# 国际主题色池 32 色（高对比度；不含蓝/白/青系——海洋与无主地专用）
THEME_COLORS = [
    '#d32f2f',  # 红
    '#b71c1c',  # 深红
    '#e64a19',  # 橙红
    '#d84315',  # 赭红
    '#f57c00',  # 橙
    '#ef6c00',  # 亮橙
    '#ff6f00',  # 琥珀
    '#f9a825',  # 金
    '#fbc02d',  # 黄
    '#cddc39',  # 青柠
    '#afb42b',  # 黄绿
    '#9e9d24',  # 苔绿
    '#827717',  # 橄榄
    '#558b2f',  # 叶绿
    '#388e3c',  # 绿
    '#2e7d32',  # 松绿
    '#1b5e20',  # 深绿
    '#00896b',  # 青绿
    '#00695c',  # 深青
    '#7b1fa2',  # 紫
    '#9c27b0',  # 藕紫
    '#4a148c',  # 深紫
    '#c2185b',  # 品红
    '#ad1457',  # 绯红
    '#e91e63',  # 玫红
    '#d81b60',  # 桃红
    '#880e4f',  # 深玫
    '#795548',  # 棕
    '#5d4037',  # 深棕
    '#4e342e',  # 咖啡
    '#455a64',  # 深灰
    '#212121',  # 黑
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
        self.elim_order = []    # 出局顺序（pid 列表，供终局结算）
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
        self._watch_memo = {}   # pid -> (gen, 视野集合) 缓存
        self.paused = False     # 投票暂停（S5）
        self.pause_votes = set()

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

    def remove_player(self, pid):
        """选地阶段移除玩家（转观战）"""
        with self.lock:
            if self.phase == 'picking':
                self.players.pop(pid, None)

    def set_color(self, pid, color):
        """选主题色（对局内同步；唯一性由房间层校验后调用）"""
        with self.lock:
            p = self.players.get(pid)
            if not p or self.phase != 'picking':
                return False, '无法设置颜色'
            p.color = color
            return True, ''

    def picks_view(self, pid=None):
        """选地保密视图（规则 2.1）：只返回本人选择 + 与本人相关的冲突地块，
        其他人的选择一律不泄露"""
        with self.lock:
            p = self.players.get(pid) if pid is not None else None
            my_pick = p.picked if p else None
            counts = {}
            for q in self.players.values():
                if q.picked is not None:
                    counts[q.picked] = counts.get(q.picked, 0) + 1
            conflicts = [i for i, c in counts.items() if c > 1 and i == my_pick] \
                if my_pick is not None else []
            return {'picks': {pid: my_pick} if pid is not None and my_pick is not None else {},
                    'colors': {q.pid: q.color for q in self.players.values()},
                    'names': {q.pid: q.name for q in self.players.values()},
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
                'public_mil': False,   # 军情默认雾（规则 8），按地开关
            }

    # ---------- 投票暂停（规则 10） ----------
    def vote_pause(self, pid):
        """投票暂停：存活玩家过半同意 → 全员暂停（tick 停止，操作冻结）"""
        with self.lock:
            if self.phase != 'playing':
                return False, '游戏未进行中'
            if self.paused:
                return False, '已处于暂停状态'
            if pid not in self.players:
                return False, '玩家不存在'
            total = sum(1 for p in self.players.values() if p.alive)
            self.pause_votes.add(pid)
            if len(self.pause_votes) > total // 2:
                self.paused = True
                self.pause_votes = set()
                return True, {'paused': True, 'msg': '投票通过，游戏已暂停'}
            return True, {'paused': False,
                          'msg': '暂停投票 %d/%d（需过半）' % (len(self.pause_votes), total)}

    def vote_resume(self, pid):
        """投票恢复：暂停中过半同意 → 继续"""
        with self.lock:
            if self.phase != 'playing' or not self.paused:
                return False, '游戏未处于暂停状态'
            if pid not in self.players:
                return False, '玩家不存在'
            total = sum(1 for p in self.players.values() if p.alive)
            self.pause_votes.add(pid)
            if len(self.pause_votes) > total // 2:
                self.paused = False
                self.pause_votes = set()
                return True, {'paused': False, 'msg': '投票通过，游戏继续'}
            return True, {'paused': True,
                          'msg': '恢复投票 %d/%d（需过半）' % (len(self.pause_votes), total)}

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
            if self.phase != 'playing' or self.paused:
                return False, '游戏未开始或已暂停'
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
                    'b': {}, 'queue': [], 'public_mil': False,
                }
            self.pending_regions.add(region_i)
            return True, ''

    # ---------- 征兵 ----------
    def recruit(self, pid, region_i, count):
        with self.lock:
            if self.phase != 'playing' or self.paused:
                return False, '游戏未开始或已暂停'
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
            if self.phase != 'playing' or self.paused:
                return False, '游戏未开始或已暂停'
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
            if self.phase != 'playing' or self.paused:
                return False, '游戏未开始或已暂停'
            r = self.regions.get(int(region_i))
            if not r or r['owner'] != pid:
                return False, '不是你的地块'
            if btype not in r['b']:
                return False, '该地没有此设施'
            del r['b'][btype]
            r['queue'] = [q for q in r['queue'] if q['type'] != btype]
            return True, ''

    # ---------- 解散军队（规则 4.3：不返还任何钱） ----------
    def disband(self, pid, region_i, count):
        with self.lock:
            if self.phase != 'playing' or self.paused:
                return False, '游戏未开始或已暂停'
            r = self.regions.get(int(region_i))
            if not r or r['garrison'] != pid:
                return False, '该地没有你的驻军'
            count = int(count)
            if count <= 0 or count > r['troops']:
                return False, '兵力数量无效'
            r['troops'] -= count
            self.pending_regions.add(int(region_i))
            return True, ''

    # ---------- 军情公开开关（规则 8：按地设置） ----------
    def set_mil(self, pid, region_i, public):
        with self.lock:
            if self.phase != 'playing' or self.paused:
                return False, '游戏未开始或已暂停'
            r = self.regions.get(int(region_i))
            if not r or r['owner'] != pid:
                return False, '不是你的地块'
            r['public_mil'] = bool(public)
            self.pending_regions.add(int(region_i))
            return True, ''

    # ---------- 调兵（按量拆分） ----------
    def send_troops(self, pid, from_i, to_i, count):
        with self.lock:
            if self.phase != 'playing' or self.paused:
                return False, '游戏未开始或已暂停'
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
            # 寻路：先陆路 BFS；不可达则跨海直航（出发地须有己方港口，公海任意通行）
            path = mdata.find_path(from_i, to_i)
            if path:
                legs = [{'mode': 'land', 'km': mdata.segment_km(path[k], path[k + 1])}
                        for k in range(len(path) - 1)]
            else:
                if not r['b'].get('port'):
                    return False, '无陆路可达，且出发地未建港口（跨海需先建港口）'
                path = [from_i, to_i]
                legs = [{'mode': 'sea', 'km': mdata.segment_km(from_i, to_i)}]
            r['troops'] -= count
            self.pending_regions.add(from_i)  # 兵力清零时归属显示需随增量更新
            dist = sum(l['km'] for l in legs)
            self.armies.append({
                'id': self.next_army_id, 'pid': pid, 'troops': count,
                'path': path, 'legs': legs, 'pos_km': 0.0, 'total_km': dist,
            })
            self.next_army_id += 1
            return True, ''

    # ---------- 每秒 tick ----------
    def tick(self, dt):
        """推进一秒结算，返回本 tick 有变更的广播增量"""
        with self.lock:
            if self.phase != 'playing' and self.phase != 'finished':
                return None
            if self.phase == 'finished' or self.paused:
                return None  # 暂停时 tick 冻结
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

            # 2) 行军（海陆分段速度：陆 83km/s，海 166km/s）
            arrived = []
            for a in self.armies:
                remain = dt
                while remain > 1e-9 and a['pos_km'] < a['total_km']:
                    speed = self._speed_at(a)
                    adv = speed * remain
                    if a['pos_km'] + adv >= a['total_km']:
                        a['pos_km'] = a['total_km']
                        remain = 0
                    else:
                        a['pos_km'] += adv
                        remain = 0
                if a['pos_km'] >= a['total_km']:
                    arrived.append(a)
            if arrived:
                for a in arrived:
                    self.armies.remove(a)
                    self._army_arrive(a, dirty_regions)

            # 2.5) 海战检测：海上两支敌军距离 < 1000km 自动开战
            self._detect_sea_battles(dirty_regions)

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
                    self.elim_order.append(pid)
                    dirty_players.add(pid)
            alive = [p for p in self.players.values() if p.alive]
            if len(alive) <= 1 and self.phase == 'playing':
                self.phase = 'finished'
                self.winner = alive[0].pid if alive else None
                dirty_players = set(self.players.keys())

            self._gen += 1
            return {'dirty_regions': dirty_regions, 'dirty_players': dirty_players}

    def finish_summary(self):
        """终局结算：胜者 + 出局顺序 + 存活者最终地块数"""
        def _land(pid):
            return sum(1 for r in self.regions.values() if r['owner'] == pid)
        def _nm(pid):
            p = self.players.get(pid)
            return p.name if p else '?'
        return {
            'winner': self.winner,
            'elim': [{'pid': pid, 'name': _nm(pid), 'land': _land(pid)}
                     for pid in self.elim_order],
            'alive': [{'pid': p.pid, 'name': p.name, 'land': _land(p.pid)}
                      for p in self.players.values() if p.alive],
        }

    # ---------- MongoDB 快照（S7：断线重连/重启恢复） ----------
    def to_snapshot(self):
        with self.lock:
            return {
                'room_id': self.room_id,
                'phase': self.phase,
                'elim_order': list(self.elim_order),
                'players': {pid: {'name': p.name, 'color': p.color, 'money': p.money,
                                  'alive': p.alive, 'picked': p.picked, 'ready': p.ready}
                            for pid, p in self.players.items()},
                'regions': {str(i): dict(r) for i, r in self.regions.items()},
                'armies': [dict(a) for a in self.armies],
                'battles': {str(k): dict(b) for k, b in self.battles.items()},
                'pending_regions': [str(i) for i in self.pending_regions],
                'next_army_id': self.next_army_id,
                'winner': self.winner,
                'started_at': self.started_at,
                'gen': self._gen,
                'paused': self.paused,
                'pause_votes': list(self.pause_votes),
            }

    @classmethod
    def from_snapshot(cls, snap):
        g = cls(snap['room_id'], {})
        g.phase = snap['phase']
        g.elim_order = list(snap.get('elim_order', []))
        for pid, pd in snap.get('players', {}).items():
            p = MapPlayer(pid, pd['name'], pd.get('color', ''))
            p.money = pd.get('money', 0)
            p.alive = pd.get('alive', True)
            p.picked = pd.get('picked')
            p.ready = pd.get('ready', False)
            g.players[pid] = p
        g.regions = {int(i): dict(r) for i, r in snap.get('regions', {}).items()}
        g.armies = [dict(a) for a in snap.get('armies', [])]
        # 战场 key：数字 → int（地块战），其余保留字符串（海战）
        g.battles = {}
        for k, b in snap.get('battles', {}).items():
            key = int(k) if str(k).isdigit() else str(k)
            g.battles[key] = dict(b)
        g.pending_regions = set(int(i) for i in snap.get('pending_regions', []))
        g.next_army_id = snap.get('next_army_id', 1)
        g.winner = snap.get('winner')
        g.started_at = snap.get('started_at')
        g._gen = snap.get('gen', 0)
        g.paused = bool(snap.get('paused'))
        g.pause_votes = set(snap.get('pause_votes', []))
        return g

    # ---------- 行军 / 海战辅助 ----------
    def _speed_at(self, a):
        """军队当前位置的行军速度（按所在段 land/sea）"""
        legs = a.get('legs') or []
        cum = 0.0
        for leg in legs:
            cum += leg['km']
            if a['pos_km'] < cum:
                return SPEED_SEA if leg['mode'] == 'sea' else SPEED_LAND
        return SPEED_LAND

    def _on_sea(self, a):
        """军队当前是否在海段"""
        legs = a.get('legs') or []
        cum = 0.0
        for leg in legs:
            cum += leg['km']
            if a['pos_km'] < cum:
                return leg['mode'] == 'sea'
        return False

    def _army_lonlat(self, a):
        """军队当前位置（沿质心路径插值），用于海战距离判定"""
        path = a['path']
        d = a['pos_km']
        for k in range(len(path) - 1):
            ra, rb = mdata.get(path[k]), mdata.get(path[k + 1])
            if not ra or not rb:
                continue
            seg = mdata.haversine_km(ra['lon'], ra['lat'], rb['lon'], rb['lat'])
            if d <= seg or k == len(path) - 2:
                t = min(1.0, d / seg) if seg > 0 else 1.0
                return (ra['lon'] + (rb['lon'] - ra['lon']) * t,
                        ra['lat'] + (rb['lat'] - ra['lat']) * t)
            d -= seg
        r = mdata.get(path[-1]) if path else None
        return (r['lon'], r['lat']) if r else (0.0, 0.0)

    def _detect_sea_battles(self, dirty_regions):
        """海战（规则 7.2）：海上两支敌军距离 < 1000km 自动开战"""
        n = len(self.armies)
        for ai in range(n):
            a = self.armies[ai]
            if not self._on_sea(a):
                continue
            for bi in range(ai + 1, n):
                b = self.armies[bi]
                if b['pid'] == a['pid'] or not self._on_sea(b):
                    continue
                lon1, lat1 = self._army_lonlat(a)
                lon2, lat2 = self._army_lonlat(b)
                if mdata.haversine_km(lon1, lat1, lon2, lat2) >= SEA_BATTLE_KM:
                    continue
                # 双方锁定到战场，从行军列表移除
                key = 'sea%d_%d' % (min(a['id'], b['id']), max(a['id'], b['id']))
                self.armies.remove(a)
                self.armies.remove(b)
                self.battles[key] = {
                    'atk_pid': a['pid'], 'atk_troops': a['troops'], 'atk_t0': a['troops'],
                    'def_pid': b['pid'], 'def_troops': b['troops'], 'def_t0': b['troops'],
                    'sea': True, 'lon': (lon1 + lon2) / 2, 'lat': (lat1 + lat2) / 2,
                    'atk_army': a, 'def_army': b,
                }
                return  # 本 tick 只触发一场，避免索引错乱

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
                'b': {}, 'queue': [], 'public_mil': False,
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
        """按比例损耗（P1/P3 已定稿：防御减伤型）：
        每秒损失 = max(对方当前有效兵力, 开战前对方兵力) × K ÷ (1 + 己方防御加成)
        有效兵力 = 兵力 × (1 + 研究院战斗力加成)
        开战前兵力×K 作为线性下限：保证均势约 1/K ≈ 67 秒分胜负，避免指数衰减僵局"""
        b = self.battles[i]
        atk, dfn = self.players.get(b['atk_pid']), self.players.get(b['def_pid'])
        r = self.regions.get(i, {})
        def_bonus = FORT_DEF_BONUS[r['b'].get('fort', 0) - 1] if r.get('b', {}).get('fort') else 0.0
        atk_pow = b['atk_troops'] * (1 + (self._combat_bonus(b['atk_pid']) if atk else 0))
        def_pow = b['def_troops'] * (1 + (self._combat_bonus(b['def_pid']) if dfn else 0))
        b['atk_troops'] = max(0.0, b['atk_troops'] - max(def_pow, b['def_t0']) * BATTLE_K * dt)
        b['def_troops'] = max(0.0, b['def_troops'] - max(atk_pow, b['atk_t0']) * BATTLE_K / (1 + def_bonus) * dt)

        if b['def_troops'] <= 0 or b['atk_troops'] <= 0:
            self._end_battle(i, b)

    def _end_battle(self, i, b):
        del self.battles[i]
        # ---- 海战：无占地奖励，胜者军队携残兵继续航行 ----
        if b.get('sea'):
            if b['atk_troops'] <= 0 and b['def_troops'] <= 0:
                return  # 两败俱伤
            winner_atk = b['def_troops'] <= 0
            wp = b['atk_pid'] if winner_atk else b['def_pid']
            lp = b['def_pid'] if winner_atk else b['atk_pid']
            loot = (b['def_t0'] if winner_atk else b['atk_t0']) * WAR_LOOT_PCT
            w = self.players.get(wp)
            if w:
                w.money += loot
            src = b['atk_army'] if winner_atk else b['def_army']
            remain = b['atk_troops'] if winner_atk else b['def_troops']
            if remain > 0:
                nav = dict(src)
                nav['troops'] = remain
                self.armies.append(nav)   # 胜者残兵继续原航程
            return
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

    # ---------- 视野迷雾（规则 8） ----------
    def _watch_radius(self, pid):
        """观察半径：默认 1 个地区，瞭望塔 L 级 → 半径 L+1"""
        r = 1
        for i in self._player_regions(pid):
            t = self.regions[i]['b'].get('tower', 0)
            if t:
                r = max(r, t + 1)
        return r

    def _watch_set(self, pid):
        """瞭望塔视野集合：从己方所有地块 BFS 跳数 ≤ 半径（按 gen 缓存）"""
        cached = self._watch_memo.get(pid)
        if cached and cached[0] == self._gen:
            return cached[1]
        regs = mdata.regions()
        radius = self._watch_radius(pid)
        seen = set(self._player_regions(pid))
        frontier = list(seen)
        for _ in range(radius):
            nxt = []
            for i in frontier:
                for nb in regs.get(i, {}).get('adj', []):
                    if nb not in seen:
                        seen.add(nb)
                        nxt.append(nb)
            frontier = nxt
        self._watch_memo[pid] = (self._gen, seen)
        return seen

    def _troops_visible(self, viewer, i, r, owner_x):
        """位于地块 i 的 owner_x 军队对 viewer 是否可见。
        规则：军情默认雾；瞭望塔半径内强制可见；堡垒区内守方军队强制隐藏（优先于瞭望塔）；
        地块主人可按地公开驻军情报（public_mil，只对驻军生效）"""
        if viewer is None or viewer == owner_x:
            return True
        rb = r.get('b', {})
        if rb.get('fort') and r.get('owner') == owner_x:
            return False
        if i in self._watch_set(viewer):
            return True
        if r.get('public_mil') and owner_x == r.get('owner'):
            return True
        return False

    def _army_region(self, a):
        """军队当前所在的区段起点地块"""
        legs = a.get('legs') or []
        cum = 0.0
        for k, leg in enumerate(legs):
            if a['pos_km'] < cum + leg['km']:
                return a['path'][k]
            cum += leg['km']
        return a['path'][-1] if a['path'] else None

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
                'paused': self.paused,
                'me': {'pid': pid,
                       'money': int(p.money) if p else 0,
                       'picked': p.picked if p else None},
                'colors': {q.pid: q.color for q in self.players.values()},
                'colonize_price': LAB_COLONIZE_PRICE[self._lab_level(pid)],
                'mine': mine,
                'armies': self._armies_view(pid),
                'battles': self._battles_view(pid),
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
                # 选地保密：只告知是否本人已选此地
                p = self.players.get(pid)
                info['my_pick'] = bool(p and p.picked == region_i)
                return info
            r = self.regions.get(region_i)
            if r is None:
                info['owner'] = None
                return info
            info['owner'] = r['owner']
            if pid == r['owner'] or pid == r['garrison']:
                info.update(self._region_view(region_i, r))   # 本人地块：全量
            else:
                # 他人地块：人口可见（地图全明），军情默认雾（规则 8）
                info['pop_approx'] = _fuzzy(r['pop'])
                if r['troops'] > 0 and self._troops_visible(pid, region_i, r, r['owner']):
                    info['troops_approx'] = _fuzzy(r['troops'])
                else:
                    info['mil_fog'] = True
                info['b_cnt'] = sum(1 for v in r['b'].values() if v)
            return info

    def tick_delta(self, dirty, viewer_pid=None):
        """每秒增量广播（per-player 视野过滤，viewer_pid=None 为全图）：归属变更 + 玩家资金/存活 + 战场"""
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
                'armies': self._armies_view(viewer_pid),
                'battles': self._battles_view(viewer_pid),
                'phase': self.phase,
                'paused': self.paused,
                'winner': self.winner,
            }

    def _armies_view(self, pid=None):
        """军队视图（视野迷雾）：本人的全可见；他人军队仅当其所在地区
        在观察视野内可见，堡垒区内强制隐藏；pid=None（观战者）全图可见"""
        out = []
        for a in self.armies:
            if pid is not None and a['pid'] != pid:
                i = self._army_region(a)
                r = self.regions.get(i, {})
                if not self._troops_visible(pid, i, r, a['pid']):
                    continue
            out.append({'id': a['id'], 'pid': a['pid'], 'troops': int(a['troops']),
                        'path': a['path'], 'legs': a.get('legs') or [],
                        'pos_km': int(a['pos_km']), 'total_km': int(a['total_km']),
                        'sea': self._on_sea(a)})
        return out

    def _battles_view(self, pid=None):
        """战场视图（视野迷雾）：涉及本人或位于视野内的陆战可见；
        他人海战一律不可见（公海无地块视野）；pid=None 全可见"""
        out = {}
        watch = self._watch_set(pid) if pid is not None else None
        for i, b in self.battles.items():
            if pid is None or pid in (b['atk_pid'], b['def_pid']):
                out[i] = self._battle_view(b)
            elif not b.get('sea'):
                try:
                    ii = int(i)
                except (TypeError, ValueError):
                    continue
                if ii in watch:
                    out[i] = self._battle_view(b)
        return out

    def _region_view(self, i, r):
        return {'owner': r['owner'], 'pop': int(r['pop']), 'troops': int(r['troops']),
                'garrison': r['garrison'], 'recruited': int(r['recruited']), 'b': dict(r['b']),
                'queue': [dict(q) for q in r['queue']], 'conquest': r['conquest'],
                'public_mil': r.get('public_mil', False)}

    def _battle_view(self, b):
        v = {'atk_pid': b['atk_pid'], 'atk_troops': int(b['atk_troops']),
             'def_pid': b['def_pid'], 'def_troops': int(b['def_troops'])}
        if b.get('sea'):
            v['sea'] = True
            v['lon'] = b['lon']
            v['lat'] = b['lat']
        return v
