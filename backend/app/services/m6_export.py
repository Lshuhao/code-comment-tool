"""
M6 导出模块 - 代码回填、格式导出
职责：
- 按采纳结果回填注释（倒序插入）
- 缩进匹配
- 合法性校验
- 源码/报告/HTML导出
"""
import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from app.models.unified_ast import ParseResult
from app.models.suggestions import (
    CommentSuggestion, SuggestionType, QualityScore
)


@dataclass
class InsertionPoint:
    """注释插入点"""
    line_number: int          # 插入行号（1-based）
    text: str                 # 要插入的注释文本
    indent: str               # 缩进
    node_id: str              # 对应节点ID
    type: SuggestionType      # 插入类型
    replace: bool = False     # 是否替换目标行（用于单行函数重写）


class ExportService:
    """M6 导出服务"""

    def generate_annotated_code(
        self,
        original_code: str,
        suggestions: List[CommentSuggestion],
        parse_result: ParseResult,
        accepted_ids: Optional[List[str]] = None,
    ) -> str:
        """
        生成带注释的代码
        优先使用 LibCST Codemod（保留格式），回退到手动插入
        """
        if accepted_ids is not None:
            suggestions = [s for s in suggestions if s.suggestion_id in accepted_ids]

        if not suggestions:
            return original_code

        # 分离 docstring 建议和行内注释建议
        docstring_suggestions = [
            s for s in suggestions
            if s.type == SuggestionType.DOCSTRING
        ]
        other_suggestions = [
            s for s in suggestions
            if s.type != SuggestionType.DOCSTRING
        ]

        result_code = original_code

        # 1. 先处理行内注释（手动倒序插入，基于原始行号，避免偏移）
        if other_suggestions:
            insertions = self._calculate_insertions(
                other_suggestions, parse_result, result_code
            )
            insertions.sort(key=lambda x: x.line_number, reverse=True)
            lines = result_code.split("\n")
            for ins in insertions:
                lines = self._insert_at(lines, ins)
            result_code = "\n".join(lines)

        # 2. 再用 LibCST Codemod 处理 docstring（按函数名匹配，不受行号影响）
        if docstring_suggestions:
            result_code = self._apply_docstrings_libcst(
                result_code, docstring_suggestions, parse_result
            )

        return result_code

    def _apply_docstrings_libcst(
        self,
        code: str,
        suggestions: List[CommentSuggestion],
        parse_result: ParseResult,
    ) -> str:
        """使用 LibCST Codemod 添加 docstring"""
        try:
            from app.services.libcst_parser import apply_docstrings_with_libcst

            # 构建 {节点ID: docstring文本} 映射
            # 通过 node_id 找到函数名
            node_name_map = {}
            self._build_node_name_map(parse_result.nodes, node_name_map)

            docstrings = {}
            for s in suggestions:
                name = node_name_map.get(s.target_node_id)
                if name:
                    # 清理 docstring 文本（去除引号和缩进）
                    text = s.suggested_text.strip()
                    for q in ['"""', "'''"]:
                        if text.startswith(q) and text.endswith(q):
                            text = text[len(q):-len(q)].strip()
                            break
                    docstrings[name] = text

            if docstrings:
                result = apply_docstrings_with_libcst(code, docstrings)
                # 验证语法
                import ast
                ast.parse(result)
                return result
        except Exception:
            pass

        # 回退到手动插入
        return self._apply_docstrings_manual(code, suggestions, parse_result)

    def _build_node_name_map(self, nodes, name_map: dict):
        """递归构建 node_id → 函数/类名 的映射"""
        for node in nodes:
            if node.name and node.node_type.value in ("function", "method", "class"):
                name_map[node.node_id] = node.name
            self._build_node_name_map(node.children, name_map)

    def _apply_docstrings_manual(
        self,
        code: str,
        suggestions: List[CommentSuggestion],
        parse_result: ParseResult,
    ) -> str:
        """手动插入 docstring（LibCST 不可用时的回退方案）"""
        insertions = self._calculate_insertions(
            suggestions, parse_result, code
        )
        insertions.sort(key=lambda x: x.line_number, reverse=True)
        lines = code.split("\n")
        for ins in insertions:
            lines = self._insert_at(lines, ins)
        return "\n".join(lines)

    def _calculate_insertions(
        self,
        suggestions: List[CommentSuggestion],
        parse_result: ParseResult,
        original_code: str,
    ) -> List[InsertionPoint]:
        """计算所有插入点"""
        insertions = []
        lines = original_code.split("\n")

        # 构建节点ID到节点的映射
        node_map = {}
        self._build_node_map(parse_result.nodes, node_map)

        for suggestion in suggestions:
            node = node_map.get(suggestion.target_node_id)
            if not node:
                continue

            if suggestion.type == SuggestionType.DOCSTRING:
                ins = self._make_docstring_insertion(
                    suggestion, node, lines, parse_result.language
                )
                if ins:
                    insertions.append(ins)

            elif suggestion.type == SuggestionType.INLINE_COMMENT:
                ins = self._make_inline_insertion(
                    suggestion, node, lines, parse_result.language
                )
                if ins:
                    insertions.append(ins)

            elif suggestion.type == SuggestionType.IMPROVE_EXISTING:
                ins = self._make_improve_insertion(
                    suggestion, node, lines, parse_result.language
                )
                if ins:
                    insertions.append(ins)

        return insertions

    def _make_docstring_insertion(
        self,
        suggestion: CommentSuggestion,
        node,
        lines: List[str],
        language: str,
    ) -> Optional[InsertionPoint]:
        """生成docstring插入点 - 插入到函数定义行之后（函数体第一行）"""
        def_idx = node.start_line - 1
        if def_idx >= len(lines):
            return None

        def_line = lines[def_idx]
        def_indent = self._get_indent(def_line)
        body_indent = def_indent + "    "

        # 格式化docstring
        text = suggestion.suggested_text.strip()
        if text.startswith("```"):
            lines_tmp = text.split("\n")
            lines_tmp = [l for l in lines_tmp if not l.strip().startswith("```")]
            text = "\n".join(lines_tmp).strip()

        quote = '"""'
        if text.startswith(quote) or text.startswith("'''"):
            q = text[:3]
            inner = text[3:]
            if inner.endswith(q):
                inner = inner[:-3]
            inner_lines = inner.split("\n")
            formatted_lines = []
            for i, line in enumerate(inner_lines):
                stripped = line.strip()
                if i == 0 and not stripped:
                    formatted_lines.append("")
                else:
                    formatted_lines.append(f"{body_indent}{stripped}")
            text = f"{body_indent}{q}\n" + "\n".join(formatted_lines) + f"\n{body_indent}{q}"
        else:
            text_lines = text.split("\n")
            if len(text_lines) == 1:
                text = f'{body_indent}{quote}{text.strip()}{quote}'
            else:
                formatted = [f'{body_indent}{line}' for line in text_lines]
                text = f'{body_indent}{quote}\n' + "\n".join(formatted) + f'\n{body_indent}{quote}'

        # 检查函数是否单行（def 和 body 在同一行）
        is_single_line = (node.start_line == node.end_line)

        if is_single_line:
            # 单行函数：将 def 行拆分，docstring 插入在 def 之后、body 之前
            import re
            m = re.match(r'^(\s*def\s+\w+\s*\([^)]*\)\s*[:\->\s]*)(.*)', def_line)
            if m:
                def_part = m.group(1).rstrip()
                body_part = m.group(2).strip()
                # 重写为多行：def行 + docstring + body行
                new_text = f"{def_part}\n{text}\n{body_indent}{body_part}"
                insert_line = node.start_line  # 替换原行
                return InsertionPoint(
                    line_number=insert_line,
                    text=new_text,
                    indent=def_indent,
                    node_id=node.node_id,
                    type=SuggestionType.DOCSTRING,
                    replace=True,
                )

        # 多行函数：插入到 def 行之后
        insert_line = node.start_line + 1
        return InsertionPoint(
            line_number=insert_line,
            text=text,
            indent=body_indent,
            node_id=node.node_id,
            type=SuggestionType.DOCSTRING,
        )

    def _make_inline_insertion(
        self,
        suggestion: CommentSuggestion,
        node,
        lines: List[str],
        language: str,
    ) -> Optional[InsertionPoint]:
        """生成行内注释插入点（使用建议的 target_line，支持函数内定位）"""
        # 优先使用 suggestion.target_line（可能定位到函数体内的复杂语句行）
        line_no = suggestion.target_line or node.start_line
        target_idx = line_no - 1
        if target_idx < 0 or target_idx >= len(lines):
            target_idx = node.start_line - 1
            line_no = node.start_line
            if target_idx < 0 or target_idx >= len(lines):
                return None

        target_line = lines[target_idx]
        indent = self._get_indent(target_line)

        # 根据语言选择注释前缀
        prefix = {"python": "#", "java": "//", "cpp": "//"}.get(language, "#")
        text = f"{indent}{prefix} {suggestion.suggested_text.lstrip('#/').strip()}"

        # 插入在目标行之前
        return InsertionPoint(
            line_number=line_no,
            text=text,
            indent=indent,
            node_id=node.node_id,
            type=SuggestionType.INLINE_COMMENT,
        )

    def _make_improve_insertion(
        self,
        suggestion: CommentSuggestion,
        node,
        lines: List[str],
        language: str,
    ) -> Optional[InsertionPoint]:
        """改进已有注释的插入点"""
        if not node.docstring_node_id:
            return None

        # 找到docstring行并替换
        target_idx = node.start_line  # docstring通常在函数定义下一行
        if target_idx >= len(lines):
            return None

        indent = self._get_indent(lines[target_idx]) if target_idx < len(lines) else ""
        body_indent = indent + "    "

        text = suggestion.suggested_text
        if not text.startswith('"""') and not text.startswith("'''"):
            quote = '"""'
            text_lines = text.strip().split("\n")
            if len(text_lines) == 1:
                text = f'{indent}{quote}{text.strip()}{quote}'
            else:
                formatted = [f'{body_indent}{line}' for line in text_lines]
                text = f'{indent}{quote}\n' + "\n".join(formatted) + f'\n{indent}{quote}'

        return InsertionPoint(
            line_number=target_idx + 1,
            text=text,
            indent=indent,
            node_id=node.node_id,
            type=SuggestionType.IMPROVE_EXISTING,
        )

    def _insert_at(self, lines: List[str], ins: InsertionPoint) -> List[str]:
        """在指定行前插入文本（replace=True 时替换目标行）"""
        idx = ins.line_number - 1  # 转为0-based
        idx = max(0, min(idx, len(lines)))

        text_lines = ins.text.split("\n")

        if ins.replace:
            # 替换模式：删除目标行，插入新内容
            new_lines = lines[:idx] + text_lines + lines[idx + 1:]
        else:
            # 插入模式：在目标行前插入
            new_lines = lines[:idx] + text_lines + lines[idx:]
        return new_lines

    def _get_indent(self, line: str) -> str:
        """获取行的缩进"""
        match = re.match(r'^(\s*)', line)
        return match.group(1) if match else ""

    def _build_node_map(self, nodes, node_map: dict):
        """递归构建节点映射"""
        for node in nodes:
            node_map[node.node_id] = node
            self._build_node_map(node.children, node_map)

    def validate_code(self, code: str, language: str) -> Dict[str, Any]:
        """验证生成代码的合法性"""
        result = {"valid": True, "errors": [], "warnings": []}

        if language == "python":
            try:
                import ast
                ast.parse(code)
            except SyntaxError as e:
                result["valid"] = False
                result["errors"].append({
                    "line": e.lineno,
                    "message": f"语法错误: {e.msg}",
                })

        return result

    def export_source(
        self,
        code: str,
        filename: str,
        language: str,
    ) -> Dict[str, Any]:
        """导出源代码文件"""
        ext_map = {
            "python": ".py",
            "java": ".java",
            "cpp": ".cpp",
        }
        ext = ext_map.get(language, ".txt")
        base_name = os.path.splitext(filename)[0]
        output_filename = f"{base_name}_annotated{ext}"

        return {
            "filename": output_filename,
            "content": code,
            "content_type": "text/plain",
            "language": language,
        }

    def export_markdown_report(
        self,
        score: QualityScore,
        defects: list,
        suggestions: list,
        filename: str = "report.md",
    ) -> Dict[str, Any]:
        """导出Markdown分析报告"""
        lines = []
        lines.append("# 代码注释质量分析报告\n")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append("")

        # 总体评分
        lines.append("## 总体评分\n")
        level = "优秀" if score.score >= 90 else "良好" if score.score >= 75 else "一般" if score.score >= 60 else "需要改进"
        lines.append(f"- **综合评分**: {score.score}/100（{level}）")
        lines.append(f"- **覆盖率**: {score.dimensions.get('coverage', 0)}%")
        lines.append(f"- **完整性**: {score.dimensions.get('completeness', 0)}%")
        lines.append(f"- **一致性**: {score.dimensions.get('consistency', 0)}%")
        lines.append(f"- **规范性**: {score.dimensions.get('standard', 0)}%")
        lines.append("")

        # 缺陷统计
        if score.defect_stats:
            lines.append("## 缺陷统计\n")
            lines.append("| 缺陷类型 | 数量 |")
            lines.append("|---------|------|")
            for dtype, count in sorted(score.defect_stats.items(), key=lambda x: -x[1]):
                lines.append(f"| {dtype} | {count} |")
            lines.append("")

        # 建议列表
        if suggestions:
            lines.append("## 注释建议\n")
            for i, s in enumerate(suggestions, 1):
                lines.append(f"### {i}. {s.type.value}（第{s.target_line}行）")
                lines.append(f"```")
                lines.append(s.suggested_text)
                lines.append(f"```")
                lines.append(f"*置信度: {s.confidence:.0%}*")
                lines.append("")

        # 评分摘要
        lines.append("## 总结\n")
        lines.append(score.summary)
        lines.append("")

        content = "\n".join(lines)
        return {
            "filename": filename,
            "content": content,
            "content_type": "text/markdown",
        }

    def export_html_report(
        self,
        score: QualityScore,
        defects: list,
        suggestions: list,
        original_code: str = "",
        annotated_code: str = "",
        filename: str = "report.html",
    ) -> Dict[str, Any]:
        """导出HTML分析报告"""
        html = self._build_html_report(
            score, defects, suggestions, original_code, annotated_code
        )
        return {
            "filename": filename,
            "content": html,
            "content_type": "text/html",
        }

    def _build_html_report(
        self,
        score: QualityScore,
        defects: list,
        suggestions: list,
        original_code: str,
        annotated_code: str,
    ) -> str:
        """构建HTML报告"""
        level = "优秀" if score.score >= 90 else "良好" if score.score >= 75 else "一般" if score.score >= 60 else "需要改进"
        score_color = "#22c55e" if score.score >= 90 else "#3b82f6" if score.score >= 75 else "#f59e0b" if score.score >= 60 else "#ef4444"

        defect_rows = ""
        for dtype, count in sorted(score.defect_stats.items(), key=lambda x: -x[1]):
            defect_rows += f"<tr><td>{dtype}</td><td>{count}</td></tr>\n"

        suggestion_html = ""
        for i, s in enumerate(suggestions, 1):
            escaped_text = s.suggested_text.replace("<", "&lt;").replace(">", "&gt;")
            suggestion_html += f"""
            <div class="suggestion-card">
                <h4>{i}. {s.type.value}（第{s.target_line}行）</h4>
                <pre><code>{escaped_text}</code></pre>
                <span class="confidence">置信度: {s.confidence:.0%}</span>
            </div>
            """

        dimension_html = ""
        for dim, val in score.dimensions.items():
            dim_label = {
                "coverage": "覆盖率",
                "completeness": "完整性",
                "consistency": "一致性",
                "standard": "规范性",
            }.get(dim, dim)
            color = "#22c55e" if val >= 80 else "#3b82f6" if val >= 60 else "#f59e0b"
            dimension_html += f"""
            <div class="dimension">
                <div class="dim-label">{dim_label}</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width:{val}%;background:{color}"></div>
                </div>
                <div class="dim-value">{val}%</div>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代码注释质量分析报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f8fafc; color: #1e293b; line-height: 1.6; padding: 2rem; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #0f172a; margin-bottom: 0.5rem; }}
        h2 {{ color: #334155; margin: 2rem 0 1rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }}
        .score-card {{ background: white; border-radius: 12px; padding: 2rem; margin: 1rem 0;
                      box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
        .score-number {{ font-size: 4rem; font-weight: bold; color: {score_color}; }}
        .score-level {{ font-size: 1.2rem; color: #64748b; }}
        .dimensions {{ display: grid; gap: 1rem; margin: 1rem 0; }}
        .dimension {{ display: flex; align-items: center; gap: 1rem; }}
        .dim-label {{ width: 80px; font-weight: 500; }}
        .progress-bar {{ flex: 1; height: 24px; background: #e2e8f0; border-radius: 12px; overflow: hidden; }}
        .progress-fill {{ height: 100%; border-radius: 12px; transition: width 0.3s; }}
        .dim-value {{ width: 50px; text-align: right; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f1f5f9; font-weight: 600; }}
        .suggestion-card {{ background: white; border-radius: 8px; padding: 1.5rem; margin: 1rem 0;
                           box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .suggestion-card pre {{ background: #f8fafc; padding: 1rem; border-radius: 6px;
                               overflow-x: auto; margin: 0.5rem 0; }}
        .confidence {{ color: #64748b; font-size: 0.875rem; }}
        .summary {{ background: #eff6ff; border-left: 4px solid #3b82f6; padding: 1rem; margin: 1rem 0;
                   border-radius: 0 8px 8px 0; }}
        .timestamp {{ color: #94a3b8; font-size: 0.875rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📝 代码注释质量分析报告</h1>
        <p class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="score-card">
            <div class="score-number">{score.score}</div>
            <div class="score-level">{level}</div>
        </div>

        <h2>📊 维度评分</h2>
        <div class="dimensions">
            {dimension_html}
        </div>

        <h2>🔍 缺陷统计</h2>
        <table>
            <thead><tr><th>缺陷类型</th><th>数量</th></tr></thead>
            <tbody>{defect_rows}</tbody>
        </table>

        <h2>💡 注释建议</h2>
        {suggestion_html if suggestion_html else '<p>暂无建议</p>'}

        <h2>📋 总结</h2>
        <div class="summary">{score.summary}</div>
    </div>
</body>
</html>"""

    def export_pdf_report(
        self,
        score: QualityScore,
        defects: list,
        suggestions: list,
        filename: str = "report.pdf",
    ) -> Optional[Dict[str, Any]]:
        """
        导出PDF报告（依赖WeasyPrint）
        如果WeasyPrint不可用则返回None
        """
        try:
            html_result = self.export_html_report(score, defects, suggestions)
            from weasyprint import HTML
            import io

            html_content = html_result["content"]
            pdf_buffer = io.BytesIO()
            HTML(string=html_content).write_pdf(pdf_buffer)

            return {
                "filename": filename,
                "content": pdf_buffer.getvalue(),
                "content_type": "application/pdf",
            }
        except ImportError:
            return None
        except Exception:
            return None


# 全局单例
export_service = ExportService()
