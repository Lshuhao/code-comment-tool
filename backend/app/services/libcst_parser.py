"""
LibCST Python 解析器 - 高优优化
替换原 tree-sitter Python 解析，优势：
1. 保留所有空白、注释、格式的精确位置
2. 直接在节点上添加/修改注释，无需手动计算缩进
3. 自动处理单行函数、装饰器、类型注解等边界情况

同时提供 LibCST Codemod 框架用于批量代码变换。
"""
import libcst as cst
import libcst.matchers as m
from libcst.metadata import PositionProvider
from typing import List, Dict, Any, Optional

from app.models.unified_ast import UnifiedASTNode, NodeType, ParseResult


# ========================
# LibCST → UnifiedASTNode 转换
# ========================

class LibCSTVisitor(cst.CSTVisitor):
    """
    LibCST 访问器 - 将 LibCST 树转换为 UnifiedASTNode
    保留所有格式信息用于后续精确插入
    """
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, source: str):
        self.source = source
        self.source_lines = source.split("\n")
        self.nodes: List[UnifiedASTNode] = []
        self._scope_stack: List[str] = []
        self._all_functions: List[UnifiedASTNode] = []
        self._all_classes: List[UnifiedASTNode] = []

    def _get_offset(self, line: int, col: int) -> int:
        """将 (line, col) 转换为字节偏移"""
        offset = 0
        for i in range(1, line):
            if i <= len(self.source_lines):
                offset += len(self.source_lines[i - 1]) + 1  # +1 for \n
        offset += col
        return min(offset, len(self.source))

    def _get_source_text(self, pos) -> str:
        """从位置信息提取源代码文本"""
        start = self._get_offset(pos.start.line, pos.start.column)
        end = self._get_offset(pos.end.line, pos.end.column)
        return self.source[start:end]

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        name = node.name.value
        self._scope_stack.append(name)

        # 获取位置信息
        pos = self.get_metadata(PositionProvider, node)
        start_line = pos.start.line
        end_line = pos.end.line

        # 提取参数
        params = self._extract_params(node.params)

        # 提取返回值类型
        return_type = None
        if node.returns:
            return_type = self._annotation_to_str(node.returns)

        # 提取装饰器
        decorators = [
            self._decorator_to_str(d.decorator)
            for d in node.decorators
        ]

        # 提取已有 docstring
        docstring = self._extract_docstring(node)

        # 获取源码
        source_text = self._get_source_text(pos)

        # 计算复杂度
        complexity = self._calc_complexity(node)

        func_type = NodeType.METHOD if len(self._scope_stack) > 1 else NodeType.FUNCTION

        func_node = UnifiedASTNode(
            node_type=func_type,
            name=name,
            start_line=start_line,
            end_line=end_line,
            start_col=pos.start.column,
            end_col=pos.end.column,
            source_text=source_text,
            parameters=params,
            return_type=return_type,
            decorators=decorators,
            docstring=docstring,
            complexity_score=complexity,
            has_nested=complexity >= 3.0,
            scope_path=list(self._scope_stack),
        )

        self._all_functions.append(func_node)
        return True  # 继续访问子节点

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        if self._scope_stack:
            self._scope_stack.pop()

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        name = node.name.value
        self._scope_stack.append(name)

        pos = self.get_metadata(PositionProvider, node)
        start_line = pos.start.line
        end_line = pos.end.line
        source_text = self._get_source_text(pos)
        docstring = self._extract_docstring(node)
        decorators = [
            self._decorator_to_str(d.decorator)
            for d in node.decorators
        ]

        class_node = UnifiedASTNode(
            node_type=NodeType.CLASS,
            name=name,
            start_line=start_line,
            end_line=end_line,
            source_text=source_text,
            docstring=docstring,
            decorators=decorators,
            scope_path=list(self._scope_stack),
        )

        self._all_classes.append(class_node)
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        if self._scope_stack:
            self._scope_stack.pop()

    def visit_Import(self, node: cst.Import) -> bool:
        pos = self.get_metadata(PositionProvider, node)
        names = ", ".join(
            name.name.value if hasattr(name, 'name') else str(name)
            for name in node.names
        )
        self.nodes.append(UnifiedASTNode(
            node_type=NodeType.IMPORT,
            name=names,
            start_line=pos.start.line,
            end_line=pos.end.line,
            source_text=self._get_source_text(pos),
            scope_path=list(self._scope_stack),
        ))
        return False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        pos = self.get_metadata(PositionProvider, node)
        module = node.module.value if node.module else ""
        names = ", ".join(
            name.name.value if hasattr(name, 'name') else str(name)
            for name in node.names
        )
        self.nodes.append(UnifiedASTNode(
            node_type=NodeType.IMPORT,
            name=f"from {module} import {names}",
            start_line=pos.start.line,
            end_line=pos.end.line,
            source_text=self._get_source_text(pos),
            scope_path=list(self._scope_stack),
        ))
        return False

    # ---- 辅助方法 ----

    def _extract_params(self, params: cst.Parameters) -> List[Dict[str, Any]]:
        result = []
        for param in params.params:
            name = param.name.value
            annotation = self._annotation_to_str(param.annotation) if param.annotation else None
            default = "has_default" if param.default else None
            if name != "self":
                result.append({"name": name, "type": annotation, "default": default})
        return result

    def _annotation_to_str(self, annotation) -> str:
        if annotation is None:
            return None
        try:
            # 使用 LibCST 的 Module 来序列化注解
            wrapper = cst.Module(body=[])
            return annotation.annotation.visit(cst.Module(body=[]).__class__)
        except Exception:
            return str(annotation)

    def _decorator_to_str(self, decorator) -> str:
        if isinstance(decorator, cst.Name):
            return decorator.value
        elif isinstance(decorator, cst.Attribute):
            return f"{self._decorator_to_str(decorator.value)}.{decorator.attr.value}"
        elif isinstance(decorator, cst.Call):
            return self._decorator_to_str(decorator.func)
        return "decorator"

    def _extract_docstring(self, node) -> Optional[str]:
        """从函数/类节点提取 docstring"""
        body = node.body
        if isinstance(body, cst.IndentedBlock):
            stmts = body.body
        elif isinstance(body, cst.SimpleStatementSuite):
            stmts = body.body
        else:
            return None

        if not stmts:
            return None

        first_stmt = stmts[0]
        if isinstance(first_stmt, cst.SimpleStatementLine):
            for expr in first_stmt.body:
                if isinstance(expr, cst.Expr):
                    val = expr.value
                    if isinstance(val, (cst.SimpleString, cst.ConcatenatedString)):
                        raw = val.value
                        # 去除引号
                        for q in ['"""', "'''", '"', "'"]:
                            if raw.startswith(q) and raw.endswith(q):
                                return raw[len(q):-len(q)]
                        return raw
        return None

    def _calc_complexity(self, node: cst.FunctionDef) -> float:
        """计算函数复杂度"""
        score = 0.0

        class ComplexityVisitor(cst.CSTVisitor):
            def __init__(self):
                self.score = 0.0
                self.depth = 0

            def visit_If(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1

            def leave_If(self, node):
                self.depth -= 1

            def visit_For(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1

            def leave_For(self, node):
                self.depth -= 1

            def visit_While(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1

            def leave_While(self, node):
                self.depth -= 1

            def visit_Try(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1

            def leave_Try(self, node):
                self.depth -= 1

            def visit_With(self, node):
                self.score += 0.5 + self.depth * 0.3

        visitor = ComplexityVisitor()
        node.body.visit(visitor)
        return min(visitor.score, 10.0)


def parse_with_libcst(source_code: str) -> ParseResult:
    """
    使用 LibCST 解析 Python 源代码
    返回 ParseResult，其中 nodes 包含所有顶层 UnifiedASTNode
    """
    try:
        tree = cst.parse_module(source_code)
    except cst.ParserSyntaxError as e:
        return ParseResult(
            language="python",
            nodes=[],
            total_lines=source_code.count("\n") + 1,
            parse_errors=[{"line": getattr(e, 'line', 0), "message": str(e), "type": "syntax_error"}],
            raw_source=source_code,
        )

    wrapper = cst.MetadataWrapper(tree)
    visitor = LibCSTVisitor(source_code)
    wrapper.visit(visitor)

    # 收集所有顶层节点（import + class + function）
    all_nodes = list(visitor.nodes)

    # 将 class 的子方法关联到 class 节点
    for class_node in visitor._all_classes:
        # 找到 class 的子函数
        for func in visitor._all_functions:
            if (len(func.scope_path) >= 2 and
                    func.scope_path[0] == class_node.name):
                func.node_type = NodeType.METHOD
                func.parent_id = class_node.node_id
                class_node.children.append(func)
        if class_node not in all_nodes:
            all_nodes.append(class_node)

    # 添加不在 class 中的顶层函数
    for func in visitor._all_functions:
        if len(func.scope_path) == 1 and func not in all_nodes:
            all_nodes.append(func)

    return ParseResult(
        language="python",
        nodes=all_nodes,
        total_lines=source_code.count("\n") + 1,
        raw_source=source_code,
    )


# ========================
# LibCST Codemod - 自动添加注释
# ========================

class AddDocstringTransformer(cst.CSTTransformer):
    """
    LibCST Codemod - 自动为缺少 docstring 的函数/类添加文档字符串
    直接操作 CST 节点，保留所有原始格式
    """

    def __init__(self, docstrings: Dict[str, str]):
        """
        docstrings: {函数名: docstring文本} 的映射
        """
        self.docstrings = docstrings
        self.added_count = 0

    def _format_docstring(self, text: str, indent: str) -> str:
        """格式化多行docstring，保留相对缩进"""
        lines = text.strip().split("\n")
        if len(lines) == 1:
            return f'"""{lines[0].strip()}"""'

        # 计算非空行的最小缩进（作为基准）
        min_indent = None
        for line in lines[1:]:
            if line.strip():
                stripped_len = len(line) - len(line.lstrip())
                if min_indent is None or stripped_len < min_indent:
                    min_indent = stripped_len
        if min_indent is None:
            min_indent = 0

        # 首行紧跟引号
        formatted = [f'"""{lines[0].strip()}']
        for line in lines[1:]:
            if not line.strip():
                formatted.append("")
            else:
                # 保留相对缩进：去除基准缩进后，加函数体缩进
                relative = line[min_indent:]
                formatted.append(f"{indent}{relative}")
        formatted.append(f'{indent}"""')
        return "\n".join(formatted)

    def _get_indent_str(self, body) -> str:
        """从 CST 节点获取缩进字符串"""
        if isinstance(body, cst.IndentedBlock) and body.indent:
            indent_obj = body.indent
            if hasattr(indent_obj, "value"):
                return indent_obj.value
            return str(indent_obj)
        return "    "

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        name = original_node.name.value
        if name not in self.docstrings:
            return updated_node

        # 检查是否已有 docstring
        if self._has_docstring(original_node):
            return updated_node

        docstring_text = self.docstrings[name]

        # 获取函数体缩进
        indent = self._get_indent_str(updated_node.body)

        # 构造 docstring 节点（多行时内部行需要正确缩进）
        formatted = self._format_docstring(docstring_text, indent)
        docstring_expr = cst.Expr(
            value=cst.SimpleString(formatted)
        )

        # 在函数体开头插入 docstring
        new_body_stmts = [
            cst.SimpleStatementLine(
                body=[docstring_expr],
                leading_lines=[],
            )
        ]

        if isinstance(updated_node.body, cst.IndentedBlock):
            new_body = updated_node.body.with_changes(
                body=new_body_stmts + list(updated_node.body.body)
            )
        elif isinstance(updated_node.body, cst.SimpleStatementSuite):
            # 单行函数：转换为多行
            new_body = cst.IndentedBlock(
                body=new_body_stmts + [
                    cst.SimpleStatementLine(body=updated_node.body.body)
                ],
                indent=indent,
            )
        else:
            return updated_node

        self.added_count += 1
        return updated_node.with_changes(body=new_body)

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        name = original_node.name.value
        if name not in self.docstrings:
            return updated_node

        if self._has_docstring(original_node):
            return updated_node

        docstring_text = self.docstrings[name]

        indent = self._get_indent_str(updated_node.body)

        formatted = self._format_docstring(docstring_text, indent)
        docstring_expr = cst.Expr(
            value=cst.SimpleString(formatted)
        )

        new_body_stmts = [
            cst.SimpleStatementLine(body=[docstring_expr], leading_lines=[])
        ]

        if isinstance(updated_node.body, cst.IndentedBlock):
            new_body = updated_node.body.with_changes(
                body=new_body_stmts + list(updated_node.body.body)
            )
        else:
            new_body = cst.IndentedBlock(
                body=new_body_stmts + [
                    cst.SimpleStatementLine(body=updated_node.body.body)
                ],
                indent=indent,
            )

        self.added_count += 1
        return updated_node.with_changes(body=new_body)

    def _has_docstring(self, node) -> bool:
        """检查节点是否已有 docstring"""
        body = node.body
        if isinstance(body, cst.IndentedBlock):
            stmts = body.body
        elif isinstance(body, cst.SimpleStatementSuite):
            stmts = body.body
        else:
            return False

        if not stmts:
            return False

        first_stmt = stmts[0]
        if isinstance(first_stmt, cst.SimpleStatementLine):
            for expr in first_stmt.body:
                if isinstance(expr, cst.Expr):
                    val = expr.value
                    if isinstance(val, (cst.SimpleString, cst.ConcatenatedString)):
                        return True
        return False


def apply_docstrings_with_libcst(
    source_code: str,
    docstrings: Dict[str, str],
) -> str:
    """
    使用 LibCST Codemod 将 docstring 添加到源代码
    保留所有原始格式（空白、注释、装饰器等）

    Args:
        source_code: 原始源代码
        docstrings: {函数/类名: docstring文本} 的映射

    Returns:
        添加了 docstring 的新源代码
    """
    try:
        tree = cst.parse_module(source_code)
        transformer = AddDocstringTransformer(docstrings)
        new_tree = tree.visit(transformer)
        return new_tree.code
    except Exception as e:
        # 回退到原始代码
        return source_code
