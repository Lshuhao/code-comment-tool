"""
M5 质量评分模块 - 四维度量化评分
职责：
- 注释覆盖率计算
- 文档完整性评估
- 风格一致性检查
- 规范符合度评分
- 缺陷扣分
- 报告数据生成
纯规则计算，无LLM依赖，保证可复现
"""
from typing import List, Dict, Any

from app.models.unified_ast import UnifiedASTNode, NodeType, ParseResult
from app.models.suggestions import Defect, DefectType, Severity, QualityScore
from app.core.config import settings


class QualityScoringService:
    """
    M5 质量评分服务
    纯函数设计，输入确定则输出确定
    """

    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or settings.SCORE_WEIGHTS

    def calculate(
        self,
        parse_result: ParseResult,
        defects: List[Defect],
    ) -> QualityScore:
        """
        计算质量评分
        四维度：覆盖率、完整性、一致性、规范性
        """
        # 计算四个维度
        coverage = self._calc_coverage(parse_result)
        completeness = self._calc_completeness(parse_result, defects)
        consistency = self._calc_consistency(parse_result)
        standard = self._calc_standard(parse_result, defects)

        # 缺陷扣分
        defect_penalty = self._calc_defect_penalty(defects)

        # 缺陷统计
        defect_stats = self._calc_defect_stats(defects)

        # 加权综合
        raw_score = (
            coverage * self.weights.get("coverage", 0.3) +
            completeness * self.weights.get("completeness", 0.3) +
            consistency * self.weights.get("consistency", 0.2) +
            standard * self.weights.get("standard", 0.2)
        )

        # 应用缺陷扣分
        final_score = max(0, raw_score - defect_penalty) * 100

        # 生成摘要
        summary = self._generate_summary(
            final_score, coverage, completeness, consistency, standard, defect_stats
        )

        return QualityScore(
            score=round(final_score, 1),
            dimensions={
                "coverage": round(coverage * 100, 1),
                "completeness": round(completeness * 100, 1),
                "consistency": round(consistency * 100, 1),
                "standard": round(standard * 100, 1),
            },
            defect_stats=defect_stats,
            before_score=round(final_score, 1),
            summary=summary,
            details={
                "weights": self.weights,
                "raw_score": round(raw_score, 3),
                "defect_penalty": round(defect_penalty, 3),
                "total_functions": len(parse_result.get_all_functions()),
                "total_classes": len(parse_result.get_all_classes()),
                "total_defects": len(defects),
            },
        )

    def calculate_after_score(
        self,
        parse_result: ParseResult,
        original_score: QualityScore,
        accepted_suggestions: int,
        total_suggestions: int,
    ) -> QualityScore:
        """
        计算采纳建议后的预期评分
        """
        if total_suggestions == 0:
            return original_score

        improvement_ratio = accepted_suggestions / total_suggestions

        # 估算改进
        improvement = (100 - original_score.score) * improvement_ratio * 0.6
        after_score = min(100, original_score.score + improvement)

        # 更新缺陷统计
        new_defect_stats = dict(original_score.defect_stats)
        for defect_type, count in list(new_defect_stats.items()):
            reduced = int(count * improvement_ratio)
            new_defect_stats[defect_type] = max(0, count - reduced)

        result = QualityScore(
            score=round(after_score, 1),
            dimensions=dict(original_score.dimensions),
            defect_stats=new_defect_stats,
            before_score=original_score.before_score,
            after_score=round(after_score, 1),
            summary=f"采纳{accepted_suggestions}/{total_suggestions}条建议后，预期评分提升{improvement:.1f}分",
            details=dict(original_score.details),
        )

        # 按比例提升各维度
        factor = after_score / original_score.score if original_score.score > 0 else 1
        for dim in result.dimensions:
            result.dimensions[dim] = round(
                min(100, original_score.dimensions[dim] * factor), 1
            )

        return result

    def _calc_coverage(self, parse_result: ParseResult) -> float:
        """
        注释覆盖率 - 有文档字符串的函数/类占总数的比例
        0-1之间
        """
        functions = parse_result.get_all_functions()
        classes = parse_result.get_all_classes()
        all_nodes = functions + classes

        if not all_nodes:
            return 1.0  # 没有函数/类时默认满分

        with_docstring = sum(1 for n in all_nodes if n.docstring)
        return with_docstring / len(all_nodes)

    def _calc_completeness(
        self, parse_result: ParseResult, defects: List[Defect]
    ) -> float:
        """
        文档完整性 - 文档字符串中是否包含参数、返回值等必要信息
        """
        functions = parse_result.get_all_functions()

        if not functions:
            return 1.0

        completeness_scores = []
        for func in functions:
            if not func.docstring:
                completeness_scores.append(0.0)
                continue

            score = 0.0
            elements = 0

            # 检查是否有功能描述
            content = func.docstring.strip().strip('"""').strip("'''").strip()
            if content and len(content) > 5:
                score += 0.3
            elements += 1

            # 检查是否有参数说明
            has_params = any(
                kw in func.docstring.lower()
                for kw in ["args", "parameters", "param", "参数"]
            )
            if has_params:
                score += 0.25
            elif func.parameters:
                score += 0.0
            else:
                score += 0.25  # 无参数也给分
            elements += 1

            # 检查是否有返回值说明
            has_returns = any(
                kw in func.docstring.lower()
                for kw in ["returns", "return", "返回"]
            )
            if has_returns:
                score += 0.25
            elif not any(
                "return " in line
                for line in func.source_text.split("\n")
                if "return" in line
            ):
                score += 0.25  # 无return语句也给分
            elements += 1

            # 检查是否有异常说明
            has_raises = any(
                kw in func.docstring.lower()
                for kw in ["raises", "raise", "throw", "异常"]
            )
            if has_raises:
                score += 0.2
            elements += 1

            completeness_scores.append(min(score, 1.0))

        return sum(completeness_scores) / len(completeness_scores) if completeness_scores else 1.0

    def _calc_consistency(self, parse_result: ParseResult) -> float:
        """
        风格一致性 - 所有注释是否遵循统一风格
        检查：缩进、格式、语言等
        """
        functions = parse_result.get_all_functions()

        if not functions:
            return 1.0

        styles_detected = []
        for func in functions:
            if func.docstring:
                style = self._detect_docstring_style(func.docstring)
                styles_detected.append(style)

        if not styles_detected:
            return 0.5

        # 统计最常见的风格
        style_counts = {}
        for s in styles_detected:
            style_counts[s] = style_counts.get(s, 0) + 1

        # 一致性 = 最常用风格的比例
        max_count = max(style_counts.values())
        return max_count / len(styles_detected)

    def _detect_docstring_style(self, docstring: str) -> str:
        """检测文档字符串风格"""
        ds = docstring.lower()
        if ":param" in ds or ":return" in ds or ":type" in ds:
            return "sphinx"
        elif "args:" in ds or "returns:" in ds or "raises:" in ds:
            return "google"
        elif "parameters" in ds and "----------" in ds:
            return "numpy"
        return "unknown"

    def _calc_standard(
        self, parse_result: ParseResult, defects: List[Defect]
    ) -> float:
        """
        规范符合度 - 是否遵循编码规范
        基于缺陷数量和严重程度扣分
        """
        if not defects:
            return 1.0

        penalty = 0.0
        for defect in defects:
            if defect.severity == Severity.ERROR:
                penalty += 0.05
            elif defect.severity == Severity.WARNING:
                penalty += 0.02
            elif defect.severity == Severity.INFO:
                penalty += 0.005

        return max(0, 1.0 - penalty)

    def _calc_defect_penalty(self, defects: List[Defect]) -> float:
        """计算缺陷扣分（0-1之间）"""
        penalty = 0.0
        for defect in defects:
            if defect.severity == Severity.ERROR:
                penalty += 0.03
            elif defect.severity == Severity.WARNING:
                penalty += 0.015
            elif defect.severity == Severity.INFO:
                penalty += 0.005
        return min(penalty, 0.5)  # 最多扣50分

    def _calc_defect_stats(self, defects: List[Defect]) -> Dict[str, int]:
        """按类型统计缺陷"""
        stats = {}
        for d in defects:
            key = d.type.value
            stats[key] = stats.get(key, 0) + 1
        return stats

    def _generate_summary(
        self,
        score: float,
        coverage: float,
        completeness: float,
        consistency: float,
        standard: float,
        defect_stats: Dict[str, int],
    ) -> str:
        """生成评分摘要"""
        total_defects = sum(defect_stats.values())

        level = "优秀" if score >= 90 else "良好" if score >= 75 else "一般" if score >= 60 else "需要改进"

        summary_parts = [f"代码注释质量评分: {score:.1f}分（{level}）"]

        # 最弱维度
        dims = {
            "覆盖率": coverage * 100,
            "完整性": completeness * 100,
            "一致性": consistency * 100,
            "规范性": standard * 100,
        }
        weakest = min(dims, key=dims.get)
        summary_parts.append(f"最需改进: {weakest}（{dims[weakest]:.1f}%）")

        if total_defects > 0:
            summary_parts.append(f"共发现{total_defects}个注释问题")

        return "；".join(summary_parts)


# 全局单例
scoring_service = QualityScoringService()
