"""
注释建议与缺陷模型 - M3/M4/M5模块的输入输出结构
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class SuggestionType(str, Enum):
    """建议类型"""
    DOCSTRING = "docstring"           # 函数/类文档字符串
    INLINE_COMMENT = "inline_comment" # 行内注释
    BLOCK_COMMENT = "block_comment"   # 块注释
    IMPROVE_EXISTING = "improve_existing"  # 改进已有注释


class DefectType(str, Enum):
    """缺陷类型"""
    MISSING_DOCSTRING = "missing_docstring"        # 缺少文档字符串
    MISSING_PARAM_DOC = "missing_param_doc"        # 缺少参数文档
    MISSING_RETURN_DOC = "missing_return_doc"      # 缺少返回值文档
    BAD_FORMAT = "bad_format"                      # 格式不规范
    REDUNDANT_COMMENT = "redundant_comment"        # 冗余注释
    OUTDATED_COMMENT = "outdated_comment"          # 过期注释
    INCONSISTENT_COMMENT = "inconsistent_comment"  # 不一致注释
    TODO_COMMENT = "todo_comment"                  # TODO注释
    COMMENTED_OUT_CODE = "commented_out_code"      # 被注释掉的代码


class Severity(str, Enum):
    """严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DetectionLayer(str, Enum):
    """检测层级"""
    RULE = "rule"         # 规则层检测
    SEMANTIC = "semantic" # 语义层检测


@dataclass
class CommentSuggestion:
    """注释建议 - M3模块输出"""
    suggestion_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    type: SuggestionType = SuggestionType.DOCSTRING
    target_node_id: str = ""           # 对应的AST节点ID
    target_line: int = 0               # 目标行号
    suggested_text: str = ""           # 建议的注释文本
    confidence: float = 0.8            # 置信度
    source: str = "llm"               # 来源：llm/rule/template
    reasoning: str = ""               # 生成理由
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "type": self.type.value,
            "target_node_id": self.target_node_id,
            "target_line": self.target_line,
            "suggested_text": self.suggested_text,
            "confidence": self.confidence,
            "source": self.source,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommentSuggestion':
        return cls(
            suggestion_id=data.get("suggestion_id", ""),
            type=SuggestionType(data.get("type", "docstring")),
            target_node_id=data.get("target_node_id", ""),
            target_line=data.get("target_line", 0),
            suggested_text=data.get("suggested_text", ""),
            confidence=data.get("confidence", 0.8),
            source=data.get("source", "llm"),
            reasoning=data.get("reasoning", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Defect:
    """注释缺陷 - M4模块输出"""
    defect_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    type: DefectType = DefectType.MISSING_DOCSTRING
    severity: Severity = Severity.WARNING
    location: str = ""                  # 位置描述
    node_id: str = ""                   # 对应AST节点ID
    start_line: int = 0
    end_line: int = 0
    description: str = ""               # 缺陷描述
    suggested_fix: str = ""             # 修复建议
    detection_layer: DetectionLayer = DetectionLayer.RULE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "defect_id": self.defect_id,
            "type": self.type.value,
            "severity": self.severity.value,
            "location": self.location,
            "node_id": self.node_id,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "detection_layer": self.detection_layer.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Defect':
        return cls(
            defect_id=data.get("defect_id", ""),
            type=DefectType(data.get("type", "missing_docstring")),
            severity=Severity(data.get("severity", "warning")),
            location=data.get("location", ""),
            node_id=data.get("node_id", ""),
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            description=data.get("description", ""),
            suggested_fix=data.get("suggested_fix", ""),
            detection_layer=DetectionLayer(data.get("detection_layer", "rule")),
            metadata=data.get("metadata", {}),
        )


@dataclass
class QualityScore:
    """质量评分 - M5模块输出"""
    score: float = 0.0                              # 综合评分（0-100）
    dimensions: Dict[str, float] = field(default_factory=lambda: {
        "coverage": 0.0,       # 注释覆盖率
        "completeness": 0.0,   # 文档完整性
        "consistency": 0.0,    # 风格一致性
        "standard": 0.0,       # 规范符合度
    })
    defect_stats: Dict[str, int] = field(default_factory=dict)
    before_score: float = 0.0   # 修复前评分
    after_score: float = 0.0    # 修复后评分（如果采纳建议）
    summary: str = ""           # 评分总结
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "dimensions": self.dimensions,
            "defect_stats": self.defect_stats,
            "before_score": self.before_score,
            "after_score": self.after_score,
            "summary": self.summary,
            "details": self.details,
        }
