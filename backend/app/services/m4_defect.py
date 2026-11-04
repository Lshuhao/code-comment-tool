"""
M4 缺陷检测模块 - 规则层 + 语义层检测
职责：
- 规则层：缺失/参数缺失/格式检查（正则规则引擎）
- 语义层：冗余/过期/不一致（CodeBERT + LLM）
- 统一接口，RuleDetector和SemanticDetector两个类
"""
import re
from typing import List, Optional, Dict, Any, Tuple
from abc import ABC, abstractmethod

from app.models.unified_ast import UnifiedASTNode, NodeType, ParseResult
from app.models.suggestions import (
    Defect, DefectType, Severity, DetectionLayer
)
from app.core.config import settings


# ========================
# 规则层检测器
# ========================

class RuleDetector:
    """
    规则层检测器 - 基于正则表达式和模式匹配
    纯函数，可完全单元测试
    """

    def detect_all(self, parse_result: ParseResult) -> List[Defect]:
        """执行所有规则检测"""
        defects = []
        defects.extend(self._check_missing_docstring(parse_result))
        defects.extend(self._check_missing_param_doc(parse_result))
        defects.extend(self._check_bad_format(parse_result))
        defects.extend(self._check_commented_out_code(parse_result))
        defects.extend(self._check_todo_comments(parse_result))
        defects.extend(self._check_empty_docstring(parse_result))
        return defects

    def _check_missing_docstring(self, parse_result: ParseResult) -> List[Defect]:
        """检查缺少文档字符串的函数/类"""
        defects = []
        functions = parse_result.get_all_functions()
        classes = parse_result.get_all_classes()

        for node in functions + classes:
            if not node.docstring:
                severity = Severity.ERROR if node.complexity_score >= 3.0 else Severity.WARNING
                type_label = "函数" if node.node_type == NodeType.FUNCTION else "方法" if node.node_type == NodeType.METHOD else "类"
                defects.append(Defect(
                    type=DefectType.MISSING_DOCSTRING,
                    severity=severity,
                    location=f"{type_label} '{node.name}'",
                    node_id=node.node_id,
                    start_line=node.start_line,
                    end_line=node.end_line,
                    description=f"{type_label} '{node.name}' 缺少文档字符串",
                    suggested_fix=f"为 {node.name} 添加文档字符串，说明其功能、参数和返回值",
                    detection_layer=DetectionLayer.RULE,
                ))
        return defects

    def _check_missing_param_doc(self, parse_result: ParseResult) -> List[Defect]:
        """检查文档字符串中缺少的参数说明"""
        defects = []
        functions = parse_result.get_all_functions()

        for func in functions:
            if not func.docstring or not func.parameters:
                continue

            docstring_lower = func.docstring.lower()
            for param in func.parameters:
                param_name = param.get("name", "")
                if param_name and param_name != "self" and param_name not in docstring_lower:
                    defects.append(Defect(
                        type=DefectType.MISSING_PARAM_DOC,
                        severity=Severity.WARNING,
                        location=f"函数 '{func.name}' 的参数 '{param_name}'",
                        node_id=func.node_id,
                        start_line=func.start_line,
                        end_line=func.end_line,
                        description=f"文档字符串中缺少参数 '{param_name}' 的说明",
                        suggested_fix=f"在文档字符串的Args/Parameters部分添加 {param_name} 的说明",
                        detection_layer=DetectionLayer.RULE,
                    ))
        return defects

    def _check_bad_format(self, parse_result: ParseResult) -> List[Defect]:
        """检查注释格式不规范"""
        defects = []
        source_lines = parse_result.raw_source.split("\n")

        for i, line in enumerate(source_lines, 1):
            stripped = line.strip()

            # 检查单字母变量注释（过于简单）
            if re.match(r'^#\s*[a-zA-Z]\s*$', stripped):
                defects.append(Defect(
                    type=DefectType.BAD_FORMAT,
                    severity=Severity.INFO,
                    location=f"第{i}行",
                    start_line=i,
                    end_line=i,
                    description=f"注释 '{stripped}' 过于简单，缺乏有意义的描述",
                    suggested_fix="扩展注释内容，说明代码的意图而非简单标记",
                    detection_layer=DetectionLayer.RULE,
                    metadata={"line_content": stripped},
                ))

            # 检查TODO/FIXME注释
            if re.match(r'^#\s*(TODO|FIXME|HACK|XXX)\s*$', stripped, re.IGNORECASE):
                defects.append(Defect(
                    type=DefectType.TODO_COMMENT,
                    severity=Severity.INFO,
                    location=f"第{i}行",
                    start_line=i,
                    end_line=i,
                    description=f"存在未完成的{stripped.lstrip('# ')}注释",
                    suggested_fix="完成待办事项后移除TODO标记，或添加详细说明",
                    detection_layer=DetectionLayer.RULE,
                ))

        return defects

    def _check_commented_out_code(self, parse_result: ParseResult) -> List[Defect]:
        """检查被注释掉的代码"""
        defects = []
        source_lines = parse_result.raw_source.split("\n")
        language = parse_result.language

        # 代码特征模式
        code_patterns = {
            "python": [
                r'^\s*#\s*(def |class |import |from |if __name__|print\(|return |for |while )',
                r'^\s*#\s*\w+\s*=\s*\w+',  # x = something
                r'^\s*#\s*\w+\.\w+\(',  # obj.method(
            ],
            "java": [
                r'^\s*//\s*(public |private |protected |System\.|return |for |while )',
                r'^\s*//\s*\w+\s+\w+\s*=\s*',
            ],
            "cpp": [
                r'^\s*//\s*(#include|int |void |return |for |while |class )',
                r'^\s*//\s*(std::|cout|cin|printf)',
            ],
        }

        patterns = code_patterns.get(language, code_patterns["python"])
        consecutive_commented_lines = []

        for i, line in enumerate(source_lines, 1):
            stripped = line.strip()
            if not stripped or (not stripped.startswith("#") and not stripped.startswith("//")):
                if len(consecutive_commented_lines) >= 2:
                    # 多行被注释掉的代码
                    start = consecutive_commented_lines[0][0]
                    defects.append(Defect(
                        type=DefectType.COMMENTED_OUT_CODE,
                        severity=Severity.WARNING,
                        location=f"第{start}行起",
                        start_line=start,
                        end_line=consecutive_commented_lines[-1][0],
                        description="存在被注释掉的代码块，建议删除或使用版本控制管理",
                        suggested_fix="删除被注释的代码，如需保留可使用Git历史查看",
                        detection_layer=DetectionLayer.RULE,
                    ))
                consecutive_commented_lines = []
                continue

            is_code_comment = any(
                re.match(p, line) for p in patterns
            )
            if is_code_comment:
                consecutive_commented_lines.append((i, stripped))

        return defects

    def _check_todo_comments(self, parse_result: ParseResult) -> List[Defect]:
        """检查TODO/FIXME注释"""
        defects = []
        source_lines = parse_result.raw_source.split("\n")

        todo_pattern = re.compile(
            r'(?:#|//)\s*(TODO|FIXME|HACK|XXX|BUG)\s*:?\s*(.*)',
            re.IGNORECASE
        )

        for i, line in enumerate(source_lines, 1):
            match = todo_pattern.search(line)
            if match:
                todo_type = match.group(1).upper()
                detail = match.group(2).strip()
                defects.append(Defect(
                    type=DefectType.TODO_COMMENT,
                    severity=Severity.WARNING if todo_type in ("FIXME", "BUG") else Severity.INFO,
                    location=f"第{i}行",
                    start_line=i,
                    end_line=i,
                    description=f"存在 {todo_type} 注释: {detail or '(无详细描述)'}",
                    suggested_fix=f"处理{todo_type}事项，完成后删除标记",
                    detection_layer=DetectionLayer.RULE,
                    metadata={"todo_type": todo_type, "detail": detail},
                ))
        return defects

    def _check_empty_docstring(self, parse_result: ParseResult) -> List[Defect]:
        """检查空的或过于简短的文档字符串"""
        defects = []
        functions = parse_result.get_all_functions()

        for func in functions:
            if func.docstring:
                # 去除引号和空白后的内容
                content = re.sub(r'["\']+', '', func.docstring).strip()
                if len(content) < 5:
                    defects.append(Defect(
                        type=DefectType.BAD_FORMAT,
                        severity=Severity.WARNING,
                        location=f"函数 '{func.name}'",
                        node_id=func.node_id,
                        start_line=func.start_line,
                        end_line=func.end_line,
                        description=f"函数 '{func.name}' 的文档字符串内容过于简短（{len(content)}字符）",
                        suggested_fix="补充函数的功能描述、参数说明和返回值说明",
                        detection_layer=DetectionLayer.RULE,
                    ))
        return defects


