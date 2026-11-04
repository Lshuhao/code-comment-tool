"""
代码注释工具 - Tkinter 桌面版启动脚本

用法:
    python start.py              # 启动 GUI
    python start.py --install    # 仅安装依赖
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"


def main():
    parser = argparse.ArgumentParser(description="代码注释工具 - Tkinter 桌面版启动")
    parser.add_argument("--install", action="store_true", help="仅安装依赖")
    args = parser.parse_args()

    print("=" * 60)
    print("       代码注释自动生成与优化建议工具")
    print("=" * 60)
    print()

    # 检查 Python
    print(f"[1/3] Python {sys.version.split()[0]}")

    # 安装依赖
    print("[2/3] 安装依赖...", end=" ")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
            cwd=str(BACKEND_DIR),
            check=True, capture_output=True,
        )
        print("[OK]")
    except subprocess.CalledProcessError:
        print("[警告] 部分依赖安装失败")

    if args.install:
        print("\n依赖安装完成！")
        return

    # 启动 GUI
    print("[3/3] 启动 Tkinter 桌面应用...")
    print()
    print("=" * 60)
    print("  直接调用后端模块，无需启动服务器")
    print("=" * 60)
    print()

    gui_script = BACKEND_DIR / "app" / "gui" / "app.py"
    os.execv(sys.executable, [sys.executable, str(gui_script)])


if __name__ == "__main__":
    main()
