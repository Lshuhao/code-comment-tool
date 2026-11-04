"""
M1 接入层模块 - 文件接收、编码检测、语言识别
职责：
- 文件上传接收与编码检测转UTF-8
- 语言识别（扩展名 + 内容关键词回退）
- 会话工作区管理（TTL）
"""
import os
import uuid
import time
import chardet
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass
class IngestResult:
    """M1模块输出结果"""
    code_text: str
    language: str
    filename: str
    file_size: int
    encoding: str = "utf-8"
    session_id: str = ""
    detected_language: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "code_text": self.code_text,
            "language": self.language,
            "filename": self.filename,
            "file_size": self.file_size,
            "encoding": self.encoding,
            "session_id": self.session_id,
            "detected_language": self.detected_language,
        }


# 扩展名到语言的映射
EXTENSION_MAP = {
    ".py": "python",
    ".pyw": "python",
    ".pyx": "python",
    ".java": "java",
    ".c": "cpp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
}

# 语言特征关键词（用于内容回退识别）
LANGUAGE_KEYWORDS = {
    "python": [
        "def ", "import ", "from ", "class ", "self.", "__init__",
        "print(", "elif ", "except:", "lambda ", "yield ",
        "if __name__", "async def", "await ",
    ],
    "java": [
        "public class", "private ", "protected ", "static void",
        "System.out", "import java", "package ", "@Override",
        "new ArrayList", "throws ", "extends ",
    ],
    "cpp": [
        "#include", "std::", "cout", "cin", "namespace ",
        "int main", "void ", "template", "class ", "struct ",
        "#define", "typedef", "using namespace",
    ],
}


class SessionManager:
    """会话工作区管理器（内存版，可选Redis扩展）"""

    def __init__(self, ttl: int = 3600):
        self.ttl = ttl
        self._sessions: Dict[str, dict] = {}

    def create_session(self) -> str:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "created_at": time.time(),
            "last_access": time.time(),
            "files": {},
        }
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话（检查TTL）"""
        if session_id not in self._sessions:
            return None
        session = self._sessions[session_id]
        if time.time() - session["last_access"] > self.ttl:
            self.delete_session(session_id)
            return None
        session["last_access"] = time.time()
        return session

    def store_file(self, session_id: str, filename: str, content: str, language: str):
        """在会话中存储文件"""
        session = self.get_session(session_id)
        if session:
            session["files"][filename] = {
                "content": content,
                "language": language,
                "uploaded_at": time.time(),
            }

    def delete_session(self, session_id: str):
        """删除会话"""
        self._sessions.pop(session_id, None)

    def cleanup_expired(self):
        """清理过期会话"""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s["last_access"] > self.ttl
        ]
        for sid in expired:
            del self._sessions[sid]


class IngestService:
    """M1 接入层服务"""

    def __init__(self):
        self.session_manager = SessionManager(ttl=settings.SESSION_TTL)

    def detect_encoding(self, raw_bytes: bytes) -> str:
        """检测文件编码"""
        result = chardet.detect(raw_bytes)
        encoding = result.get("encoding", "utf-8")
        confidence = result.get("confidence", 0)

        # 低置信度回退到UTF-8
        if confidence < 0.5:
            return "utf-8"
        return encoding or "utf-8"

    def detect_language_by_extension(self, filename: str) -> Optional[str]:
        """通过扩展名识别语言"""
        _, ext = os.path.splitext(filename.lower())
        return EXTENSION_MAP.get(ext)

    def detect_language_by_content(self, code: str) -> Optional[str]:
        """通过内容关键词识别语言（回退方案）"""
        scores = {}
        for lang, keywords in LANGUAGE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in code)
            scores[lang] = score

        if not scores or max(scores.values()) == 0:
            return None

        return max(scores, key=scores.get)

    def detect_language(self, filename: str, code: str) -> str:
        """
        综合语言识别：扩展名优先，内容关键词回退
        """
        # 1. 先尝试扩展名
        lang = self.detect_language_by_extension(filename)
        if lang:
            return lang

        # 2. 内容关键词回退
        lang = self.detect_language_by_content(code)
        if lang:
            return lang

        # 3. 默认为python（可扩展）
        return "python"

    def ingest_file(
        self,
        file_content: bytes,
        filename: str,
        session_id: Optional[str] = None,
    ) -> IngestResult:
        """
        处理上传文件
        1. 检测编码并转UTF-8
        2. 识别语言
        3. 存入会话工作区
        """
        # 1. 检测编码
        encoding = self.detect_encoding(file_content)

        # 2. 解码为UTF-8字符串
        try:
            code_text = file_content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            code_text = file_content.decode("utf-8", errors="replace")

        # 3. 识别语言
        language = self.detect_language(filename, code_text)

        # 4. 会话管理
        if not session_id:
            session_id = self.session_manager.create_session()

        self.session_manager.store_file(
            session_id, filename, code_text, language
        )

        return IngestResult(
            code_text=code_text,
            language=language,
            filename=filename,
            file_size=len(file_content),
            encoding=encoding,
            session_id=session_id,
            detected_language=language,
        )

    def ingest_text(
        self,
        text: str,
        filename: str = "untitled.py",
        language_hint: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> IngestResult:
        """
        处理粘贴的文本
        """
        code_text = text.encode("utf-8").decode("utf-8")  # 确保UTF-8

        # 语言识别
        if language_hint:
            language = language_hint
        else:
            language = self.detect_language(filename, code_text)

        # 会话管理
        if not session_id:
            session_id = self.session_manager.create_session()

        self.session_manager.store_file(
            session_id, filename, code_text, language
        )

        return IngestResult(
            code_text=code_text,
            language=language,
            filename=filename,
            file_size=len(text.encode("utf-8")),
            encoding="utf-8",
            session_id=session_id,
            detected_language=language,
        )


# 全局单例
ingest_service = IngestService()
