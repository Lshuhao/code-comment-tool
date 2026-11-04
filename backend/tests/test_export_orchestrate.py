"""
单元测试 - M6导出 + M7编排
"""
import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.m2_parser import parse_code
from app.services.m6_export import ExportService
from app.services.m7_orchestrator import PipelineOrchestrator
from app.services.m3_comment_gen import MockLLMClient, CommentGenerationService
from app.services.m4_defect import RuleDetector
from app.services.m5_scoring import QualityScoringService


SAMPLE_CODE = '''
import os

class Calculator:
    """A simple calculator."""

    def __init__(self):
        self.result = 0

    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b

def main():
    calc = Calculator()
    print(calc.add(1, 2))

if __name__ == "__main__":
    main()
'''


# ========================
# M6 导出模块测试
# ========================

class TestM6ExportService:
    """M6 导出服务测试"""

    def setup_method(self):
        self.service = ExportService()

    def test_generate_annotated_code_no_suggestions(self):
        result = parse_code(SAMPLE_CODE, "python")
        code = self.service.generate_annotated_code(SAMPLE_CODE, [], result)
        assert code == SAMPLE_CODE

    def test_export_source(self):
        result = self.service.export_source("print('hi')", "test.py", "python")
        assert result["filename"] == "test_annotated.py"
        assert result["content_type"] == "text/plain"
        assert "print" in result["content"]

    def test_export_markdown_report(self):
        from app.models.suggestions import QualityScore
        score = QualityScore(
            score=75.0,
            dimensions={"coverage": 80.0, "completeness": 70.0, "consistency": 75.0, "standard": 80.0},
            defect_stats={"missing_docstring": 3},
            summary="测试评分",
        )
        result = self.service.export_markdown_report(score, [], [])
        assert result["content_type"] == "text/markdown"
        assert "75" in result["content"]
        assert "测试评分" in result["content"]

    def test_export_html_report(self):
        from app.models.suggestions import QualityScore
        score = QualityScore(
            score=85.0,
            dimensions={"coverage": 90.0, "completeness": 80.0, "consistency": 85.0, "standard": 85.0},
            summary="HTML测试",
        )
        result = self.service.export_html_report(score, [], [])
        assert result["content_type"] == "text/html"
        assert "<html" in result["content"]
        assert "85" in result["content"]

    def test_validate_python_code(self):
        valid = self.service.validate_code("def foo(): pass", "python")
        assert valid["valid"] is True

    def test_validate_invalid_python(self):
        invalid = self.service.validate_code("def foo(:", "python")
        assert invalid["valid"] is False
        assert len(invalid["errors"]) > 0

    def test_get_indent(self):
        assert self.service._get_indent("    hello") == "    "
        assert self.service._get_indent("hello") == ""
        assert self.service._get_indent("\t\thello") == "\t\t"


# ========================
# M7 编排服务测试
# ========================

class TestM7Orchestrator:
    """M7 编排服务测试"""

    def setup_method(self):
        self.orchestrator = PipelineOrchestrator()
        # 替换为Mock LLM
        self.orchestrator.comment_gen = CommentGenerationService(
            llm_client=MockLLMClient()
        )

    def test_create_task(self):
        task = self.orchestrator.create_task()
        assert task.task_id
        assert task.status == "pending"

    def test_get_task(self):
        task = self.orchestrator.create_task()
        found = self.orchestrator.get_task(task.task_id)
        assert found is not None
        assert found.task_id == task.task_id

    def test_get_nonexistent_task(self):
        assert self.orchestrator.get_task("nonexistent") is None

    def test_list_tasks(self):
        self.orchestrator.create_task()
        tasks = self.orchestrator.list_tasks()
        assert len(tasks) >= 1

    def test_run_analysis(self):
        task = asyncio.get_event_loop().run_until_complete(
            self.orchestrator.run_analysis(SAMPLE_CODE, "test.py")
        )
        assert task.status == "completed"
        assert task.ingest_result is not None
        assert task.parse_result is not None
        assert task.score is not None
        assert isinstance(task.suggestions, list)
        assert isinstance(task.defects, list)

    def test_run_analysis_error_handling(self):
        task = asyncio.get_event_loop().run_until_complete(
            self.orchestrator.run_analysis("", "test.py")
        )
        # 空代码也应该不崩溃
        assert task.status == "completed" or task.status == "failed"

    def test_apply_suggestions(self):
        task = asyncio.get_event_loop().run_until_complete(
            self.orchestrator.run_analysis(SAMPLE_CODE, "test.py")
        )
        if task.suggestions:
            ids = [task.suggestions[0].suggestion_id]
            result = self.orchestrator.apply_suggestions(task.task_id, ids)
            assert "annotated_code" in result or "error" not in result

    def test_export_task_source(self):
        task = asyncio.get_event_loop().run_until_complete(
            self.orchestrator.run_analysis(SAMPLE_CODE, "test.py")
        )
        result = self.orchestrator.export_task(task.task_id, "source")
        assert "content" in result

    def test_export_task_html(self):
        task = asyncio.get_event_loop().run_until_complete(
            self.orchestrator.run_analysis(SAMPLE_CODE, "test.py")
        )
        result = self.orchestrator.export_task(task.task_id, "html")
        assert "content" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
