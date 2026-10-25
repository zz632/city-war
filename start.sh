#!/bin/bash
set -e

# 启动 nginx（后台）
nginx -g 'daemon off;' &
NGINX_PID=$!

# 启动 gunicorn + eventlet（前台）
exec gunicorn \
    --worker-class eventlet \
    --workers 1 \
    --bind 127.0.0.1:5000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
