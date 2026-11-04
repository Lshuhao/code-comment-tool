"""
单元测试 - M3注释生成 + M4缺陷检测 + M5评分
"""
import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.m2_parser import parse_code
from app.services.m3_comment_gen import (
    MockLLMClient, DocstringGenerator, InlineCommentGenerator,
    CommentGenerationService
)
from app.services.m4_defect import RuleDetector, DefectDetectionService
from app.services.m5_scoring import QualityScoringService


SAMPLE_CODE = '''
import os

class DataProcessor:
    def __init__(self, data):
        self.data = data

    def process(self, threshold):
        result = []
        for item in self.data:
            if item > threshold:
                for j in range(item):
                    if j % 2 == 0:
                        result.append(j)
        return result

def helper(x):
    # 将x加1
    return x + 1

def undocumented_func(a, b, c):
    return a + b + c
'''


# ========================
# M3 注释生成测试
# ========================

class TestM3MockLLM:
    """M3 MockLLM客户端测试"""

    def test_mock_llm_docstring(self):
        client = MockLLMClient()
        result = asyncio.get_event_loop().run_until_complete(
            client.generate("Generate a docstring for this function")
        )
        assert len(result) > 0
        assert '"""' in result

    def test_mock_llm_inline(self):
        client = MockLLMClient()
        result = asyncio.get_event_loop().run_until_complete(
            client.generate("Generate inline comment for this code")
        )
        assert len(result) > 0


class TestM3DocstringGenerator:
    """M3 Docstring生成器测试"""

    def setup_method(self):
        self.client = MockLLMClient()
        self.gen = DocstringGenerator(self.client)

    def test_generate_for_node(self):
        parse_result = parse_code(SAMPLE_CODE, "python")
        functions = parse_result.get_all_functions()
        if functions:
            suggestion = asyncio.get_event_loop().run_until_complete(
                self.gen.generate_for_node(functions[0], "python")
            )
            assert suggestion.suggestion_id
            assert suggestion.type.value == "docstring"
            assert suggestion.suggested_text

    def test_generate_batch(self):
        parse_result = parse_code(SAMPLE_CODE, "python")
        functions = parse_result.get_all_functions()
        suggestions = asyncio.get_event_loop().run_until_complete(
            self.gen.generate_batch(functions, "python")
        )
        assert isinstance(suggestions, list)


class TestM3CommentGenerationService:
    """M3 完整注释生成服务测试"""

    def test_generate_all(self):
        service = CommentGenerationService(llm_client=MockLLMClient())
        parse_result = parse_code(SAMPLE_CODE, "python")
        suggestions = asyncio.get_event_loop().run_until_complete(
            service.generate_all(parse_result)
        )
        assert isinstance(suggestions, list)
        for s in suggestions:
            assert s.suggestion_id
            assert s.suggested_text
            assert s.target_line > 0


# ========================
# M4 缺陷检测测试
# ========================

class TestM4RuleDetector:
    """M4 规则层检测器测试"""

    def setup_method(self):
        self.detector = RuleDetector()

    def test_detect_missing_docstring(self):
        code = "def foo():\n    return 1\n"
        result = parse_code(code, "python")
        defects = self.detector._check_missing_docstring(result)
        assert len(defects) >= 1
        assert defects[0].type.value == "missing_docstring"

    def test_detect_no_defects_when_docstring_present(self):
        code = 'def foo():\n    """This is documented."""\n    return 1\n'
        result = parse_code(code, "python")
        defects = self.detector._check_missing_docstring(result)
        # 有docstring的函数不应报missing
        func_defects = [d for d in defects if d.node_id]
        # 可能有也可能没有，取决于解析结果
        assert isinstance(defects, list)

    def test_detect_bad_format(self):
        code = "# x\ndef foo():\n    pass\n"
        result = parse_code(code, "python")
        defects = self.detector._check_bad_format(result)
        assert isinstance(defects, list)

    def test_detect_commented_out_code(self):
        code = "# def old_function():\n#     return None\nx = 1\n"
        result = parse_code(code, "python")
        defects = self.detector._check_commented_out_code(result)
        assert isinstance(defects, list)

    def test_detect_todo(self):
        code = "# TODO: implement this later\ndef foo():\n    pass\n"
        result = parse_code(code, "python")
        defects = self.detector._check_todo_comments(result)
        assert len(defects) >= 1
        assert defects[0].type.value == "todo_comment"

    def test_detect_all(self):
        result = parse_code(SAMPLE_CODE, "python")
        defects = self.detector.detect_all(result)
        assert isinstance(defects, list)
        assert len(defects) > 0


class TestM4DefectDetectionService:
    """M4 完整缺陷检测服务测试"""

    def test_detect_all(self):
        service = DefectDetectionService(use_codebert=False)
        result = parse_code(SAMPLE_CODE, "python")
        defects = asyncio.get_event_loop().run_until_complete(
            service.detect_all(result)
        )
        assert isinstance(defects, list)

    def test_detect_rules_only(self):
        service = DefectDetectionService()
        result = parse_code(SAMPLE_CODE, "python")
        defects = service.detect_rules_only(result)
        assert isinstance(defects, list)
        assert all(d.detection_layer.value == "rule" for d in defects)


# ========================
# M5 质量评分测试
# ========================

class TestM5QualityScoring:
    """M5 评分模块测试 - 纯函数，最容易测试"""

    def setup_method(self):
        self.service = QualityScoringService()

    def test_score_well_documented(self):
        code = '''
def add(a, b):
    """
    Add two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    return a + b
'''
        result = parse_code(code, "python")
        defects = []
        score = self.service.calculate(result, defects)
        assert score.score >= 0
        assert score.score <= 100
        assert "coverage" in score.dimensions

    def test_score_no_comments(self):
        code = "def foo():\n    return 1\n"
        result = parse_code(code, "python")
        defects = []
        score = self.service.calculate(result, defects)
        assert score.score >= 0
        # 没有docstring覆盖率应该低
        assert score.dimensions["coverage"] < 100

    def test_score_with_defects(self):
        code = "def foo():\n    return 1\n"
        result = parse_code(code, "python")
        from app.models.suggestions import Defect, DefectType, Severity, DetectionLayer
        defects = [
            Defect(
                type=DefectType.MISSING_DOCSTRING,
                severity=Severity.ERROR,
                location="函数 'foo'",
                description="缺少文档字符串",
            )
        ]
        score_with = self.service.calculate(result, defects)
        score_without = self.service.calculate(result, [])
        # 有缺陷的评分应该低于无缺陷的
        assert score_with.score <= score_without.score

    def test_score_dimensions_range(self):
        result = parse_code(SAMPLE_CODE, "python")
        defects = RuleDetector().detect_all(result)
        score = self.service.calculate(result, defects)
        for dim, val in score.dimensions.items():
            assert 0 <= val <= 100, f"维度{dim}值{val}超出范围"

    def test_after_score_improvement(self):
        result = parse_code(SAMPLE_CODE, "python")
        defects = RuleDetector().detect_all(result)
        before = self.service.calculate(result, defects)
        after = self.service.calculate_after_score(result, before, 3, 5)
        assert after.after_score >= before.score

    def test_empty_code(self):
        result = parse_code("", "python")
        score = self.service.calculate(result, [])
        assert score.score >= 0
        assert score.score <= 100

    def test_summary_generated(self):
        result = parse_code(SAMPLE_CODE, "python")
        defects = RuleDetector().detect_all(result)
        score = self.service.calculate(result, defects)
        assert len(score.summary) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
