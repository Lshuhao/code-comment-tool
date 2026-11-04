# 代码注释自动生成与优化建议工具

## 项目简介

基于 LLM 和 AST 分析的代码注释自动生成与质量优化工具，支持 Python/Java/C++ 三种语言。

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    M8 前端交互层 (Vue3)                   │
│    Monaco Editor │ ECharts │ Element Plus │ Diff视图     │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP API
┌────────────────────────┴────────────────────────────────┐
│               M7 编排服务层 (FastAPI)                     │
│          路由定义 │ 流水线调度 │ 错误处理                   │
└────┬────┬────┬────┬────┬────────────────────────────────┘
     │    │    │    │    │
┌────┴┐ ┌┴───┐┌┴──┐┌┴───┐┌┴────┐
│ M1  │ │ M2 ││M3 ││M4  ││M5   │ M6导出 │ M9历史
│接入 │ │AST ││注释││缺陷││评分 │        │
│层   │ │解析││生成││检测││模块 │        │
└─────┘ └────┘└───┘└────┘└─────┘
```

## 模块说明

| 模块 | 职责 | 工作量 |
|------|------|--------|
| M1 接入层 | 文件接收、编码检测、语言识别 | 小(1-2天) |
| M2 AST解析 | tree-sitter解析、统一中间表示 | 大(4-5天) |
| M3 注释生成 | LLM docstring/行内注释生成 | 中(3-4天) |
| M4 缺陷检测 | 规则层+语义层检测 | 大(4-5天) |
| M5 质量评分 | 四维度量化评分(纯规则) | 小(1-2天) |
| M6 导出 | 代码回填、多格式导出 | 中(2天) |
| M7 编排 | FastAPI路由、流水线调度 | 中(2-3天) |
| M8 前端 | Vue3 + Monaco + ECharts | 大(5-6天) |
| M9 历史 | 任务持久化(SQLite) | 可选 |

## 快速开始

### Tkinter 桌面版（推荐）

```bash
# 方式一：双击启动
start.bat          # Windows
./start.sh         # Linux/macOS

# 方式二：命令行
python backend/app/gui/app.py
```

直接调用后端模块，无需启动服务器，无需浏览器。

### Web 版（可选）

```bash
# 后端
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev
```

访问: http://localhost:3000

### 运行测试

```bash
cd backend
pytest tests/ -v
```

## 技术栈

- **后端**: FastAPI, tree-sitter, chardet, Jinja2, SQLAlchemy
- **LLM**: OpenAI兼容API (DeepSeek / OpenAI / Qwen / Zhipu)
- **桌面端**: Tkinter（主界面）
- **Web端**: Vue3, Element Plus, Monaco Editor, ECharts（可选）
- **存储**: SQLite + gzip压缩 + JSON文件配置

## 项目结构

```
代码注释自动生成与优化建议工具/
├── backend/
│   ├── app/
│   │   ├── api/routes.py         # API路由
│   │   ├── core/config.py        # 全局配置
│   │   ├── models/
│   │   │   ├── unified_ast.py    # 统一AST模型(核心契约)
│   │   │   └── suggestions.py    # 建议/缺陷/评分模型
│   │   ├── services/
│   │   │   ├── m1_ingest.py      # 接入层
│   │   │   ├── m2_parser.py      # AST解析层
│   │   │   ├── m3_comment_gen.py # 注释生成
│   │   │   ├── m4_defect.py      # 缺陷检测
│   │   │   ├── m5_scoring.py     # 质量评分
│   │   │   ├── m6_export.py      # 导出模块
│   │   │   ├── m7_orchestrator.py# 编排服务
│   │   │   └── m9_history.py     # 历史记录
│   │   └── main.py               # FastAPI入口
│   ├── tests/                    # 单元测试
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/index.js          # API客户端
│   │   ├── components/           # Vue组件
│   │   │   ├── ScoreOverview.vue     # 评分概览
│   │   │   ├── MonacoDiffViewer.vue  # Diff对比
│   │   │   ├── SuggestionList.vue    # 建议列表
│   │   │   └── DefectPanel.vue       # 缺陷面板
│   │   ├── views/
│   │   │   ├── HomeView.vue      # 主页
│   │   │   └── HistoryView.vue   # 历史记录
│   │   ├── App.vue
│   │   ├── main.js
│   │   └── router.js
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## 核心设计

### UnifiedASTNode (全系统契约)

所有语言解析后统一转换为 `UnifiedASTNode` 中间表示，确保模块间完全解耦。

### LLMClient 抽象

定义 `generate(prompt) -> text` 接口，开发阶段用 `MockLLMClient`，生产环境切换为 `DeepSeekClient`。

### 倒序插入算法

M6导出时从文件末尾向前插入注释，避免行号偏移问题。

### 四维度评分

- **覆盖率**: 有文档字符串的函数/类占比
- **完整性**: 文档中参数/返回值/异常的说明完整度
- **一致性**: 注释风格统一程度
- **规范性**: 编码规范遵循程度
