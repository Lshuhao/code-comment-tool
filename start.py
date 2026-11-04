"""
代码注释工具 - 跨平台一键启动脚本

用法:
    python start.py              # 启动后端 + 前端（开发模式）
    python start.py --backend    # 仅启动后端
    python start.py --frontend   # 仅启动前端
    python start.py --install    # 仅安装依赖
"""
import os
import sys
import subprocess
import time
import argparse
import signal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"

# 全局进程列表
child_processes = []


def cleanup(signum=None, frame=None):
    """停止所有子进程"""
    print("\n正在停止服务...")
    for p in child_processes:
        if p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def check_python():
    print("[1/4] 检查 Python 环境...", end=" ")
    try:
        version = subprocess.check_output([sys.executable, "--version"], text=True).strip()
        print(f"[OK] {version}")
    except Exception:
        print("[错误] Python 不可用")
        sys.exit(1)


def check_node():
    print("[2/4] 检查 Node.js 环境...", end=" ")
    try:
        version = subprocess.check_output(["node", "--version"], text=True).strip()
        print(f"[OK] {version}")
        return True
    except FileNotFoundError:
        print("[警告] Node.js 未安装，前端不可用")
        return False


def install_deps():
    print("[3/4] 安装后端依赖...", end=" ")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
            cwd=str(BACKEND_DIR),
            check=True, capture_output=True,
        )
        print("[OK]")
    except subprocess.CalledProcessError:
        print("[警告] 部分依赖安装失败，将继续尝试启动")


def install_frontend_deps():
    print("  安装前端依赖...", end=" ")
    try:
        subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR), check=True, capture_output=True, shell=True)
        print("[OK]")
    except Exception as e:
        print(f"[错误] npm install 失败: {e}")


def start_backend():
    print("[4/4] 启动后端 (FastAPI :8000)...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(BACKEND_DIR),
    )
    child_processes.append(proc)
    print(f"  后端 PID: {proc.pid}")


def start_frontend():
    print("       启动前端 (Vue3 :3000)...")

    if not (FRONTEND_DIR / "node_modules").exists():
        print("  首次运行，安装前端依赖...")
        install_frontend_deps()
        if not (FRONTEND_DIR / "node_modules").exists():
            print("  [错误] 前端依赖安装失败，请手动执行: cd frontend && npm install")
            return

    proc = subprocess.Popen(
        "npm run dev",
        cwd=str(FRONTEND_DIR),
        shell=True,
    )
    child_processes.append(proc)
    print(f"  前端 PID: {proc.pid}")


def wait_for_backend():
    """等待后端就绪"""
    print("\n等待后端就绪...", end=" ")
    import urllib.request
    for i in range(15):
        try:
            urllib.request.urlopen("http://localhost:8000/api/v1/health", timeout=2)
            print(f"[OK] ({i+1}s)")
            return True
        except Exception:
            time.sleep(1)
            print(".", end="", flush=True)
    print(" [超时]")
    return False


def main():
    parser = argparse.ArgumentParser(description="代码注释工具 - 一键启动")
    parser.add_argument("--backend", action="store_true", help="仅启动后端")
    parser.add_argument("--frontend", action="store_true", help="仅启动前端")
    parser.add_argument("--install", action="store_true", help="仅安装依赖")
    parser.add_argument("--no-frontend", action="store_true", help="强制不启动前端")
    parser.add_argument("--port", type=int, default=8000, help="后端端口 (默认 8000)")
    args = parser.parse_args()

    print("=" * 60)
    print("       代码注释自动生成与优化建议工具 - 一键启动")
    print("=" * 60)
    print()

    # 环境检查
    check_python()
    has_node = check_node()
    install_deps()

    # 仅安装模式
    if args.install:
        print("\n依赖安装完成！")
        return

    # 启动后端
    if not args.frontend:
        start_backend()

    # 启动前端
    start_frontend_flag = has_node and not args.backend and not args.no_frontend
    if start_frontend_flag:
        start_frontend()

    # 等待后端
    if not args.frontend:
        wait_for_backend()

    # 打印信息
    print()
    print("=" * 60)
    print("  启动完成！")
    print("  后端 API:  http://localhost:8000")
    print("  API 文档:  http://localhost:8000/docs")
    if start_frontend_flag:
        print("  前端界面:  http://localhost:3000")
    print("=" * 60)
    print()
    print("  按 Ctrl+C 停止所有服务")

    # 保持运行
    try:
        while True:
            time.sleep(1)
            # 检查子进程是否异常退出
            for p in child_processes:
                if p.poll() is not None:
                    print(f"\n[警告] 进程 {p.pid} 已退出 (code={p.returncode})")
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
