"""
LLM 供应商配置数据模型
支持动态管理多个大模型供应商（DeepSeek、OpenAI、本地模型等）
配置持久化到 JSON 文件，无需数据库依赖
"""
import json
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


class APIFormat(str, Enum):
    """API 格式枚举"""
    OPENAI_CHAT = "openai_chat"           # OpenAI Chat Completions (/v1/chat/completions)
    ANTHROPIC_MESSAGES = "anthropic_messages"  # Anthropic Messages (/v1/messages)
    GOOGLE_GENAI = "google_genai"         # Google Generative AI
    CUSTOM = "custom"                     # 自定义格式


# API 格式到 Endpoint 路径的映射
API_FORMAT_ENDPOINTS = {
    APIFormat.OPENAI_CHAT: "/v1/chat/completions",
    APIFormat.ANTHROPIC_MESSAGES: "/v1/messages",
    APIFormat.GOOGLE_GENAI: "/v1beta/models/{model}:generateContent",
    APIFormat.CUSTOM: "",
}

# API 格式到请求格式的映射说明
API_FORMAT_DESCRIPTIONS = {
    APIFormat.OPENAI_CHAT: "OpenAI Chat Completions (/v1/chat/completions)",
    APIFormat.ANTHROPIC_MESSAGES: "Anthropic Messages (/v1/messages)",
    APIFormat.GOOGLE_GENAI: "Google Generative AI",
    APIFormat.CUSTOM: "自定义格式",
}


@dataclass
class LLMModel:
    """单个模型配置"""
    model_id: str = ""                    # 模型ID，如 deepseek-coder
    model_name: str = ""                  # 显示名称
    max_context: int = 16384              # 最大上下文长度（tokens）
    has_vision: bool = False             # 是否支持视觉（图片输入）
    enabled: bool = True                  # 是否启用

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "max_context": self.max_context,
            "has_vision": self.has_vision,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LLMModel':
        return cls(
            model_id=data.get("model_id", ""),
            model_name=data.get("model_name", ""),
            max_context=data.get("max_context", 16384),
            has_vision=data.get("has_vision", False),
            enabled=data.get("enabled", True),
        )


