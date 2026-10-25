#!/usr/bin/env python3
"""
代理救援：绕过 v2rayN GUI，直接用其自带内核（xray/sing-box）测速并起临时代理。
由 auto_push.sh 在节点失效（退出码2路径）时调用，不写入 v2rayN 任何文件，只读其数据库。

用法:
  python3 proxy_rescue.py test    # 测速所有节点并打印报告
  python3 proxy_rescue.py serve   # 测速→选最快节点→在10810起代理，写就绪文件后常驻
                                   # 就绪文件: /tmp/citywar_rescue.ready，内容 "OK http://127.0.0.1:10810"
                                   # 失败时写 "FAIL"，退出码2
流程: 直连更新订阅解析最新节点（订阅拉取失败则回退v2rayN数据库节点）→ 全部测速 → 最快节点常驻
"""
import base64
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, parse_qs, unquote

APP_SUPPORT = os.path.expanduser('~/Library/Application Support/v2rayN')
DB_PATH = os.path.join(APP_SUPPORT, 'guiConfigs', 'guiNDB.db')
XRAY = os.path.join(APP_SUPPORT, 'bin', 'xray', 'xray')
SING_BOX = os.path.join(APP_SUPPORT, 'bin', 'sing_box', 'sing-box')
PORT = 10810
READY_FILE = '/tmp/citywar_rescue.ready'
TEST_URL = 'https://github.com'

# v2rayN EConfigType: 1=VMess 3=Shadowsocks 5=VLESS 6=Trojan 7=Hysteria2 8=Tuic
CT_VMESS, CT_SS, CT_VLESS, CT_TROJAN, CT_HY2 = 1, 3, 5, 6, 7


def read_db_nodes():
    """只读 v2rayN SQLite，返回节点 dict 列表"""
    uri = f'file:{DB_PATH}?mode=ro&immutable=1'
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT IndexId, ConfigType, Remarks, Address, Port, Password, Id, Security,'
        ' Network, RequestHost, Path, StreamSecurity, Sni, PublicKey, ShortId, Fingerprint,'
        ' Flow, TransportExtra FROM ProfileItem').fetchall()
    conn.close()
    nodes = []
    for r in rows:
        if not r['Address'] or not r['Port']:
            continue
        n = dict(r)
        # 新版 v2rayN 把 ws 的 Host/Path 藏在 TransportExtra JSON 里
        if n['TransportExtra']:
            try:
                te = json.loads(n['TransportExtra'])
                n['ws_host'] = te.get('Host', '')
                n['ws_path'] = te.get('Path', '')
            except Exception:
                n['ws_host'], n['ws_path'] = '', ''
        else:
            n['ws_host'], n['ws_path'] = '', ''
        nodes.append(n)
    return nodes


def read_sub_urls():
    uri = f'file:{DB_PATH}?mode=ro&immutable=1'
    conn = sqlite3.connect(uri, uri=True)
    rows = conn.execute('SELECT Url FROM SubItem WHERE Enabled IS NULL OR Enabled=1').fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


# ===== share link 解析（订阅更新用）=====

def parse_links(text):
    """解析订阅返回的 share links 为节点 dict 列表（字段对齐 ProfileItem）"""
    nodes = []
    text = text.strip()
    # 尝试整体 base64 解码
    try:
        dec = base64.b64decode(text + '=' * (-len(text) % 4)).decode('utf-8', 'ignore')
        if '://' in dec:
            text = dec
    except Exception:
        pass
    for line in text.splitlines():
        line = line.strip()
        if not line or '://' not in line:
            continue
        n = _parse_link(line)
        if n:
            nodes.append(n)
    return nodes


def _parse_link(link):
    try:
        scheme = link.split('://', 1)[0].lower()
        if scheme == 'vmess':
            payload = json.loads(base64.b64decode(link.split('://', 1)[1] + '==').decode('utf-8', 'ignore'))
            return dict(ConfigType=CT_VMESS, Remarks=payload.get('ps', ''), Address=payload.get('add', ''),
                        Port=int(payload.get('port', 0)), Password=payload.get('id', ''),
                        Security=payload.get('scy') or 'auto', Network=payload.get('net') or 'tcp',
                        Sni=payload.get('sni', ''), ws_host=payload.get('host', ''),
                        ws_path=payload.get('path', '/'), StreamSecurity='tls' if payload.get('tls') else '')
        u = urlsplit(link)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        name = unquote(u.fragment) or u.hostname
        common = dict(Remarks=name, Address=u.hostname, Port=u.port or 443,
                      Network=q.get('type', 'tcp'), Sni=q.get('sni', ''),
                      ws_host=q.get('host', ''), ws_path=unquote(q.get('path', '/')) or '/',
                      StreamSecurity=q.get('security', ''), Fingerprint=q.get('fp', ''))
        if scheme == 'trojan':
            common.update(ConfigType=CT_TROJAN, Password=unquote(u.username or ''))
        elif scheme == 'vless':
            common.update(ConfigType=CT_VLESS, Password=unquote(u.username or ''), Flow=q.get('flow', ''),
                          PublicKey=q.get('pbk', ''), ShortId=q.get('sid', ''))
        elif scheme == 'hysteria2':
            common.update(ConfigType=CT_HY2, Password=unquote(u.username or ''))
        elif scheme == 'ss':
            try:  # SIP002: ss://base64(method:pass)@host:port 或 ss://base64(全部)
                body = link.split('://', 1)[1].split('#', 1)[0].split('?', 1)[0]
                if '@' not in body:
                    body = base64.b64decode(body + '==').decode('utf-8', 'ignore')
                userinfo, hostport = body.rsplit('@', 1)
                method, pw = base64.b64decode(userinfo + '==').decode('utf-8', 'ignore').split(':', 1)
                host, port = hostport.rsplit(':', 1)
                return dict(ConfigType=CT_SS, Remarks=name, Address=host, Port=int(port),
                            Password=pw, Security=method, Network='tcp', StreamSecurity='',
                            ws_host='', ws_path='', Sni='')
            except Exception:
                return None
        else:
            return None
        return common
    except Exception:
        return None


