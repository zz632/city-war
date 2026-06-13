FROM python:3.11-slim

WORKDIR /app

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

# Hugging Face Spaces 环境变量
ENV ONLINE_MODE=1
ENV PORT=7860

EXPOSE 7860

CMD ["python", "server.py"]
