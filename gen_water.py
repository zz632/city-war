#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成世界地图水体数据 map_water.bin（湖泊面 + 河流线）
数据源: Natural Earth 10m (geojson, /tmp/ne_lakes.geojson + /tmp/ne_rivers.geojson)
投影: 与 static/map/index.html 一致 (Web墨卡托, W=4096, 78N~58S)
输出: static/map/map_water.bin (gzip)
二进制布局:
  magic "WMWAT1\\0\\0" + jsonLen(u32) + json + pad4
  湖精版: LBOX(f32 nl*4) LRING(i32 nl+1) LROFF(i32 nring+1) LC(f32 lpts*2)
  湖粗版: 同布局 (nl2/nring2/lpts2)
  河精版: RBOX(f32 nriv*4) ROFFF(i32 nriv+1) RC(f32 rivpts*2) RW(u8 nriv)
  河粗版: 同布局
湖 ring 为闭合环（可含洞, 前端 evenodd 填充）; 河为开放折线。
"""
import json, gzip, hashlib, math, struct

W = 4096
PPR = W / (2 * math.pi)
YTOP = math.log(math.tan(math.pi / 4 + (78 * math.pi / 180) / 2))
LAT_MIN, LAT_MAX = -58, 78

def X(lon): return (lon + 180) * math.pi / 180 * PPR
def Y(lat):
    t = max(-85, min(85, lat))
    return (YTOP - math.log(math.tan(math.pi / 4 + (t * math.pi / 180) / 2))) * PPR

# ---------- RDP 简化（迭代栈, 容差单位=图上像素） ----------
def rdp(pts, tol):
    n = len(pts)
    if n < 3: return pts
    keep = [False] * n; keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1: continue
        ax, ay = pts[a]; bx, by = pts[b]
        dx = bx - ax; dy = by - ay
        L2 = dx * dx + dy * dy
        md = -1.0; mi = -1
        for k in range(a + 1, b):
            px, py = pts[k]
            if L2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / L2
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > md: md = d; mi = k
        if md > tol:
            keep[mi] = True
            stack.append((a, mi)); stack.append((mi, b))
    return [pts[k] for k in range(n) if keep[k]]

def proj_ring(ring, tol):
    """经纬环 -> 投影、裁纬度、去重、简化。None=整体出界/点太少"""
    pts = []
    for lon, lat in ring:
        if lat > LAT_MAX + 0.5 or lat < LAT_MIN - 0.5: continue
        pts.append((X(lon), Y(lat)))
    if len(pts) < 4: return None
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]: out.append(p)
    if len(out) < 4: return None
    return rdp(out, tol)

def proj_line(line, tol):
    """河流折线: 跨180°拆段、裁纬度, 返回 [段, ...]"""
    segs, cur, prev_lon = [], [], None
    for lon, lat in line:
        if lat > LAT_MAX or lat < LAT_MIN:
            if len(cur) >= 2: segs.append(cur)
            cur = []; prev_lon = None
            continue
        if prev_lon is not None and abs(lon - prev_lon) > 180:
            if len(cur) >= 2: segs.append(cur)
            cur = []
        cur.append((X(lon), Y(lat)))
        prev_lon = lon
    if len(cur) >= 2: segs.append(cur)
    out = []
    for s in segs:
        d = [s[0]]
        for p in s[1:]:
            if p != d[-1]: d.append(p)
        if len(d) < 2: continue
        r = rdp(d, tol)
        if len(r) >= 2: out.append(r)
    return out

# ---------- 湖泊 ----------
print("处理湖泊…")
lakes = json.load(open('/Users/sha/Downloads/ne_10m_lakes.geojson', encoding='utf-8'))
L_full, L_coarse = [], []
for f in lakes['features']:
    g = f.get('geometry')
    if not g: continue
    polys = [g['coordinates']] if g['type'] == 'Polygon' else (g['coordinates'] if g['type'] == 'MultiPolygon' else [])
    for poly in polys:
        fr, cr = [], []
        ok = True
        for ring in poly:
            p = proj_ring(ring, 0.8)
            if p is None:
                if len(ring) >= 4: ok = False
                break
            fr.append(p)
            c = proj_ring(ring, 3.0)
            if c and len(c) >= 4: cr.append(c)
        if ok and fr:
            L_full.append(fr)
            if cr: L_coarse.append(cr)

def poly_bbox(rings):
    xs = [x for r in rings for x, _ in r]; ys = [y for r in rings for _, y in r]
    return min(xs), min(ys), max(xs), max(ys)
L_coarse = [p for p in L_coarse if (lambda b: b[2] - b[0] > 5 or b[3] - b[1] > 5)(poly_bbox(p))]
print(f"湖泊: 精版 {len(L_full)} 面, 粗版 {len(L_coarse)} 面")

# ---------- 河流 ----------
print("处理河流…")
rivers = json.load(open('/Users/sha/Downloads/ne_10m_rivers_lake_centerlines.geojson', encoding='utf-8'))
R_full, R_coarse, RW, RW2 = [], [], [], []
for f in rivers['features']:
    g = f.get('geometry')
    if not g: continue
    prop = f.get('properties') or {}
    sw = prop.get('strokeweig', 0.5)
    if g['type'] == 'LineString': lines = [g['coordinates']]
    elif g['type'] == 'MultiLineString': lines = g['coordinates']
    else: continue
    for line in lines:
        for s in proj_line(line, 0.8):
            w = 2 if sw >= 0.9 else (1 if sw >= 0.5 else 0)
            R_full.append(s); RW.append(w)
            c = rdp(s, 3.0)
            if len(c) >= 2:
                R_coarse.append(c); RW2.append(w)
print(f"河流: 精版 {len(R_full)} 段, 粗版 {len(R_coarse)} 段")

# ---------- 序列化 ----------
def pack_polys(polys):
    """polys: [[ring,...],...] -> (bytes, counts)"""
    flat = bytearray()
    box = []; ring_idx = [0]; roff = [0]
    nring = 0; npts = 0
    for rings in polys:
        x0 = y0 = 1e18; x1 = y1 = -1e18
        for r in rings:
            for x, y in r:
                if x < x0: x0 = x
                if y < y0: y0 = y
                if x > x1: x1 = x
                if y > y1: y1 = y
                flat += struct.pack('<2f', x, y); npts += 1
            roff.append(npts); nring += 1
        box += [x0, y0, x1, y1]
        ring_idx.append(nring)
    b = bytearray()
    b += struct.pack('<%df' % len(box), *box)
    b += struct.pack('<%di' % len(ring_idx), *ring_idx)
    b += struct.pack('<%di' % len(roff), *roff)
    b += flat
    return bytes(b), {"nl": len(polys), "nring": nring, "lpts": npts}

def pack_lines(lines, widths):
    flat = bytearray(); box = []; off = [0]
    npts = 0
    for s in lines:
        x0 = y0 = 1e18; x1 = y1 = -1e18
        for x, y in s:
            if x < x0: x0 = x
            if y < y0: y0 = y
            if x > x1: x1 = x
            if y > y1: y1 = y
            flat += struct.pack('<2f', x, y); npts += 1
        box += [x0, y0, x1, y1]
        off.append(npts)
    b = bytearray()
    b += struct.pack('<%df' % len(box), *box)
    b += struct.pack('<%di' % len(off), *off)
    b += flat
    b += bytes(widths)
    return bytes(b), {"nriv": len(lines), "rivpts": npts}

BL1, m1 = pack_polys(L_full)
BL2, m2 = pack_polys(L_coarse)
BR1, m3 = pack_lines(R_full, RW)
BR2, m4 = pack_lines(R_coarse, RW2)
meta = {"nl": m1["nl"], "nring": m1["nring"], "lpts": m1["lpts"],
        "nl2": m2["nl"], "nring2": m2["nring"], "lpts2": m2["lpts"],
        "nriv": m3["nriv"], "rivpts": m3["rivpts"],
        "nriv2": m4["nriv"], "rivpts2": m4["rivpts"]}
jsb = json.dumps(meta, separators=(',', ':')).encode()
hdr = bytearray(b"WMWAT1\0\0") + struct.pack('<I', len(jsb)) + jsb
while len(hdr) % 4: hdr.append(0)

raw = bytes(hdr) + BL1 + BL2 + BR1 + BR2
data = gzip.compress(raw, 9)
open('/Users/sha/Downloads/city-war/static/map/map_water.bin', 'wb').write(data)
print(f"map_water.bin: {len(data)} bytes  md5={hashlib.md5(data).hexdigest()}  (原始 {len(raw)})")
