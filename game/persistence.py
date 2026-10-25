"""
房间与会话持久化模块
MongoDB 存储房间快照与登录会话，服务重启（如 HF Space 定期重启）后恢复对局与自动登录
未配置 MONGODB_URI 时全部操作静默跳过（本地模式）
"""
import os
import time
from typing import Dict

from .models import Room, Player, GameState, GamePhase

MONGODB_URI = os.environ.get('MONGODB_URI', '')

SESSION_TTL = 30 * 86400  # 登录会话有效期：30天
ROOM_TTL = 24 * 3600     # 房间恢复上限：24小时（超时的对局不再恢复）

_client = None
_rooms_col = None
_sessions_col = None


def _init():
    global _client, _rooms_col, _sessions_col
    if _client is not None or not MONGODB_URI:
        return
    try:
        import pymongo
        _client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        _client.admin.command('ping')
        db = _client['citywar']
        _rooms_col = db['rooms']
        _sessions_col = db['sessions']
        print('[Persistence] MongoDB 已连接，房间/会话将持久化')
    except Exception as e:
        print(f'[Persistence] MongoDB 连接失败，持久化停用: {e}')
        _client = None
        _rooms_col = None
        _sessions_col = None


_init()


def available() -> bool:
    return _rooms_col is not None


# ===== 房间序列化 =====

def _player_to_doc(p: Player) -> dict:
    return {
        'id': p.id, 'name': p.name, 'room_id': p.room_id, 'cities': p.cities,
        'is_alive': p.is_alive, 'is_host': p.is_host, 'is_ready': p.is_ready,
        'is_spectator': p.is_spectator, 'is_ai': p.is_ai, 'username': p.username,
        'skills': p.skills, 'action': p.action, 'alliance_with': p.alliance_with,
        'alliance_benefits': p.alliance_benefits, 'alliance_damages': p.alliance_damages,
        'repair_active': p.repair_active, 'status_effects': p.status_effects,
        'action_history': p.action_history, 'created_at': p.created_at,
    }


def _player_from_doc(d: dict) -> Player:
    return Player(
        id=d['id'], name=d['name'], room_id=d['room_id'], cities=d.get('cities', 250),
        is_alive=d.get('is_alive', True), is_host=d.get('is_host', False),
        is_ready=d.get('is_ready', False), is_spectator=d.get('is_spectator', False),
        is_ai=d.get('is_ai', False), username=d.get('username', ''),
        skills=d.get('skills', []), action=d.get('action'),
        alliance_with=d.get('alliance_with'), alliance_benefits=d.get('alliance_benefits', 0),
        alliance_damages=d.get('alliance_damages', 0), repair_active=d.get('repair_active', False),
        status_effects=d.get('status_effects', {}), action_history=d.get('action_history', []),
        created_at=d.get('created_at', time.time()),
    )


def _game_state_to_doc(gs: GameState) -> dict:
    return {
        'round': gs.round, 'phase': gs.phase.value,
        'actions': gs.actions, 'extra_actions': gs.extra_actions,
        'messages': gs.messages[-100:],  # 只保留最近100条，控制体积
        'auction': gs.auction, 'duel': gs.duel, 'meeting_results': gs.meeting_results,
        'skill_cards_drawn': gs.skill_cards_drawn,
        # 挂在 game_state 上的临时状态（重建时恢复，防止拍卖重复触发/濒死抉择丢失）
        'pending_totem': list(getattr(gs, 'pending_totem', [])),
        '_auction_done_this_round': bool(getattr(gs, '_auction_done_this_round', False)),
    }


def _game_state_from_doc(d: dict) -> GameState:
    gs = GameState(
        round=d.get('round', 1), phase=GamePhase(d.get('phase', 'waiting')),
        actions=d.get('actions', {}), extra_actions=d.get('extra_actions', {}),
        messages=d.get('messages', []), auction=d.get('auction'),
        duel=d.get('duel'), meeting_results=d.get('meeting_results'),
        skill_cards_drawn=d.get('skill_cards_drawn', 0),
    )
    if d.get('pending_totem'):
        gs.pending_totem = list(d['pending_totem'])
    if d.get('_auction_done_this_round'):
        gs._auction_done_this_round = True
    return gs


