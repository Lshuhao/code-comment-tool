"""
M9 历史记录模块（可选）
职责：
- 任务持久化
- SQLite存储
- gzip压缩存储源码
"""
import json
import gzip
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict

try:
    from sqlalchemy import Column, Integer, String, Float, Text, DateTime, create_engine
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker, declarative_base
    from sqlalchemy import select
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

from app.core.config import settings


Base = declarative_base() if HAS_SQLALCHEMY else None


class HistoryRecord(Base if HAS_SQLALCHEMY else object):
    """历史记录数据库模型"""

    if HAS_SQLALCHEMY:
        __tablename__ = "analysis_history"

        id = Column(Integer, primary_key=True, autoincrement=True)
        task_id = Column(String(64), unique=True, index=True)
        filename = Column(String(256))
        language = Column(String(32))
        score = Column(Float)
        suggestions_count = Column(Integer, default=0)
        defects_count = Column(Integer, default=0)
        accepted_count = Column(Integer, default=0)
        source_code_gz = Column(Text)  # gzip压缩的源码
        result_json = Column(Text)  # JSON格式的结果
        created_at = Column(DateTime)
        updated_at = Column(DateTime)


class HistoryService:
    """历史记录服务"""

    def __init__(self, database_url: str = None):
        self.database_url = database_url or settings.DATABASE_URL
        self._memory_store: Dict[str, dict] = {}  # 内存回退存储
        self._initialized = False

        if HAS_SQLALCHEMY:
            try:
                self.engine = create_async_engine(self.database_url, echo=False)
                self.async_session = sessionmaker(
                    self.engine, class_=AsyncSession, expire_on_commit=False
                )
            except Exception:
                self.engine = None
                self.async_session = None
        else:
            self.engine = None
            self.async_session = None

    async def init_db(self):
        """初始化数据库"""
        if self._initialized:
            return
        if HAS_SQLALCHEMY and self.engine:
            try:
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                self._initialized = True
            except Exception:
                pass

    async def save_task(self, task_data: dict):
        """保存任务记录"""
        # 压缩源码
        source_code = task_data.get("ingest", {}).get("code_text", "")
        source_gz = self._compress(source_code)

        record = {
            "task_id": task_data.get("task_id", ""),
            "filename": task_data.get("ingest", {}).get("filename", ""),
            "language": task_data.get("ingest", {}).get("language", ""),
            "score": task_data.get("score", {}).get("score", 0) if task_data.get("score") else 0,
            "suggestions_count": len(task_data.get("suggestions", [])),
            "defects_count": len(task_data.get("defects", [])),
            "accepted_count": len(task_data.get("accepted_ids", [])),
            "source_code_gz": source_gz,
            "result_json": json.dumps(task_data, ensure_ascii=False),
            "created_at": task_data.get("created_at", time.time()),
        }

        if HAS_SQLALCHEMY and self.async_session:
            try:
                async with self.async_session() as session:
                    db_record = HistoryRecord(**record)
                    session.add(db_record)
                    await session.commit()
                    return
            except Exception:
                pass

        # 回退到内存存储
        self._memory_store[record["task_id"]] = record

    async def get_history(
        self, limit: int = 20, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取历史记录列表"""
        if HAS_SQLALCHEMY and self.async_session:
            try:
                async with self.async_session() as session:
                    result = await session.execute(
                        select(HistoryRecord)
                        .order_by(HistoryRecord.created_at.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                    records = result.scalars().all()
                    return [
                        {
                            "task_id": r.task_id,
                            "filename": r.filename,
                            "language": r.language,
                            "score": r.score,
                            "suggestions_count": r.suggestions_count,
                            "defects_count": r.defects_count,
                            "accepted_count": r.accepted_count,
                            "created_at": str(r.created_at) if r.created_at else "",
                        }
                        for r in records
                    ]
            except Exception:
                pass

        # 回退到内存
        records = sorted(
            self._memory_store.values(),
            key=lambda x: x.get("created_at", 0),
            reverse=True,
        )
        return [
            {
                "task_id": r["task_id"],
                "filename": r["filename"],
                "language": r["language"],
                "score": r["score"],
                "suggestions_count": r["suggestions_count"],
                "defects_count": r["defects_count"],
                "accepted_count": r["accepted_count"],
                "created_at": str(r.get("created_at", "")),
            }
            for r in records[offset:offset + limit]
        ]

    async def get_task_detail(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务详细记录"""
        if HAS_SQLALCHEMY and self.async_session:
            try:
                async with self.async_session() as session:
                    result = await session.execute(
                        select(HistoryRecord).where(
                            HistoryRecord.task_id == task_id
                        )
                    )
                    record = result.scalars().first()
                    if record:
                        return json.loads(record.result_json)
            except Exception:
                pass

        # 回退到内存
        record = self._memory_store.get(task_id)
        if record:
            return json.loads(record.get("result_json", "{}"))
        return None

    async def delete_task(self, task_id: str) -> bool:
        """删除任务记录"""
        if HAS_SQLALCHEMY and self.async_session:
            try:
                async with self.async_session() as session:
                    result = await session.execute(
                        select(HistoryRecord).where(
                            HistoryRecord.task_id == task_id
                        )
                    )
                    record = result.scalars().first()
                    if record:
                        await session.delete(record)
                        await session.commit()
                        return True
            except Exception:
                pass

        if task_id in self._memory_store:
            del self._memory_store[task_id]
            return True
        return False

    def _compress(self, text: str) -> str:
        """gzip压缩文本"""
        import base64
        compressed = gzip.compress(text.encode("utf-8"))
        return base64.b64encode(compressed).decode("ascii")

    def _decompress(self, text: str) -> str:
        """gzip解压文本"""
        import base64
        compressed = base64.b64decode(text.encode("ascii"))
        return gzip.decompress(compressed).decode("utf-8")


# 全局单例
history_service = HistoryService()
