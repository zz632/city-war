@echo off
chcp 65001 >nul
title 城池战争 - Windows 打包

echo ==========================================
echo   城池战争 - Windows 打包
echo ==========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python
    pause
    exit /b 1
)
for /f "tokens=*" %%a in ('python --version 2^>^&1') do echo [OK] %%a

:: 安装依赖
echo.
echo [1/3] 安装项目依赖...
python -m pip install -r requirements.txt -q
echo [OK] 依赖安装完成

:: 安装 PyInstaller
echo.
echo [2/3] 安装 PyInstaller...
python -m pip install pyinstaller -q
echo [OK] PyInstaller 安装完成

:: 打包
echo.
echo [3/3] 开始打包...
python -m PyInstaller citywar.spec --noconfirm --clean

echo.
if exist "dist\citywar.exe" (
    echo ==========================================
    echo   打包成功！
    echo   产物: dist\citywar.exe
    echo.
    echo   使用方法：
    echo     dist\citywar.exe
    echo ==========================================
) else (
    echo [错误] 打包失败，请检查上方日志
)

pause
