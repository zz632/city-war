@echo off
chcp 65001 >nul
@echo off
title 城池战争游戏启动器
@echo off

set "APP_NAME=城池战争"
set "APP_DIR=%~dp0"
set "PID_FILE=%TEMP%\citywar_server.pid"

echo ========================================
echo   欢迎使用 %APP_NAME%
echo ========================================
echo.

:: 检查 Python
call :check_python
if errorlevel 1 goto :error

:: 安装依赖
call :install_deps
if errorlevel 1 goto :error

:: 启动服务器
call :start_server
if errorlevel 1 goto :error

:: 打开浏览器
call :open_browser

echo.
echo 游戏已启动!
echo 请保持此窗口运行，关闭此窗口将停止服务器
echo.

:: 等待用户按键
echo 按任意键停止服务器...
pause >nul

call :stop_server
goto :end

:check_python
    python --version >nul 2>&1
    if errorlevel 1 (
        python3 --version >nul 2>&1
        if errorlevel 1 (
            echo [错误] 未找到 Python。请安装 Python 3.8 或更高版本。
            exit /b 1
        ) else (
            set "PYTHON_CMD=python3"
        )
    ) else (
        set "PYTHON_CMD=python"
    )
    for /f "tokens=*" %%a in ('%PYTHON_CMD% --version 2^>^&1') do echo [OK] 找到: %%a
    exit /b 0

:install_deps
    echo 检查并安装依赖...
    %PYTHON_CMD% -m pip install -r "..\..\requirements.txt" --force-reinstall -q
    if errorlevel 1 (
        echo [警告] 依赖安装可能遇到问题，尝试继续...
    )
    exit /b 0

:start_server
    echo 启动游戏服务器...
    cd /d "%APP_DIR%\..\.."

    start /b "" %PYTHON_CMD% app.py

    :: 等待服务器启动
    timeout /t 2 /nobreak >nul

    echo [OK] 服务器已启动
    exit /b 0

:open_browser
    echo 正在打开浏览器...
    start "" "http://localhost:5000"
    exit /b 0

:stop_server
    echo 停止服务器...
    if exist "%PID_FILE%" (
        for /f %%i in (%PID_FILE%) do taskkill /F /PID %%i >nul 2>&1
        del "%PID_FILE%"
    )
    taskkill /F /IM python.exe >nul 2>&1
    taskkill /F /IM python3.exe >nul 2>&1
    echo [OK] 服务器已停止
    exit /b 0

:error
echo.
echo [错误] 游戏启动失败
pause
exit /b 1

:end
echo.
echo 感谢使用 %APP_NAME%!
timeout /t 2 >nul
