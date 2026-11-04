"""
动态 LLM 客户端 - 优化版
支持：
- 重试机制（自动重试3次，指数退避）
- 流式输出（SSE，实时返回token）
- Token计数和费用估算
- HTTP连接池复用
- 多供应商切换
"""
import json
import time
import logging
from typing import Optional, Dict, Any, List, AsyncIterator
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ========================
# 数据结构
# ========================

@dataclass
class TokenUsage:
    """Token使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        """估算费用（以DeepSeek定价为基准）"""
        # DeepSeek: 输入2元/百万token，输出8元/百万token
        return (self.prompt_tokens * 2 + self.total_tokens * 8) / 1_000_000


@dataclass
class LLMResponse:
    """LLM响应"""
    text: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    is_streaming: bool = False


# ========================
# 接口定义
# ========================

class LLMClient(ABC):
    """LLM 客户端接口"""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """生成文本（非流式）"""
        pass

    async def generate_stream(self, prompt: str, system_prompt: str = None, **kwargs) -> AsyncIterator[str]:
        """流式生成（可选实现）"""
        # 默认回退到非流式
        text = await self.generate(prompt, system_prompt, **kwargs)
        yield text

    @abstractmethod
    def get_usage(self) -> TokenUsage:
        """获取Token使用统计"""
        pass


# ========================
# Mock 客户端
# ========================

class MockLLMClient(LLMClient):
    """Mock LLM 客户端 - 开发阶段使用"""

    def __init__(self):
        self._usage = TokenUsage()

    async def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        code = self._extract_code(prompt)
        func_name = self._extract_func_name(prompt)

        if "docstring" in prompt.lower() or "文档" in prompt:
            return self._generate_docstring(code, func_name)
        elif "inline" in prompt.lower() or "行内" in prompt:
            return self._generate_inline(code)
        return "# Auto-generated comment"

    def get_usage(self) -> TokenUsage:
        return self._usage

    # --- Mock智能生成（从原llm_client.py迁移） ---

    def _extract_code(self, prompt: str) -> str:
        import re
        match = re.search(r'```(?:\w+)?\n(.*?)```', prompt, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _extract_func_name(self, prompt: str) -> str:
        import re
        match = re.search(r'(?:函数[//]类|函数)名称[:\s]*(\w+)', prompt)
        if match:
            return match.group(1)
        match = re.search(r'def\s+(\w+)', prompt)
        if match:
            return match.group(1)
        return "unknown"

    def _analyze_function(self, code: str) -> dict:
        import re
        info = {"name": "unknown", "params": [], "has_return": False,
                "has_loop": False, "has_condition": False, "has_try": False,
                "description": "", "complexity": 0}
        m = re.search(r'def\s+(\w+)\s*\(([^)]*)\)', code)
        if m:
            info["name"] = m.group(1)
            params_str = m.group(2).strip()
            if params_str:
                info["params"] = [p.strip().split(':')[0].split('=')[0].strip()
                                  for p in params_str.split(',') if p.strip() and p.strip() != 'self']
        info["has_return"] = bool(re.search(r'\breturn\b', code))
        info["has_loop"] = bool(re.search(r'\b(for|while)\b', code))
        info["has_condition"] = bool(re.search(r'\bif\b', code))
        info["has_try"] = bool(re.search(r'\btry\b', code))
        info["complexity"] = sum([len(re.findall(r'\bfor\b', code)),
                                   len(re.findall(r'\bwhile\b', code)),
                                   len(re.findall(r'\bif\b', code))])
        name_hints = {
            "calculate": "计算", "compute": "计算", "get": "获取", "set": "设置",
            "find": "查找", "search": "搜索", "sort": "排序", "filter": "过滤",
            "parse": "解析", "convert": "转换", "validate": "验证", "process": "处理",
            "read": "读取", "write": "写入", "connect": "连接", "initialize": "初始化",
            "average": "计算平均值", "sum": "求和", "max": "获取最大值", "min": "获取最小值",
            "merge": "合并", "split": "拆分", "check": "检查", "helper": "辅助函数",
            "main": "主函数", "test": "测试",
        }
        for kw, desc in name_hints.items():
            if kw in info["name"].lower():
                info["description"] = desc
                break
        return info

    def _generate_docstring(self, code: str, func_name: str) -> str:
        info = self._analyze_function(code)
        desc = info["description"] or f"执行{info['name']}相关操作"
        extras = []
        if info["has_loop"]: extras.append("通过循环处理数据")
        if info["has_condition"]: extras.append("包含条件判断逻辑")
        if info["has_try"]: extras.append("包含异常处理")
        if extras: desc += "，" + "，".join(extras)

        lines = [f"{desc}。", ""]
        if info["params"]:
            lines.append("Args:")
            for p in info["params"]:
                lines.append(f"    {p}: 输入参数")
            lines.append("")
        if info["has_return"]:
            lines.append("Returns:")
            lines.append("    处理结果。")
            lines.append("")
        return "\n".join(lines)

    def _generate_inline(self, code: str) -> str:
        if "for " in code and "in " in code: return "# 遍历数据集合进行处理"
        if "if " in code and "else" in code: return "# 根据条件分支处理不同情况"
        if "return " in code:
            import re
            m = re.search(r'return\s+(.+)', code)
            if m:
                expr = m.group(1).strip()
                if "/" in expr and "len" in expr: return "# 计算并返回平均值"
                if "+" in expr: return "# 返回累加结果"
            return "# 返回处理结果"
        if ".append(" in code: return "# 将结果添加到列表"
        return "# 执行操作"


# ========================
# 动态 LLM 客户端（优化版）
# ========================

class DynamicLLMClient(LLMClient):
    """
    动态 LLM 客户端 - 支持重试、流式、Token计数、连接池
    """

    # 默认重试配置
    MAX_RETRIES = 3
    RETRY_BACKOFF = 1.0  # 秒，指数退避基数

    def __init__(self, provider_config: dict = None):
        self.config = provider_config or {}
        self._client = None  # httpx.AsyncClient（连接池）
        self._usage = TokenUsage()
        self._total_cost = 0.0

    def _get_client(self):
        """获取或创建HTTP客户端（连接池复用）"""
        if self._client is None or self._client.is_closed:
            import httpx
            self._client = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                    keepalive_expiry=30.0,
                ),
            )
        return self._client

    async def _close(self):
        """关闭连接池"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def get_usage(self) -> TokenUsage:
        return self._usage

    def get_total_cost(self) -> float:
        """获取累计费用（美元）"""
        return self._total_cost

    async def generate(self, prompt: str, system_prompt: str = None, timeout: int = None, **kwargs) -> str:
        """生成文本（带重试）"""
        if timeout:
            kwargs["timeout"] = timeout
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return await self._do_generate(prompt, system_prompt, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = self.RETRY_BACKOFF * (2 ** attempt)
                    logger.warning(f"LLM调用失败(第{attempt+1}次): {e}，{wait:.1f}秒后重试...")
                    await asyncio.sleep(wait)
                else:
                    logger.warning(f"LLM调用{self.MAX_RETRIES}次均失败，回退Mock: {e}")

        # 所有重试失败，回退Mock
        mock = MockLLMClient()
        return await mock.generate(prompt, system_prompt, **kwargs)

    async def generate_stream(
        self, prompt: str, system_prompt: str = None, **kwargs
    ) -> AsyncIterator[str]:
        """流式生成（SSE）"""
        api_format = self.config.get("api_format", "openai_chat")
        base_url = self.config.get("base_url", "").rstrip("/")
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "")

        if not api_key or not base_url:
            mock = MockLLMClient()
            text = await mock.generate(prompt, system_prompt, **kwargs)
            yield text
            return

        client = self._get_client()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if api_format == "openai_chat":
            url = f"{base_url}/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": kwargs.get("max_tokens", self.config.get("max_tokens", 2048)),
                "temperature": kwargs.get("temperature", self.config.get("temperature", 0.3)),
                "stream": True,
            }

            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                            # 收集usage（通常在最后一个chunk）
                            if "usage" in chunk:
                                u = chunk["usage"]
                                self._usage = TokenUsage(
                                    prompt_tokens=u.get("prompt_tokens", 0),
                                    completion_tokens=u.get("completion_tokens", 0),
                                    total_tokens=u.get("total_tokens", 0),
                                )
                                self._total_cost += self._usage.cost_usd
                        except json.JSONDecodeError:
                            continue

    async def _do_generate(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """执行单次API调用"""
        api_format = self.config.get("api_format", "openai_chat")
        base_url = self.config.get("base_url", "").rstrip("/")
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "")
        max_tokens = kwargs.get("max_tokens", self.config.get("max_tokens", 2048))
        temperature = kwargs.get("temperature", self.config.get("temperature", 0.3))
        timeout = kwargs.get("timeout", 60)

        if not api_key or not base_url:
            mock = MockLLMClient()
            return await mock.generate(prompt, system_prompt, **kwargs)

        client = self._get_client()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if api_format == "openai_chat":
            url = f"{base_url}/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # 提取文本
            text = data["choices"][0]["message"]["content"]

            # 统计Token
            if "usage" in data:
                u = data["usage"]
                self._usage = TokenUsage(
                    prompt_tokens=u.get("prompt_tokens", 0),
                    completion_tokens=u.get("completion_tokens", 0),
                    total_tokens=u.get("total_tokens", 0),
                )
                self._total_cost += self._usage.cost_usd

            return text

        elif api_format == "anthropic_messages":
            url = f"{base_url}/messages"
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            headers.pop("Authorization", None)

            messages = [{"role": "user", "content": prompt}]
            payload = {
                "model": model, "messages": messages,
                "max_tokens": max_tokens, "system": system_prompt or "",
            }

            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

        return ""

