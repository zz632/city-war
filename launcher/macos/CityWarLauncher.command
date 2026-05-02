#!/bin/bash

# 城池战争游戏启动器 for macOS
# CityWar Game Launcher for macOS

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 项目目录是脚本的上两级目录
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 进程 ID 文件
PID_FILE="/tmp/citywar_server.pid"

# 打印带颜色的信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║   城池战争 CityWar - 本地多人策略游戏                        ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 检查 Python
check_python() {
    print_info "检查 Python 环境..."

    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PYTHON_VERSION=$(python3 --version 2>&1)
        print_success "找到 Python: $PYTHON_VERSION"
        return 0
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
        PYTHON_VERSION=$(python --version 2>&1)
        print_success "找到 Python: $PYTHON_VERSION"
        return 0
    else
        print_error "未找到 Python！"
        echo ""
        echo "请安装 Python 3.8 或更高版本:"
        echo "  方法1: 访问 https://www.python.org/downloads/ 下载安装"
        echo "  方法2: 使用 Homebrew: brew install python"
        echo ""
        return 1
    fi
}

# 查找可用端口
find_available_port() {
    local port=5000
    while lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; do
        ((port++))
        if [ $port -gt 5100 ]; then
            print_error "无法找到可用端口"
            return 1
        fi
    done
    echo $port
}

# 启动游戏服务器
start_server() {
    print_info "启动游戏服务器..."
    print_info "工作目录: $PROJECT_DIR"

    # 切换到项目目录
    cd "$PROJECT_DIR" || {
        print_error "无法切换到项目目录: $PROJECT_DIR"
        return 1
    }

    # 验证 app.py 存在
    if [ ! -f "app.py" ]; then
        print_error "未找到 app.py 文件"
        print_info "当前目录: $(pwd)"
        print_info "目录内容:"
        ls -la
        return 1
    fi

    # 查找可用端口
    PORT=$(find_available_port)
    print_info "使用端口: $PORT"

    # 设置环境变量
    export FLASK_APP="app.py"
    export FLASK_ENV="production"
    export PORT=$PORT

    # 启动服务器（后台运行）
    print_info "正在启动服务器..."
    $PYTHON_CMD "$PROJECT_DIR/app.py" > /tmp/citywar_server.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > "$PID_FILE"

    # 等待服务器启动
    print_info "等待服务器启动..."
    local count=0
    while ! curl -s http://localhost:$PORT >/dev/null 2>&1; do
        sleep 1
        ((count++))
        if [ $count -gt 30 ]; then
            print_error "服务器启动超时"
            kill $SERVER_PID 2>/dev/null
            return 1
        fi
        # 检查进程是否还在运行
        if ! kill -0 $SERVER_PID 2>/dev/null; then
            print_error "服务器进程异常退出"
            print_info "日志:"
            cat /tmp/citywar_server.log 2>/dev/null
            return 1
        fi
    done

    print_success "服务器启动成功！"
    echo ""

    # 打开浏览器
    print_info "正在打开浏览器..."
    sleep 1

    if command -v open &> /dev/null; then
        open "http://localhost:$PORT"
    else
        print_warning "无法自动打开浏览器，请手动访问: http://localhost:$PORT"
    fi

    echo ""
    print_success "游戏已启动！"
    echo -e "${GREEN}请访问: http://localhost:$PORT${NC}"
    echo ""
    echo "按 Ctrl+C 停止服务器"
    echo ""

    # 等待服务器进程
    wait $SERVER_PID
}

# 清理函数
cleanup() {
    echo ""
    print_info "正在关闭..."

    # 停止服务器
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 $pid 2>/dev/null; then
            kill $pid 2>/dev/null
        fi
        rm -f "$PID_FILE"
    fi

    # 兜底：查找并终止进程
    pkill -f "python.*app.py" 2>/dev/null

    print_success "服务器已关闭"
    exit 0
}

# 设置信号处理
trap cleanup SIGINT SIGTERM

# 主函数
main() {
    print_banner

    # 检查 Python
    if ! check_python; then
        echo ""
        read -p "按回车键退出..."
        exit 1
    fi

    # 安装依赖
    print_info "检查并安装依赖..."
    $PYTHON_CMD -m pip install -r "$PROJECT_DIR/requirements.txt" --force-reinstall -q
    if [ $? -ne 0 ]; then
        print_warning "依赖安装可能遇到问题，尝试继续..."
    fi

    # 启动服务器
    start_server

    # 清理
    cleanup
}

# 运行主函数
main
