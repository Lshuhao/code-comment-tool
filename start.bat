@echo off
chcp 65001 >nul
title 代码注释自动生成与优化建议工具
color 0A

echo ============================================================
echo         代码注释自动生成与优化建议工具
echo ============================================================
echo.

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend

REM ========== 检查 Python ==========
echo [1/3] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [错误] 未检测到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)
echo   [OK] Python 已安装

REM ========== 安装依赖 ==========
echo [2/3] 检查依赖...
cd /d "%BACKEND_DIR%"
pip install -r requirements.txt -q 2>nul
echo   [OK] 依赖就绪

REM ========== 启动 Tkinter GUI ==========
echo [3/3] 启动桌面应用...
echo.
echo ============================================================
echo   启动 Tkinter 桌面界面
echo   直接调用后端模块，无需启动服务器
echo ============================================================
echo.

python backend/app/gui/app.py
