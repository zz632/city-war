FROM python:3.11-slim

WORKDIR /app

# 安装 nginx 和构建依赖（bcrypt/pymongo C 扩展需要）
RUN apt-get update && apt-get install -y --no-install-recommends nginx gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/citywar.conf
RUN rm -f /etc/nginx/sites-enabled/default

# 安装依赖
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# 复制服务端代码
COPY app.py .
COPY server.py .
COPY game/ game/
COPY websocket/ websocket/
COPY static/ static/
COPY templates/ templates/
COPY start.sh .
RUN chmod +x start.sh

# 创建数据目录
RUN mkdir -p /app/data /data

# 声明持久化卷（HF Spaces 会自动挂载 /data 为持久存储）
VOLUME /data

# Hugging Face Spaces 环境变量
ENV ONLINE_MODE=1
ENV PORT=7860

EXPOSE 7860

CMD ["./start.sh"]
