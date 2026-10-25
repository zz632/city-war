#!/usr/bin/env python3
"""一次性脚本：重新生成 static/icons/ 下 4 个图标（纯 Pillow 绘制，无 AI 生成）"""
from PIL import Image, ImageDraw

BG = (15, 23, 42, 255)      # #0f172a 深蓝黑
GOLD = (251, 191, 36, 255)  # #fbbf24 金色
GOLD_DARK = (217, 119, 6, 255)  # #d97706 暗金（底座）

SS = 4  # 超采样倍数


def draw_castle(img, scale_ratio=1.0):
    """在 img 上绘制居中城堡（复刻首页 logo 形状），scale_ratio 为内容缩放"""
    W = img.width
    draw = ImageDraw.Draw(img)
    s = W / 24.0 * scale_ratio  # 24 单位 viewBox 缩放到画布
    cx = W / 2
    # 城堡在 viewBox 中占 y:3~21，中心 y=12；先相对中心计算再平移
    def P(x, y):
        return (cx + (x - 12) * s, W / 2 + (y - 12) * s)

    # 底座横线（y=21，x 3~21）
    draw.line([P(3, 21), P(21, 21)], fill=GOLD_DARK, width=max(1, round(1.6 * s)))

    # 塔身+尖顶多边形 (5,21)(5,7)(12,3)(19,7)(19,21)
    body = [P(5, 21), P(5, 7), P(12, 3), P(19, 7), P(19, 21)]
    draw.polygon(body, fill=GOLD)

    # 门洞（背景色挖出）：矩形 x9~15 y21~15 + 顶部半圆 r=3 圆心(12,15)
    x1, y1 = P(9, 15)
    x2, y2 = P(15, 21)
    draw.rounded_rectangle([x1, y1, x2, y2], radius=(x2 - x1) / 2, fill=BG,
                           corners=(True, True, False, False))  # 拱门：只上圆角
    return img


def make(size, maskable=False, solid=False, name=''):
    img = Image.new('RGBA', (size * SS, size * SS), BG if (maskable or solid) else (0, 0, 0, 0))
    if not maskable and not solid:
        # 普通图标：圆角背景，留透明角
        mask = Image.new('L', img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1],
                                               radius=size * SS * 0.22, fill=255)
        img.putalpha(mask)
    ratio = 0.62 if not maskable else 0.62 * 0.8  # maskable 内容缩到 80% 安全区
    draw_castle(img, ratio)
    img = img.resize((size, size), Image.LANCZOS)
    if solid:
        # apple-touch-icon 必须实底无透明
        base = Image.new('RGB', (size, size), BG[:3])
        base.paste(img, (0, 0), img)
        img = base
    img.save(name)
    print(f'saved {name} {img.size}')


import os
os.chdir('/Users/sha/Downloads/city-war/static/icons')
make(512, name='icon-512.png')
make(192, name='icon-192.png')
make(180, solid=True, name='apple-touch-icon.png')
make(512, maskable=True, name='maskable-512.png')
