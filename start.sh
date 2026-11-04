#!/bin/bash
# 代码注释工具 - Tkinter 桌面版启动脚本

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

echo "============================================================"
echo "        代码注释自动生成与优化建议工具"
echo "============================================================"
echo ""

# 检查 Python
echo -n "[1/3] 检查 Python... "
if command -v python3 &>/dev/null; then
    echo "[OK] $(python3 --version)"
    PYTHON=python3
else
    echo "[错误] 需要 Python 3.10+"
    exit 1
fi

# 安装依赖
echo -n "[2/3] 检查依赖... "
cd "$BACKEND_DIR"
pip3 install -r requirements.txt -q 2>/dev/null || pip install -r requirements.txt -q 2>/dev/null
echo "[OK]"

# 启动 GUI
echo "[3/3] 启动 Tkinter 桌面应用..."
echo ""
echo "============================================================"
echo "  启动 Tkinter 桌面界面"
echo "  直接调用后端模块，无需启动服务器"
echo "============================================================"
echo ""

cd "$ROOT_DIR"
$PYTHON backend/app/gui/app.py
