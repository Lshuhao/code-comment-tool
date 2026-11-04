"""
全局配置模块 - 集中管理应用配置项
使用 pydantic-settings 支持环境变量覆盖
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用全局配置"""

    # 应用基础配置
    APP_NAME: str = "代码注释自动生成与优化建议工具"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # LLM配置
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-coder"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.3

    # Redis配置（会话缓存）
    REDIS_URL: Optional[str] = None  # None时使用内存字典
    SESSION_TTL: int = 3600  # 会话过期时间（秒）

    # 文件上传限制
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: list = [".py", ".java", ".cpp", ".c", ".h", ".hpp"]

    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # 评分权重
    SCORE_WEIGHTS: dict = {
        "coverage": 0.3,
        "completeness": 0.3,
        "consistency": 0.2,
        "standard": 0.2,
    }

    # CodeBERT模型路径
    CODEBERT_MODEL: str = "microsoft/codebert-base"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
