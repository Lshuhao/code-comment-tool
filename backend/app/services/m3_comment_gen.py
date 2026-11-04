"""
M3 注释生成模块 - 函数/类级docstring生成 + 行内注释生成
职责：
- Prompt构建与模板引擎
- LLM调用（支持Mock / 动态多供应商）
- 格式校验
- 批量分批处理
"""
import re
from typing import List, Optional, Dict, Any
from jinja2 import Template

from app.models.unified_ast import UnifiedASTNode, NodeType, ParseResult
from app.models.suggestions import CommentSuggestion, SuggestionType
from app.core.config import settings


# 从独立的 llm_client 模块导入
from app.services.llm_client import LLMClient, MockLLMClient, DynamicLLMClient, LLMClientFactory


# ========================
# Prompt 模板引擎
# ========================

DOCSTRING_PROMPT_TEMPLATE = Template("""为以下{{ language }}代码生成{{ style }}风格的文档字符串。

函数/类名称: {{ name }}
作用域: {{ scope_path }}
参数: {{ parameters }}
返回类型: {{ return_type }}
装饰器: {{ decorators }}

源代码:
```{{ language }}
{{ source_code }}
```

请生成{{ style }}风格的文档字符串，要求：
1. 首行简要说明功能（不超过80字符）
2. 详细描述行为（如有复杂逻辑需解释）
3. Args部分列出所有参数及类型说明
4. Returns部分说明返回值
5. Raises部分列出可能抛出的异常

只输出文档字符串本身，不要输出其他内容。""")

INLINE_COMMENT_TEMPLATE = Template("""为以下{{ language }}代码片段生成行内注释。

上下文（所属函数/类）: {{ context }}
代码位置: 第{{ line }}行

源代码:
```{{ language }}
{{ source_code }}
```

请为这段代码生成简洁的行内注释，要求：
1. 解释代码的意图（为什么这样做），而非重复代码字面意思
2. 对于复杂逻辑，解释算法思路
3. 注释长度不超过一行（80字符以内）
4. 使用{{ language }}的注释语法

只输出注释文本，不要输出代码或其他内容。""")

IMPROVE_PROMPT_TEMPLATE = Template("""改进以下已有的{{ language }}注释。

已有注释:
```
{{ existing_comment }}
```

对应代码:
```{{ language }}
{{ source_code }}
```

请改进这个注释，使其：
1. 更加准确和完整
2. 使用专业简洁的语言
3. 符合{{ style }}风格规范
4. 如果原注释已经很好，保持原样

只输出改进后的注释文本。""")


# ========================
# 注释生成器
# ========================