def save_room(room: Room):
    """保存房间快照（失败仅记日志，不影响游戏）"""
    if not available():
        return
    try:
        doc = {
            '_id': room.id, 'name': room.name, 'host_id': room.host_id,
            'players': [_player_to_doc(p) for p in room.players.values()],
            'game_state': _game_state_to_doc(room.game_state) if room.game_state else None,
            'created_at': room.created_at, 'max_players': room.max_players,
            'allow_join_after_start': room.allow_join_after_start,
            'password': room.password, 'saved_at': time.time(),
        }
        _rooms_col.replace_one({'_id': room.id}, doc, upsert=True)
    except Exception as e:
        print(f'[Persistence] 保存房间 {room.id} 失败: {e}')


def delete_room(room_id: str):
    if not available():
        return
    try:
        _rooms_col.delete_one({'_id': room_id})
    except Exception as e:
        print(f'[Persistence] 删除房间 {room_id} 失败: {e}')


def sync_room_ids(live_ids):
    """删除数据库中已不在内存里的房间（房间关闭/游戏结束后的清理）"""
    if not available():
        return
    try:
        _rooms_col.delete_many({'_id': {'$nin': list(live_ids)}})
    except Exception as e:
        print(f'[Persistence] 清理房间失败: {e}')


def load_rooms() -> Dict[str, Room]:
    """启动时恢复房间，返回 {room_id: Room}"""
    rooms = {}
    if not available():
        return rooms
    try:
        cutoff = time.time() - ROOM_TTL
        for doc in _rooms_col.find({'saved_at': {'$gt': cutoff}}):
            try:
                gs_doc = doc.get('game_state')
                if gs_doc and gs_doc.get('phase') == 'finished':
                    _rooms_col.delete_one({'_id': doc['_id']})
                    continue
                room = Room(
                    id=doc['_id'], name=doc.get('name', ''), host_id=doc.get('host_id', ''),
                    created_at=doc.get('created_at', time.time()),
                    max_players=doc.get('max_players', 8),
                    allow_join_after_start=doc.get('allow_join_after_start', False),
                    password=doc.get('password', ''),
                )
                for pd in doc.get('players', []):
                    p = _player_from_doc(pd)
                    room.players[p.id] = p
                room.game_state = _game_state_from_doc(gs_doc) if gs_doc else None
                if room.players:  # 空房间不恢复
                    rooms[room.id] = room
            except Exception as e:
                print(f'[Persistence] 恢复房间 {doc.get("_id")} 失败: {e}')
        if rooms:
            print(f'[Persistence] 已恢复 {len(rooms)} 个房间: {", ".join(rooms.keys())}')
    except Exception as e:
        print(f'[Persistence] 加载房间失败: {e}')
    return rooms


# ===== 会话持久化 =====

def save_session(token: str, username: str):
    if not available():
        return
    try:
        _sessions_col.replace_one(
            {'_id': token},
            {'_id': token, 'username': username, 'created_at': time.time()},
            upsert=True,
        )
    except Exception as e:
        print(f'[Persistence] 保存会话失败: {e}')


def delete_session(token: str):
    if not available():
        return
    try:
        _sessions_col.delete_one({'_id': token})
    except Exception as e:
        print(f'[Persistence] 删除会话失败: {e}')


def delete_user_sessions(username: str):
    """删除某用户全部会话（注销/管理员删除用户时）"""
    if not available():
        return
    try:
        _sessions_col.delete_many({'username': username})
    except Exception as e:
        print(f'[Persistence] 清理用户会话失败: {e}')


def load_sessions() -> Dict[str, str]:
    """启动时恢复登录会话，返回 {token: username}（30天内有效）"""
    result = {}
    if not available():
        return result
    try:
        cutoff = time.time() - SESSION_TTL
        for doc in _sessions_col.find({'created_at': {'$gt': cutoff}}):
            result[doc['_id']] = doc.get('username', '')
        # 顺带清理过期会话
        _sessions_col.delete_many({'created_at': {'$lte': cutoff}})
        if result:
            print(f'[Persistence] 已恢复 {len(result)} 个登录会话')
    except Exception as e:
        print(f'[Persistence] 加载会话失败: {e}')
    return result
