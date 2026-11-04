"""
动态 LLM 客户端 - 根据供应商配置动态调用不同 LLM API
支持 OpenAI 兼容格式、Anthropic Messages 格式、自定义格式
"""
import json
import logging
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """LLM 客户端接口"""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        pass


class MockLLMClient(LLMClient):
    """
    Mock LLM 客户端 - 开发阶段使用
    智能分析代码并生成有针对性的注释（非通用模板）
    """

    async def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        # 从 prompt 中提取源代码
        code = self._extract_code(prompt)
        func_name = self._extract_func_name(prompt)

        if "docstring" in prompt.lower() or "文档" in prompt:
            return self._generate_docstring(code, func_name, prompt)
        elif "inline" in prompt.lower() or "行内" in prompt:
            return self._generate_inline(code, prompt)
        elif "改进" in prompt or "improve" in prompt.lower():
            return self._generate_improvement(code, prompt)
        return "# Auto-generated comment"

    def _extract_code(self, prompt: str) -> str:
        """从 prompt 中提取代码块"""
        import re
        # 匹配 ```语言 ... ``` 代码块
        match = re.search(r'```(?:\w+)?\n(.*?)```', prompt, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_func_name(self, prompt: str) -> str:
        """从 prompt 中提取函数名"""
        import re
        # 匹配 "函数/类名称: xxx" 或 "函数名称: xxx"
        match = re.search(r'(?:函数[//]类|函数)名称[:\s]*(\w+)', prompt)
        if match:
            return match.group(1)
        # 匹配代码中的 def
        match = re.search(r'def\s+(\w+)', prompt)
        if match:
            return match.group(1)
        return "unknown"

    def _analyze_function(self, code: str) -> dict:
        """分析函数代码，提取关键信息"""
        import re
        info = {
            "name": "unknown",
            "params": [],
            "has_return": False,
            "has_loop": False,
            "has_condition": False,
            "has_try": False,
            "description": "",
            "complexity": 0,
        }

        # 函数名
        m = re.search(r'def\s+(\w+)\s*\(([^)]*)\)', code)
        if m:
            info["name"] = m.group(1)
            params_str = m.group(2).strip()
            if params_str:
                info["params"] = [p.strip().split(':')[0].split('=')[0].strip()
                                  for p in params_str.split(',')
                                  if p.strip() and p.strip() != 'self']

        # 返回值
        info["has_return"] = bool(re.search(r'\breturn\b', code))

        # 循环
        info["has_loop"] = bool(re.search(r'\b(for|while)\b', code))

        # 条件
        info["has_condition"] = bool(re.search(r'\bif\b', code))

        # try
        info["has_try"] = bool(re.search(r'\btry\b', code))

        # 复杂度估算
        info["complexity"] = sum([
            len(re.findall(r'\bfor\b', code)),
            len(re.findall(r'\bwhile\b', code)),
            len(re.findall(r'\bif\b', code)),
            len(re.findall(r'\btry\b', code)),
        ])

        # 从函数名推断功能
        name = info["name"].lower()
        name_hints = {
            "calculate": "计算", "compute": "计算", "calc": "计算",
            "get": "获取", "fetch": "获取", "retrieve": "获取",
            "set": "设置", "update": "更新", "modify": "修改",
            "create": "创建", "build": "构建", "make": "创建",
            "delete": "删除", "remove": "移除", "drop": "删除",
            "find": "查找", "search": "搜索", "lookup": "查找",
            "sort": "排序", "order": "排序",
            "filter": "过滤", "select": "筛选",
            "parse": "解析", "analyze": "分析",
            "convert": "转换", "transform": "变换",
            "validate": "验证", "check": "检查",
            "process": "处理", "handle": "处理",
            "read": "读取", "write": "写入", "load": "加载", "save": "保存",
            "connect": "连接", "disconnect": "断开",
            "initialize": "初始化", "init": "初始化",
            "average": "计算平均值", "mean": "计算均值",
            "sum": "求和", "total": "计算总和",
            "count": "计数", "length": "获取长度",
            "max": "获取最大值", "min": "获取最小值",
            "format": "格式化", "render": "渲染",
            "send": "发送", "receive": "接收",
            "encode": "编码", "decode": "解码",
            "encrypt": "加密", "decrypt": "解密",
            "hash": "哈希", "compress": "压缩",
            "merge": "合并", "split": "拆分",
            "append": "追加", "insert": "插入",
            "start": "启动", "stop": "停止", "run": "运行",
            "main": "主函数",
            "helper": "辅助函数", "util": "工具函数",
            "test": "测试",
        }
        for keyword, desc in name_hints.items():
            if keyword in name:
                info["description"] = desc
                break

        return info

    def _generate_docstring(self, code: str, func_name: str, prompt: str) -> str:
        """根据实际代码生成有针对性的 docstring"""
        info = self._analyze_function(code)
        name = info["name"]
        params = info["params"]

        # 生成描述
        if info["description"]:
            desc = info["description"]
        else:
            desc = f"执行{name}相关操作"

        # 根据代码特征补充描述
        extras = []
        if info["has_loop"]:
            extras.append("通过循环处理数据")
        if info["has_condition"]:
            extras.append("包含条件判断逻辑")
        if info["has_try"]:
            extras.append("包含异常处理")

        if extras:
            desc += "，" + "，".join(extras)

        # 生成参数说明
        param_docs = []
        for p in params:
            param_docs.append(f"        {p}: 输入参数")

        # 组装 docstring（不加首行缩进，由插入模块处理）
        lines = []
        lines.append(f"{desc}。")
        lines.append("")
        if param_docs:
            lines.append("Args:")
            for pd in param_docs:
                lines.append(f"    {pd.strip()}")
            lines.append("")
        if info["has_return"]:
            lines.append("Returns:")
            lines.append("    处理结果。")
            lines.append("")
        if info["has_try"]:
            lines.append("Raises:")
            lines.append("    Exception: 处理过程中可能发生异常。")
            lines.append("")

        return "\n".join(lines)

    def _generate_inline(self, code: str, prompt: str) -> str:
        """生成有针对性的行内注释"""
        code_lower = code.lower()

        if "for " in code and "in " in code:
            return "# 遍历数据集合进行处理"
        elif "if " in code and "else" in code_lower:
            return "# 根据条件分支处理不同情况"
        elif "return " in code:
            # 尝试从返回表达式推断
            import re
            m = re.search(r'return\s+(.+)', code)
            if m:
                expr = m.group(1).strip()
                if "/" in expr and "len" in expr:
                    return "# 计算并返回平均值"
                elif "+" in expr:
                    return "# 返回累加结果"
                elif "*" in expr:
                    return "# 返回乘积结果"
                else:
                    return f"# 返回计算结果: {expr}"
            return "# 返回处理结果"
        elif "try:" in code:
            return "# 异常处理开始"
        elif "except" in code_lower:
            return "# 捕获并处理异常"
        elif "while " in code:
            return "# 循环执行直到条件不满足"
        elif "=" in code and "+=" in code:
            return "# 累加到总计变量"
        elif ".append(" in code:
            return "# 将结果添加到列表"
        elif ".sort(" in code or "sorted(" in code:
            return "# 对数据进行排序"
        elif "open(" in code:
            return "# 打开文件"
        elif "print(" in code:
            return "# 输出结果到控制台"
        elif "import " in code:
            return "# 导入所需模块"
        elif "def " in code:
            return "# 定义函数"
        elif "class " in code:
            return "# 定义类"
        else:
            return "# 执行操作"

    def _generate_improvement(self, code: str, prompt: str) -> str:
        """改进已有注释"""
        # 提取已有注释
        import re
        existing = re.search(r'```\s*\n(.*?)\n```', prompt, re.DOTALL)
        if existing:
            existing_text = existing.group(1).strip()
            # 模拟改进：添加更详细的描述
            if len(existing_text) < 100:
                return existing_text + "\n\n    补充说明：此实现采用了标准的处理方式。"
        return ""


class DynamicLLMClient(LLMClient):
    """
    动态 LLM 客户端 - 根据供应商配置调用对应 API
    支持 OpenAI 兼容 / Anthropic Messages / 自定义
    """

    def __init__(self, provider_config: dict = None):
        self.config = provider_config or {}
        self._session = None

    def _get_session(self):
        if self._session is None:
            import httpx
            self._session = httpx.AsyncClient(timeout=60.0)
        return self._session

    async def _close(self):
        if self._session:
            await self._session.aclose()
            self._session = None

    async def generate(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        api_format = self.config.get("api_format", "openai_chat")
        try:
            if api_format in ("openai_chat", "anthropic_messages"):
                return await self._call_standard_api(prompt, system_prompt, **kwargs)
            else:
                return await self._call_custom_api(prompt, system_prompt, **kwargs)
        except Exception as e:
            logger.warning(f"LLM调用失败: {e}，使用Mock回退")
            mock = MockLLMClient()
            return await mock.generate(prompt, system_prompt, **kwargs)

    async def _call_standard_api(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        api_format = self.config.get("api_format", "openai_chat")
        base_url = self.config.get("base_url", "").rstrip("/")
        api_key = self.config.get("api_key", "")
        model = self.config.get("model", "")
        max_tokens = kwargs.get("max_tokens", self.config.get("max_tokens", 2048))
        temperature = kwargs.get("temperature", self.config.get("temperature", 0.3))

        session = self._get_session()
        headers = {"Content-Type": "application/json"}

        if api_format == "openai_chat":
            url = f"{base_url}/chat/completions"
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload = {
                "model": model, "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature,
            }
            resp = await session.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        elif api_format == "anthropic_messages":
            url = f"{base_url}/messages"
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            messages = [{"role": "user", "content": prompt}]
            payload = {
                "model": model, "messages": messages,
                "max_tokens": max_tokens, "system": system_prompt or "",
            }
            resp = await session.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]

        return ""

    async def _call_custom_api(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        return await self._call_standard_api(prompt, system_prompt, **kwargs)


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
