"""
Tkinter GUI 三个标签页：代码分析、历史记录、模型设置
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime

# 添加 backend 路径以便导入后端模块
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.gui.widgets import ScoreOverview, SuggestionList, DefectPanel


# ========================
# Tab 1: 代码分析页
# ========================

class AnalysisPage(ttk.Frame):
    """代码分析标签页"""

    def __init__(self, parent, app_ref=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.app_ref = app_ref  # 用于调用后端服务
        self._current_task = None

        self._build_ui()

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(toolbar, text=" 打开文件", command=self._open_file).pack(side=tk.LEFT, padx=2)
        self.filename_label = ttk.Label(toolbar, text="")
        self.filename_label.pack(side=tk.LEFT, padx=8)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(toolbar, text="语言:").pack(side=tk.LEFT)
        self.lang_var = tk.StringVar(value="自动检测")
        lang_combo = ttk.Combobox(toolbar, textvariable=self.lang_var,
                                   values=["自动检测", "python", "java", "cpp"], width=12, state="readonly")
        lang_combo.pack(side=tk.LEFT, padx=4)

        self.analyze_btn = ttk.Button(toolbar, text="  开始分析", command=self._start_analysis)
        self.analyze_btn.pack(side=tk.RIGHT, padx=4)

        # 进度条
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=200)
        self.progress.pack(fill=tk.X, pady=2)

        # 评分区域
        self.score_overview = ScoreOverview(self)
        self.score_overview.pack(fill=tk.X, pady=4)

        # 底部操作栏（先 pack，固定在底部）
        action_bar = ttk.Frame(self)
        action_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))
        ttk.Button(action_bar, text="导出源码", command=lambda: self._export("source")).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="导出Markdown报告", command=lambda: self._export("markdown")).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_bar, text="导出HTML报告", command=lambda: self._export("html")).pack(side=tk.LEFT, padx=2)

        self.status_label = ttk.Label(action_bar, text="就绪", foreground="#888")
        self.status_label.pack(side=tk.RIGHT, padx=8)

        # 垂直分栏：上方代码区 + 下方建议/缺陷区（填充剩余空间）
        self.main_vertical = ttk.PanedWindow(self, orient=tk.VERTICAL)
        self.main_vertical.pack(fill=tk.BOTH, expand=True)

        # 上半部分：代码输入 + 注释后代码
        top_frame = ttk.Frame(self.main_vertical)

        code_pane = ttk.PanedWindow(top_frame, orient=tk.HORIZONTAL)
        code_pane.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.LabelFrame(code_pane, text="代码输入")
        self.code_text = scrolledtext.ScrolledText(left_frame, wrap=tk.NONE,
                                                    font=("Consolas", 11), height=10)
        self.code_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        code_pane.add(left_frame, weight=1)

        right_frame = ttk.LabelFrame(code_pane, text="注释后代码")
        self.annot_text = scrolledtext.ScrolledText(right_frame, wrap=tk.NONE,
                                                     font=("Consolas", 10), state=tk.DISABLED,
                                                     bg="#f0fff0", height=10)
        self.annot_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        code_pane.add(right_frame, weight=1)

        top_frame.pack(fill=tk.BOTH, expand=True)
        self.main_vertical.add(top_frame, weight=1)

        # 下半部分：建议+缺陷（随窗口缩放）
        bottom_frame = ttk.Frame(self.main_vertical)

        self.bottom_notebook = ttk.Notebook(bottom_frame)
        self.bottom_notebook.pack(fill=tk.BOTH, expand=True)

        suggest_frame = ttk.Frame(self.bottom_notebook)
        self.suggestion_list = SuggestionList(suggest_frame,
                                               on_accept=self._on_accept,
                                               on_reject=self._on_reject)
        self.suggestion_list.pack(fill=tk.BOTH, expand=True)
        self.bottom_notebook.add(suggest_frame, text="  注释建议  ")

        defect_frame = ttk.Frame(self.bottom_notebook)
        self.defect_panel = DefectPanel(defect_frame)
        self.defect_panel.pack(fill=tk.BOTH, expand=True)
        self.bottom_notebook.add(defect_frame, text="  缺陷检测  ")

        bottom_frame.pack(fill=tk.BOTH, expand=True)
        self.main_vertical.add(bottom_frame, weight=1)

        # 延迟设置分隔条位置（代码区60% / 建议区40%）
        self.after(200, self._set_sash_position)

    def _set_sash_position(self):
        """设置 PanedWindow 分隔条初始位置"""
        try:
            total_height = self.main_vertical.winfo_height()
            if total_height > 200:
                self.main_vertical.sashpos(0, int(total_height * 0.60))
        except Exception:
            pass

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="选择代码文件",
            filetypes=[
                ("Python", "*.py"),
                ("Java", "*.java"),
                ("C/C++", "*.c *.cpp *.h *.hpp"),
                ("所有文件", "*.*"),
            ]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    code = f.read()
                self.code_text.delete("1.0", tk.END)
                self.code_text.insert("1.0", code)
                self.filename_label.config(text=os.path.basename(path))

                # 自动检测语言
                ext = os.path.splitext(path)[1].lower()
                lang_map = {".py": "python", ".java": "java", ".cpp": "cpp", ".c": "cpp", ".h": "cpp", ".hpp": "cpp"}
                if ext in lang_map:
                    self.lang_var.set(lang_map[ext])
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败: {e}")

    def _start_analysis(self):
        code = self.code_text.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("提示", "请先输入或打开代码文件")
            return

        lang = self.lang_var.get()
        lang_hint = None if lang == "自动检测" else lang
        filename = self.filename_label.cget("text") or "untitled.py"

        self.analyze_btn.config(state=tk.DISABLED)
        self.progress.start(10)
        self.status_label.config(text="分析中...")

        def do_analysis():
            try:
                from app.services.m1_ingest import ingest_service
                from app.services.m2_parser import parse_code
                from app.services.m3_comment_gen import CommentGenerationService
                from app.services.m4_defect import defect_detection_service
                from app.services.m5_scoring import scoring_service
                from app.services.m6_export import export_service
                from app.services.llm_client import LLMClientFactory

                # M1: 接入
                ingest = ingest_service.ingest_text(code, filename, lang_hint)

                # M2: 解析
                parse = parse_code(ingest.code_text, ingest.language)

                # M3: 注释生成
                llm = LLMClientFactory.create()
                comment_gen = CommentGenerationService(llm_client=llm)
                import asyncio
                loop = asyncio.new_event_loop()
                suggestions = loop.run_until_complete(comment_gen.generate_all(parse))
                loop.close()

                # M4: 缺陷检测
                loop2 = asyncio.new_event_loop()
                defects = loop2.run_until_complete(defect_detection_service.detect_all(parse))
                loop2.close()

                # M5: 评分
                score = scoring_service.calculate(parse, defects)

                return {
                    "task_id": "local",
                    "ingest": ingest.to_dict(),
                    "parse": parse.to_dict(),
                    "suggestions": [s.to_dict() for s in suggestions],
                    "defects": [d.to_dict() for d in defects],
                    "score": score.to_dict(),
                    "original_code": ingest.code_text,
                    "annotated_code": None,
                }
            except Exception as e:
                return {"error": str(e)}

        def on_done(result):
            # 线程安全：所有 UI 操作通过 root.after 回到主线程
            root = self.winfo_toplevel()

            def update_ui():
                self.progress.stop()
                self.analyze_btn.config(state=tk.NORMAL)

                if "error" in result:
                    self.status_label.config(text=f"分析失败: {result['error']}")
                    messagebox.showerror("分析失败", result["error"])
                    return

                self._current_task = result

                # 更新评分
                self.score_overview.set_score(result.get("score", {}))

                # 更新建议列表
                self.suggestion_list.set_suggestions(result.get("suggestions", []))

                # 更新缺陷面板
                self.defect_panel.set_defects(result.get("defects", []))

                # 自动生成全部采纳后的注释代码
                from app.services.m2_parser import ParseResult
                from app.services.m6_export import export_service
                from app.models.suggestions import CommentSuggestion

                parse = ParseResult.from_dict(result["parse"])
                suggestions = [CommentSuggestion.from_dict(s) for s in result.get("suggestions", [])]
                all_ids = [s.suggestion_id for s in suggestions]
                annotated = export_service.generate_annotated_code(
                    result["original_code"], suggestions, parse, all_ids
                )
                result["annotated_code"] = annotated

                self.annot_text.config(state=tk.NORMAL)
                self.annot_text.delete("1.0", tk.END)
                self.annot_text.insert("1.0", annotated)
                self.annot_text.config(state=tk.DISABLED)

                self.status_label.config(text=f"分析完成 | 评分: {result.get('score', {}).get('score', 0):.1f} | 已自动生成 {len(suggestions)} 条注释")

                # 同步到历史记录页
                app = self.app_ref
                if app and hasattr(app, 'history_page') and app.history_page:
                    app.history_page.add_record(result)

            root.after(0, update_ui)

        thread = threading.Thread(target=lambda: on_done(do_analysis()))
        thread.daemon = True
        thread.start()

    def _on_accept(self, accepted_ids):
        if not self._current_task:
            return
        from app.services.m2_parser import ParseResult
        from app.services.m6_export import export_service
        from app.models.suggestions import CommentSuggestion

        parse = ParseResult.from_dict(self._current_task["parse"])

        # 将字典转回 CommentSuggestion 对象
        suggestions = [
            CommentSuggestion.from_dict(s)
            for s in self._current_task["suggestions"]
        ]

        annotated = export_service.generate_annotated_code(
            self._current_task["original_code"],
            suggestions,
            parse,
            accepted_ids,
        )
        self._current_task["annotated_code"] = annotated

        # 首次采纳时显示绿色注释后代码区域（上下分栏）
        if not self._annot_visible:
            self.orig_text.pack_forget()
            self.orig_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            self.annot_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            self._annot_visible = True

        self.annot_text.config(state=tk.NORMAL)
        self.annot_text.delete("1.0", tk.END)
        self.annot_text.insert("1.0", annotated)
        self.annot_text.config(state=tk.DISABLED)

        self.status_label.config(text=f"已采纳 {len(accepted_ids)} 条建议")

    def _on_reject(self):
        self.status_label.config(text="已忽略选中建议")

    def _export(self, fmt):
        if not self._current_task:
            messagebox.showwarning("提示", "请先完成分析")
            return
        try:
            from app.services.m2_parser import ParseResult
            from app.services.m6_export import export_service
            from app.models.suggestions import QualityScore

            score_data = self._current_task.get("score", {})
            parse = ParseResult.from_dict(self._current_task["parse"])

            # 让文件选择对话框置顶显示
            root = self.winfo_toplevel()
            root.attributes("-topmost", True)
            root.update()

            if fmt == "source":
                code = self._current_task.get("annotated_code") or self._current_task.get("original_code", "")
                path = filedialog.asksaveasfilename(
                    title="导出注释后源码",
                    defaultextension=".py",
                    filetypes=[("Python", "*.py"), ("Java", "*.java"), ("C++", "*.cpp"), ("所有文件", "*.*")],
                    initialfile="annotated_code.py",
                )
                if path:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(code)
                    messagebox.showinfo("成功", f"源码已导出到：\n{path}")

            elif fmt == "markdown":
                from app.models.suggestions import Defect, CommentSuggestion
                score = QualityScore(**{k: v for k, v in score_data.items()
                                        if k in ("score", "dimensions", "defect_stats", "summary")})
                defects = [Defect.from_dict(d) if isinstance(d, dict) else d
                           for d in self._current_task.get("defects", [])]
                suggestions = [CommentSuggestion.from_dict(s) if isinstance(s, dict) else s
                               for s in self._current_task.get("suggestions", [])]
                result = export_service.export_markdown_report(score, defects, suggestions)
                path = filedialog.asksaveasfilename(
                    title="导出Markdown报告",
                    defaultextension=".md",
                    filetypes=[("Markdown", "*.md"), ("所有文件", "*.*")],
                    initialfile="report.md",
                )
                if path:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(result["content"])
                    messagebox.showinfo("成功", f"Markdown报告已导出到：\n{path}")

            elif fmt == "html":
                from app.models.suggestions import Defect, CommentSuggestion
                score = QualityScore(**{k: v for k, v in score_data.items()
                                        if k in ("score", "dimensions", "defect_stats", "summary")})
                defects = [Defect.from_dict(d) if isinstance(d, dict) else d
                           for d in self._current_task.get("defects", [])]
                suggestions = [CommentSuggestion.from_dict(s) if isinstance(s, dict) else s
                               for s in self._current_task.get("suggestions", [])]
                result = export_service.export_html_report(
                    score, defects, suggestions,
                    self._current_task.get("original_code", ""),
                    self._current_task.get("annotated_code", ""),
                )
                path = filedialog.asksaveasfilename(
                    title="导出HTML报告",
                    defaultextension=".html",
                    filetypes=[("HTML", "*.html"), ("所有文件", "*.*")],
                    initialfile="report.html",
                )
                if path:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(result["content"])
                    messagebox.showinfo("成功", f"HTML报告已导出到：\n{path}")

            # 恢复窗口层级
            root.attributes("-topmost", False)

        except Exception as e:
            root.attributes("-topmost", False)
            messagebox.showerror("导出失败", str(e))


# ========================
# Tab 2: 历史记录页
# ========================

class HistoryPage(ttk.Frame):
    """历史记录标签页"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._records = []
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text="分析历史记录", font=("Microsoft YaHei", 13, "bold")).pack(fill=tk.X, pady=8)

        columns = ("filename", "language", "score", "suggestions", "defects", "time")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=15)
        self.tree.heading("filename", text="文件名")
        self.tree.heading("language", text="语言")
        self.tree.heading("score", text="评分")
        self.tree.heading("suggestions", text="建议数")
        self.tree.heading("defects", text="缺陷数")
        self.tree.heading("time", text="分析时间")

        self.tree.column("filename", width=180, minwidth=100)
        self.tree.column("language", width=80, minwidth=60)
        self.tree.column("score", width=80, minwidth=50)
        self.tree.column("suggestions", width=80, minwidth=50)
        self.tree.column("defects", width=80, minwidth=50)
        self.tree.column("time", width=160, minwidth=100)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(btn_frame, text="删除选中", command=self._delete_selected).pack(side=tk.RIGHT, padx=4)

        self.status = ttk.Label(btn_frame, text="")
        self.status.pack(side=tk.LEFT)

    def add_record(self, task_data: dict):
        record = {
            "filename": task_data.get("ingest", {}).get("filename", "unknown"),
            "language": task_data.get("ingest", {}).get("language", "unknown"),
            "score": task_data.get("score", {}).get("score", 0),
            "suggestions": len(task_data.get("suggestions", [])),
            "defects": len(task_data.get("defects", [])),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "_raw": task_data,
        }
        self._records.insert(0, record)
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for r in self._records:
            self.tree.insert("", "end", values=(
                r["filename"], r["language"], f"{r['score']:.1f}",
                r["suggestions"], r["defects"], r["time"],
            ))
        self.status.config(text=f"共 {len(self._records)} 条记录")

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("确认", "删除选中的历史记录？"):
            return
        for item in sel:
            idx = self.tree.index(item)
            if 0 <= idx < len(self._records):
                del self._records[idx]
        self._refresh()


