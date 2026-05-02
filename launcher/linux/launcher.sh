#!/bin/bash

# 城池战争 - Linux 启动器

APP_NAME="城池战争"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="/tmp/citywar_server.pid"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_msg() {
    echo -e "${2}${1}${NC}"
}

# 检查 Python
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_msg "错误: 未找到 Python，请先安装 Python 3.8+" "$RED"
        exit 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    print_msg "找到 Python: $PYTHON_VERSION" "$GREEN"
}

# 安装依赖
install_deps() {
    print_msg "检查并安装依赖..." "$YELLOW"
    $PYTHON_CMD -m pip install -r "$APP_DIR/requirements.txt" --force-reinstall -q
    if [ $? -ne 0 ]; then
        print_msg "依赖安装可能遇到问题，尝试继续..." "$YELLOW"
    fi
}

# 启动服务器
start_server() {
    print_msg "正在启动 $APP_NAME 服务器..." "$YELLOW"
    cd "$APP_DIR"

    # 后台启动服务器
    $PYTHON_CMD app.py > /tmp/citywar_server.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > "$PID_FILE"

    # 等待服务器启动
    sleep 2

    if kill -0 $SERVER_PID 2>/dev/null; then
        print_msg "服务器已启动 (PID: $SERVER_PID)" "$GREEN"
        return 0
    else
        print_msg "服务器启动失败" "$RED"
        print_msg "日志:" "$YELLOW"
        cat /tmp/citywar_server.log 2>/dev/null
        return 1
    fi
}

# 打开浏览器
open_browser() {
    print_msg "正在打开浏览器..." "$YELLOW"
    sleep 1

    URL="http://localhost:5000"

    if command -v xdg-open &> /dev/null; then
        xdg-open "$URL"
    elif command -v gnome-open &> /dev/null; then
        gnome-open "$URL"
    elif command -v kde-open &> /dev/null; then
        kde-open "$URL"
    else
        print_msg "请手动打开浏览器访问: $URL" "$BLUE"
    fi
}

# 停止服务器
stop_server() {
    # 停止游戏服务器
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            print_msg "正在停止服务器..." "$YELLOW"
            kill $PID
            rm -f "$PID_FILE"
            print_msg "服务器已停止" "$GREEN"
        else
            print_msg "服务器未运行" "$YELLOW"
            rm -f "$PID_FILE"
        fi
    else
        print_msg "未找到运行中的服务器" "$YELLOW"
    fi
}

# 显示状态
show_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            print_msg "$APP_NAME 服务器正在运行 (PID: $PID)" "$GREEN"
            print_msg "访问地址: http://localhost:5000" "$BLUE"
        else
            print_msg "$APP_NAME 服务器未运行" "$RED"
            rm -f "$PID_FILE"
        fi
    else
        print_msg "$APP_NAME 服务器未运行" "$RED"
    fi
}

# 显示帮助
show_help() {
    echo "城池战争 - Linux 启动器"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  start    启动服务器并打开浏览器"
    echo "  stop     停止服务器"
    echo "  restart  重启服务器"
    echo "  status   查看服务器状态"
    echo "  help     显示此帮助信息"
    echo ""
    echo "直接运行 $0 将启动服务器"
}

# 主函数
main() {
    case "${1:-start}" in
        start)
            check_python
            install_deps
            start_server || exit 1
            open_browser
            print_msg ""
            print_msg "========================================" "$BLUE"
            print_msg "  $APP_NAME 已启动!" "$GREEN"
            print_msg "  访问地址: http://localhost:5000" "$BLUE"
            print_msg "========================================" "$BLUE"
            ;;
        stop)
            stop_server
            ;;
        restart)
            stop_server
            sleep 1
            check_python
            install_deps
            start_server || exit 1
            open_browser
        status)
            show_status
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_msg "未知选项: $1" "$RED"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
