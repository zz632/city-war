# -*- coding: utf-8 -*-
"""
地图模式 MongoDB 持久化（S7）：
- 对局快照定期写入 map_games（含房间成员信息），服务器重启后恢复未结束对局
- 外交聊天持久化在 S8（mm_conversations / mm_messages）
"""
import time

COL_GAMES = 'map_games'


def save_game(db, room, game):
    """写入/更新一局快照（room 为 game.manager.Room，可含观战者）"""
    if db is None or room is None:
        return
    doc = {
        '_id': str(room.id),
        'updated': time.time(),
        'room': {
            'host_id': room.host_id,
            'room_type': room.room_type,
            'name': room.name,
            'max_players': room.max_players,
            'password': room.password or '',
            'players': {pid: {'name': p.name,
                              'theme_color': getattr(p, 'theme_color', '') or '',
                              'is_spectator': bool(p.is_spectator),
                              'is_host': bool(getattr(p, 'is_host', False))}
                        for pid, p in room.players.items()},
        },
        'game': game.to_snapshot(),
    }
    try:
        db[COL_GAMES].replace_one({'_id': doc['_id']}, doc, upsert=True)
    except Exception as e:
        print('[MM_PERSIST] 保存快照失败 room=%s: %r' % (room.id, e))


def delete_game(db, room_id):
    """对局结束/房间解散时清除快照"""
    if db is None:
        return
    try:
        db[COL_GAMES].delete_one({'_id': str(room_id)})
    except Exception as e:
        print('[MM_PERSIST] 删除快照失败 room=%s: %r' % (room_id, e))


def restore_all(db, map_manager, room_manager):
    """启动时恢复所有未结束对局（重建房间 + 对局，等待玩家重连）"""
    if db is None:
        return
    try:
        docs = list(db[COL_GAMES].find())
    except Exception as e:
        print('[MM_PERSIST] 读取快照失败: %r' % e)
        return
    n = 0
    for doc in docs:
        try:
            rid = doc['_id']
            rd = doc.get('room', {})
            snap = doc.get('game')
            if not snap or snap.get('phase') == 'finished':
                db[COL_GAMES].delete_one({'_id': rid})
                continue
            # 重建房间与玩家
            from ..models import Room, Player
            players = {}
            for pid, pd in rd.get('players', {}).items():
                pl = Player(id=pid, name=pd['name'], room_id=rid,
                            is_spectator=pd.get('is_spectator', False),
                            is_alive=not pd.get('is_spectator', False),
                            cities=0 if pd.get('is_spectator') else 250)
                pl.theme_color = pd.get('theme_color', '')
                pl.is_host = pd.get('is_host', False)
                players[pid] = pl
            room = Room(id=rid, name=rd.get('name', '房间-' + rid),
                        host_id=rd.get('host_id', ''),
                        players=players,
                        max_players=rd.get('max_players', 32),
                        password=rd.get('password', ''),
                        room_type=rd.get('room_type', 'map_mode'))
            room_manager.rooms[rid] = room
            for pl in players.values():
                room_manager.players[pl.id] = pl
            # 重建对局
            from .engine import MapGame
            game = MapGame.from_snapshot(snap)
            map_manager.games[rid] = game
            n += 1
        except Exception as e:
            print('[MM_PERSIST] 恢复对局失败 %s: %r' % (doc.get('_id'), e))
    if n:
        print('[MM_PERSIST] 已恢复 %d 局未结束对局，等待玩家重连' % n)