# ========================
# Tab 3: 模型设置页
# ========================

class ModelSettingsPage(ttk.Frame):
    """模型设置标签页"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._providers = []
        self._selected_id = None
        self._build_ui()
        self._load_providers()

    def _build_ui(self):
        ttk.Label(self, text="模型设置", font=("Microsoft YaHei", 13, "bold")).pack(fill=tk.X, pady=8)

        # 左右分栏
        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 左侧：供应商列表
        left = ttk.LabelFrame(main, text="供应商列表")
        self.provider_listbox = tk.Listbox(left, font=("Microsoft YaHei", 11), height=15, width=20)
        self.provider_listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.provider_listbox.bind("<<ListboxSelect>>", self._on_select_provider)
        ttk.Button(left, text="+ 添加供应商", command=self._add_provider).pack(fill=tk.X, padx=4, pady=4)
        main.add(left, weight=0)

        # 右侧：详情面板
        right = ttk.LabelFrame(main, text="配置详情")
        right_inner = ttk.Frame(right)
        right_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 供应商名
        row = ttk.Frame(right_inner)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="名称:", width=8).pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        ttk.Label(row, textvariable=self.name_var, font=("Microsoft YaHei", 12, "bold")).pack(side=tk.LEFT, padx=8)
        self.enable_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="启用", variable=self.enable_var, command=self._toggle_enable).pack(side=tk.RIGHT)

        # Base URL
        row = ttk.Frame(right_inner)
        row.pack(fill=tk.X, pady=6)
        ttk.Label(row, text="Base URL:", width=10).pack(side=tk.LEFT)
        self.base_url_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.base_url_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # API 格式
        row = ttk.Frame(right_inner)
        row.pack(fill=tk.X, pady=6)
        ttk.Label(row, text="API 格式:", width=10).pack(side=tk.LEFT)
        self.api_format_var = tk.StringVar(value="openai_chat")
        ttk.Combobox(row, textvariable=self.api_format_var,
                      values=["openai_chat", "anthropic_messages", "google_genai", "custom"],
                      width=30, state="readonly").pack(side=tk.LEFT, padx=4)

        # API Key
        row = ttk.Frame(right_inner)
        row.pack(fill=tk.X, pady=6)
        ttk.Label(row, text="API Key:", width=10).pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.api_key_var, show="•", width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        ttk.Separator(right_inner).pack(fill=tk.X, pady=10)

        # 模型列表
        ttk.Label(right_inner, text="模型列表", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=4)

        columns = ("model_id", "context", "vision", "enabled")
        self.model_tree = ttk.Treeview(right_inner, columns=columns, show="headings", height=5)
        self.model_tree.heading("model_id", text="模型ID")
        self.model_tree.heading("context", text="上下文")
        self.model_tree.heading("vision", text="视觉")
        self.model_tree.heading("enabled", text="启用")
        self.model_tree.column("model_id", width=150)
        self.model_tree.column("context", width=80)
        self.model_tree.column("vision", width=50)
        self.model_tree.column("enabled", width=50)
        self.model_tree.pack(fill=tk.X, pady=4)

        btn_row = ttk.Frame(right_inner)
        btn_row.pack(fill=tk.X, pady=4)
        ttk.Button(btn_row, text="+ 添加模型", command=self._add_model).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="测试连接", command=self._test_connection).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="保存", command=self._save_provider).pack(side=tk.RIGHT, padx=2)

        main.add(right, weight=1)

    def _load_providers(self):
        from app.models.llm_provider import provider_store
        self._providers = provider_store.list_providers()
        self.provider_listbox.delete(0, tk.END)
        for p in self._providers:
            icon = "●" if p.enabled else "○"
            prefix = "  " if p.provider_type == "custom" else ""
            self.provider_listbox.insert(tk.END, f"{prefix}{p.provider_name} {icon}")

    def _on_select_provider(self, event):
        sel = self.provider_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._providers):
            p = self._providers[idx]
            self._selected_id = p.provider_id
            self.name_var.set(p.provider_name)
            self.base_url_var.set(p.base_url)
            self.api_format_var.set(p.api_format)
            self.api_key_var.set(p.api_key)
            self.enable_var.set(p.enabled)

            # 更新模型列表
            self.model_tree.delete(*self.model_tree.get_children())
            for m in p.models:
                self.model_tree.insert("", "end", values=(
                    m.model_id,
                    f"{m.max_context // 1000}K" if m.max_context >= 1000 else m.max_context,
                    "是" if m.has_vision else "否",
                    "✓" if m.enabled else "",
                ))

    def _toggle_enable(self):
        if not self._selected_id:
            return
        from app.models.llm_provider import provider_store
        provider_store.toggle_provider(self._selected_id)
        self._load_providers()

    def _add_provider(self):
        dialog = tk.Toplevel(self)
        dialog.title("添加供应商")
        dialog.geometry("400x300")
        dialog.transient(self.winfo_toplevel())

        ttk.Label(dialog, text="供应商名称:").pack(anchor=tk.W, padx=10, pady=(10, 2))
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(padx=10, fill=tk.X)

        ttk.Label(dialog, text="Base URL:").pack(anchor=tk.W, padx=10, pady=(10, 2))
        url_entry = ttk.Entry(dialog, width=40)
        url_entry.pack(padx=10, fill=tk.X)

        ttk.Label(dialog, text="API Key:").pack(anchor=tk.W, padx=10, pady=(10, 2))
        key_entry = ttk.Entry(dialog, width=40, show="•")
        key_entry.pack(padx=10, fill=tk.X)

        def do_add():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入供应商名称")
                return
            from app.models.llm_provider import provider_store
            provider_store.create_provider({
                "provider_name": name,
                "base_url": url_entry.get().strip(),
                "api_format": "openai_chat",
                "api_key": key_entry.get().strip(),
                "models": [{"model_id": "default", "model_name": "Default", "max_context": 16384, "has_vision": False, "enabled": True}],
            })
            dialog.destroy()
            self._load_providers()

        ttk.Button(dialog, text="确认添加", command=do_add).pack(pady=16)

    def _add_model(self):
        if not self._selected_id:
            messagebox.showwarning("提示", "请先选择供应商")
            return
        dialog = tk.Toplevel(self)
        dialog.title("添加模型")
        dialog.geometry("350x250")
        dialog.transient(self.winfo_toplevel())

        ttk.Label(dialog, text="模型ID:").pack(anchor=tk.W, padx=10, pady=(10, 2))
        id_entry = ttk.Entry(dialog, width=35)
        id_entry.pack(padx=10, fill=tk.X)

        ttk.Label(dialog, text="显示名称:").pack(anchor=tk.W, padx=10, pady=(10, 2))
        name_entry = ttk.Entry(dialog, width=35)
        name_entry.pack(padx=10, fill=tk.X)

        ttk.Label(dialog, text="上下文长度:").pack(anchor=tk.W, padx=10, pady=(10, 2))
        ctx_var = tk.IntVar(value=16384)
        ttk.Spinbox(dialog, textvariable=ctx_var, from_=1024, to=1000000, increment=4096, width=35).pack(padx=10, fill=tk.X)

        vision_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="支持视觉", variable=vision_var).pack(anchor=tk.W, padx=10, pady=8)

        def do_add():
            mid = id_entry.get().strip()
            if not mid:
                messagebox.showwarning("提示", "请输入模型ID")
                return
            from app.models.llm_provider import provider_store
            provider = provider_store.get_provider(self._selected_id)
            if provider:
                provider.models.append({
                    "model_id": mid,
                    "model_name": name_entry.get().strip() or mid,
                    "max_context": ctx_var.get(),
                    "has_vision": vision_var.get(),
                    "enabled": True,
                })
                provider_store.update_provider(self._selected_id, {
                    "models": [m.to_dict() if hasattr(m, 'to_dict') else m for m in provider.models],
                })
            dialog.destroy()
            self._on_select_provider(None)

        ttk.Button(dialog, text="确认", command=do_add).pack(pady=12)

    def _test_connection(self):
        if not self._selected_id:
            return
        messagebox.showinfo("测试连接", f"测试 {self.name_var.get()} 的连接...\n（需要后端服务支持）")

    def _save_provider(self):
        if not self._selected_id:
            return
        from app.models.llm_provider import provider_store
        provider_store.update_provider(self._selected_id, {
            "base_url": self.base_url_var.get(),
            "api_format": self.api_format_var.get(),
            "api_key": self.api_key_var.get(),
            "enabled": self.enable_var.get(),
        })
        self._load_providers()
