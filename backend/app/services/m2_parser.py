"""
M2 AST解析层模块 - 多语言AST解析与统一中间表示生成
职责：
- 多语言AST解析（tree-sitter为主）
- 统一UnifiedASTNode中间表示生成
- 复杂度评分、行号映射、scope_path
"""
import re
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

from app.models.unified_ast import (
    UnifiedASTNode, NodeType, ParseResult
)


class LanguageParser(ABC):
    """语言解析器抽象基类"""

    @abstractmethod
    def parse(self, source_code: str) -> ParseResult:
        """解析源代码为统一AST"""
        pass

    @abstractmethod
    def get_language(self) -> str:
        """返回语言标识"""
        pass


class PythonParser(LanguageParser):
    """
    Python解析器 - 使用tree-sitter-python
    如tree-sitter不可用，回退到标准库ast模块
    """

    def get_language(self) -> str:
        return "python"

    def parse(self, source_code: str) -> ParseResult:
        """解析Python源代码"""
        try:
            return self._parse_with_tree_sitter(source_code)
        except Exception:
            return self._parse_with_ast(source_code)

    def _parse_with_tree_sitter(self, source_code: str) -> ParseResult:
        """使用tree-sitter解析"""
        try:
            import tree_sitter_python as tspython
            from tree_sitter import Language, Parser

            PY_LANGUAGE = Language(tspython.language())
            parser = Parser(PY_LANGUAGE)
            tree = parser.parse(bytes(source_code, "utf8"))

            nodes = self._convert_tree(tree.root_node, source_code)
            return ParseResult(
                language="python",
                nodes=nodes,
                total_lines=source_code.count("\n") + 1,
                raw_source=source_code,
            )
        except ImportError:
            raise Exception("tree-sitter not available")

    def _parse_with_ast(self, source_code: str) -> ParseResult:
        """回退：使用Python标准库ast模块"""
        import ast as stdlib_ast

        try:
            tree = stdlib_ast.parse(source_code)
        except SyntaxError as e:
            return ParseResult(
                language="python",
                nodes=[],
                total_lines=source_code.count("\n") + 1,
                parse_errors=[{
                    "line": e.lineno or 0,
                    "message": str(e),
                    "type": "syntax_error",
                }],
                raw_source=source_code,
            )

        nodes = self._convert_stdlib_ast(tree, source_code)
        return ParseResult(
            language="python",
            nodes=nodes,
            total_lines=source_code.count("\n") + 1,
            raw_source=source_code,
        )

    def _convert_tree(self, ts_node, source: str) -> List[UnifiedASTNode]:
        """转换tree-sitter节点为统一节点"""
        nodes = []
        for child in ts_node.children:
            node = self._ts_node_to_unified(child, source)
            if node:
                nodes.append(node)
        return nodes

    def _ts_node_to_unified(
        self, ts_node, source: str, parent_id: str = None, scope: List[str] = None
    ) -> Optional[UnifiedASTNode]:
        """将tree-sitter节点转换为UnifiedASTNode"""
        if scope is None:
            scope = []

        node_type_map = {
            "function_definition": NodeType.FUNCTION,
            "class_definition": NodeType.CLASS,
            "decorated_definition": NodeType.FUNCTION,
            "import_statement": NodeType.IMPORT,
            "import_from_statement": NodeType.IMPORT,
            "expression_statement": NodeType.EXPRESSION,
            "return_statement": NodeType.RETURN,
            "assignment": NodeType.ASSIGNMENT,
            "comment": NodeType.LINE_COMMENT,
            "block_comment": NodeType.BLOCK_COMMENT,
        }

        ts_type = ts_node.type
        node_type = node_type_map.get(ts_type)

        if node_type is None:
            # 递归处理子节点，收集所有结果（展平）
            results = []
            for child in ts_node.children:
                result = self._ts_node_to_unified(child, source, parent_id, scope)
                if result:
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)
            if len(results) == 0:
                return None
            if len(results) == 1:
                return results[0]
            return results  # 返回多个节点

        source_text = source[ts_node.start_byte:ts_node.end_byte]
        name = self._extract_name(ts_node, ts_type)
        current_scope = scope + [name] if name else scope

        # 提取docstring
        docstring = None
        docstring_node_id = None

        # 提取参数（函数节点）
        parameters = []
        if ts_type in ("function_definition", "decorated_definition"):
            parameters = self._extract_parameters(ts_node, source)

        node = UnifiedASTNode(
            node_type=node_type,
            name=name,
            start_line=ts_node.start_point[0] + 1,
            end_line=ts_node.end_point[0] + 1,
            start_col=ts_node.start_point[1],
            end_col=ts_node.end_point[1],
            source_text=source_text,
            parent_id=parent_id,
            parameters=parameters,
            docstring=docstring,
            docstring_node_id=docstring_node_id,
            scope_path=current_scope,
        )

        # 计算复杂度
        node.complexity_score = self._calculate_complexity(ts_node)
        node.has_nested = self._has_nested_structure(ts_node)

        # 递归处理子节点
        for child in ts_node.children:
            child_node = self._ts_node_to_unified(
                child, source, node.node_id, current_scope
            )
            if child_node:
                if isinstance(child_node, list):
                    node.children.extend(child_node)
                else:
                    node.children.append(child_node)
                    # 检查直接子节点是否是docstring
                    if (child.type == "expression_statement" and
                            node.node_type in (NodeType.FUNCTION, NodeType.CLASS, NodeType.METHOD)):
                        expr_text = source[child.start_byte:child.end_byte].strip()
                        if (expr_text.startswith(('"""', "'''")) or
                                expr_text.startswith(('r"""', 'r"""'))):
                            node.docstring = expr_text
                            node.docstring_node_id = child_node.node_id

        # 额外检查：在 block 子节点中查找 docstring（tree-sitter 结构）
        if node.docstring is None and node.node_type in (NodeType.FUNCTION, NodeType.CLASS, NodeType.METHOD):
            for child in ts_node.children:
                if child.type == "block":
                    for block_child in child.children:
                        if block_child.type == "expression_statement":
                            expr_text = source[block_child.start_byte:block_child.end_byte].strip()
                            if expr_text.startswith(('"""', "'''", 'r"""', "r'''")):
                                # 找到对应的已处理子节点
                                for cn in node.children:
                                    if (cn.start_line == block_child.start_point[0] + 1 and
                                            cn.end_line == block_child.end_point[0] + 1):
                                        node.docstring = expr_text
                                        node.docstring_node_id = cn.node_id
                                        break
                            break  # 只检查第一个表达式
                    break

        return node

    def _convert_stdlib_ast(
        self, tree, source: str
    ) -> List[UnifiedASTNode]:
        """使用标准库ast转换（回退方案）"""
        import ast as stdlib_ast

        nodes = []
        for stmt in tree.body:
            node = self._stdlib_stmt_to_unified(stmt, source, scope=[])
            if node:
                nodes.append(node)
        return nodes

    def _stdlib_stmt_to_unified(
        self, stmt, source: str, scope: List[str]
    ) -> Optional[UnifiedASTNode]:
        """将stdlib ast节点转为统一节点"""
        import ast as stdlib_ast

        if isinstance(stmt, stdlib_ast.FunctionDef) or isinstance(stmt, stdlib_ast.AsyncFunctionDef):
            name = stmt.name
            current_scope = scope + [name]
            params = self._extract_stdlib_params(stmt)
            docstring = stdlib_ast.get_docstring(stmt)
            lines = source.split("\n")
            start_line = stmt.lineno
            end_line = getattr(stmt, "end_lineno", stmt.lineno)

            node = UnifiedASTNode(
                node_type=NodeType.FUNCTION,
                name=name,
                start_line=start_line,
                end_line=end_line,
                source_text="\n".join(lines[start_line-1:end_line]),
                parameters=params,
                docstring=docstring,
                scope_path=current_scope,
                decorators=[
                    self._stdlib_decorator_str(d) for d in stmt.decorator_list
                ],
            )
            node.complexity_score = self._stdlib_complexity(stmt)
            node.has_nested = self._stdlib_has_nested(stmt)
            return node

        elif isinstance(stmt, stdlib_ast.ClassDef):
            name = stmt.name
            current_scope = scope + [name]
            docstring = stdlib_ast.get_docstring(stmt)
            lines = source.split("\n")
            start_line = stmt.lineno
            end_line = getattr(stmt, "end_lineno", stmt.lineno)

            node = UnifiedASTNode(
                node_type=NodeType.CLASS,
                name=name,
                start_line=start_line,
                end_line=end_line,
                source_text="\n".join(lines[start_line-1:end_line]),
                docstring=docstring,
                scope_path=current_scope,
                decorators=[
                    self._stdlib_decorator_str(d) for d in stmt.decorator_list
                ],
            )

            # 递归处理类方法
            for child_stmt in stmt.body:
                child_node = self._stdlib_stmt_to_unified(
                    child_stmt, source, current_scope
                )
                if child_node:
                    if child_node.node_type == NodeType.FUNCTION:
                        child_node.node_type = NodeType.METHOD
                    node.children.append(child_node)

            node.complexity_score = self._stdlib_complexity(stmt)
            return node

        elif isinstance(stmt, stdlib_ast.Import):
            names = [alias.name for alias in stmt.names]
            return UnifiedASTNode(
                node_type=NodeType.IMPORT,
                name=", ".join(names),
                start_line=stmt.lineno,
                end_line=getattr(stmt, "end_lineno", stmt.lineno),
                source_text=stdlib_ast.get_source_segment(source, stmt) or "",
                scope_path=scope,
            )

        elif isinstance(stmt, stdlib_ast.ImportFrom):
            module = stmt.module or ""
            names = [alias.name for alias in stmt.names]
            return UnifiedASTNode(
                node_type=NodeType.IMPORT,
                name=f"from {module} import {', '.join(names)}",
                start_line=stmt.lineno,
                end_line=getattr(stmt, "end_lineno", stmt.lineno),
                source_text=stdlib_ast.get_source_segment(source, stmt) or "",
                scope_path=scope,
            )

        return None

    def _extract_name(self, ts_node, ts_type: str) -> Optional[str]:
        """从tree-sitter节点提取名称"""
        for child in ts_node.children:
            if child.type == "identifier":
                return child.text.decode("utf8") if isinstance(child.text, bytes) else child.text
            elif child.type == "name":
                return child.text.decode("utf8") if isinstance(child.text, bytes) else child.text
        return None

    def _extract_parameters(self, ts_node, source: str) -> List[Dict[str, Any]]:
        """提取函数参数"""
        params = []
        for child in ts_node.children:
            if child.type == "parameters":
                for param_child in child.children:
                    if param_child.type == "identifier":
                        name = param_child.text.decode("utf8") if isinstance(param_child.text, bytes) else param_child.text
                        params.append({"name": name, "type": None, "default": None})
                    elif param_child.type == "typed_parameter":
                        name_node = param_child.children[0] if param_child.children else None
                        if name_node:
                            name = name_node.text.decode("utf8") if isinstance(name_node.text, bytes) else name_node.text
                            params.append({"name": name, "type": None, "default": None})
                    elif param_child.type == "default_parameter":
                        for sub in param_child.children:
                            if sub.type == "identifier":
                                name = sub.text.decode("utf8") if isinstance(sub.text, bytes) else sub.text
                                params.append({"name": name, "type": None, "default": "has_default"})
        return params

    def _extract_stdlib_params(self, func_node) -> List[Dict[str, Any]]:
        """从stdlib ast提取参数"""
        params = []
        args = func_node.args
        for arg in args.args:
            if arg.arg != "self":
                params.append({
                    "name": arg.arg,
                    "type": None,
                    "default": None,
                })
        return params

    def _stdlib_decorator_str(self, dec) -> str:
        """将stdlib装饰器转为字符串"""
        import ast as stdlib_ast
        if isinstance(dec, stdlib_ast.Name):
            return dec.id
        elif isinstance(dec, stdlib_ast.Attribute):
            return f"....{dec.attr}"
        elif isinstance(dec, stdlib_ast.Call):
            if isinstance(dec.func, stdlib_ast.Name):
                return dec.func.id
        return "decorator"

    def _calculate_complexity(self, ts_node) -> float:
        """计算节点复杂度（0-10分）"""
        score = 0.0
        complex_types = {
            "if_statement", "elif_clause", "for_statement",
            "while_statement", "try_statement", "with_statement",
            "list_comprehension", "dictionary_comprehension",
        }

        def walk(node, depth=0):
            nonlocal score
            if node.type in complex_types:
                score += 1.0 + depth * 0.5
            for child in node.children:
                walk(child, depth + 1)

        walk(ts_node)
        return min(score, 10.0)

    def _has_nested_structure(self, ts_node) -> bool:
        """检查是否有嵌套结构"""
        nested_types = {
            "if_statement", "for_statement", "while_statement",
            "try_statement", "with_statement",
        }

        def check(node, depth=0):
            if depth > 1 and node.type in nested_types:
                return True
            for child in node.children:
                if check(child, depth + 1):
                    return True
            return False

        return check(ts_node)

    def _stdlib_complexity(self, stmt) -> float:
        """stdlib ast复杂度计算"""
        import ast as stdlib_ast
        score = 0.0

        class ComplexityVisitor(stdlib_ast.NodeVisitor):
            def __init__(self):
                self.score = 0
                self.depth = 0

            def visit_If(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1
                self.generic_visit(node)
                self.depth -= 1

            def visit_For(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1
                self.generic_visit(node)
                self.depth -= 1

            def visit_While(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1
                self.generic_visit(node)
                self.depth -= 1

            def visit_Try(self, node):
                self.score += 1.0 + self.depth * 0.5
                self.depth += 1
                self.generic_visit(node)
                self.depth -= 1

            def visit_With(self, node):
                self.score += 0.5 + self.depth * 0.3
                self.generic_visit(node)

        visitor = ComplexityVisitor()
        visitor.visit(stmt)
        return min(visitor.score, 10.0)

    def _stdlib_has_nested(self, stmt) -> bool:
        """检查stdlib ast嵌套"""
        import ast as stdlib_ast
        for node in stdlib_ast.walk(stmt):
            if isinstance(node, (stdlib_ast.If, stdlib_ast.For, stdlib_ast.While)):
                for child in stdlib_ast.walk(node):
                    if child is not node and isinstance(
                        child, (stdlib_ast.If, stdlib_ast.For, stdlib_ast.While)
                    ):
                        return True
        return False

    def _make_group(self, results: list) -> Optional[UnifiedASTNode]:
        """将多个结果合并"""
        if not results:
            return None
        if len(results) == 1:
            return results[0]
        return results[0]


class JavaParser(LanguageParser):
    """Java解析器 - 使用tree-sitter-java"""

    def get_language(self) -> str:
        return "java"

    def parse(self, source_code: str) -> ParseResult:
        """解析Java源代码"""
        try:
            import tree_sitter_java as tspjava
            from tree_sitter import Language, Parser

            JAVA_LANGUAGE = Language(tspjava.language())
            parser = Parser(JAVA_LANGUAGE)
            tree = parser.parse(bytes(source_code, "utf8"))

            nodes = self._convert_tree(tree.root_node, source_code)
            return ParseResult(
                language="java",
                nodes=nodes,
                total_lines=source_code.count("\n") + 1,
                raw_source=source_code,
            )
        except ImportError:
            return self._parse_with_regex(source_code)

    def _parse_with_regex(self, source_code: str) -> ParseResult:
        """正则回退解析"""
        nodes = []
        lines = source_code.split("\n")

        # 简单正则匹配类和方法
        class_pattern = re.compile(r'(?:public|private|protected)?\s*class\s+(\w+)')
        method_pattern = re.compile(
            r'(?:public|private|protected)?\s*(?:static\s+)?\w+\s+(\w+)\s*\('
        )

        for i, line in enumerate(lines, 1):
            class_match = class_pattern.search(line)
            if class_match:
                nodes.append(UnifiedASTNode(
                    node_type=NodeType.CLASS,
                    name=class_match.group(1),
                    start_line=i,
                    end_line=i,
                    source_text=line.strip(),
                    scope_path=[class_match.group(1)],
                ))

            method_match = method_pattern.search(line)
            if method_match and not class_match:
                name = method_match.group(1)
                if name not in ("if", "for", "while", "switch", "catch"):
                    nodes.append(UnifiedASTNode(
                        node_type=NodeType.METHOD,
                        name=name,
                        start_line=i,
                        end_line=i,
                        source_text=line.strip(),
                        complexity_score=0.0,
                    ))

        return ParseResult(
            language="java",
            nodes=nodes,
            total_lines=len(lines),
            raw_source=source_code,
        )

    def _convert_tree(self, ts_node, source: str) -> List[UnifiedASTNode]:
        """转换tree-sitter节点"""
        nodes = []
        for child in ts_node.children:
            node = self._ts_to_unified(child, source)
            if node:
                nodes.append(node)
        return nodes

    def _ts_to_unified(self, ts_node, source: str, scope: List[str] = None) -> Optional[UnifiedASTNode]:
        if scope is None:
            scope = []

        type_map = {
            "class_declaration": NodeType.CLASS,
            "method_declaration": NodeType.METHOD,
            "constructor_declaration": NodeType.METHOD,
            "interface_declaration": NodeType.CLASS,
            "import_declaration": NodeType.IMPORT,
        }

        node_type = type_map.get(ts_node.type)
        if node_type is None:
            results = []
            for child in ts_node.children:
                r = self._ts_to_unified(child, source, scope)
                if r:
                    results.append(r)
            return results[0] if len(results) == 1 else (results[0] if results else None)

        source_text = source[ts_node.start_byte:ts_node.end_byte]
        name = None
        for child in ts_node.children:
            if child.type == "identifier":
                name = child.text.decode("utf8") if isinstance(child.text, bytes) else child.text
                break

        current_scope = scope + [name] if name else scope

        node = UnifiedASTNode(
            node_type=node_type,
            name=name,
            start_line=ts_node.start_point[0] + 1,
            end_line=ts_node.end_point[0] + 1,
            source_text=source_text,
            scope_path=current_scope,
        )
        node.complexity_score = self._complexity(ts_node)

        for child in ts_node.children:
            child_node = self._ts_to_unified(child, source, current_scope)
            if child_node:
                node.children.append(child_node)

        return node

    def _complexity(self, ts_node) -> float:
        score = 0.0
        complex_types = {"if_statement", "for_statement", "while_statement", "try_statement", "switch_expression"}

        def walk(node, depth=0):
            nonlocal score
            if node.type in complex_types:
                score += 1.0 + depth * 0.5
            for child in node.children:
                walk(child, depth + 1)

        walk(ts_node)
        return min(score, 10.0)


class CppParser(LanguageParser):
    """C++解析器 - 使用tree-sitter-cpp"""

    def get_language(self) -> str:
        return "cpp"

    def parse(self, source_code: str) -> ParseResult:
        """解析C++源代码"""
        try:
            import tree_sitter_cpp as tspcpp
            from tree_sitter import Language, Parser

            CPP_LANGUAGE = Language(tspcpp.language())
            parser = Parser(CPP_LANGUAGE)
            tree = parser.parse(bytes(source_code, "utf8"))

            nodes = self._convert_tree(tree.root_node, source_code)
            return ParseResult(
                language="cpp",
                nodes=nodes,
                total_lines=source_code.count("\n") + 1,
                raw_source=source_code,
            )
        except ImportError:
            return self._parse_with_regex(source_code)

    def _parse_with_regex(self, source_code: str) -> ParseResult:
        """正则回退解析"""
        nodes = []
        lines = source_code.split("\n")

        func_pattern = re.compile(
            r'(?:(?:static|inline|virtual|void|int|bool|char|float|double|std::\w+)\s+)+(\w+)\s*\('
        )
        class_pattern = re.compile(r'(?:class|struct)\s+(\w+)')

        for i, line in enumerate(lines, 1):
            class_match = class_pattern.search(line)
            if class_match:
                nodes.append(UnifiedASTNode(
                    node_type=NodeType.CLASS,
                    name=class_match.group(1),
                    start_line=i,
                    end_line=i,
                    source_text=line.strip(),
                    scope_path=[class_match.group(1)],
                ))

            func_match = func_pattern.search(line)
            if func_match and not class_match:
                name = func_match.group(1)
                if name not in ("if", "for", "while", "switch", "catch", "return"):
                    nodes.append(UnifiedASTNode(
                        node_type=NodeType.FUNCTION,
                        name=name,
                        start_line=i,
                        end_line=i,
                        source_text=line.strip(),
                    ))

        return ParseResult(
            language="cpp",
            nodes=nodes,
            total_lines=len(lines),
            raw_source=source_code,
        )

    def _convert_tree(self, ts_node, source: str) -> List[UnifiedASTNode]:
        nodes = []
        for child in ts_node.children:
            node = self._ts_to_unified(child, source)
            if node:
                nodes.append(node)
        return nodes

    def _ts_to_unified(self, ts_node, source: str, scope: List[str] = None) -> Optional[UnifiedASTNode]:
        if scope is None:
            scope = []

        type_map = {
            "class_specifier": NodeType.CLASS,
            "struct_specifier": NodeType.CLASS,
            "function_definition": NodeType.FUNCTION,
            "declaration": NodeType.STATEMENT,
            "preproc_include": NodeType.IMPORT,
        }

        node_type = type_map.get(ts_node.type)
        if node_type is None:
            for child in ts_node.children:
                r = self._ts_to_unified(child, source, scope)
                if r:
                    return r
            return None

        source_text = source[ts_node.start_byte:ts_node.end_byte]
        name = None
        for child in ts_node.children:
            if child.type in ("identifier", "type_identifier", "field_identifier"):
                name = child.text.decode("utf8") if isinstance(child.text, bytes) else child.text
                break

        current_scope = scope + [name] if name else scope

        node = UnifiedASTNode(
            node_type=node_type,
            name=name,
            start_line=ts_node.start_point[0] + 1,
            end_line=ts_node.end_point[0] + 1,
            source_text=source_text,
            scope_path=current_scope,
        )
        node.complexity_score = self._complexity(ts_node)

        for child in ts_node.children:
            child_node = self._ts_to_unified(child, source, current_scope)
            if child_node:
                node.children.append(child_node)

        return node

    def _complexity(self, ts_node) -> float:
        score = 0.0
        complex_types = {"if_statement", "for_statement", "while_statement", "try_statement", "switch_statement"}

        def walk(node, depth=0):
            nonlocal score
            if node.type in complex_types:
                score += 1.0 + depth * 0.5
            for child in node.children:
                walk(child, depth + 1)

        walk(ts_node)
        return min(score, 10.0)


class ParserFactory:
    """解析器工厂"""

    _parsers = {
        "python": PythonParser,
        "java": JavaParser,
        "cpp": CppParser,
    }

    @classmethod
    def get_parser(cls, language: str) -> LanguageParser:
        """获取语言对应的解析器"""
        parser_class = cls._parsers.get(language)
        if parser_class is None:
            raise ValueError(f"不支持的语言: {language}")
        return parser_class()

    @classmethod
    def parse(cls, code_text: str, language: str) -> ParseResult:
        """直接解析"""
        parser = cls.get_parser(language)
        return parser.parse(code_text)


# 全局便捷函数
def parse_code(code_text: str, language: str) -> ParseResult:
    """全局解析函数"""
    return ParserFactory.parse(code_text, language)
