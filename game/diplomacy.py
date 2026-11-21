# -*- coding: utf-8 -*-
"""
外交聊天系统（规则 12，全局：地图模式与经典模式共用）
- 会话类型：私聊(dm) / 群聊(group)；公开频道沿用房间 chat_message
- 群聊：建群（发起者为群主）、入群申请（现有成员全员同意）、退群、踢人（群主）
- 消息历史与未读持久化（MongoDB mm_conversations），断线重连后可查看
"""
import threading
import time
import uuid

MAX_MSGS = 200  # 每会话保留的消息条数


class DiplomacyManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.convs = {}   # cid -> {id,type,room,members(list),name,owner,join_req:{pid:[已同意成员]}}
        self.msgs = {}    # cid -> [{'pid','name','msg','ts'}]
        self.unread = {}  # pid -> {cid: n}
        self.db = None    # MongoDB（可选；None 时仅内存）

    def bind_mongo(self, db):
        self.db = db

    # ---------- 持久化 ----------
    def _persist(self, cid):
        if self.db is None:
            return
        conv = self.convs.get(cid)
        if not conv:
            return
        doc = dict(conv)
        doc['msgs'] = self.msgs.get(cid, [])
        doc['unread'] = self._unread_for(cid)
        try:
            self.db['mm_conversations'].replace_one({'_id': cid}, doc, upsert=True)
        except Exception as e:
            print('[DIPLO] 持久化失败 %s: %r' % (cid, e))

    def _unread_for(self, cid):
        out = {}
        for pid, m in self.unread.items():
            if cid in m and m[cid] > 0:
                out[pid] = m[cid]
        return out

    def load_room(self, room_id):
        """重启后懒加载该房间的会话（进入房间时调用一次）"""
        if self.db is None:
            return
        try:
            for doc in self.db['mm_conversations'].find({'room': str(room_id)}):
                cid = doc['_id']
                if cid in self.convs:
                    continue
                conv = {k: doc[k] for k in ('id', 'type', 'room', 'members', 'name', 'owner')}
                conv['join_req'] = doc.get('join_req', {})
                self.convs[cid] = conv
                self.msgs[cid] = doc.get('msgs', [])
                for pid, n in doc.get('unread', {}).items():
                    self.unread.setdefault(pid, {})[cid] = n
        except Exception as e:
            print('[DIPLO] 加载会话失败 room=%s: %r' % (room_id, e))

    def _dm_key(self, room_id, a, b):
        return 'dm_%s_%s' % (room_id, '_'.join(sorted([str(a), str(b)])))

    def open_dm(self, room_id, pid_a, pid_b):
        """打开/创建私聊会话"""
        with self.lock:
            if str(pid_a) == str(pid_b):
                return None, '不能和自己私聊'
            cid = self._dm_key(room_id, pid_a, pid_b)
            if cid not in self.convs:
                self.convs[cid] = {'id': cid, 'type': 'dm', 'room': str(room_id),
                                   'members': [str(pid_a), str(pid_b)],
                                   'name': '', 'owner': None, 'join_req': {}}
                self.msgs[cid] = []
                self._persist(cid)
            return self.convs[cid], ''

    def create_group(self, room_id, owner, name, members):
        """建群：发起者为群主，成员 = 发起者 + 自选成员"""
        with self.lock:
            mem = [str(owner)] + [str(m) for m in members if str(m) != str(owner)]
            # 去重保序
            seen = set()
            mem = [m for m in mem if not (m in seen or seen.add(m))]
            cid = 'grp_' + uuid.uuid4().hex[:10]
            self.convs[cid] = {'id': cid, 'type': 'group', 'room': str(room_id),
                               'members': mem, 'name': name or '群聊',
                               'owner': str(owner), 'join_req': {}}
            self.msgs[cid] = []
            self._persist(cid)
            return self.convs[cid], ''

    def join_request(self, cid, pid, name):
        """入群申请：记录申请，等待现有成员全员同意"""
        with self.lock:
            conv = self.convs.get(cid)
            if not conv or conv['type'] != 'group':
                return None, '群不存在'
            if str(pid) in conv['members']:
                return None, '已是群成员'
            conv['join_req'][str(pid)] = {'name': name, 'approved': []}
            self._persist(cid)
            return conv, ''

    def join_vote(self, cid, voter, approve):
        """成员对入群申请投票：全员同意 → 入群；任一拒绝 → 拒绝"""
        with self.lock:
            conv = self.convs.get(cid)
            if not conv or conv['type'] != 'group':
                return None, None, '群不存在', None
            reqs = conv['join_req']
            applicant = None
            for apid, req in reqs.items():
                if str(voter) in req['approved']:
                    return None, None, '已投过票', None
            # 找到 voter 尚未投票的申请（按时间取第一个）
            for apid, req in reqs.items():
                if str(voter) not in req['approved']:
                    applicant = apid
                    break
            if applicant is None:
                return None, None, '没有待处理的入群申请', None
            if not approve:
                del reqs[applicant]
                self._persist(cid)
                return conv, applicant, 'rejected', None
            reqs[applicant]['approved'].append(str(voter))
            if set(reqs[applicant]['approved']) >= set(conv['members']):
                conv['members'].append(applicant)
                del reqs[applicant]
                self._persist(cid)
                return conv, applicant, 'joined', None
            self._persist(cid)
            return conv, applicant, 'voted', reqs[applicant]['approved']

    def leave(self, cid, pid):
        with self.lock:
            conv = self.convs.get(cid)
            if not conv or str(pid) not in conv['members']:
                return None, '不在群中'
            conv['members'] = [m for m in conv['members'] if m != str(pid)]
            # 群主退出：转让给第一个成员；无人则解散
            if conv['owner'] == str(pid):
                conv['owner'] = conv['members'][0] if conv['members'] else None
            if not conv['members'] or (conv['type'] == 'dm'):
                self.convs.pop(cid, None)
                self.msgs.pop(cid, None)
                self._delete(cid)
                return None, ''
            if conv['type'] == 'group' and len(conv['members']) < 2:
                self.convs.pop(cid, None)
                self.msgs.pop(cid, None)
                self._delete(cid)
                return None, ''
            self._persist(cid)
            return conv, ''

    def kick(self, cid, owner, target):
        with self.lock:
            conv = self.convs.get(cid)
            if not conv or conv['type'] != 'group':
                return None, '群不存在'
            if conv['owner'] != str(owner):
                return None, '只有群主可以移出成员'
            if str(target) not in conv['members']:
                return None, '该玩家不在群中'
            conv['members'] = [m for m in conv['members'] if m != str(target)]
            self._persist(cid)
            return conv, ''

    def _delete(self, cid):
        if self.db is not None:
            try:
                self.db['mm_conversations'].delete_one({'_id': cid})
            except Exception:
                pass

    # ---------- 消息 ----------
    def send_msg(self, cid, pid, name, msg, ts=None):
        with self.lock:
            conv = self.convs.get(cid)
            if not conv or str(pid) not in conv['members']:
                return None, '会话不存在或不是成员'
            entry = {'pid': str(pid), 'name': name, 'msg': str(msg)[:500],
                     'ts': ts or time.time()}
            lst = self.msgs.setdefault(cid, [])
            lst.append(entry)
            if len(lst) > MAX_MSGS:
                self.msgs[cid] = lst[-MAX_MSGS:]
            # 其他成员未读 +1
            for m in conv['members']:
                if m != str(pid):
                    self.unread.setdefault(m, {})
                    self.unread[m][cid] = self.unread[m].get(cid, 0) + 1
            self._persist(cid)
            return {'conv': conv, 'msg': entry}, ''

    def read(self, cid, pid):
        with self.lock:
            u = self.unread.get(str(pid))
            if u:
                u[cid] = 0

    def list_for(self, pid, room_id):
        """某玩家在某房间的会话列表 + 未读数"""
        with self.lock:
            out = []
            for cid, conv in self.convs.items():
                if conv['room'] != str(room_id) or str(pid) not in conv['members']:
                    continue
                out.append({'id': cid, 'type': conv['type'],
                            'name': conv['name'],
                            'members': list(conv['members']),
                            'owner': conv['owner'],
                            'join_req': {k: {'name': v.get('name', ''),
                                             'approved': list(v.get('approved', []))}
                                         for k, v in conv.get('join_req', {}).items()},
                            'unread': self.unread.get(str(pid), {}).get(cid, 0),
                            'last': self.msgs.get(cid, [])[-1] if self.msgs.get(cid) else None})
            return out

    def history(self, cid):
        with self.lock:
            return list(self.msgs.get(cid, []))


# 全局单例
diplomacy = DiplomacyManager()
