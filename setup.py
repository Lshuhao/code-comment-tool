"""
环境诊断与安装脚本
检测问题并安装所有依赖
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

def run(cmd, cwd=None, check=False):
    print(f"  > {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120
        )
        if result.stdout:
            print(result.stdout[:500])
        if result.returncode != 0 and result.stderr:
            print(f"  [stderr] {result.stderr[:500]}")
        return result.returncode == 0
    except Exception as e:
        print(f"  [错误] {e}")
        return False

def main():
    print("=" * 60)
    print("  环境诊断与安装")
    print("=" * 60)
    print()

    # Python 版本
    print(f"Python: {sys.version}")
    print(f"路径: {sys.executable}")
    print()

    # 1. 后端依赖
    print("[后端依赖安装]")
    ok = run(f'"{sys.executable}" -m pip install -r requirements.txt', cwd=str(BACKEND))
    if not ok:
        print("  pip install 失败，尝试逐个安装核心包...")
        core_packages = [
            "fastapi", "uvicorn", "python-multipart", "chardet",
            "pydantic", "pydantic-settings", "jinja2", "aiofiles", "httpx",
            "tree-sitter", "tree-sitter-python", "tree-sitter-java", "tree-sitter-cpp",
            "openai",
        ]
        for pkg in core_packages:
            print(f"  安装 {pkg}...", end=" ")
            ok2 = run(f'"{sys.executable}" -m pip install {pkg} -q', cwd=str(BACKEND))
            print("OK" if ok2 else "FAIL")

    # 2. 验证关键模块
    print()
    print("[验证关键模块]")
    modules = {
        "chardet": "chardet",
        "fastapi": "fastapi",
        "jinja2": "jinja2",
        "tree_sitter": "tree_sitter",
    }
    for mod_name, import_name in modules.items():
        ok = run(f'"{sys.executable}" -c "import {import_name}; print(\'OK\')"')
        if not ok:
            print(f"  [!] {mod_name} 导入失败")

    # 3. 前端依赖
    print()
    print("[前端依赖安装]")
    npm_path = shutil.which("npm")
    if npm_path:
        print(f"npm 路径: {npm_path}")
        ok = run("npm install", cwd=str(FRONTEND))
        if not ok:
            print("  npm install 失败，请手动执行: cd frontend && npm install")
    else:
        print("  [!] npm 未找到，请安装 Node.js")

    print()
    print("=" * 60)
    print("  诊断完成！请根据以上输出排查问题。")
    print("=" * 60)

if __name__ == "__main__":
    main()
