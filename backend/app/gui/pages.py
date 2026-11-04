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

        root = self.winfo_toplevel()  # 主窗口引用，用于线程安全的UI更新

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
                root.after(0, lambda: self.status_label.config(text="解析代码..."))

                # M2: 解析
                parse = parse_code(ingest.code_text, ingest.language)
                root.after(0, lambda: self.status_label.config(text="生成注释..."))

                # M3: 注释生成（流式）
                llm = LLMClientFactory.create()
                comment_gen = CommentGenerationService(llm_client=llm)
                import asyncio
                loop = asyncio.new_event_loop()
                suggestions = loop.run_until_complete(comment_gen.generate_all(parse))
                loop.close()

                # 获取Token统计
                usage = llm.get_usage() if hasattr(llm, 'get_usage') else None
                token_info = ""
                if usage and usage.total_tokens > 0:
                    token_info = f" | Token: {usage.total_tokens} | 费用: ${usage.cost_usd:.4f}"

                root.after(0, lambda: self.status_label.config(text=f"检测缺陷{token_info}..."))

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
                    "token_info": token_info,
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

                self.status_label.config(
                    text=f"分析完成 | 评分: {result.get('score', {}).get('score', 0):.1f}"
                         f" | 已生成 {len(result.get('suggestions', []))} 条注释"
                         f"{result.get('token_info', '')}"
                )

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
    """历史记录标签页 - 支持JSON持久化存储"""

    _DATA_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "history.json"
    )

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._records = []
        self._load_from_file()
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        ttk.Label(self, text="分析历史记录", font=("Microsoft YaHei", 13, "bold")).pack(fill=tk.X, pady=8)

        columns = ("id", "filename", "language", "score", "suggestions", "defects", "time")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=15)
        self.tree.heading("id", text="ID")
        self.tree.heading("filename", text="文件名")
        self.tree.heading("language", text="语言")
        self.tree.heading("score", text="评分")
        self.tree.heading("suggestions", text="建议数")
        self.tree.heading("defects", text="缺陷数")
        self.tree.heading("time", text="分析时间")

        self.tree.column("id", width=0, minwidth=0, stretch=False)  # 隐藏ID列
        self.tree.column("filename", width=180, minwidth=100)
        self.tree.column("language", width=80, minwidth=60)
        self.tree.column("score", width=80, minwidth=50)
        self.tree.column("suggestions", width=80, minwidth=50)
        self.tree.column("defects", width=80, minwidth=50)
        self.tree.column("time", width=160, minwidth=100)

        # 滚动条和Treeview用Frame包裹，确保布局正确
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 双击查看详情
        self.tree.bind("<Double-1>", lambda e: self._show_detail())

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(btn_frame, text="查看详情", command=self._show_detail).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="删除选中", command=self._delete_selected).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="清空全部", command=self._clear_all).pack(side=tk.RIGHT, padx=4)

        self.status = ttk.Label(btn_frame, text="")
        self.status.pack(side=tk.LEFT)

    def _load_from_file(self):
        """从JSON文件加载历史记录"""
        if os.path.exists(self._DATA_FILE):
            try:
                import json
                with open(self._DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._records = data.get("records", [])
            except Exception:
                self._records = []

    def _save_to_file(self):
        """保存历史记录到JSON文件"""
        try:
            import json
            os.makedirs(os.path.dirname(self._DATA_FILE), exist_ok=True)
            # 不保存 _raw 中的大字段（parse树），只保留摘要
            save_records = []
            for r in self._records:
                rec = {k: v for k, v in r.items() if k != "_raw"}
                save_records.append(rec)
            with open(self._DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"records": save_records}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_record(self, task_data: dict):
        import uuid
        record = {
            "id": str(uuid.uuid4())[:8],
            "filename": task_data.get("ingest", {}).get("filename", "unknown"),
            "language": task_data.get("ingest", {}).get("language", "unknown"),
            "score": task_data.get("score", {}).get("score", 0),
            "suggestions": len(task_data.get("suggestions", [])),
            "defects": len(task_data.get("defects", [])),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "_raw": task_data,
        }
        self._records.insert(0, record)
        self._save_to_file()
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for r in self._records:
            score_color = ""
            s = r.get("score", 0)
            self.tree.insert("", "end", iid=r["id"], values=(
                r["id"], r["filename"], r["language"], f"{s:.1f}",
                r["suggestions"], r["defects"], r["time"],
            ))
        self.status.config(text=f"共 {len(self._records)} 条记录")

    def _get_selected_record(self):
        """获取选中记录的完整数据"""
        sel = self.tree.selection()
        if not sel:
            return None
        record_id = sel[0]
        for r in self._records:
            if r.get("id") == record_id:
                return r
        return None

    def _show_detail(self):
        """查看详情对话框"""
        record = self._get_selected_record()
        if not record:
            messagebox.showinfo("提示", "请先选中一条记录")
            return

        raw = record.get("_raw", {})
        dialog = tk.Toplevel(self)
        dialog.title(f"分析详情 - {record['filename']}")
        dialog.geometry("700x500")
        dialog.transient(self.winfo_toplevel())

        # 评分信息
        info_frame = ttk.LabelFrame(dialog, text="评分信息")
        info_frame.pack(fill=tk.X, padx=8, pady=4)
        score = record.get("score", 0)
        dims = raw.get("score", {}).get("dimensions", {})
        ttk.Label(info_frame,
                  text=f"综合评分: {score:.1f}  |  覆盖率: {dims.get('coverage', 0):.0f}%  |  "
                       f"完整性: {dims.get('completeness', 0):.0f}%  |  "
                       f"一致性: {dims.get('consistency', 0):.0f}%  |  "
                       f"规范性: {dims.get('standard', 0):.0f}%").pack(padx=8, pady=4)

        # 摘要
        summary = raw.get("score", {}).get("summary", "")
        if summary:
            ttk.Label(dialog, text=summary, foreground="#3b82f6", wraplength=650).pack(padx=8, pady=2)

        # 原始代码
        code_frame = ttk.LabelFrame(dialog, text="原始代码")
        code_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        code_text = scrolledtext.ScrolledText(code_frame, wrap=tk.NONE, font=("Consolas", 10), height=12)
        code_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        code_text.insert("1.0", raw.get("original_code", ""))
        code_text.config(state=tk.DISABLED)

        # 注释后代码
        annot_code = raw.get("annotated_code", "")
        if annot_code:
            annot_frame = ttk.LabelFrame(dialog, text="注释后代码")
            annot_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
            annot_text = scrolledtext.ScrolledText(annot_frame, wrap=tk.NONE, font=("Consolas", 10), height=8, bg="#f0fff0")
            annot_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            annot_text.insert("1.0", annot_code)
            annot_text.config(state=tk.DISABLED)

        ttk.Button(dialog, text="关闭", command=dialog.destroy).pack(pady=8)

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中要删除的记录")
            return
        if not messagebox.askyesno("确认", f"删除选中的 {len(sel)} 条记录？"):
            return
        ids_to_delete = set(sel)
        self._records = [r for r in self._records if r.get("id") not in ids_to_delete]
        self._save_to_file()
        self._refresh()

    def _clear_all(self):
        if not self._records:
            return
        if not messagebox.askyesno("确认", "清空所有历史记录？此操作不可恢复。"):
            return
        self._records.clear()
        self._save_to_file()
        self._refresh()


# ========================
# Tab 3: 模型设置页
# ========================

# API 格式友好名称映射
_API_FORMAT_LABELS = {
    "openai_chat": "OpenAI 兼容（DeepSeek / 千问 / 智谱等）",
    "anthropic_messages": "Anthropic Messages",
    "google_genai": "Google Generative AI",
    "custom": "自定义",
}


class ModelSettingsPage(ttk.Frame):
    """模型设置标签页 - 简洁版"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._providers = []
        self._selected_id = None
        self._building = True  # 防止构建时触发自动保存
        self._build_ui()
        self._load_providers()
        self._building = False

    def _build_ui(self):
        # 标题栏
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(header, text="模型设置", font=("Microsoft YaHei", 13, "bold")).pack(side=tk.LEFT, padx=8)
        ttk.Button(header, text="＋ 添加供应商", command=self._add_provider).pack(side=tk.RIGHT, padx=8)

        # 左右分栏
        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # === 左侧：供应商列表 ===
        left_frame = ttk.Frame(main, width=180)
        left_frame.pack_propagate(False)

        ttk.Label(left_frame, text="供应商", font=("Microsoft YaHei", 9, "bold"),
                  foreground="#666").pack(anchor=tk.W, padx=8, pady=(4, 2))

        # 用 Treeview 替代 Listbox，显示更多信息
        columns = ("name", "status")
        self.provider_tree = ttk.Treeview(left_frame, columns=columns, show="tree", selectmode="browse")
        self.provider_tree.column("#0", width=0, minwidth=0)
        self.provider_tree.column("name", width=120)
        self.provider_tree.column("status", width=30)
        self.provider_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.provider_tree.bind("<<TreeviewSelect>>", self._on_select_provider)

        # 分组标签
        self._builtin_id = self.provider_tree.insert("", "end", text="── 内置 ──", open=True, tags=("header",))
        self._custom_id = self.provider_tree.insert("", "end", text="── 自定义 ──", open=True, tags=("header",))
        self.provider_tree.tag_configure("header", foreground="#999", font=("Microsoft YaHei", 9))

        main.add(left_frame, weight=0)

        # === 右侧：配置面板 ===
        right_frame = ttk.Frame(main)
        right_frame.pack(fill=tk.BOTH, expand=True)

        # 空状态提示
        self.empty_label = ttk.Label(right_frame, text="← 请从左侧选择一个供应商",
                                      font=("Microsoft YaHei", 11), foreground="#999")
        self.empty_label.pack(expand=True)

        # 配置内容（初始隐藏）
        self.config_frame = ttk.Frame(right_frame)

        # 名称 + 启用开关
        row = ttk.Frame(self.config_frame)
        row.pack(fill=tk.X, pady=(10, 6))
        self.name_var = tk.StringVar()
        ttk.Label(row, textvariable=self.name_var, font=("Microsoft YaHei", 14, "bold")).pack(side=tk.LEFT)
        self.enable_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="启用", variable=self.enable_var,
                        command=self._auto_save).pack(side=tk.RIGHT)

        # 分隔线
        ttk.Separator(self.config_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # Base URL
        ttk.Label(self.config_frame, text="接口地址", font=("Microsoft YaHei", 9, "bold"),
                  foreground="#666").pack(anchor=tk.W)
        self.base_url_var = tk.StringVar()
        self.base_url_var.trace_add("write", lambda *_: self._auto_save())
        ttk.Entry(self.config_frame, textvariable=self.base_url_var).pack(fill=tk.X, pady=(2, 8))

        # API 格式
        ttk.Label(self.config_frame, text="接口类型", font=("Microsoft YaHei", 9, "bold"),
                  foreground="#666").pack(anchor=tk.W)
        self.api_format_var = tk.StringVar(value="openai_chat")
        self.api_format_var.trace_add("write", lambda *_: self._auto_save())
        format_combo = ttk.Combobox(self.config_frame, textvariable=self.api_format_var,
                                     values=list(_API_FORMAT_LABELS.values()),
                                     state="readonly")
        format_combo.pack(fill=tk.X, pady=(2, 8))
        # 反向映射：显示名 → 值
        self._format_reverse = {v: k for k, v in _API_FORMAT_LABELS.items()}

        # API Key
        ttk.Label(self.config_frame, text="API 密钥", font=("Microsoft YaHei", 9, "bold"),
                  foreground="#666").pack(anchor=tk.W)
        self.api_key_var = tk.StringVar()
        self.api_key_var.trace_add("write", lambda *_: self._auto_save())
        key_frame = ttk.Frame(self.config_frame)
        key_frame.pack(fill=tk.X, pady=(2, 8))
        ttk.Entry(key_frame, textvariable=self.api_key_var, show="•").pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._show_key_btn = ttk.Button(key_frame, text="👁", width=3, command=self._toggle_key_visibility)
        self._show_key_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # 分隔线
        ttk.Separator(self.config_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # 模型列表
        ttk.Label(self.config_frame, text="可用模型", font=("Microsoft YaHei", 9, "bold"),
                  foreground="#666").pack(anchor=tk.W)

        model_columns = ("model_id", "model_name", "context", "vision", "enabled")
        self.model_tree = ttk.Treeview(self.config_frame, columns=model_columns, show="headings", height=6)
        self.model_tree.heading("model_id", text="模型 ID")
        self.model_tree.heading("model_name", text="显示名称")
        self.model_tree.heading("context", text="上下文")
        self.model_tree.heading("vision", text="视觉")
        self.model_tree.heading("enabled", text="启用")
        self.model_tree.column("model_id", width=130)
        self.model_tree.column("model_name", width=120)
        self.model_tree.column("context", width=70)
        self.model_tree.column("vision", width=40)
        self.model_tree.column("enabled", width=40)
        self.model_tree.pack(fill=tk.X, pady=(2, 6))

        # 模型操作按钮
        btn_row = ttk.Frame(self.config_frame)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="＋ 添加模型", command=self._add_model).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="删除模型", command=self._delete_model).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="测试连接", command=self._test_connection).pack(side=tk.LEFT, padx=4)

        self.config_frame.pack(fill=tk.BOTH, expand=True)
        self.config_frame.pack_forget()  # 初始隐藏

        main.add(right_frame, weight=1)

    def _load_providers(self):
        from app.models.llm_provider import provider_store
        self._providers = provider_store.list_providers()

        # 清空列表（保留分组标题）
        for item in self.provider_tree.get_children():
            if item not in (self._builtin_id, self._custom_id):
                self.provider_tree.delete(item)

        for p in self._providers:
            status = "✓" if p.enabled else "○"
            parent = self._custom_id if p.provider_type == "custom" else self._builtin_id
            self.provider_tree.insert(parent, "end", iid=p.provider_id,
                                       values=(p.provider_name, status))

    def _on_select_provider(self, event):
        sel = self.provider_tree.selection()
        if not sel:
            return
        provider_id = sel[0]
        if provider_id in (self._builtin_id, self._custom_id):
            return

        provider = None
        for p in self._providers:
            if p.provider_id == provider_id:
                provider = p
                break
        if not provider:
            return

        self._selected_id = provider_id
        self._building = True

        # 显示配置面板
        self.empty_label.pack_forget()
        self.config_frame.pack(fill=tk.BOTH, expand=True)

        # 填充数据
        self.name_var.set(provider.provider_name)
        self.base_url_var.set(provider.base_url)
        self.api_key_var.set(provider.api_key)
        self.enable_var.set(provider.enabled)

        # API 格式：值 → 显示名
        format_label = _API_FORMAT_LABELS.get(provider.api_format, provider.api_format)
        self.api_format_var.set(format_label)

        # 模型列表
        self.model_tree.delete(*self.model_tree.get_children())
        for m in provider.models:
            ctx = f"{m.max_context // 1000}K" if m.max_context >= 1000 else str(m.max_context)
            self.model_tree.insert("", "end", values=(
                m.model_id,
                m.model_name or m.model_id,
                ctx,
                "✓" if m.has_vision else "",
                "✓" if m.enabled else "",
            ))

        self._building = False

    def _auto_save(self):
        """字段变化时自动保存"""
        if self._building or not self._selected_id:
            return
        from app.models.llm_provider import provider_store
        # 显示名 → 值
        format_value = self._format_reverse.get(self.api_format_var.get(), self.api_format_var.get())
        provider_store.update_provider(self._selected_id, {
            "base_url": self.base_url_var.get(),
            "api_format": format_value,
            "api_key": self.api_key_var.get(),
            "enabled": self.enable_var.get(),
        })
        # 刷新左侧状态图标
        self._load_providers()

    def _toggle_key_visibility(self):
        """切换 API Key 显示/隐藏"""
        for child in self.config_frame.winfo_children():
            if isinstance(child, ttk.Frame):
                for sub in child.winfo_children():
                    if isinstance(sub, ttk.Entry):
                        if sub.cget("show") == "•":
                            sub.config(show="")
                            self._show_key_btn.config(text="🔒")
                            return
                        else:
                            sub.config(show="•")
                            self._show_key_btn.config(text="👁")
                            return

    def _add_provider(self):
        dialog = tk.Toplevel(self)
        dialog.title("添加供应商")
        dialog.geometry("420x280")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        ttk.Label(dialog, text="添加新供应商", font=("Microsoft YaHei", 12, "bold")).pack(pady=12)

        fields = {}
        for label, key in [("供应商名称", "name"), ("接口地址", "url"), ("API 密钥", "key")]:
            ttk.Label(dialog, text=label).pack(anchor=tk.W, padx=20, pady=(8, 2))
            entry = ttk.Entry(dialog, width=45)
            entry.pack(padx=20, fill=tk.X)
            fields[key] = entry

        def do_add():
            name = fields["name"].get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入供应商名称", parent=dialog)
                return
            from app.models.llm_provider import provider_store
            provider_store.create_provider({
                "provider_name": name,
                "provider_type": "custom",
                "base_url": fields["url"].get().strip(),
                "api_format": "openai_chat",
                "api_key": fields["key"].get().strip(),
                "models": [{"model_id": "default", "model_name": "Default Model",
                            "max_context": 16384, "has_vision": False, "enabled": True}],
            })
            dialog.destroy()
            self._load_providers()
            # 自动选中新添加的供应商
            for child in self.provider_tree.get_children(self._custom_id):
                self.provider_tree.selection_set(child)
                break
            self._on_select_provider(None)

    def _delete_model(self):
        """删除选中的模型"""
        sel = self.model_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在模型列表中选一个模型")
            return
        if not messagebox.askyesno("确认", "删除选中的模型？"):
            return

        from app.models.llm_provider import provider_store
        provider = provider_store.get_provider(self._selected_id)
        if not provider:
            return

        # 获取选中模型的 ID
        selected_ids = set()
        for item in sel:
            vals = self.model_tree.item(item)["values"]
            selected_ids.add(vals[0])

        # 过滤掉选中的模型（兼容 dict 和对象）
        provider.models = [m for m in provider.models
                          if (m.get("model_id") if isinstance(m, dict) else m.model_id) not in selected_ids]

        provider_store.update_provider(self._selected_id, {
            "models": [m.to_dict() if hasattr(m, 'to_dict') else m for m in provider.models],
        })
        self._load_providers()
        self._on_select_provider(None)

        ttk.Button(dialog, text="确认添加", command=do_add).pack(pady=16)

    def _add_model(self):
        if not self._selected_id:
            messagebox.showwarning("提示", "请先选择供应商")
            return
        dialog = tk.Toplevel(self)
        dialog.title("添加模型")
        dialog.geometry("380x260")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        ttk.Label(dialog, text="添加新模型", font=("Microsoft YaHei", 12, "bold")).pack(pady=12)

        ttk.Label(dialog, text="模型 ID").pack(anchor=tk.W, padx=20, pady=(8, 2))
        id_entry = ttk.Entry(dialog, width=40)
        id_entry.pack(padx=20, fill=tk.X)

        ttk.Label(dialog, text="显示名称").pack(anchor=tk.W, padx=20, pady=(8, 2))
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(padx=20, fill=tk.X)

        ttk.Label(dialog, text="上下文长度").pack(anchor=tk.W, padx=20, pady=(8, 2))
        ctx_var = tk.IntVar(value=16384)
        ttk.Spinbox(dialog, textvariable=ctx_var, from_=1024, to=1000000, increment=4096, width=38).pack(padx=20, fill=tk.X)

        vision_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="支持视觉（图片输入）", variable=vision_var).pack(anchor=tk.W, padx=20, pady=8)

        def do_add():
            mid = id_entry.get().strip()
            if not mid:
                messagebox.showwarning("提示", "请输入模型 ID", parent=dialog)
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

        ttk.Button(dialog, text="确认", command=do_add).pack(pady=16)

    def _test_connection(self):
        if not self._selected_id:
            messagebox.showwarning("提示", "请先选择供应商")
            return

        # 获取第一个启用的模型
        model_id = ""
        for item in self.model_tree.get_children():
            vals = self.model_tree.item(item)["values"]
            if vals[4] == "✓":
                model_id = vals[0]
                break

        if not model_id:
            messagebox.showwarning("提示", "请先启用一个模型")
            return

        # 显示值 → 格式值
        format_value = self._format_reverse.get(self.api_format_var.get(), self.api_format_var.get())

        test_dialog = tk.Toplevel(self)
        test_dialog.title("测试连接")
        test_dialog.geometry("320x120")
        test_dialog.transient(self.winfo_toplevel())
        test_dialog.resizable(False, False)
        test_dialog.grab_set()

        status_var = tk.StringVar(value="正在连接...")
        ttk.Label(test_dialog, textvariable=status_var).pack(pady=15)

        def do_test():
            try:
                from app.services.llm_client import DynamicLLMClient
                import asyncio

                client = DynamicLLMClient({
                    "base_url": self.base_url_var.get(),
                    "api_format": format_value,
                    "api_key": self.api_key_var.get(),
                    "model": model_id,
                    "max_tokens": 50,
                    "temperature": 0.1,
                })

                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(client.generate("回复OK", timeout=15))
                loop.close()

                test_dialog.destroy()
                messagebox.showinfo("连接成功",
                    f"供应商: {self.name_var.get()}\n模型: {model_id}\n响应: {result[:80]}")
            except Exception as e:
                test_dialog.destroy()
                messagebox.showerror("连接失败", f"{self.name_var.get()}\n\n{str(e)[:200]}")

        import threading
        threading.Thread(target=do_test, daemon=True).start()
