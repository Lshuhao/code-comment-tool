"""
API路由定义 - HTTP接口层
"""
import os
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse, Response

from app.services.m7_orchestrator import orchestrator
from app.core.config import settings

router = APIRouter()


# ========================
# 文件上传接口
# ========================

@router.post("/api/v1/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """
    上传代码文件进行分析
    支持 .py, .java, .cpp, .c, .h 等格式
    """
    # 检查文件扩展名
    filename = file.filename or "untitled.py"
    _, ext = os.path.splitext(filename.lower())
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，支持: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # 读取文件内容
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大支持 {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB"
        )

    # 创建任务并运行分析
    task = await orchestrator.run_analysis(
        code_text=content.decode("utf-8", errors="replace"),
        filename=filename,
        session_id=session_id,
    )

    return JSONResponse(content={
        "task_id": task.task_id,
        "status": task.status,
        "filename": filename,
        "language": task.ingest_result.language if task.ingest_result else None,
        "summary": {
            "total_functions": len(task.parse_result.get_all_functions()) if task.parse_result else 0,
            "total_classes": len(task.parse_result.get_all_classes()) if task.parse_result else 0,
            "suggestions_count": len(task.suggestions),
            "defects_count": len(task.defects),
            "score": task.score.score if task.score else 0,
        },
    })


# ========================
# 文本粘贴接口
# ========================

@router.post("/api/v1/analyze")
async def analyze_text(
    code: str = Form(...),
    filename: str = Form("untitled.py"),
    language: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
):
    """
    分析粘贴的代码文本
    """
    if not code.strip():
        raise HTTPException(status_code=400, detail="代码内容不能为空")

    task = await orchestrator.run_analysis(
        code_text=code,
        filename=filename,
        language_hint=language,
        session_id=session_id,
    )

    return JSONResponse(content=task.to_dict())


# ========================
# 任务查询接口
# ========================

@router.get("/api/v1/task/{task_id}")
async def get_task(task_id: str):
    """获取任务详情（完整结果）"""
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JSONResponse(content=task.to_dict())


@router.get("/api/v1/tasks")
async def list_tasks():
    """列出所有任务"""
    tasks = orchestrator.list_tasks()
    return JSONResponse(content={"tasks": tasks, "total": len(tasks)})


# ========================
# 建议管理接口
# ========================

@router.get("/api/v1/task/{task_id}/suggestions")
async def get_suggestions(task_id: str):
    """获取任务的所有注释建议"""
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JSONResponse(content={
        "suggestions": [s.to_dict() for s in task.suggestions],
        "total": len(task.suggestions),
    })


@router.post("/api/v1/task/{task_id}/accept")
async def accept_suggestions(
    task_id: str,
    suggestion_ids: List[str] = None,
):
    """
    采纳注释建议，生成带注释的代码
    """
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if suggestion_ids is None:
        # 采纳所有建议
        suggestion_ids = [s.suggestion_id for s in task.suggestions]

    result = orchestrator.apply_suggestions(task_id, suggestion_ids)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return JSONResponse(content=result)


@router.post("/api/v1/task/{task_id}/reject")
async def reject_suggestions(
    task_id: str,
    suggestion_ids: List[str] = None,
):
    """拒绝注释建议"""
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if suggestion_ids:
        task.rejected_suggestion_ids.extend(suggestion_ids)

    return JSONResponse(content={"status": "ok", "rejected": len(suggestion_ids or [])})


# ========================
# 缺陷查询接口
# ========================

@router.get("/api/v1/task/{task_id}/defects")
async def get_defects(task_id: str):
    """获取检测到的注释缺陷"""
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JSONResponse(content={
        "defects": [d.to_dict() for d in task.defects],
        "total": len(task.defects),
    })


# ========================
# 评分查询接口
# ========================

@router.get("/api/v1/task/{task_id}/score")
async def get_score(task_id: str):
    """获取质量评分"""
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.score:
        raise HTTPException(status_code=404, detail="评分尚未生成")
    return JSONResponse(content=task.score.to_dict())


# ========================
# 导出接口
# ========================

@router.get("/api/v1/task/{task_id}/export/{format}")
async def export_result(
    task_id: str,
    format: str,  # source/markdown/html/pdf
):
    """导出分析结果"""
    result = orchestrator.export_task(task_id, format)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    content = result["content"]
    content_type = result.get("content_type", "text/plain")
    filename = result.get("filename", f"export.{format}")

    if isinstance(content, bytes):
        return Response(content=content, media_type=content_type)
    else:
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


# ========================
# 健康检查
# ========================

@router.get("/api/v1/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "supported_languages": ["python", "java", "cpp"],
    }


# ========================
# LLM 供应商管理接口
# ========================

@router.get("/api/v1/providers")
async def list_providers():
    """列出所有 LLM 供应商"""
    from app.models.llm_provider import provider_store
    providers = provider_store.list_providers()
    return {
        "providers": [
            {
                "provider_id": p.provider_id,
                "provider_name": p.provider_name,
                "provider_type": p.provider_type,
                "base_url": p.base_url,
                "api_format": p.api_format,
                "api_key": p.api_key[:8] + "..." + p.api_key[-4:] if len(p.api_key) > 12 else ("***" if p.api_key else ""),
                "api_key_full": p.api_key,
                "models": [m.to_dict() for m in p.models],
                "enabled": p.enabled,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in providers
        ],
        "total": len(providers),
    }


@router.get("/api/v1/providers/models")
async def list_all_models():
    """获取所有已启用供应商的可用模型列表"""
    from app.models.llm_provider import provider_store
    models = provider_store.get_all_models()
    return {"models": models, "total": len(models)}


@router.post("/api/v1/providers/test")
async def test_provider_connection(data: dict):
    """测试供应商连接（验证 API Key 和 Base URL）"""
    from app.services.llm_client import DynamicLLMClient

    client = DynamicLLMClient({
        "base_url": data.get("base_url", ""),
        "api_format": data.get("api_format", "openai_chat"),
        "api_key": data.get("api_key", ""),
        "model": data.get("model", ""),
        "max_tokens": 50,
        "temperature": 0.1,
    })

    try:
        result = await client.generate("你好，请回复'连接成功'四个字")
        return {"status": "ok", "response": result[:100]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接失败: {str(e)}")


@router.get("/api/v1/providers/{provider_id}")
async def get_provider(provider_id: str):
    """获取单个供应商详情"""
    from app.models.llm_provider import provider_store
    provider = provider_store.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {
        "provider": {
            "provider_id": provider.provider_id,
            "provider_name": provider.provider_name,
            "provider_type": provider.provider_type,
            "base_url": provider.base_url,
            "api_format": provider.api_format,
            "api_key": provider.api_key,
            "models": [m.to_dict() for m in provider.models],
            "enabled": provider.enabled,
        }
    }


@router.post("/api/v1/providers")
async def create_provider(data: dict):
    """创建新 LLM 供应商"""
    from app.models.llm_provider import provider_store
    provider = provider_store.create_provider(data)
    return {"provider": provider.to_dict()}


@router.put("/api/v1/providers/{provider_id}")
async def update_provider(provider_id: str, data: dict):
    """更新供应商配置"""
    from app.models.llm_provider import provider_store
    provider = provider_store.update_provider(provider_id, data)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {"provider": provider.to_dict()}


@router.delete("/api/v1/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """删除供应商（内置供应商改为禁用）"""
    from app.models.llm_provider import provider_store
    ok = provider_store.delete_provider(provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {"status": "ok"}


@router.post("/api/v1/providers/{provider_id}/toggle")
async def toggle_provider(provider_id: str):
    """切换供应商启用/禁用状态"""
    from app.models.llm_provider import provider_store
    provider = provider_store.toggle_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {"provider": provider.to_dict()}
