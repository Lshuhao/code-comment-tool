"""
统一AST中间表示模型 - 全系统契约
定义所有模块共享的数据结构，确保模块间解耦
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class NodeType(str, Enum):
    """节点类型枚举"""
    MODULE = "module"           # 文件/模块
    CLASS = "class"             # 类定义
    FUNCTION = "function"       # 函数定义
    METHOD = "method"           # 方法定义
    PARAMETER = "parameter"     # 参数
    DOCSTRING = "docstring"     # 文档字符串
    LINE_COMMENT = "line_comment"    # 行注释
    BLOCK_COMMENT = "block_comment"  # 块注释
    STATEMENT = "statement"     # 普通语句
    COMPLEX_STATEMENT = "complex_statement"  # 复杂语句（条件/循环/嵌套）
    RETURN = "return"           # 返回语句
    IMPORT = "import"           # 导入语句
    ASSIGNMENT = "assignment"   # 赋值语句
    EXPRESSION = "expression"   # 表达式
    DECORATOR = "decorator"     # 装饰器


@dataclass
class UnifiedASTNode:
    """
    统一AST节点 - 全系统的核心数据结构
    所有语言解析后都转换为此格式，作为模块间传递的契约
    """
    node_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    node_type: NodeType = NodeType.STATEMENT
    name: Optional[str] = None           # 函数名/类名/变量名
    start_line: int = 0                   # 起始行号（1-based）
    end_line: int = 0                     # 结束行号（1-based）
    start_col: int = 0                    # 起始列
    end_col: int = 0                      # 结束列
    source_text: str = ""                 # 原始源代码文本
    children: List['UnifiedASTNode'] = field(default_factory=list)
    parent_id: Optional[str] = None       # 父节点ID

    # 函数/类特有属性
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    return_type: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None       # 已有文档字符串
    docstring_node_id: Optional[str] = None  # docstring子节点ID

    # 复杂度分析
    complexity_score: float = 0.0         # 复杂度评分（0-10）
    has_nested: bool = False              # 是否包含嵌套结构

    # 作用域路径，如 ["MyClass", "my_method"]
    scope_path: List[str] = field(default_factory=list)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于JSON序列化）"""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_col": self.start_col,
            "end_col": self.end_col,
            "source_text": self.source_text,
            "children": [c.to_dict() for c in self.children],
            "parent_id": self.parent_id,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "decorators": self.decorators,
            "docstring": self.docstring,
            "docstring_node_id": self.docstring_node_id,
            "complexity_score": self.complexity_score,
            "has_nested": self.has_nested,
            "scope_path": self.scope_path,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedASTNode':
        """从字典重建节点"""
        node = cls(
            node_id=data.get("node_id", ""),
            node_type=NodeType(data["node_type"]),
            name=data.get("name"),
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            start_col=data.get("start_col", 0),
            end_col=data.get("end_col", 0),
            source_text=data.get("source_text", ""),
            parent_id=data.get("parent_id"),
            parameters=data.get("parameters", []),
            return_type=data.get("return_type"),
            decorators=data.get("decorators", []),
            docstring=data.get("docstring"),
            docstring_node_id=data.get("docstring_node_id"),
            complexity_score=data.get("complexity_score", 0.0),
            has_nested=data.get("has_nested", False),
            scope_path=data.get("scope_path", []),
            metadata=data.get("metadata", {}),
        )
        node.children = [
            cls.from_dict(c) for c in data.get("children", [])
        ]
        return node


@dataclass
class ParseResult:
    """AST解析结果 - M2模块的输出"""
    language: str
    nodes: List[UnifiedASTNode]
    total_lines: int
    parse_errors: List[Dict[str, Any]] = field(default_factory=list)
    raw_source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "nodes": [n.to_dict() for n in self.nodes],
            "total_lines": self.total_lines,
            "parse_errors": self.parse_errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParseResult':
        return cls(
            language=data["language"],
            nodes=[UnifiedASTNode.from_dict(n) for n in data.get("nodes", [])],
            total_lines=data.get("total_lines", 0),
            parse_errors=data.get("parse_errors", []),
        )

    def get_all_functions(self) -> List[UnifiedASTNode]:
        """获取所有函数/方法节点"""
        result = []
        for node in self.nodes:
            result.extend(self._collect_functions(node))
        return result

    def _collect_functions(self, node: UnifiedASTNode) -> List[UnifiedASTNode]:
        result = []
        if node.node_type in (NodeType.FUNCTION, NodeType.METHOD):
            result.append(node)
        for child in node.children:
            result.extend(self._collect_functions(child))
        return result

    def get_all_classes(self) -> List[UnifiedASTNode]:
        """获取所有类节点"""
        result = []
        for node in self.nodes:
            result.extend(self._collect_classes(node))
        return result

    def _collect_classes(self, node: UnifiedASTNode) -> List[UnifiedASTNode]:
        result = []
        if node.node_type == NodeType.CLASS:
            result.append(node)
        for child in node.children:
            result.extend(self._collect_classes(child))
        return result

    def get_complex_nodes(self, threshold: float = 3.0) -> List[UnifiedASTNode]:
        """获取复杂度超过阈值的节点"""
        result = []
        for node in self.nodes:
            result.extend(self._collect_complex(node, threshold))
        return result

    def _collect_complex(self, node: UnifiedASTNode, threshold: float) -> List[UnifiedASTNode]:
        result = []
        if node.complexity_score >= threshold:
            result.append(node)
        for child in node.children:
            result.extend(self._collect_complex(child, threshold))
        return result
