# -*- coding: utf-8 -*-
"""
地图模式管理器：持有所有进行中的 MapGame，每秒全局 tick 并广播增量
"""
import threading
import time

from .engine import MapGame, TICK_SECONDS


class MapModeManager:
    def __init__(self):
        self.games = {}  # room_id -> MapGame
        self._sio = None
        self._lock = threading.Lock()
        self._started = False
        self.full_state_cb = None  # 由 events 注入：定期给每人推完整状态

    def bind_socketio(self, sio):
        """注入 socketio 用于广播（app 启动后调用一次）"""
        self._sio = sio
        if not self._started:
            self._started = True
            t = threading.Thread(target=self._loop, daemon=True)
            t.start()

    def create_game(self, room):
        """房间开始游戏：用非观战玩家建局"""
        players = {}
        for pid, p in room.players.items():
            if not p.is_spectator:
                players[pid] = {'name': p.name, 'color': getattr(p, 'theme_color', '') or _default_color(pid, len(players))}
        game = MapGame(room.id, players)
        with self._lock:
            self.games[room.id] = game
        return game

    def get(self, room_id):
        return self.games.get(str(room_id))

    def stop(self, room_id):
        with self._lock:
            self.games.pop(str(room_id), None)

    def _loop(self):
        last = time.time()
        last_full = 0.0
        while True:
            time.sleep(0.25)
            now = time.time()
            dt = min(now - last, 5.0)  # 卡顿兜底：最多按 5 秒结算
            if dt < TICK_SECONDS:
                continue
            last = now
            dt = min(dt, 3.0)
            for room_id, game in list(self.games.items()):
                try:
                    dirty = game.tick(dt)
                    if dirty and self._sio:
                        delta = game.tick_delta(dirty)
                        if delta:
                            self._sio.emit('mm_delta', delta, room=room_id)
                    # 终局补推一次完整状态（mine 详情/归属定格），之后兜底不再发
                    if game.phase == 'finished' and not getattr(game, '_finish_pushed', False):
                        game._finish_pushed = True
                        if self.full_state_cb:
                            self.full_state_cb(room_id, game)
                except Exception as e:
                    print('[MapMode] tick 异常 room=%s: %r' % (room_id, e))
            # 每 5 秒全量兜底：mine 详情（人口/驻军/建造进度）不在增量里
            if self.full_state_cb and now - last_full >= 5.0:
                last_full = now
                for room_id, game in list(self.games.items()):
                    if game.phase in ('picking', 'playing'):
                        try:
                            self.full_state_cb(room_id, game)
                        except Exception as e:
                            print('[MapMode] 全量兜底异常 room=%s: %r' % (room_id, e))


# 主题色兜底调色板（玩家未选色时自动分配，无蓝/白）
from .engine import THEME_COLORS as _POOL


def _default_color(pid, index):
    return _POOL[index % len(_POOL)]


# 全局管理器单例（与 app.py 的 room_manager 一样进程级）
map_manager = MapModeManager()
