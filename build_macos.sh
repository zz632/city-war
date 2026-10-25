#!/bin/bash
# 城池战争 - macOS 打包脚本

set -e

echo "=========================================="
echo "  城池战争 - macOS 打包"
echo "=========================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 python3"
    exit 1
fi
echo "[OK] Python: $(python3 --version)"

echo ""
echo "[1/4] 安装项目依赖..."
python3 -m pip install -r requirements.txt -q
echo "[OK] 依赖安装完成"

echo ""
echo "[2/4] 安装 PyInstaller..."
python3 -m pip install pyinstaller -q
echo "[OK] PyInstaller 安装完成"

echo ""
echo "[3/4] 打包客户端 (citywar-client)..."
python3 -m PyInstaller citywar-client.spec --noconfirm --clean

echo ""
echo "[4/4] 打包服务器 (citywar-server)..."
python3 -m PyInstaller citywar-server.spec --noconfirm --clean

echo ""
if [ -f "dist/citywar-client" ] && [ -f "dist/citywar-server" ]; then
    echo "=========================================="
    echo "  打包成功！"
    echo ""
    echo "  客户端: dist/citywar-client ($(du -h dist/citywar-client | cut -f1))"
    echo "  服务器: dist/citywar-server ($(du -h dist/citywar-server | cut -f1))"
    echo ""
    echo "  使用方法："
    echo "    ./dist/citywar-server   # 启动服务器"
    echo "    ./dist/citywar-client   # 启动游戏客户端"
    echo "=========================================="
else
    echo "[错误] 打包失败，请检查上方日志"
    exit 1
fi
