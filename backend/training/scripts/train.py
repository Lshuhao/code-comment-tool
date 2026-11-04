"""
CodeBERT 微调训练脚本

基于 CodeSearchNet 代码-注释配对数据，使用对比学习（MultipleNegativesRankingLoss）
微调 CodeBERT 使其学会代码与注释的语义匹配。

训练流程:
1. 加载预处理后的 JSONL 数据
2. 构建 sentence-transformers 训练 pipeline
3. 使用 MultipleNegativesRankingLoss 对比学习
4. 评估: MRR@K, Recall@K
5. 保存微调模型

用法:
    # 使用演示数据快速验证
    python train.py --demo

    # 使用完整 CodeSearchNet 数据
    python train.py --train_data ../data/train_pairs.jsonl --valid_data ../data/valid_pairs.jsonl

    # 自定义参数
    python train.py --model microsoft/codebert-base --epochs 5 --batch_size 32 --lr 2e-5
"""
import os
import json
import logging
import argparse
import random
import time
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ========================
# 数据加载
# ========================

def load_jsonl(filepath: str) -> List[Dict[str, str]]:
    """加载 JSONL 格式的数据"""
    pairs = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    logger.info(f"从 {filepath} 加载 {len(pairs)} 条数据")
    return pairs


def truncate_code(code: str, max_tokens: int = 384) -> str:
    """截断代码到最大token数（简化版：按字符截断，大约1 token ≈ 4 chars）"""
    max_chars = max_tokens * 4
    if len(code) > max_chars:
        return code[:max_chars] + "\n# ... (truncated)"
    return code


def truncate_docstring(docstring: str, max_length: int = 256) -> str:
    """截断文档字符串"""
    if len(docstring) > max_length:
        return docstring[:max_length].rsplit(" ", 1)[0] + "..."
    return docstring


# ========================
# 训练核心逻辑
# ========================

