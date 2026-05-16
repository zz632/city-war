#!/bin/bash
# 城池战争 - macOS 手动打包脚本（备用）
# 正式打包建议使用 GitHub Actions：git tag v1.0 && git push origin v1.0

set -e

echo "=========================================="
echo "  城池战争 - macOS 打包"
echo "=========================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 python3"
    exit 1
fi
echo "[OK] Python: $(python3 --version)"

# 安装依赖
echo ""
echo "[1/3] 安装项目依赖..."
python3 -m pip install -r requirements.txt -q
echo "[OK] 依赖安装完成"

# 安装 PyInstaller
echo ""
echo "[2/3] 安装 PyInstaller..."
python3 -m pip install pyinstaller -q
echo "[OK] PyInstaller 安装完成"

# 打包
echo ""
echo "[3/3] 开始打包..."
python3 -m PyInstaller citywar.spec --noconfirm --clean

echo ""
if [ -f "dist/citywar" ]; then
    echo "=========================================="
    echo "  打包成功！"
    echo "  产物: dist/citywar"
    echo "  大小: $(du -h dist/citywar | cut -f1)"
    echo ""
    echo "  使用方法："
    echo "    ./dist/citywar"
    echo "=========================================="
else
    echo "[错误] 打包失败，请检查上方日志"
    exit 1
fi
