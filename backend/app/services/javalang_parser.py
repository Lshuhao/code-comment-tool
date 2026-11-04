"""
javalang Java 解析器 - 高优优化 + JavadocParser 结构化解析
替换原 tree-sitter-java，优势：
1. 纯 Python 实现，无需 Java 运行时
2. 完整的 Java 语法支持（泛型、注解、record 等）
3. 自动提取 Javadoc 并结构化解析（@param/@return/@throws）
4. 精确的方法签名解析（类型、修饰符、参数默认值）
"""
import re
import javalang
from typing import List, Dict, Any, Optional, Tuple

from app.models.unified_ast import UnifiedASTNode, NodeType, ParseResult


# ========================
# Javadoc 结构化解析器
# ========================

class JavadocParser:
    """
    Javadoc 结构化解析
    将 Javadoc 文本解析为结构化数据：
    - description: 描述文本
    - params: [(参数名, 描述)]
    - return_type: 返回值描述
    - throws: [(异常类型, 描述)]
    - tags: 其他标签
    """

    @staticmethod
    def parse(javadoc_text: str) -> Dict[str, Any]:
        """解析 Javadoc 文本"""
        if not javadoc_text:
            return {
                "description": "",
                "params": [],
                "return": None,
                "throws": [],
                "tags": {},
            }

        # 去除 Javadoc 标记
        text = javadoc_text.strip()
        text = re.sub(r'^/\*\*\s*', '', text)
        text = re.sub(r'\s*\*/$', '', text)
        # 去除每行开头的 *
        lines = []
        for line in text.split("\n"):
            line = re.sub(r'^\s*\*\s?', '', line)
            lines.append(line)
        text = "\n".join(lines).strip()

        result = {
            "description": "",
            "params": [],
            "return": None,
            "throws": [],
            "tags": {},
        }

        # 提取 @param
        param_pattern = re.compile(r'@param\s+(\w+)\s+(.*?)(?=\n\s*@|\Z)', re.DOTALL)
        for m in param_pattern.finditer(text):
            result["params"].append({
                "name": m.group(1),
                "description": m.group(2).strip(),
            })

        # 提取 @return / @returns
        return_pattern = re.compile(r'@returns?\s+(.*?)(?=\n\s*@|\Z)', re.DOTALL)
        m = return_pattern.search(text)
        if m:
            result["return"] = m.group(1).strip()

        # 提取 @throws / @exception
        throws_pattern = re.compile(r'@(?:throws|exception)\s+(\w+)\s+(.*?)(?=\n\s*@|\Z)', re.DOTALL)
        for m in throws_pattern.finditer(text):
            result["throws"].append({
                "type": m.group(1),
                "description": m.group(2).strip(),
            })

        # 提取其他标签
        other_pattern = re.compile(r'@(\w+)\s+(.*?)(?=\n\s*@|\Z)', re.DOTALL)
        for m in other_pattern.finditer(text):
            tag = m.group(1)
            if tag not in ("param", "return", "returns", "throws", "exception"):
                result["tags"][tag] = m.group(2).strip()

        # 提取描述（@标签之前的部分）
        desc_end = text.find("\n@")
        if desc_end == -1:
            desc_end = len(text)
        result["description"] = text[:desc_end].strip()

        return result

    @staticmethod
    def check_completeness(javadoc_text: str, actual_params: List[str]) -> Dict[str, Any]:
        """
        检查 Javadoc 完整性
        返回缺失的参数、返回值等
        """
        parsed = JavadocParser.parse(javadoc_text)
        issues = []

        # 检查参数文档
        doc_params = {p["name"] for p in parsed["params"]}
        actual_set = set(actual_params)
        missing_params = actual_set - doc_params
        extra_params = doc_params - actual_set

        if missing_params:
            issues.append({
                "type": "missing_param_doc",
                "params": list(missing_params),
                "message": f"缺少参数文档: {', '.join(missing_params)}",
            })
        if extra_params:
            issues.append({
                "type": "extra_param_doc",
                "params": list(extra_params),
                "message": f"文档中有多余参数: {', '.join(extra_params)}",
            })

        return {
            "parsed": parsed,
            "issues": issues,
            "has_description": bool(parsed["description"]),
            "has_return": parsed["return"] is not None,
            "param_coverage": len(doc_params & actual_set) / len(actual_set) if actual_set else 1.0,
        }


# ========================
# javalang → UnifiedASTNode 转换
# ========================

def _get_line_number(node) -> int:
    """获取节点的行号"""
    pos = getattr(node, 'position', None)
    return pos.line if pos else 0


def _type_to_str(type_obj) -> str:
    """将 javalang 类型对象转为字符串"""
    if type_obj is None:
        return None
    if isinstance(type_obj, javalang.tree.BasicType):
        return type_obj.name
    if isinstance(type_obj, javalang.tree.ReferenceType):
        name = type_obj.name
        if type_obj.sub_type:
            name += "." + type_obj.sub_type
        if type_obj.arguments:
            args = ", ".join(str(a) for a in type_obj.arguments)
            name += f"<{args}>"
        return name
    return str(type_obj)


