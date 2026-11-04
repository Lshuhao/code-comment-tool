"""
全局配置模块 - 仅保留 Tkinter GUI 实际使用的配置项
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用全局配置"""

    # LLM配置
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-coder"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.3

    # 会话配置（M1接入层使用）
    SESSION_TTL: int = 3600  # 会话过期时间（秒）

    # 评分权重（M5评分模块使用）
    SCORE_WEIGHTS: dict = {
        "coverage": 0.3,
        "completeness": 0.3,
        "consistency": 0.2,
        "standard": 0.2,
    }

    # CodeBERT模型路径（M4语义层检测使用）
    CODEBERT_MODEL: str = "microsoft/codebert-base"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
