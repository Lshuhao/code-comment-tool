"""
Tkinter GUI 可复用组件
评分圆环、维度进度条、建议列表、缺陷面板
"""
import tkinter as tk
from tkinter import ttk
import math


# ========================
# 评分圆环组件
# ========================

class ScoreRing(tk.Canvas):
    """圆形评分指示器"""

    def __init__(self, parent, size=120, **kwargs):
        try:
            bg = parent.cget('bg')
        except Exception:
            bg = '#f5f5f5'
        super().__init__(parent, width=size, height=size,
                         bg=bg, highlightthickness=0, **kwargs)
        self.size = size
        self.score = 0
        self._draw(0)

    def set_score(self, score: float):
        self.score = score
        self._draw(score)

    def _draw(self, score: float):
        self.delete("all")
        cx, cy = self.size // 2, self.size // 2
        r = self.size // 2 - 12
        width = 10

        # 背景弧
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=0, extent=360, style="arc",
                        outline="#e0e0e0", width=width)

        # 分数弧
        if score > 0:
            color = self._score_color(score)
            extent = score / 100 * 360
            self.create_arc(cx - r, cy - r, cx + r, cy + r,
                            start=90, extent=-extent, style="arc",
                            outline=color, width=width)

        # 分数文字
        self.create_text(cx, cy - 6, text=f"{score:.1f}",
                         font=("Consolas", 22, "bold"),
                         fill=self._score_color(score))
        level = "优秀" if score >= 90 else "良好" if score >= 75 else "一般" if score >= 60 else "需改进"
        self.create_text(cx, cy + 22, text=level,
                         font=("Microsoft YaHei", 11), fill="#888")

    @staticmethod
    def _score_color(score):
        if score >= 90: return "#22c55e"
        if score >= 75: return "#3b82f6"
        if score >= 60: return "#f59e0b"
        return "#ef4444"


# ========================
# 维度进度条组件
# ========================

class DimensionBar(ttk.Frame):
    """单个维度进度条"""

    def __init__(self, parent, label, icon="", **kwargs):
        super().__init__(parent, **kwargs)
        self.label_text = label

        self.label = ttk.Label(self, text=f"{icon} {label}", width=10)
        self.label.pack(side=tk.LEFT, padx=(0, 8))

        self.progress = ttk.Progressbar(self, orient="horizontal",
                                        mode="determinate", length=180)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self.value_label = ttk.Label(self, text="0%", width=5)
        self.value_label.pack(side=tk.LEFT, padx=(4, 0))

    def set_value(self, value: float):
        self.progress["value"] = value
        self.value_label.config(text=f"{value:.0f}%")


class DimensionPanel(ttk.Frame):
    """四维度评分面板"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.bars = {}
        dims = [
            ("coverage", "覆盖率", "📝"),
            ("completeness", "完整性", "📋"),
            ("consistency", "一致性", ""),
            ("standard", "规范性", "✅"),
        ]
        for i, (key, name, icon) in enumerate(dims):
            bar = DimensionBar(self, name, icon)
            bar.grid(row=i, column=0, padx=4, pady=3, sticky="ew")
            self.bars[key] = bar

    def set_dimensions(self, dims: dict):
        for key, val in dims.items():
            if key in self.bars:
                self.bars[key].set_value(val)


# ========================
# 评分概览组件
# ========================

class ScoreOverview(ttk.Frame):
    """评分概览（圆环 + 四维度）"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.ring = ScoreRing(self, size=130)
        self.ring.pack(side=tk.LEFT, padx=10, pady=5)

        self.dim_panel = DimensionPanel(self)
        self.dim_panel.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)

        self.summary_label = ttk.Label(self, text="", wraplength=500, foreground="#3b82f6")
        self.summary_label.pack(fill=tk.X, padx=10, pady=(0, 5))

    def set_score(self, score_data: dict):
        if not score_data:
            self.ring.set_score(0)
            return
        self.ring.set_score(score_data.get("score", 0))
        self.dim_panel.set_dimensions(score_data.get("dimensions", {}))
        self.summary_label.config(text=score_data.get("summary", ""))


# ========================
# 建议列表组件
# ========================

TYPE_LABELS = {
    "docstring": "文档字符串",
    "inline_comment": "行内注释",
    "block_comment": "块注释",
    "improve_existing": "改进注释",
}

TYPE_COLORS = {
    "docstring": "#3b82f6",
    "inline_comment": "#22c55e",
    "block_comment": "#f59e0b",
    "improve_existing": "#8b5cf6",
}


