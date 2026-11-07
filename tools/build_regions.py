#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地图模式 · 地块元数据构建脚本（一次性工具，产物提交进仓库）

解析 static/map/map_world.bin（与 /map 渲染器同一份二进制数据）。
数据中 3337 个多边形按国家分组（键 g），每个多边形近似一个一级行政区
（如中国的 33 块≈各省），但没有省级名称——因此游戏单位 = 单个多边形
（feature 索引 i），显示名为「国名·序号」。

产物 game/mapmode/regions.json，每块地：
  i -> {c:国名, g:国家键, a:面积km², lon:质心经度, lat:质心纬度, adj:[邻接地块i...]}

邻接判定：精版几何顶点落入 3px 网格，同一网格(含 8 邻域)出现不同地块的
顶点即视为相邻（共享边界顶点几乎重合；3px ≈ 赤道 30km，海峡/岛屿间亦
视为可达，与玩法相容）。

用法：python3 tools/build_regions.py
"""
import gzip
import json
import math
import os
import struct
import time
from array import array

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PARTS = [os.path.join(ROOT, 'static', 'map', 'map_world.bin.part%d' % i) for i in range(8)]
OUT = os.path.join(ROOT, 'game', 'mapmode', 'regions.json')

CELL = 3.0  # 邻接判定网格（像素）
W = 4096
PPR = W / (2 * math.pi)


def main():
    t0 = time.time()
    raw = b''.join(open(p, 'rb').read() for p in SRC_PARTS if os.path.exists(p))
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    jl = struct.unpack_from('<I', raw, 8)[0]
    meta = json.loads(raw[12:12 + jl].decode('utf-8'))
    nf, npts = meta['nf'], meta['npts']
    off = 12 + jl
    while off % 4:
        off += 1
    box = array('f')
    box.frombytes(raw[off:off + nf * 16]); off += nf * 16
    fr = array('i')
    fr.frombytes(raw[off:off + (nf + 1) * 4]); off += (nf + 1) * 4
    roff = array('i')
    roff.frombytes(raw[off:off + (meta['nring'] + 1) * 4]); off += (meta['nring'] + 1) * 4
    coords = array('f')
    coords.frombytes(raw[off:off + npts * 8])
    print('解析完成: nf=%d npts=%d (%.1fs)' % (nf, npts, time.time() - t0))

    def px_to_lonlat(x, y):
        lon = x / (PPR * math.pi / 180) - 180
        ym = math.log(math.tan(math.pi / 4 + (85 * math.pi / 180) / 2)) - y / PPR
        lat = (2 * math.atan(math.exp(ym)) - math.pi / 2) * 180 / math.pi
        return round(lon, 3), round(lat, 3)

    # ---- 每块地的国名 / 面积 / 质心（南极洲已从游戏剔除） ----
    # 注意：跳过南极洲后列表序号 ≠ 数据要素索引，键必须保留原始 feature 索引 i
    regions = []
    for i, p in enumerate(meta['meta']):
        if p.get('gn') == '南极洲':
            continue
        regions.append({'i': i})  # 占位，循环末替换
        cx = (box[i * 4] + box[i * 4 + 2]) / 2
        cy = (box[i * 4 + 1] + box[i * 4 + 3]) / 2
        # bbox 跨 180° 经线时（如斐济/楚科奇），中心可能落在空档处；
        # 用环坐标均值兜底修正（仅对 bbox 宽 > 半球的要素）
        w = box[i * 4 + 2] - box[i * 4]
        if w > W / 2:
            s = roff[fr[i]] * 2
            t = roff[fr[i + 1] - 1] * 2 if fr[i + 1] - 1 < len(roff) else len(coords) - 2
            xs = [coords[a] for a in range(s, t, 2)]
            # 平移到正半轴求均值再归一
            xs2 = [(x + W / 2 if x < W / 2 else x - W / 2) for x in xs]
            cx = (sum(xs2) / len(xs2) + W / 2) % W
        lon, lat = px_to_lonlat(cx, cy)
        regions[-1] = {
            'i': i,                          # 原始要素索引（客户端 pick 返回的键）
            'c': p.get('gn', '?'),          # country 国家名
            'g': p['g'],                     # 国家键（渲染器 GM 高亮用）
            'a': round(p.get('area') or 0),  # area km²
            'lon': lon,
            'lat': lat,
        }
    # 国名+序号（同国多块时编号）
    counters = {}
    for r in regions:
        n = counters.get(r['g'], 0) + 1
        counters[r['g']] = n
        r['idx'] = n

    # ---- 邻接：顶点 3px 网格哈希（跳过南极洲） ----
    grid = {}
    for i in range(nf):
        if meta['meta'][i].get('gn') == '南极洲':
            continue
        for rr in range(fr[i], fr[i + 1]):
            s = roff[rr] * 2
            t = roff[rr + 1] * 2
            prev = None
            for a in range(s, t, 2):
                x = coords[a]
                y = coords[a + 1]
                key = (int(x // CELL), int(y // CELL))
                if key == prev:
                    continue
                prev = key
                arr = grid.get(key)
                if arr is None:
                    grid[key] = [i]
                elif arr[-1] != i:
                    arr.append(i)
    print('顶点网格构建完成: %d 格 (%.1fs)' % (len(grid), time.time() - t0))

    adj = [set() for _ in range(nf)]
    for (gx, gy), arr in grid.items():
        near = set(arr)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                other = grid.get((gx + dx, gy + dy))
                if other:
                    near.update(other)
        if len(near) < 2:
            continue
        nl = list(near)
        for a in range(len(nl)):
            for b in range(a + 1, len(nl)):
                adj[nl[a]].add(nl[b])
                adj[nl[b]].add(nl[a])
    # 经度环绕：x 最左与最右格相邻
    xmax = int(W // CELL)
    for (gx, gy), arr in grid.items():
        for gx2 in (gx - xmax, gx + xmax):
            other = grid.get((gx2, gy))
            if other:
                for a in arr:
                    for b in other:
                        if a != b:
                            adj[a].add(b)
                            adj[b].add(a)

    valid = set(r['i'] for r in regions)
    out = {}
    for r in regions:
        i = r['i']
        out[i] = {
            'c': r['c'],
            'n': '%s·%d' % (r['c'], r['idx']),   # 显示名：国名·序号
            'g': r['g'],
            'a': r['a'],
            'lon': r['lon'],
            'lat': r['lat'],
            'adj': sorted(x for x in adj[i] if x in valid),
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    sz = os.path.getsize(OUT)
    print('邻接完成 (%.1fs)，输出 %s: %d 块地, %.0f KB, 平均邻接数 %.1f' % (
        time.time() - t0, OUT, len(out), sz / 1024,
        sum(len(v['adj']) for v in out.values()) / len(out)))

    # 抽样验证：中国/美国各取一块看邻接显示名
    for i, v in out.items():
        if v['n'] in ('中国·1', '美国·1'):
            print(v['n'], '(%d km²) ->' % v['a'], [out[x]['n'] for x in v['adj'][:10]])


if __name__ == '__main__':
    main()