class DocstringGenerator:
    """函数/类级文档字符串生成器 (F3)"""

    def __init__(self, llm_client: LLMClient, style: str = "google"):
        self.llm = llm_client
        self.style = style

    async def generate_for_node(
        self, node: UnifiedASTNode, language: str
    ) -> CommentSuggestion:
        prompt = DOCSTRING_PROMPT_TEMPLATE.render(
            language=language,
            style=self.style,
            name=node.name or "unknown",
            scope_path=" > ".join(node.scope_path),
            parameters=self._format_params(node.parameters),
            return_type=node.return_type or "Not specified",
            decorators=", ".join(node.decorators) if node.decorators else "None",
            source_code=node.source_text,
        )

        result = await self.llm.generate(prompt)
        result = self._validate_format(result, language)

        return CommentSuggestion(
            type=SuggestionType.DOCSTRING,
            target_node_id=node.node_id,
            target_line=node.start_line,
            suggested_text=result,
            confidence=0.85,
            source="llm",
            reasoning=f"Generated {self.style}-style docstring for {node.name}",
        )

    async def generate_batch(
        self, nodes: List[UnifiedASTNode], language: str, batch_size: int = 5
    ) -> List[CommentSuggestion]:
        suggestions = []
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            for node in batch:
                if node.docstring:
                    continue
                suggestion = await self.generate_for_node(node, language)
                suggestions.append(suggestion)
        return suggestions

    def _format_params(self, params: List[Dict]) -> str:
        if not params:
            return "No parameters"
        return ", ".join(f"{p.get('name', '?')}({p.get('type', 'any')})" for p in params)

    def _validate_format(self, text: str, language: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return text.strip()


class InlineCommentGenerator:
    """行内注释生成器 (F4)"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def generate_for_statement(
        self, node: UnifiedASTNode, language: str, context: str = ""
    ) -> CommentSuggestion:
        prompt = INLINE_COMMENT_TEMPLATE.render(
            language=language,
            context=context or " > ".join(node.scope_path),
            line=node.start_line,
            source_code=node.source_text,
        )
        result = await self.llm.generate(prompt)
        result = self._format_inline(result, language)

        return CommentSuggestion(
            type=SuggestionType.INLINE_COMMENT,
            target_node_id=node.node_id,
            target_line=node.start_line,
            suggested_text=result,
            confidence=0.75,
            source="llm",
            reasoning=f"Generated inline comment for line {node.start_line}",
        )

    async def generate_for_complex_blocks(
        self, nodes: List[UnifiedASTNode], language: str
    ) -> List[CommentSuggestion]:
        suggestions = []
        for node in nodes:
            # 跳过类节点，只给复杂语句/函数体加行内注释
            if node.node_type.value in ("class",):
                continue
            if node.complexity_score >= 3.0:
                suggestion = await self.generate_for_statement(node, language)
                suggestions.append(suggestion)
        return suggestions

    def _format_inline(self, text: str, language: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        prefix = {"python": "# ", "java": "// ", "cpp": "// "}.get(language, "# ")
        if not text.startswith(prefix.strip()):
            text = prefix + text.lstrip("#/ ").strip()
        return text


class ImproveCommentGenerator:
    """已有注释改进生成器"""

    def __init__(self, llm_client: LLMClient, style: str = "google"):
        self.llm = llm_client
        self.style = style

    async def generate_improvement(
        self, node: UnifiedASTNode, language: str
    ) -> Optional[CommentSuggestion]:
        if not node.docstring:
            return None
        prompt = IMPROVE_PROMPT_TEMPLATE.render(
            language=language, style=self.style,
            existing_comment=node.docstring,
            source_code=node.source_text,
        )
        result = await self.llm.generate(prompt).strip()
        if result == node.docstring.strip():
            return None
        return CommentSuggestion(
            type=SuggestionType.IMPROVE_EXISTING,
            target_node_id=node.node_id,
            target_line=node.start_line,
            suggested_text=result,
            confidence=0.7,
            source="llm",
            reasoning="Improved existing comment quality",
        )


# ========================
# M3 模块主服务
# ========================

class CommentGenerationService:
    """M3 注释生成服务 - 整合F3和F4"""

    def __init__(self, llm_client: Optional[LLMClient] = None, style: str = "google"):
        self.llm = llm_client or MockLLMClient()
        self.docstring_gen = DocstringGenerator(self.llm, style)
        self.inline_gen = InlineCommentGenerator(self.llm)
        self.improve_gen = ImproveCommentGenerator(self.llm, style)

    async def generate_all(self, parse_result: ParseResult) -> List[CommentSuggestion]:
        all_suggestions = []

        # 1. 收集需要docstring的节点
        functions = parse_result.get_all_functions()
        classes = parse_result.get_all_classes()
        needs_docstring = [n for n in functions + classes if not n.docstring]

        # 2. 生成docstring
        docstring_suggestions = await self.docstring_gen.generate_batch(
            needs_docstring, parse_result.language
        )
        all_suggestions.extend(docstring_suggestions)

        # 3. 为复杂节点生成行内注释
        complex_nodes = parse_result.get_complex_nodes(threshold=3.0)
        inline_suggestions = await self.inline_gen.generate_for_complex_blocks(
            complex_nodes, parse_result.language
        )
        all_suggestions.extend(inline_suggestions)

        # 4. 改进已有注释
        has_docstring = [n for n in functions + classes if n.docstring]
        for node in has_docstring[:10]:
            improvement = await self.improve_gen.generate_improvement(
                node, parse_result.language
            )
            if improvement:
                all_suggestions.append(improvement)

        return all_suggestions


# 全局单例
comment_gen_service = CommentGenerationService()