# ===== 内核配置生成 =====

def build_xray_config(n, port):
    """xray 格式配置（trojan/vless/vmess/ss）"""
    out = {'tag': 'proxy'}
    ct = n['ConfigType']
    if ct == CT_TROJAN:
        out['protocol'] = 'trojan'
        out['settings'] = {'servers': [{'address': n['Address'], 'port': n['Port'],
                                        'password': n['Password'], 'level': 1}]}
    elif ct == CT_VLESS:
        user = {'id': n['Password'], 'encryption': 'none'}
        if n.get('Flow'):
            user['flow'] = n['Flow']
        out['protocol'] = 'vless'
        out['settings'] = {'vnext': [{'address': n['Address'], 'port': n['Port'], 'users': [user]}]}
    elif ct == CT_VMESS:
        out['protocol'] = 'vmess'
        out['settings'] = {'vnext': [{'address': n['Address'], 'port': n['Port'],
                                      'users': [{'id': n['Password'], 'security': n.get('Security') or 'auto',
                                                 'alterId': 0}]}]}
    elif ct == CT_SS:
        out['protocol'] = 'shadowsocks'
        out['settings'] = {'servers': [{'address': n['Address'], 'port': n['Port'],
                                        'method': n.get('Security') or 'aes-256-gcm',
                                        'password': n['Password'], 'ota': False, 'level': 1}]}
    else:
        return None

    ss = {'network': n.get('Network') or 'tcp'}
    sec = n.get('StreamSecurity') or ''
    if sec == 'tls':
        ss['security'] = 'tls'
        ss['tlsSettings'] = {'serverName': n.get('Sni') or n.get('ws_host') or n['Address']}
    elif sec == 'reality':
        ss['security'] = 'reality'
        ss['realitySettings'] = {'serverName': n.get('Sni') or n['Address'],
                                 'publicKey': n.get('PublicKey') or '',
                                 'shortId': n.get('ShortId') or '',
                                 'fingerprint': n.get('Fingerprint') or 'chrome'}
    if ss['network'] == 'ws':
        ss['wsSettings'] = {'path': n.get('ws_path') or '/',
                            'host': n.get('ws_host') or n.get('Sni') or ''}
    out['streamSettings'] = ss
    return {'log': {'loglevel': 'error'},
            'inbounds': [{'tag': 'socks', 'port': port, 'listen': '127.0.0.1',
                          'protocol': 'mixed', 'settings': {'auth': 'noauth', 'udp': True}}],
            'outbounds': [out]}


def build_singbox_config(n, port):
    """sing-box 格式配置（hysteria2/tuic 等 xray 不支持的协议）"""
    ct = n['ConfigType']
    if ct == CT_HY2:
        ob = {'type': 'hysteria2', 'server': n['Address'], 'server_port': n['Port'],
              'password': n['Password'],
              'tls': {'enabled': True, 'server_name': n.get('Sni') or n['Address']}}
    else:
        return None
    return {'log': {'level': 'error'},
            'inbounds': [{'type': 'socks', 'listen': '127.0.0.1', 'listen_port': port}],
            'outbounds': [ob]}


# ===== 进程与测速 =====

