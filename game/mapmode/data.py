# -*- coding: utf-8 -*-
"""
地图模式数据加载：地块元数据（面积/质心/邻接）
regions.json 由 tools/build_regions.py 从 map_world.bin 生成（随仓库提交）
"""
import json
import math
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_REGIONS_FILE = os.path.join(_HERE, 'regions.json')

_regions = None  # {int i: dict}


def _load():
    global _regions
    if _regions is None:
        with open(_REGIONS_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        _regions = {int(k): v for k, v in raw.items()}
    return _regions


def regions():
    """全部地块元数据 {i: {c:国名, n:显示名, g:国家键, a:面积, lon, lat, adj:[...]}}"""
    return _load()


def get(i):
    return _load().get(int(i))


def exists(i):
    return int(i) in _load()


def adjacent(a, b):
    r = _load().get(int(b))
    return r is not None and int(a) in r['adj']


def haversine_km(lon1, lat1, lon2, lat2):
    """两质心球面距离（千米）"""
    p = math.pi / 180
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlon / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def segment_km(a, b):
    ra, rb = _load().get(int(a)), _load().get(int(b))
    return haversine_km(ra['lon'], ra['lat'], rb['lon'], rb['lat'])


def find_path(start, goal):
    """BFS 陆路寻路（跨海需港口，二期实装），返回地块序列或 None"""
    regs = _load()
    if int(start) not in regs or int(goal) not in regs:
        return None
    start, goal = int(start), int(goal)
    if start == goal:
        return [start]
    prev = {start: None}
    queue = [start]
    qi = 0
    while qi < len(queue):
        cur = queue[qi]
        qi += 1
        for nb in regs[cur]['adj']:
            if nb in prev:
                continue
            prev[nb] = cur
            if nb == goal:
                path = [goal]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                return path[::-1]
            queue.append(nb)
    return None