@dataclass
class LLMProvider:
    """LLM 供应商配置"""
    provider_id: str = ""                 # 供应商ID（唯一标识）
    provider_name: str = ""               # 供应商名称（如 deepseek、openai）
    provider_type: str = "custom"         # 类型：builtin 内置 / custom 自定义
    base_url: str = ""                    # Base URL，如 https://api.deepseek.com/v1
    api_format: str = APIFormat.OPENAI_CHAT.value  # API 格式
    api_key: str = ""                     # API Key
    models: List[LLMModel] = field(default_factory=list)
    enabled: bool = True                  # 是否启用
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "base_url": self.base_url,
            "api_format": self.api_format,
            "api_key": self.api_key,
            "models": [m.to_dict() for m in self.models],
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LLMProvider':
        return cls(
            provider_id=data.get("provider_id", ""),
            provider_name=data.get("provider_name", ""),
            provider_type=data.get("provider_type", "custom"),
            base_url=data.get("base_url", ""),
            api_format=data.get("api_format", APIFormat.OPENAI_CHAT.value),
            api_key=data.get("api_key", ""),
            models=[LLMModel.from_dict(m) for m in data.get("models", [])],
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


# ========================
# 预设供应商模板
# ========================

BUILTIN_PROVIDERS = [
    {
        "provider_id": "deepseek",
        "provider_name": "DeepSeek",
        "provider_type": "builtin",
        "base_url": "https://api.deepseek.com/v1",
        "api_format": APIFormat.OPENAI_CHAT.value,
        "api_key": "",
        "models": [
            {"model_id": "deepseek-chat", "model_name": "DeepSeek Chat", "max_context": 65536, "has_vision": False, "enabled": True},
            {"model_id": "deepseek-coder", "model_name": "DeepSeek Coder", "max_context": 16384, "has_vision": False, "enabled": True},
        ],
        "enabled": False,
    },
    {
        "provider_id": "openai",
        "provider_name": "OpenAI",
        "provider_type": "builtin",
        "base_url": "https://api.openai.com/v1",
        "api_format": APIFormat.OPENAI_CHAT.value,
        "api_key": "",
        "models": [
            {"model_id": "gpt-4o", "model_name": "GPT-4o", "max_context": 128000, "has_vision": True, "enabled": True},
            {"model_id": "gpt-4o-mini", "model_name": "GPT-4o Mini", "max_context": 128000, "has_vision": True, "enabled": True},
            {"model_id": "gpt-4-turbo", "model_name": "GPT-4 Turbo", "max_context": 128000, "has_vision": True, "enabled": True},
        ],
        "enabled": False,
    },
    {
        "provider_id": "qwen",
        "provider_name": "千问 (Qwen)",
        "provider_type": "builtin",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_format": APIFormat.OPENAI_CHAT.value,
        "api_key": "",
        "models": [
            {"model_id": "qwen-turbo", "model_name": "Qwen Turbo", "max_context": 128000, "has_vision": False, "enabled": True},
            {"model_id": "qwen-plus", "model_name": "Qwen Plus", "max_context": 128000, "has_vision": False, "enabled": True},
            {"model_id": "qwen-max", "model_name": "Qwen Max", "max_context": 32000, "has_vision": True, "enabled": True},
        ],
        "enabled": False,
    },
    {
        "provider_id": "zhipu",
        "provider_name": "智谱 (Zhipu)",
        "provider_type": "builtin",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_format": APIFormat.OPENAI_CHAT.value,
        "api_key": "",
        "models": [
            {"model_id": "glm-4", "model_name": "GLM-4", "max_context": 128000, "has_vision": False, "enabled": True},
            {"model_id": "glm-4-flash", "model_name": "GLM-4 Flash", "max_context": 128000, "has_vision": False, "enabled": True},
            {"model_id": "glm-4v", "model_name": "GLM-4V", "max_context": 2048, "has_vision": True, "enabled": True},
        ],
        "enabled": False,
    },
]


# ========================
# 配置存储管理
# ========================

class ProviderConfigStore:
    """
    LLM 供应商配置存储
    使用 JSON 文件持久化，支持热加载
    """

    def __init__(self, config_path: str = None):
        self.config_path = config_path or self._default_config_path()
        self._providers: Dict[str, LLMProvider] = {}
        self._load_or_init()

    def _default_config_path(self) -> str:
        """默认配置路径"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_dir, "data", "llm_providers.json")

    def _load_or_init(self):
        """加载已有配置或初始化内置供应商"""
        if os.path.exists(self.config_path):
            self._load()
        else:
            self._init_defaults()

    def _load(self):
        """从 JSON 文件加载配置"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for p_data in data.get("providers", []):
                provider = LLMProvider.from_dict(p_data)
                self._providers[provider.provider_id] = provider
        except (json.JSONDecodeError, IOError) as e:
            import logging
            logging.getLogger(__name__).warning(f"加载LLM配置失败: {e}，使用默认配置")
            self._init_defaults()

    def _save(self):
        """保存配置到 JSON 文件"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        data = {
            "providers": [p.to_dict() for p in self._providers.values()],
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _init_defaults(self):
        """初始化内置供应商"""
        from datetime import datetime
        now = datetime.now().isoformat()
        for p_data in BUILTIN_PROVIDERS:
            p_data["created_at"] = now
            p_data["updated_at"] = now
            provider = LLMProvider.from_dict(p_data)
            self._providers[provider.provider_id] = provider
        self._save()

    # ---- CRUD 操作 ----

    def list_providers(self) -> List[LLMProvider]:
        """列出所有供应商"""
        return list(self._providers.values())

    def get_provider(self, provider_id: str) -> Optional[LLMProvider]:
        """获取单个供应商"""
        return self._providers.get(provider_id)

    def create_provider(self, data: dict) -> LLMProvider:
        """创建新供应商"""
        from datetime import datetime
        provider_id = data.get("provider_id") or f"provider-{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        provider = LLMProvider(
            provider_id=provider_id,
            provider_name=data.get("provider_name", "New Provider"),
            provider_type=data.get("provider_type", "custom"),
            base_url=data.get("base_url", ""),
            api_format=data.get("api_format", APIFormat.OPENAI_CHAT.value),
            api_key=data.get("api_key", ""),
            models=[LLMModel.from_dict(m) for m in data.get("models", [])],
            enabled=data.get("enabled", True),
            created_at=now,
            updated_at=now,
        )
        self._providers[provider_id] = provider
        self._save()
        return provider

    def update_provider(self, provider_id: str, data: dict) -> Optional[LLMProvider]:
        """更新供应商"""
        provider = self._providers.get(provider_id)
        if not provider:
            return None

        from datetime import datetime
        if "provider_name" in data:
            provider.provider_name = data["provider_name"]
        if "base_url" in data:
            provider.base_url = data["base_url"]
        if "api_format" in data:
            provider.api_format = data["api_format"]
        if "api_key" in data:
            provider.api_key = data["api_key"]
        if "enabled" in data:
            provider.enabled = data["enabled"]
        if "models" in data:
            provider.models = [LLMModel.from_dict(m) for m in data["models"]]

        provider.updated_at = datetime.now().isoformat()
        self._save()
        return provider

    def delete_provider(self, provider_id: str) -> bool:
        """删除供应商"""
        if provider_id in self._providers:
            # 内置供应商不允许删除，只允许禁用
            provider = self._providers[provider_id]
            if provider.provider_type == "builtin":
                provider.enabled = False
                from datetime import datetime
                provider.updated_at = datetime.now().isoformat()
                self._save()
                return True
            del self._providers[provider_id]
            self._save()
            return True
        return False

    def toggle_provider(self, provider_id: str) -> Optional[LLMProvider]:
        """切换供应商启用状态"""
        provider = self._providers.get(provider_id)
        if provider:
            provider.enabled = not provider.enabled
            from datetime import datetime
            provider.updated_at = datetime.now().isoformat()
            self._save()
        return provider

    def get_enabled_providers(self) -> List[LLMProvider]:
        """获取所有已启用的供应商"""
        return [p for p in self._providers.values() if p.enabled]

    def get_all_models(self) -> List[Dict[str, Any]]:
        """获取所有供应商的所有模型（扁平化列表）"""
        models = []
        for provider in self._providers.values():
            if not provider.enabled:
                continue
            for model in provider.models:
                if not model.enabled:
                    continue
                models.append({
                    "model_id": model.model_id,
                    "model_name": model.model_name,
                    "provider_id": provider.provider_id,
                    "provider_name": provider.provider_name,
                    "base_url": provider.base_url,
                    "api_format": provider.api_format,
                    "api_key": provider.api_key,
                    "max_context": model.max_context,
                    "has_vision": model.has_vision,
                })
        return models


# 全局单例
provider_store = ProviderConfigStore()