class CodeCommentTrainer:
    """CodeBERT 代码-注释对比学习训练器"""

    def __init__(self, config: dict):
        self.config = config
        self.model_config = config.get("model", {})
        self.train_config = config.get("training", {})
        self.eval_config = config.get("evaluation", {})

        self.base_model_name = self.model_config.get("base_model", "microsoft/codebert-base")
        self.max_seq_length = self.model_config.get("max_seq_length", 512)
        self.output_dir = self.model_config.get("output_dir", "./models/finetuned_codebert")

        self.epochs = self.train_config.get("epochs", 5)
        self.batch_size = self.train_config.get("batch_size", 32)
        self.eval_batch_size = self.train_config.get("eval_batch_size", 64)
        self.learning_rate = self.train_config.get("learning_rate", 2e-5)
        self.weight_decay = self.train_config.get("weight_decay", 0.01)
        self.warmup_ratio = self.train_config.get("warmup_ratio", 0.1)
        self.temperature = self.train_config.get("temperature", 0.05)
        self.seed = self.train_config.get("seed", 42)
        self.fp16 = self.train_config.get("fp16", True)

    def set_seed(self):
        """设置随机种子"""
        random.seed(self.seed)
        np.random.seed(self.seed)
        try:
            import torch
            torch.manual_seed(self.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.seed)
        except ImportError:
            pass

    def build_model(self):
        """构建 sentence-transformers 模型"""
        from sentence_transformers import SentenceTransformer

        logger.info(f"加载预训练模型: {self.base_model_name}")
        model = SentenceTransformer(self.base_model_name)
        model.max_seq_length = self.max_seq_length

        logger.info(f"  模型参数量: {sum(p.numel() for p in model.parameters()):,}")
        logger.info(f"  设备: {'CUDA' if self._cuda_available() else 'CPU'}")

        return model

    def _cuda_available(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def prepare_training_data(
        self, train_pairs: List[Dict]
    ) -> Tuple[list, list]:
        """
        准备训练数据
        返回: (codes, docstrings) 两个平行列表
        训练时 MultipleNegativesRankingLoss 会自动将 batch 内其他样本作为负例
        """
        codes = []
        docstrings = []

        for pair in train_pairs:
            code = truncate_code(pair["code"])
            doc = truncate_docstring(pair["docstring"])

            if code and doc:
                codes.append(code)
                docstrings.append(doc)

        logger.info(f"训练数据: {len(codes)} 对")
        return codes, docstrings

    def prepare_eval_data(
        self, eval_pairs: List[Dict]
    ) -> Tuple[list, list]:
        """准备评估数据"""
        return self.prepare_training_data(eval_pairs)

    def train(self, train_pairs: List[Dict], eval_pairs: List[Dict] = None):
        """
        执行训练
        """
        self.set_seed()
        model = self.build_model()

        # 准备数据
        train_codes, train_docs = self.prepare_training_data(train_pairs)

        # 构建 InputExample 列表
        from sentence_transformers import InputExample

        train_examples = []
        for code, doc in zip(train_codes, train_docs):
            train_examples.append(InputExample(texts=[code, doc]))

        logger.info(f"构建训练样本: {len(train_examples)} 对")

        # 数据加载器
        from torch.utils.data import DataLoader
        train_dataloader = DataLoader(
            train_examples,
            shuffle=True,
            batch_size=self.batch_size,
            drop_last=True,
        )

        # 损失函数: MultipleNegativesRankingLoss
        from sentence_transformers import losses
        train_loss = losses.MultipleNegativesRankingLoss(model)

        # warmup 步数
        total_steps = len(train_dataloader) * self.epochs
        warmup_steps = int(total_steps * self.warmup_ratio)
        logger.info(f"训练配置: epochs={self.epochs}, batch_size={self.batch_size}, "
                     f"total_steps={total_steps}, warmup_steps={warmup_steps}")

        # 评估器（如果有验证数据）
        evaluators = []
        if eval_pairs:
            eval_codes, eval_docs = self.prepare_eval_data(eval_pairs)
            # 取子集做评估（避免太慢）
            max_eval = min(2000, len(eval_codes))
            indices = random.sample(range(len(eval_codes)), max_eval)
            eval_codes_sub = [eval_codes[i] for i in indices]
            eval_docs_sub = [eval_docs[i] for i in indices]

            evaluator = CodeCommentEvaluator(
                eval_codes_sub, eval_docs_sub,
                batch_size=self.eval_batch_size,
                name="code-comment-eval",
            )
            evaluators.append(evaluator)

        # 训练参数
        eval_steps = self.eval_config.get("eval_steps", 500)
        save_steps = self.eval_config.get("save_steps", 1000)

        # 训练
        logger.info("开始训练...")
        start_time = time.time()

        model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=self.epochs,
            warmup_steps=warmup_steps,
            optimizer_params={"lr": self.learning_rate, "weight_decay": self.weight_decay},
            evaluator=evaluators[0] if evaluators else None,
            evaluation_steps=eval_steps if evaluators else 0,
            output_path=self.output_dir,
            save_best_model=True,
            show_progress_bar=True,
            use_amp=self.fp16 and self._cuda_available(),
        )

        elapsed = time.time() - start_time
        logger.info(f"训练完成! 耗时: {elapsed/60:.1f} 分钟")
        logger.info(f"模型已保存到: {self.output_dir}")

        # 最终评估
        if evaluators:
            logger.info("最终评估...")
            evaluators[0](model, output_path=self.output_dir)

        return model

    def load_and_evaluate(
        self, model_path: str, test_pairs: List[Dict]
    ):
        """加载模型并在测试集上评估"""
        from sentence_transformers import SentenceTransformer

        logger.info(f"加载模型: {model_path}")
        model = SentenceTransformer(model_path)

        test_codes, test_docs = self.prepare_eval_data(test_pairs)
        evaluator = CodeCommentEvaluator(
            test_codes, test_docs,
            batch_size=self.eval_batch_size,
            name="test-eval",
        )
        results = evaluator(model, output_path=None)
        logger.info(f"测试结果: {results}")
        return results


