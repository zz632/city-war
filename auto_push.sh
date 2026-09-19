#!/bin/bash
# 自动推送脚本：代理未开时自动启动 v2rayN 并等待就绪，节点可用则推送双远端
# 用法: ./auto_push.sh [commit message]
# 退出码: 0=成功 1=代理启动超时 2=节点失效(需更新订阅/切换节点) 3=GitHub推送失败 4=HF推送失败

PROXY_HOST=127.0.0.1
PROXY_PORT=10808
PROXY="http://$PROXY_HOST:$PROXY_PORT"

proxy_alive() { nc -z "$PROXY_HOST" "$PROXY_PORT" >/dev/null 2>&1; }

# 1. 代理检测：没开就启动 v2rayN 并等待（最多120秒）
if ! proxy_alive; then
    echo "[auto_push] 代理未运行，启动 v2rayN..."
    open -a v2rayN
    ok=0
    for i in $(seq 1 60); do
        sleep 2
        if proxy_alive; then ok=1; break; fi
    done
    if [ "$ok" != 1 ]; then
        echo "[auto_push] 错误：等待代理就绪超时（120秒），请手动检查 v2rayN"
        exit 1
    fi
    echo "[auto_push] 代理已就绪"
    sleep 2  # 端口起来后核心还需几秒完成初始化
fi

# 2. 节点连通性测试：经代理访问 GitHub
if ! curl -s -o /dev/null -m 15 -x "$PROXY" https://github.com; then
    echo "[auto_push] 代理端口活着但无法经它访问 GitHub（当前节点可能失效）"
    echo "[auto_push] 请在 v2rayN 中更新订阅并切换可用节点后重试"
    exit 2
fi

# 3. 有改动先提交
if [ -n "$(git status --porcelain)" ]; then
    MSG="${1:-auto update}"
    git add -A
    git commit -m "$MSG" || true
fi

# 4. 推送双远端
git push origin main || exit 3
git push hf main || exit 4
echo "[auto_push] 推送完成（origin + hf）"
