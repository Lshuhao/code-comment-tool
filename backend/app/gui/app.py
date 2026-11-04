"""
代码注释自动生成与优化建议工具 - Tkinter 桌面应用

直接调用后端模块，无需启动 HTTP 服务。
启动方式: python backend/app/gui/app.py
"""
import os
import sys
import tkinter as tk
from tkinter import ttk

# 确保 backend 目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.gui.pages import AnalysisPage, HistoryPage, ModelSettingsPage


class MainWindow:
    """主窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("代码注释自动生成与优化建议工具")
        self.root.geometry("1100x780")
        self.root.minsize(900, 600)

        # 窗口图标居中
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 1100) // 2
        y = (self.root.winfo_screenheight() - 780) // 2
        if x > 0 and y > 0:
            self.root.geometry(f"1100x780+{x}+{y}")

        # 设置样式
        self._setup_style()

        # 页面引用（用于跨页面交互，在 _build_notebook 中赋值）
        self.analysis_page = None
        self.history_page = None

        # 构建界面
        self._build_header()
        self._build_notebook()
        self._build_statusbar()

    def _setup_style(self):
        """配置 ttk 样式"""
        style = ttk.Style()
        style.theme_use("clam")

        # Notebook 样式
        style.configure("TNotebook", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[16, 6], font=("Microsoft YaHei", 10))
        style.map("TNotebook.Tab",
                   background=[("selected", "#e8f0fe")],
                   foreground=[("selected", "#1a73e8")])

        # 按钮样式
        style.configure("Accent.TButton", font=("Microsoft YaHei", 10, "bold"))

        # Treeview 样式
        style.configure("Treeview", rowheight=26, font=("Microsoft YaHei", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 9, "bold"))

    def _build_header(self):
        """顶部标题栏"""
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=12, pady=(12, 4))

        # 图标 + 标题
        title_frame = ttk.Frame(header)
        title_frame.pack(side=tk.LEFT)

        icon_label = ttk.Label(title_frame, text="📝", font=("", 18))
        icon_label.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(title_frame, text="代码注释自动生成与优化建议工具",
                  font=("Microsoft YaHei", 14, "bold")).pack(side=tk.LEFT)

        ttk.Label(title_frame, text=" v1.0", font=("Microsoft YaHei", 9), foreground="#999").pack(side=tk.LEFT)

    def _build_notebook(self):
        """标签页容器"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        # Tab 1: 代码分析
        self.analysis_page = AnalysisPage(self.notebook, app_ref=self)
        self.notebook.add(self.analysis_page, text="  代码分析  ", padding=8)

        # Tab 2: 历史记录
        self.history_page = HistoryPage(self.notebook)
        self.notebook.add(self.history_page, text="  历史记录  ", padding=8)

        # Tab 3: 模型设置
        settings_page = ModelSettingsPage(self.notebook)
        self.notebook.add(settings_page, text="  模型设置  ", padding=8)

    def _build_statusbar(self):
        """底部状态栏"""
        statusbar = ttk.Frame(self.root)
        statusbar.pack(fill=tk.X, side=tk.BOTTOM, padx=12, pady=(0, 8))

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.BOTTOM)

        self.status_text = tk.StringVar(value="就绪")
        ttk.Label(statusbar, textvariable=self.status_text, font=("Microsoft YaHei", 9),
                  foreground="#888").pack(side=tk.LEFT)

        ttk.Label(statusbar, text="v1.0.0", font=("Microsoft YaHei", 9),
                  foreground="#bbb").pack(side=tk.RIGHT)

    def run(self):
        """启动应用"""
        self.root.mainloop()


def main():
    """入口函数"""
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