class CodeCommentEvaluator:
    """
    代码-注释匹配评估器
    计算 MRR@K 和 Recall@K
    """

    def __init__(
        self,
        codes: List[str],
        docstrings: List[str],
        batch_size: int = 64,
        name: str = "eval",
    ):
        self.codes = codes
        self.docstrings = docstrings
        self.batch_size = batch_size
        self.name = name
        self.primary_metric = "mrr@10"

    def __call__(self, model, output_path: str = None, epoch: int = -1, steps: int = -1) -> float:
        """执行评估"""
        from sentence_transformers import util

        logger.info(f"评估 [{self.name}] (epoch={epoch}, steps={steps}): "
                     f"{len(self.codes)} 对样本...")

        # 编码所有代码和文档字符串
        code_embeddings = model.encode(
            self.codes,
            batch_size=self.batch_size,
            show_progress_bar=True,
            convert_to_tensor=True,
            normalize_embeddings=True,
        )
        doc_embeddings = model.encode(
            self.docstrings,
            batch_size=self.batch_size,
            show_progress_bar=True,
            convert_to_tensor=True,
            normalize_embeddings=True,
        )

        # 计算余弦相似度矩阵
        cos_scores = util.cos_sim(code_embeddings, doc_embeddings)

        # 计算指标
        results = self._compute_metrics(cos_scores)

        if output_path:
            os.makedirs(output_path, exist_ok=True)
            metrics_file = os.path.join(output_path, f"{self.name}_metrics.json")
            with open(metrics_file, "w") as f:
                json.dump(results, f, indent=2)

        logger.info(f"  MRR@10: {results['mrr@10']:.4f}")
        logger.info(f"  Recall@1: {results['recall@1']:.4f}")
        logger.info(f"  Recall@5: {results['recall@5']:.4f}")
        logger.info(f"  Recall@10: {results['recall@10']:.4f}")

        return results.get("mrr@10", 0.0)

    def _compute_metrics(self, cos_scores) -> Dict[str, float]:
        """计算 MRR 和 Recall"""
        import torch

        n = cos_scores.shape[0]
        mrr_sum = 0.0
        recall_at = {1: 0, 5: 0, 10: 0}

        for i in range(n):
            # 对第 i 个代码，找到其匹配的文档字符串排名
            scores = cos_scores[i]
            sorted_indices = torch.argsort(scores, descending=True)

            # 正确匹配的索引
            correct_idx = i  # 对角线位置

            # 在排序列表中找到正确匹配的位置
            rank = (sorted_indices == correct_idx).nonzero(as_tuple=True)[0]
            if len(rank) > 0:
                rank = rank[0].item() + 1  # 1-based
            else:
                rank = n

            # MRR
            mrr_sum += 1.0 / rank

            # Recall@K
            top_k_indices = set(sorted_indices[:10].tolist())
            if correct_idx in top_k_indices:
                for k in recall_at:
                    if correct_idx in set(sorted_indices[:k].tolist()):
                        recall_at[k] += 1

        results = {
            "mrr@10": mrr_sum / n,
            "recall@1": recall_at[1] / n,
            "recall@5": recall_at[5] / n,
            "recall@10": recall_at[10] / n,
            "num_samples": n,
        }
        return results


# ========================
# 主入口
# ========================

def main():
    parser = argparse.ArgumentParser(description="CodeBERT 微调训练")
    parser.add_argument("--config", type=str, default="../configs/train_config.yaml")
    parser.add_argument("--train_data", type=str, default="../data/train_pairs.jsonl")
    parser.add_argument("--valid_data", type=str, default="../data/valid_pairs.jsonl")
    parser.add_argument("--test_data", type=str, default="../data/test_pairs.jsonl")
    parser.add_argument("--model", type=str, default="microsoft/codebert-base")
    parser.add_argument("--output_dir", type=str, default="../models/finetuned_codebert")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max_seq_length", type=int, default=512)
    parser.add_argument("--demo", action="store_true", help="使用演示数据快速验证")
    parser.add_argument("--evaluate_only", action="store_true", help="仅评估不训练")
    parser.add_argument("--model_path", type=str, help="评估时加载的模型路径")
    args = parser.parse_args()

    # 加载配置
    config = {}
    if os.path.exists(args.config):
        try:
            import yaml
            with open(args.config) as f:
                config = yaml.safe_load(f)
        except ImportError:
            logger.warning("PyYAML未安装，使用命令行参数")

    # 命令行参数覆盖配置
    config.setdefault("model", {})
    config["model"]["base_model"] = args.model
    config["model"]["output_dir"] = args.output_dir
    config["model"]["max_seq_length"] = args.max_seq_length

    config.setdefault("training", {})
    config["training"]["epochs"] = args.epochs
    config["training"]["batch_size"] = args.batch_size
    config["training"]["learning_rate"] = args.lr

    # 创建训练器
    trainer = CodeCommentTrainer(config)

    if args.evaluate_only:
        # 仅评估
        model_path = args.model_path or args.output_dir
        test_pairs = load_jsonl(args.test_data)
        trainer.load_and_evaluate(model_path, test_pairs)
        return

    # 加载数据
    if args.demo:
        logger.info("使用演示数据进行快速训练验证...")
        from prepare_data import create_demo_data
        data_dir = os.path.join(os.path.dirname(args.train_data), "..", "data")
        create_demo_data(data_dir, num_train=500, num_valid=100)
        args.train_data = os.path.join(data_dir, "train_pairs.jsonl")
        args.valid_data = os.path.join(data_dir, "valid_pairs.jsonl")
        args.test_data = os.path.join(data_dir, "test_pairs.jsonl")

    train_pairs = load_jsonl(args.train_data)

    eval_pairs = None
    if os.path.exists(args.valid_data):
        eval_pairs = load_jsonl(args.valid_data)

    # 训练
    model = trainer.train(train_pairs, eval_pairs)

    # 测试
    if os.path.exists(args.test_data):
        test_pairs = load_jsonl(args.test_data)
        trainer.load_and_evaluate(trainer.output_dir, test_pairs)


if __name__ == "__main__":
    main()