class SuggestionList(ttk.Frame):
    """注释建议列表"""

    def __init__(self, parent, on_accept=None, on_reject=None, **kwargs):
        super().__init__(parent, **kwargs)

        # 标题栏
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 4))
        self.title_label = ttk.Label(header, text=" 注释建议 (0)", font=("Microsoft YaHei", 11, "bold"))
        self.title_label.pack(side=tk.LEFT)

        ttk.Button(header, text="全部采纳", command=self._accept_all, width=10).pack(side=tk.RIGHT)

        # 列表
        columns = ("id", "type", "line", "text", "confidence", "status")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8)
        self.tree.heading("id", text="ID")
        self.tree.heading("type", text="类型")
        self.tree.heading("line", text="行号")
        self.tree.heading("text", text="建议内容")
        self.tree.heading("confidence", text="置信度")
        self.tree.heading("status", text="状态")

        self.tree.column("id", width=80, minwidth=50)
        self.tree.column("type", width=100, minwidth=60)
        self.tree.column("line", width=50, minwidth=40)
        self.tree.column("text", width=300, minwidth=100)
        self.tree.column("confidence", width=60, minwidth=50)
        self.tree.column("status", width=50, minwidth=40)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 操作按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=4)
        ttk.Button(btn_frame, text="采纳选中", command=self._on_accept).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="忽略选中", command=self._on_reject).pack(side=tk.LEFT, padx=2)

        self._on_accept_cb = on_accept
        self._on_reject_cb = on_reject
        self._suggestions = []
        self._accepted = set()

    def set_suggestions(self, suggestions: list):
        self._suggestions = suggestions
        self._accepted = set()
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for s in self._suggestions:
            status = "✓" if s["suggestion_id"] in self._accepted else ""
            self.tree.insert("", "end", values=(
                s["suggestion_id"][:10],
                TYPE_LABELS.get(s["type"], s["type"]),
                s["target_line"],
                s["suggested_text"][:60],
                f"{s.get('confidence', 0):.0%}",
                status,
            ))
        self.title_label.config(text=f"💡 注释建议 ({len(self._suggestions)})")

    def _on_accept(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item in sel:
            vals = self.tree.item(item)["values"]
            sid = next((s["suggestion_id"] for s in self._suggestions
                        if s["suggestion_id"][:10] == vals[0]), None)
            if sid:
                self._accepted.add(sid)
        self._refresh()
        if self._on_accept_cb:
            self._on_accept_cb(list(self._accepted))

    def _on_reject(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item in sel:
            self.tree.delete(item)
        if self._on_reject_cb:
            self._on_reject_cb()

    def _accept_all(self):
        self._accepted = {s["suggestion_id"] for s in self._suggestions}
        self._refresh()
        if self._on_accept_cb:
            self._on_accept_cb(list(self._accepted))

    def get_accepted_ids(self):
        return list(self._accepted)


# ========================
# 缺陷面板组件
# ========================

SEVERITY_LABELS = {"error": "错误", "warning": "警告", "info": "提示"}
SEVERITY_ICONS = {"error": "🔴", "warning": "🟡", "info": ""}

DEFECT_TYPE_LABELS = {
    "missing_docstring": "缺少文档字符串",
    "missing_param_doc": "缺少参数文档",
    "missing_return_doc": "缺少返回值文档",
    "bad_format": "格式不规范",
    "redundant_comment": "冗余注释",
    "outdated_comment": "过期注释",
    "inconsistent_comment": "不一致注释",
    "todo_comment": "TODO注释",
    "commented_out_code": "被注释的代码",
}


class DefectPanel(ttk.Frame):
    """缺陷检测面板"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # 标题
        self.title_label = ttk.Label(self, text=" 缺陷检测 (0)",
                                     font=("Microsoft YaHei", 11, "bold"))
        self.title_label.pack(fill=tk.X, pady=(0, 4))

        # 统计栏
        self.stats_frame = ttk.Frame(self)
        self.stats_frame.pack(fill=tk.X, pady=2)
        self.error_label = ttk.Label(self.stats_frame, text="")
        self.error_label.pack(side=tk.LEFT, padx=8)
        self.warn_label = ttk.Label(self.stats_frame, text="")
        self.warn_label.pack(side=tk.LEFT, padx=8)
        self.info_label = ttk.Label(self.stats_frame, text="")
        self.info_label.pack(side=tk.LEFT, padx=8)

        # 缺陷列表
        columns = ("severity", "type", "location", "description")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8)
        self.tree.heading("severity", text="级别")
        self.tree.heading("type", text="类型")
        self.tree.heading("location", text="位置")
        self.tree.heading("description", text="描述")

        self.tree.column("severity", width=50, minwidth=40)
        self.tree.column("type", width=120, minwidth=80)
        self.tree.column("location", width=100, minwidth=60)
        self.tree.column("description", width=300, minwidth=100)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 详情
        self.detail_label = ttk.Label(self, text="", wraplength=400, foreground="#666")
        self.detail_label.pack(fill=tk.X, pady=(4, 0))

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._defects = []

    def set_defects(self, defects: list):
        self._defects = defects
        self.tree.delete(*self.tree.get_children())
        counts = {"error": 0, "warning": 0, "info": 0}

        for d in defects:
            counts[d["severity"]] = counts.get(d["severity"], 0) + 1
            self.tree.insert("", "end", values=(
                SEVERITY_ICONS.get(d["severity"], ""),
                DEFECT_TYPE_LABELS.get(d["type"], d["type"]),
                d["location"],
                d["description"][:50],
            ))

        self.title_label.config(text=f"🔍 缺陷检测 ({len(defects)})")
        parts = []
        if counts["error"]: parts.append(f"🔴 {counts['error']}个错误")
        if counts["warning"]: parts.append(f"🟡 {counts['warning']}个警告")
        if counts["info"]: parts.append(f" {counts['info']}个提示")
        self.error_label.config(text=parts[0] if parts else "")
        self.warn_label.config(text=parts[1] if len(parts) > 1 else "")
        self.info_label.config(text=parts[2] if len(parts) > 2 else "")

        if not defects:
            self.detail_label.config(text="✅ 未检测到缺陷")

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self._defects):
            d = self._defects[idx]
            fix = d.get("suggested_fix", "")
            self.detail_label.config(text=f"修复建议: {fix}" if fix else "")