def parse_with_javalang(source_code: str) -> ParseResult:
    """
    使用 javalang 解析 Java 源代码
    返回 ParseResult，包含结构化的 UnifiedASTNode 树
    """
    try:
        tree = javalang.parse.parse(source_code)
    except javalang.parser.JavaSyntaxError as e:
        return ParseResult(
            language="java",
            nodes=[],
            total_lines=source_code.count("\n") + 1,
            parse_errors=[{"line": e.at[0] if e.at else 0, "message": str(e), "type": "syntax_error"}],
            raw_source=source_code,
        )
    except Exception as e:
        return ParseResult(
            language="java",
            nodes=[],
            total_lines=source_code.count("\n") + 1,
            parse_errors=[{"message": str(e), "type": "parse_error"}],
            raw_source=source_code,
        )

    lines = source_code.split("\n")
    all_nodes = []

    for path, node in tree:
        # 类/接口/枚举
        if isinstance(node, (javalang.tree.ClassDeclaration,
                              javalang.tree.InterfaceDeclaration,
                              javalang.tree.EnumDeclaration)):
            class_line = _get_line_number(node)
            # 找到类的结束行
            class_end_line = class_line
            for _, child in tree:
                child_line = _get_line_number(child)
                if child_line > class_end_line:
                    class_end_line = child_line

            class_node = UnifiedASTNode(
                node_type=NodeType.CLASS,
                name=node.name,
                start_line=class_line,
                end_line=class_end_line,
                source_text="\n".join(lines[max(0, class_line-1):class_end_line]),
                docstring=node.documentation,
                decorators=list(node.modifiers) if node.modifiers else [],
                scope_path=[node.name],
            )

            # 解析类成员
            if node.body:
                for member in node.body:
                    if isinstance(member, javalang.tree.MethodDeclaration):
                        method_node = _parse_method(member, lines, [node.name])
                        if method_node:
                            class_node.children.append(method_node)
                    elif isinstance(member, javalang.tree.ConstructorDeclaration):
                        method_node = _parse_constructor(member, lines, [node.name])
                        if method_node:
                            class_node.children.append(method_node)
                    elif isinstance(member, javalang.tree.FieldDeclaration):
                        field_node = _parse_field(member, lines, [node.name])
                        if field_node:
                            class_node.children.append(field_node)

            all_nodes.append(class_node)

        # 顶层方法（不太常见但在某些情况下存在）
        # javalang 通常不会解析顶层方法

    return ParseResult(
        language="java",
        nodes=all_nodes,
        total_lines=len(lines),
        raw_source=source_code,
    )


def _parse_method(method, lines: List[str], scope: List[str]) -> Optional[UnifiedASTNode]:
    """解析方法声明"""
    line = _get_line_number(method)
    if line == 0:
        return None

    params = []
    if method.parameters:
        for p in method.parameters:
            params.append({
                "name": p.name,
                "type": _type_to_str(p.type),
                "default": None,
            })

    return_type = _type_to_str(method.return_type)
    decorators = list(method.modifiers) if method.modifiers else []

    # 估算结束行
    end_line = line + 5  # 粗略估计

    return UnifiedASTNode(
        node_type=NodeType.METHOD,
        name=method.name,
        start_line=line,
        end_line=end_line,
        source_text="\n".join(lines[max(0, line-1):end_line]),
        parameters=params,
        return_type=return_type,
        decorators=decorators,
        docstring=method.documentation,
        scope_path=scope + [method.name],
    )


def _parse_constructor(constructor, lines: List[str], scope: List[str]) -> Optional[UnifiedASTNode]:
    """解析构造方法"""
    line = _get_line_number(constructor)
    if line == 0:
        return None

    params = []
    if constructor.parameters:
        for p in constructor.parameters:
            params.append({
                "name": p.name,
                "type": _type_to_str(p.type),
                "default": None,
            })

    end_line = line + 5

    return UnifiedASTNode(
        node_type=NodeType.METHOD,
        name=constructor.name,
        start_line=line,
        end_line=end_line,
        source_text="\n".join(lines[max(0, line-1):end_line]),
        parameters=params,
        return_type="void",
        decorators=list(constructor.modifiers) if constructor.modifiers else [],
        docstring=constructor.documentation,
        scope_path=scope + [constructor.name],
    )


def _parse_field(field, lines: List[str], scope: List[str]) -> Optional[UnifiedASTNode]:
    """解析字段声明"""
    line = _get_line_number(field)
    if line == 0:
        return None

    for decl in field.declarators:
        return UnifiedASTNode(
            node_type=NodeType.STATEMENT,
            name=decl.name,
            start_line=line,
            end_line=line,
            source_text=lines[max(0, line-1)] if line <= len(lines) else "",
            scope_path=scope + [decl.name],
            metadata={"type": _type_to_str(field.type), "javadoc": field.documentation},
        )
    return None