# ========================
# 语义层检测器
# ========================

class SemanticDetector:
    """
    语义层检测器 - 基于CodeBERT和LLM的语义分析
    检测冗余/过期/不一致注释

    支持两种模型加载模式：
    1. 微调模型（推荐）: 指定 finetuned_model_path，使用 CodeSearchNet 微调后的 CodeBERT
    2. 预训练模型: 使用原始 microsoft/codebert-base
    3. 回退模式: 当 sentence-transformers 不可用时，使用简单文本匹配
    """

    def __init__(
        self,
        llm_client=None,
        use_codebert: bool = False,
        finetuned_model_path: str = None,
    ):
        self.llm = llm_client
        self.use_codebert = use_codebert
        self.finetuned_model_path = finetuned_model_path
        self._codebert_model = None
        self._tokenizer = None
        self._inference_service = None  # 微调模型推理服务

    def _load_codebert(self):
        """延迟加载CodeBERT模型（优先加载微调模型）"""
        if self._codebert_model is not None:
            return

        # 1. 优先尝试加载微调推理服务
        if self.finetuned_model_path:
            try:
                import sys
                import os
                training_dir = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "training", "scripts"
                )
                if training_dir not in sys.path:
                    sys.path.insert(0, training_dir)
                from inference import FineTunedCodeBERTService
                self._inference_service = FineTunedCodeBERTService(
                    model_path=self.finetuned_model_path
                )
                self.use_codebert = True
                return
            except Exception:
                pass  # 回退到预训练模型

        # 2. 回退到原始预训练模型
        try:
            from sentence_transformers import SentenceTransformer
            self._codebert_model = SentenceTransformer(settings.CODEBERT_MODEL)
            self.use_codebert = True
        except Exception:
            self.use_codebert = False

    async def detect_all(
        self, parse_result: ParseResult
    ) -> List[Defect]:
        """执行所有语义检测"""
        defects = []
        defects.extend(await self._check_redundant_comments(parse_result))
        defects.extend(await self._check_inconsistent_comments(parse_result))
        defects.extend(await self._check_outdated_comments(parse_result))
        return defects

    async def _check_redundant_comments(
        self, parse_result: ParseResult
    ) -> List[Defect]:
        """
        检测冗余注释 - 注释内容直接重复代码字面意思
        例: x += 1  # 将x加1
        """
        defects = []
        source_lines = parse_result.raw_source.split("\n")
        language = parse_result.language

        # 冗余模式
        redundant_patterns = {
            "python": [
                (r'^\s*(\w+)\s*\+=\s*1\s*#\s*.*(\1).*加.*1', "变量自增注释冗余"),
                (r'^\s*return\s+(\w+)\s*#\s*返回\s*\1', "返回值注释冗余"),
                (r'^\s*print\s*\((.+)\)\s*#\s*打印\s*\1', "打印语句注释冗余"),
            ],
            "java": [
                (r'//\s*设置\s*(\w+)', "设置器方法注释可能冗余"),
                (r'//\s*获取\s*(\w+)', "获取器方法注释可能冗余"),
            ],
            "cpp": [],
        }

        patterns = redundant_patterns.get(language, [])
        for i, line in enumerate(source_lines, 1):
            for pattern, desc in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    defects.append(Defect(
                        type=DefectType.REDUNDANT_COMMENT,
                        severity=Severity.INFO,
                        location=f"第{i}行",
                        start_line=i,
                        end_line=i,
                        description=desc,
                        suggested_fix="删除冗余注释或改写为说明'为什么'这样做",
                        detection_layer=DetectionLayer.SEMANTIC,
                    ))
                    break
        return defects

    async def _check_inconsistent_comments(
        self, parse_result: ParseResult
    ) -> List[Defect]:
        """
        检测不一致注释 - 注释描述与实际代码不符
        使用CodeBERT计算注释和代码的语义相似度
        """
        defects = []

        if not self.use_codebert:
            return defects

        self._load_codebert()
        if self._codebert_model is None:
            return defects

        functions = parse_result.get_all_functions()
        for func in functions:
            if func.docstring:
                # 计算docstring与代码的语义相似度
                similarity = self._compute_similarity(
                    func.docstring, func.source_text
                )
                # 极低相似度可能表示注释与代码不一致
                if similarity < 0.15 and len(func.docstring) > 20:
                    defects.append(Defect(
                        type=DefectType.INCONSISTENT_COMMENT,
                        severity=Severity.WARNING,
                        location=f"函数 '{func.name}'",
                        node_id=func.node_id,
                        start_line=func.start_line,
                        end_line=func.end_line,
                        description=f"函数 '{func.name}' 的文档字符串可能与代码实现不一致（相似度: {similarity:.2f}）",
                        suggested_fix="检查文档字符串是否准确描述了函数的实际行为",
                        detection_layer=DetectionLayer.SEMANTIC,
                        metadata={"similarity": similarity},
                    ))
        return defects

    async def _check_outdated_comments(
        self, parse_result: ParseResult
    ) -> List[Defect]:
        """
        检测可能过期的注释
        启发式方法：参数数量变化、函数签名变化等
        """
        defects = []
        functions = parse_result.get_all_functions()

        for func in functions:
            if not func.docstring:
                continue

            # 检查docstring中提到的参数是否与实际参数匹配
            docstring_lower = func.docstring.lower()
            actual_params = {p.get("name", "") for p in func.parameters if p.get("name")}
            actual_params.discard("self")

            # 提取docstring中提到的参数名
            mentioned_params = set(re.findall(
                r'(?:Args?|Parameters?|param)\s*[:\s]*\n?\s*(\w+)',
                func.docstring, re.IGNORECASE
            ))

            # 如果docstring提到的参数不在实际参数中
            ghost_params = mentioned_params - actual_params
            if ghost_params and actual_params:
                defects.append(Defect(
                    type=DefectType.OUTDATED_COMMENT,
                    severity=Severity.WARNING,
                    location=f"函数 '{func.name}'",
                    node_id=func.node_id,
                    start_line=func.start_line,
                    end_line=func.end_line,
                    description=f"文档字符串中提到了不存在的参数: {', '.join(ghost_params)}",
                    suggested_fix="更新文档字符串，移除已不存在的参数说明，添加新参数说明",
                    detection_layer=DetectionLayer.SEMANTIC,
                    metadata={"ghost_params": list(ghost_params)},
                ))

        return defects

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的语义相似度"""
        # 优先使用微调推理服务
        if self._inference_service is not None:
            return self._inference_service.compute_similarity(text1, text2)

        if self._codebert_model is None:
            return 0.5
        try:
            emb1 = self._codebert_model.encode([text1])[0]
            emb2 = self._codebert_model.encode([text2])[0]
            import numpy as np
            return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))
        except Exception:
            return 0.5


# ========================
# M4 模块主服务
# ========================

class DefectDetectionService:
    """M4 缺陷检测服务 - 整合规则层和语义层"""

    def __init__(
        self,
        llm_client=None,
        use_codebert: bool = False,
        finetuned_model_path: str = None,
    ):
        self.rule_detector = RuleDetector()
        self.semantic_detector = SemanticDetector(
            llm_client=llm_client,
            use_codebert=use_codebert,
            finetuned_model_path=finetuned_model_path,
        )

    async def detect_all(self, parse_result: ParseResult) -> List[Defect]:
        """
        执行所有缺陷检测
        1. 规则层检测（纯函数，快速）
        2. 语义层检测（可能涉及模型推理，较慢）
        """
        # 规则层
        rule_defects = self.rule_detector.detect_all(parse_result)

        # 语义层
        semantic_defects = await self.semantic_detector.detect_all(parse_result)

        return rule_defects + semantic_defects

    def detect_rules_only(self, parse_result: ParseResult) -> List[Defect]:
        """仅执行规则层检测（同步，快速）"""
        return self.rule_detector.detect_all(parse_result)


# 全局单例
defect_detection_service = DefectDetectionService()