# ========================
# 客户端工厂
# ========================

class LLMClientFactory:
    """LLM 客户端工厂"""

    @staticmethod
    def create(provider_id: str = None, model_id: str = None) -> LLMClient:
        from app.models.llm_provider import provider_store

        if provider_id and model_id:
            provider = provider_store.get_provider(provider_id)
            if provider and provider.enabled:
                model_config = next(
                    (m for m in provider.models if m.model_id == model_id and m.enabled), None
                )
                if model_config:
                    return DynamicLLMClient({
                        "base_url": provider.base_url,
                        "api_format": provider.api_format,
                        "api_key": provider.api_key,
                        "model": model_config.model_id,
                        "max_tokens": min(model_config.max_context // 2, 4096),
                        "temperature": 0.3,
                    })

        enabled = provider_store.get_enabled_providers()
        if enabled:
            provider = enabled[0]
            active_models = [m for m in provider.models if m.enabled]
            if active_models:
                model = active_models[0]
                return DynamicLLMClient({
                    "base_url": provider.base_url,
                    "api_format": provider.api_format,
                    "api_key": provider.api_key,
                    "model": model.model_id,
                    "max_tokens": min(model.max_context // 2, 4096),
                    "temperature": 0.3,
                })

        return MockLLMClient()

    @staticmethod
    def create_from_config(config: dict) -> LLMClient:
        if not config.get("api_key") or not config.get("base_url"):
            return MockLLMClient()
        return DynamicLLMClient(config)


# 需要 asyncio
import asyncio
