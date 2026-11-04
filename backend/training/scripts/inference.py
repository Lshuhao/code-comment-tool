"""
微调后模型的推理服务封装

提供与原 M4 SemanticDetector 兼容的接口，
可无缝替换原始 CodeBERT 预训练模型。

用法:
    from inference import FineTunedCodeBERTService

    service = FineTunedCodeBERTService(model_path="./models/finetuned_codebert")

    # 计算代码与注释的语义相似度
    score = service.compute_similarity(code, docstring)

    # 检测注释是否与代码不一致
    is_inconsistent = service.check_inconsistency(code, docstring)

    # 批量推理
    scores = service.batch_similarity(codes, docstrings)
"""
import logging
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)


class FineTunedCodeBERTService:
    """
    微调后 CodeBERT 推理服务

    设计为可插拔组件：
    - 如果微调模型存在 → 加载微调模型
    - 如果不存在 → 回退到原始预训练模型
    - 如果 sentence-transformers 未安装 → 回退到简单文本匹配
    """

    def __init__(
        self,
        model_path: str = None,
        base_model: str = "microsoft/codebert-base",
        inconsistency_threshold: float = 0.25,
        redundancy_threshold: float = 0.85,
        batch_size: int = 64,
    ):
        self.model_path = model_path or "./models/finetuned_codebert"
        self.base_model = base_model
        self.inconsistency_threshold = inconsistency_threshold
        self.redundancy_threshold = redundancy_threshold
        self.batch_size = batch_size

        self._model = None
        self._use_finetuned = False
        self._fallback_mode = False

        self._load_model()

    def _load_model(self):
        """加载模型（优先微调模型，回退到预训练，再回退到文本匹配）"""
        import os

        # 1. 尝试加载微调模型
        if os.path.exists(self.model_path):
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_path)
                self._use_finetuned = True
                logger.info(f"已加载微调模型: {self.model_path}")
                return
            except Exception as e:
                logger.warning(f"加载微调模型失败: {e}")

        # 2. 回退到原始预训练模型
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.base_model)
            self._use_finetuned = False
            logger.info(f"使用预训练模型: {self.base_model}（未检测到微调模型）")
            return
        except ImportError:
            logger.warning("sentence-transformers 未安装，使用文本匹配回退")

        # 3. 回退到简单文本匹配
        self._fallback_mode = True
        logger.info("使用简单文本匹配回退模式")

    @property
    def is_finetuned(self) -> bool:
        """是否使用了微调模型"""
        return self._use_finetuned

    def compute_similarity(self, code: str, docstring: str) -> float:
        """
        计算代码与注释的语义相似度

        Returns:
            float: 0-1之间的相似度分数
        """
        if self._fallback_mode:
            return self._text_similarity(code, docstring)

        code_emb = self._model.encode(
            [code], show_progress_bar=False, normalize_embeddings=True
        )
        doc_emb = self._model.encode(
            [docstring], show_progress_bar=False, normalize_embeddings=True
        )
        similarity = float(np.dot(code_emb[0], doc_emb[0]))
        # 归一化到 0-1
        return (similarity + 1) / 2

    def batch_similarity(
        self, codes: List[str], docstrings: List[str]
    ) -> List[float]:
        """批量计算相似度"""
        if self._fallback_mode:
            return [self._text_similarity(c, d) for c, d in zip(codes, docstrings)]

        code_embs = self._model.encode(
            codes, batch_size=self.batch_size,
            show_progress_bar=True, normalize_embeddings=True
        )
        doc_embs = self._model.encode(
            docstrings, batch_size=self.batch_size,
            show_progress_bar=True, normalize_embeddings=True
        )

        # 逐对计算余弦相似度
        similarities = []
        for c_emb, d_emb in zip(code_embs, doc_embs):
            sim = float(np.dot(c_emb, d_emb))
            similarities.append((sim + 1) / 2)

        return similarities

    def check_inconsistency(self, code: str, docstring: str) -> Tuple[bool, float]:
        """
        检测注释是否与代码不一致

        Returns:
            (is_inconsistent, similarity_score)
        """
        score = self.compute_similarity(code, docstring)
        return score < self.inconsistency_threshold, score

    def check_redundancy(self, code: str, comment: str) -> Tuple[bool, float]:
        """
        检测注释是否是冗余的（与代码语义过于相似 = 只是重复代码字面意思）

        Returns:
            (is_redundant, similarity_score)
        """
        score = self.compute_similarity(code, comment)
        return score > self.redundancy_threshold, score

    def find_best_match(
        self, query_code: str, candidate_docstrings: List[str]
    ) -> Tuple[int, float]:
        """
        在一组候选文档字符串中，找到与代码最匹配的那个

        Returns:
            (best_index, best_score)
        """
        if not candidate_docstrings:
            return -1, 0.0

        if self._fallback_mode:
            scores = [self._text_similarity(query_code, d) for d in candidate_docstrings]
        else:
            code_emb = self._model.encode(
                [query_code], show_progress_bar=False, normalize_embeddings=True
            )
            doc_embs = self._model.encode(
                candidate_docstrings, batch_size=self.batch_size,
                show_progress_bar=False, normalize_embeddings=True
            )
            scores = [float(np.dot(code_emb[0], d)) for d in doc_embs]
            scores = [(s + 1) / 2 for s in scores]

        best_idx = int(np.argmax(scores))
        return best_idx, scores[best_idx]

    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        简单文本相似度回退（TF-IDF余弦相似度）
        当 sentence-transformers 不可用时使用
        """
        # 分词
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        # Jaccard相似度
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0

    def encode(self, texts: List[str]) -> np.ndarray:
        """直接获取embedding向量（供外部使用）"""
        if self._fallback_mode:
            raise RuntimeError("回退模式不支持embedding提取")
        return self._model.encode(
            texts, batch_size=self.batch_size,
            show_progress_bar=True, normalize_embeddings=True
        )


# ========================
# 与 M4 SemanticDetector 的集成适配器
# ========================

class M4SemanticAdapter:
    """
    将 FineTunedCodeBERTService 适配为 M4 SemanticDetector 可用的接口

    用法:
        from inference import M4SemanticAdapter
        adapter = M4SemanticAdapter(model_path="./models/finetuned_codebert")

        # 在 M4 中使用
        defects = adapter.detect_semantic_issues(parse_result)
    """

    def __init__(self, model_path: str = None, **kwargs):
        self.service = FineTunedCodeBERTService(model_path=model_path, **kwargs)

    def compute_similarity(self, text1: str, text2: str) -> float:
        """与 M4 SemanticDetector._compute_similarity 签名一致"""
        return self.service.compute_similarity(text1, text2)

    def detect_inconsistent_comments(self, parse_result) -> list:
        """
        检测不一致注释（与 M4 的 _check_inconsistent_comments 逻辑一致）
        返回 Defect 列表
        """
        from app.models.suggestions import Defect, DefectType, Severity, DetectionLayer

        defects = []
        functions = parse_result.get_all_functions()

        for func in functions:
            if func.docstring and len(func.docstring) > 20:
                is_inconsistent, score = self.service.check_inconsistency(
                    func.source_text, func.docstring
                )
                if is_inconsistent:
                    defects.append(Defect(
                        type=DefectType.INCONSISTENT_COMMENT,
                        severity=Severity.WARNING,
                        location=f"函数 '{func.name}'",
                        node_id=func.node_id,
                        start_line=func.start_line,
                        end_line=func.end_line,
                        description=f"函数 '{func.name}' 的文档字符串可能与代码实现不一致（相似度: {score:.2f}）",
                        suggested_fix="检查文档字符串是否准确描述了函数的实际行为",
                        detection_layer=DetectionLayer.SEMANTIC,
                        metadata={"similarity": score, "model": "finetuned_codebert"},
                    ))

        return defects

    def detect_redundant_comments(self, source_lines: List[str]) -> list:
        """检测冗余注释"""
        from app.models.suggestions import Defect, DefectType, Severity, DetectionLayer

        defects = []
        for i, line in enumerate(source_lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                comment_text = stripped.lstrip("#/ ").strip()
                code_context = "\n".join(source_lines[max(0, i-2):min(len(source_lines), i+2)])
                is_redundant, score = self.service.check_redundancy(code_context, comment_text)
                if is_redundant:
                    defects.append(Defect(
                        type=DefectType.REDUNDANT_COMMENT,
                        severity=Severity.INFO,
                        location=f"第{i}行",
                        start_line=i,
                        end_line=i,
                        description=f"注释可能冗余（与代码语义高度相似: {score:.2f}）",
                        suggested_fix="删除仅重复代码字面意思的注释，改为说明'为什么'这样做",
                        detection_layer=DetectionLayer.SEMANTIC,
                        metadata={"similarity": score, "model": "finetuned_codebert"},
                    ))

        return defects