def start_core(n, port):
    """按协议选择内核并启动，返回 (proc, cfgfile) 或 (None, None)"""
    cfg = build_xray_config(n, port)
    binary = XRAY
    if cfg is None:
        cfg = build_singbox_config(n, port)
        binary = SING_BOX
    if cfg is None:
        return None, None
    fd, cfgfile = tempfile.mkstemp(suffix='.json', prefix='rescue_')
    with os.fdopen(fd, 'w') as f:
        json.dump(cfg, f)
    try:
        proc = subprocess.Popen([binary, 'run', '-c', cfgfile],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        os.unlink(cfgfile)
        return None, None
    return proc, cfgfile


def stop_core(proc, cfgfile):
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    if cfgfile and os.path.exists(cfgfile):
        os.unlink(cfgfile)


def test_node(n, port=PORT, timeout=8):
    """测一个节点经代理访问 TEST_URL，成功返回耗时秒，失败返回 None"""
    proc, cfgfile = start_core(n, port)
    if proc is None:
        return None
    try:
        # 等端口就绪（最多4秒）
        for _ in range(20):
            time.sleep(0.2)
            if proc.poll() is not None:  # 内核秒退，配置或节点无效
                return None
            r = subprocess.run(['nc', '-z', '127.0.0.1', str(port)],
                               capture_output=True)
            if r.returncode == 0:
                break
        else:
            return None
        import urllib.request
        proxy_handler = urllib.request.ProxyHandler({'http': f'http://127.0.0.1:{port}',
                                                     'https': f'http://127.0.0.1:{port}'})
        opener = urllib.request.build_opener(proxy_handler)
        t0 = time.time()
        opener.open(TEST_URL, timeout=timeout)
        return round(time.time() - t0, 2)
    except Exception:
        return None
    finally:
        stop_core(proc, cfgfile)


def fetch_subscription():
    """直连（不走代理）拉取所有订阅并解析为新节点列表"""
    nodes = []
    for url in read_sub_urls():
        try:
            r = subprocess.run(['curl', '-s', '-m', '25', '-A',
                                'v2rayN/7.x', url], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                nodes.extend(parse_links(r.stdout))
        except Exception:
            continue
    return nodes


def speed_run(nodes, verbose=True):
    """测全部节点，返回 [(耗时, 节点)] 成功列表（按耗时升序）"""
    results = []
    for i, n in enumerate(nodes, 1):
        name = (n.get('Remarks') or n['Address'])[:40]
        ct = {CT_VMESS: 'vmess', CT_SS: 'ss', CT_VLESS: 'vless', CT_TROJAN: 'trojan', CT_HY2: 'hy2'}.get(n['ConfigType'], '?')
        if verbose:
            print(f'[rescue] ({i}/{len(nodes)}) 测试 {ct} {name} ...', flush=True)
        t = test_node(n)
        if verbose:
            print(f'[rescue]   -> {"%.2fs" % t if t else "失败"}', flush=True)
        if t:
            results.append((t, n))
    results.sort(key=lambda x: x[0])
    return results


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'test'
    if os.path.exists(READY_FILE):
        os.unlink(READY_FILE)

    # 先直连更新订阅拿最新节点，再测速选最快
    print('[rescue] 直连更新订阅（不走代理）...', flush=True)
    nodes = fetch_subscription()
    print(f'[rescue] 订阅解析到 {len(nodes)} 个节点', flush=True)
    if not nodes:
        print('[rescue] 订阅拉取失败，回退到 v2rayN 数据库节点', flush=True)
        nodes = read_db_nodes()
        print(f'[rescue] 从 v2rayN 数据库读取 {len(nodes)} 个节点', flush=True)
    results = speed_run(nodes)

    if not results:
        print('[rescue] 所有节点均不可用（含订阅刷新），放弃', flush=True)
        if mode == 'serve':
            with open(READY_FILE, 'w') as f:
                f.write('FAIL')
        sys.exit(2)

    best_t, best = results[0]
    print(f'[rescue] 最快节点: {best.get("Remarks", best["Address"])} ({best_t}s)，'
          f'共 {len(results)}/{len(nodes)} 个可用', flush=True)

    if mode == 'test':
        for t, n in results:
            print(f'  {t:>6.2f}s  {n.get("Remarks", n["Address"])}')
        return

    # serve 模式：用最快节点常驻
    proc, cfgfile = start_core(best, PORT)
    if proc is None:
        with open(READY_FILE, 'w') as f:
            f.write('FAIL')
        sys.exit(2)
    for _ in range(20):
        time.sleep(0.2)
        if proc.poll() is not None:
            with open(READY_FILE, 'w') as f:
                f.write('FAIL')
            sys.exit(2)
        r = subprocess.run(['nc', '-z', '127.0.0.1', str(PORT)], capture_output=True)
        if r.returncode == 0:
            break

    def cleanup(*_):
        stop_core(proc, cfgfile)
        if os.path.exists(READY_FILE):
            os.unlink(READY_FILE)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    with open(READY_FILE, 'w') as f:
        f.write(f'OK http://127.0.0.1:{PORT}')
    print(f'[rescue] 临时代理已就绪: http://127.0.0.1:{PORT}（常驻，等推送方 kill）', flush=True)
    while True:
        if proc.poll() is not None:
            print('[rescue] 内核意外退出', flush=True)
            with open(READY_FILE, 'w') as f:
                f.write('FAIL')
            sys.exit(1)
        time.sleep(1)


if __name__ == '__main__':
    main()
