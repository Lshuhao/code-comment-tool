# CodeBERT 微调训练指南

## 概述

本模块基于 **CodeSearchNet** 数据集微调 **CodeBERT**，使 M4 缺陷检测模块的语义层能够更准确地检测：
- 注释与代码不一致（注释描述的 ≠ 代码实际做的）
- 冗余注释（注释只是代码字面意思的翻译）

## 快速开始

### 1. 安装训练依赖

```bash
cd backend/training
pip install -r requirements.txt
```

### 2. 准备数据

```bash
# 使用内置演示数据（快速验证，无需下载）
cd training/scripts
python prepare_data.py --source demo --output_dir ../data

# 使用完整 CodeSearchNet 数据（需要约10GB磁盘空间）
python prepare_data.py --source huggingface --languages python java --output_dir ../data
```

### 3. 训练模型

```bash
# 使用演示数据快速训练（验证流程）
python train.py --demo --epochs 2 --batch_size 16

# 使用完整数据训练
python train.py \
    --train_data ../data/train_pairs.jsonl \
    --valid_data ../data/valid_pairs.jsonl \
    --test_data ../data/test_pairs.jsonl \
    --epochs 5 \
    --batch_size 32 \
    --lr 2e-5

# 仅评估已训练模型
python train.py --evaluate_only --model_path ../models/finetuned_codebert
```

### 4. 在 M4 中使用微调模型

训练完成后，微调模型会自动保存到 `training/models/finetuned_codebert/`。
在 `app/core/config.py` 中配置模型路径即可：

```python
FINETUNED_CODEBERT_PATH: str = "./training/models/finetuned_codebert"
```

M4 的 `DefectDetectionService` 会自动检测并加载微调模型：

```python
from app.services.m4_defect import DefectDetectionService

# 自动加载微调模型
service = DefectDetectionService(
    use_codebert=True,
    finetuned_model_path="./training/models/finetuned_codebert"
)
```

## 训练原理

```
┌──────────────────────────────────────────────────┐
│            CodeSearchNet 数据集                    │
│  代码函数 ←→ 文档字符串 配对（约200万对）           │
└───────────────┬──────────────────────────────────┘
                │ 预处理
                ▼
┌──────────────────────────────────────────────────┐
│      (code, docstring) 配对 → JSONL 文件          │
│  清洗 → 去重 → 长度过滤 → 质量过滤               │
└───────────────┬──────────────────────────────────┘
                │ 训练
                ▼
┌──────────────────────────────────────────────────┐
│           CodeBERT (microsoft/codebert-base)      │
│                                                   │
│   code_encoder ──→ [code_embedding] ─┐            │
│                                       ├─ cos_sim  │
│   doc_encoder  ──→ [doc_embedding]  ─┘            │
│                                                   │
│   Loss: MultipleNegativesRankingLoss              │
│   (batch内其他样本自动作为负例)                     │
└───────────────┬──────────────────────────────────┘
                │ 评估
                ▼
┌──────────────────────────────────────────────────┐
│   指标: MRR@10, Recall@1, Recall@5, Recall@10   │
│   含义: 给定代码，正确文档在候选中的排名            │
└──────────────────────────────────────────────────┘
```

### 损失函数

**MultipleNegativesRankingLoss**: 对比学习损失
- 正例: (code_i, docstring_i)
- 负例: (code_i, docstring_j) where j ≠ i（batch内其他样本）
- 目标: 拉近正例对的embedding，推远负例对

### 评估指标

| 指标 | 含义 | 优秀线 |
|------|------|--------|
| MRR@10 | 正确文档排在前10的倒数排名均值 | > 0.7 |
| Recall@1 | 正确文档排第1的比例 | > 0.5 |
| Recall@5 | 正确文档排在前5的比例 | > 0.7 |
| Recall@10 | 正确文档排在前10的比例 | > 0.8 |

## 文件结构

```
training/
├── configs/
│   └── train_config.yaml      # 训练超参数配置
├── scripts/
│   ├── prepare_data.py        # 数据下载与预处理
│   ├── train.py               # 微调训练脚本
│   └── inference.py           # 推理服务封装
├── data/                      # 数据目录（git忽略）
│   ├── train_pairs.jsonl
│   ├── valid_pairs.jsonl
│   └── test_pairs.jsonl
├── models/                    # 训练输出模型（git忽略）
│   └── finetuned_codebert/
├── logs/                      # 训练日志
├── requirements.txt           # 训练依赖
└── README.md                  # 本文档
```

## 硬件要求

| 配置 | 建议 |
|------|------|
| GPU | NVIDIA GPU，显存 ≥ 8GB（16GB推荐） |
| 内存 | ≥ 16GB |
| 磁盘 | ≥ 20GB（完整CodeSearchNet数据） |
| 训练时间 | 演示数据 ~5分钟，完整数据 ~2-4小时 |

无GPU也可运行（自动回退CPU），但训练速度会慢10-50倍。

## CodeSearchNet 数据说明

**CodeSearchNet** 是 GitHub 发布的大规模代码搜索数据集：
- 论文: Husain et al., "CodeSearchNet Challenge: Evaluating the State of Semantic Code Search" (2019)
- 数据量: ~200万 (code, docstring) 对
- 语言: Python, Java, Go, PHP, Ruby, JavaScript
- 来源: 从 GitHub 公开仓库中提取的函数及其文档字符串
- 许可: MIT License

## 常见问题

### Q: 没有GPU能训练吗？
A: 可以，但速度很慢。建议先用 `--demo` 模式验证流程，再在有GPU的机器上训练完整数据。

### Q: 微调模型比预训练模型好多少？
A: 在代码-注释匹配任务上，微调后 MRR@10 通常能提升 15-30%。对冗余/不一致注释检测的准确率提升明显。

### Q: 只训练Python够吗？
A: 如果项目主要处理Python代码，只训练Python即可。CodeBERT本身是多语言的，微调数据越多效果越好。

### Q: 训练完成后如何部署？
A: 训练输出的模型目录可以直接拷贝到生产服务器，M4模块通过 `finetuned_model_path` 参数加载。
