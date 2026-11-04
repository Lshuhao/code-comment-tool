"""
M7 编排服务层 - 流水线调度
职责：
- FastAPI路由定义
- 会话工作区管理
- 流水线调度（M1→M2→M3/M4/M5）
- 错误处理
注意：此层只做编排不做业务，避免逻辑泄漏
"""
import time
import uuid
from typing import List, Optional, Dict, Any

from app.services.m1_ingest import IngestService, IngestResult, ingest_service
from app.services.m2_parser import ParserFactory, parse_code
from app.services.m3_comment_gen import CommentGenerationService, comment_gen_service
from app.services.m4_defect import DefectDetectionService, defect_detection_service
from app.services.m5_scoring import QualityScoringService, scoring_service
from app.services.m6_export import ExportService, export_service
from app.models.unified_ast import ParseResult
from app.models.suggestions import (
    CommentSuggestion, Defect, QualityScore
)


class AnalysisTask:
    """分析任务 - 跟踪流水线状态"""

    def __init__(self, task_id: str = None):
        self.task_id = task_id or str(uuid.uuid4())
        self.status: str = "pending"  # pending/running/completed/failed
        self.created_at: float = time.time()
        self.updated_at: float = time.time()

        # 各阶段结果
        self.ingest_result: Optional[IngestResult] = None
        self.parse_result: Optional[ParseResult] = None
        self.suggestions: List[CommentSuggestion] = []
        self.defects: List[Defect] = []
        self.score: Optional[QualityScore] = None
        self.annotated_code: Optional[str] = None
        self.error: Optional[str] = None

        # 用户采纳状态
        self.accepted_suggestion_ids: List[str] = []
        self.rejected_suggestion_ids: List[str] = []

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ingest": self.ingest_result.to_dict() if self.ingest_result else None,
            "parse": self.parse_result.to_dict() if self.parse_result else None,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "defects": [d.to_dict() for d in self.defects],
            "score": self.score.to_dict() if self.score else None,
            "annotated_code": self.annotated_code,
            "error": self.error,
            "accepted_ids": self.accepted_suggestion_ids,
            "rejected_ids": self.rejected_suggestion_ids,
        }


class PipelineOrchestrator:
    """
    流水线编排器
    职责：按顺序调度M1→M2→M3/M4→M5，不做业务逻辑
    """

    def __init__(self):
        self.ingest = ingest_service
        self.comment_gen = comment_gen_service
        self.defect_detect = defect_detection_service
        self.scoring = scoring_service
        self.export = export_service
        self._tasks: Dict[str, AnalysisTask] = {}
        self._llm_provider_id = None
        self._llm_model_id = None

    def set_llm_config(self, provider_id: str = None, model_id: str = None):
        """设置使用的LLM供应商和模型"""
        self._llm_provider_id = provider_id
        self._llm_model_id = model_id

    def _get_llm_client(self):
        """获取LLM客户端（优先使用配置的供应商）"""
        from app.services.llm_client import LLMClientFactory
        if self._llm_provider_id and self._llm_model_id:
            return LLMClientFactory.create(self._llm_provider_id, self._llm_model_id)
        return LLMClientFactory.create()

    def create_task(self) -> AnalysisTask:
        """创建新任务"""
        task = AnalysisTask()
        self._tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[AnalysisTask]:
        """获取任务"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        return [t.to_dict() for t in self._tasks.values()]

    async def run_analysis(
        self,
        code_text: str,
        filename: str = "untitled.py",
        language_hint: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> AnalysisTask:
        """
        执行完整分析流水线
        M1(接入) → M2(解析) → M3(注释生成) + M4(缺陷检测) → M5(评分)
        """
        # 获取或创建任务
        task = self.get_task(task_id) if task_id else None
        if not task:
            task = self.create_task()

        task.status = "running"
        task.updated_at = time.time()

        try:
            # === M1: 接入层 ===
            ingest_result = self.ingest.ingest_text(
                code_text, filename, language_hint, session_id
            )
            task.ingest_result = ingest_result

            # === M2: AST解析层 ===
            parse_result = parse_code(
                ingest_result.code_text, ingest_result.language
            )
            task.parse_result = parse_result

            # === M3: 注释生成（使用动态LLM客户端）===
            llm_client = self._get_llm_client()
            dynamic_comment_gen = CommentGenerationService(llm_client=llm_client)
            suggestions = await dynamic_comment_gen.generate_all(parse_result)
            task.suggestions = suggestions

            # === M4: 缺陷检测 ===
            defects = await self.defect_detect.detect_all(parse_result)
            task.defects = defects

            # === M5: 质量评分 ===
            score = self.scoring.calculate(parse_result, defects)
            task.score = score

            task.status = "completed"
            task.updated_at = time.time()

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.updated_at = time.time()

        return task

    def apply_suggestions(
        self,
        task_id: str,
        accepted_ids: List[str],
    ) -> Dict[str, Any]:
        """
        应用用户采纳的建议
        生成带注释的代码并重新评分
        """
        task = self.get_task(task_id)
        if not task or task.status != "completed":
            return {"error": "任务不存在或未完成"}

        task.accepted_suggestion_ids = accepted_ids

        # 生成带注释的代码
        annotated_code = self.export.generate_annotated_code(
            task.ingest_result.code_text,
            task.suggestions,
            task.parse_result,
            accepted_ids,
        )

        # 验证代码合法性
        validation = self.export.validate_code(
            annotated_code, task.ingest_result.language
        )

        task.annotated_code = annotated_code

        # 计算采纳后的评分
        after_score = self.scoring.calculate_after_score(
            task.parse_result,
            task.score,
            len(accepted_ids),
            len(task.suggestions),
        )

        return {
            "annotated_code": annotated_code,
            "validation": validation,
            "after_score": after_score.to_dict(),
            "accepted_count": len(accepted_ids),
            "total_count": len(task.suggestions),
        }

    def export_task(
        self,
        task_id: str,
        export_format: str = "source",
        accepted_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """导出任务结果"""
        task = self.get_task(task_id)
        if not task or task.status != "completed":
            return {"error": "任务不存在或未完成"}

        if export_format == "source":
            code = task.annotated_code or task.ingest_result.code_text
            return self.export.export_source(
                code,
                task.ingest_result.filename,
                task.ingest_result.language,
            )

        elif export_format == "markdown":
            return self.export.export_markdown_report(
                task.score, task.defects, task.suggestions
            )

        elif export_format == "html":
            return self.export.export_html_report(
                task.score, task.defects, task.suggestions,
                task.ingest_result.code_text,
                task.annotated_code or "",
            )

        elif export_format == "pdf":
            result = self.export.export_pdf_report(
                task.score, task.defects, task.suggestions
            )
            return result or {"error": "PDF导出不可用"}

        return {"error": f"不支持的导出格式: {export_format}"}


# 全局单例
orchestrator = PipelineOrchestrator()
