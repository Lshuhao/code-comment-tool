#!/bin/bash
# CodeBERT 微调一键训练脚本
# 用法: bash run_train.sh [demo|full]

set -e

MODE=${1:-demo}
SCRIPT_DIR="$(cd "$(dirname "$0")/scripts" && pwd)"
DATA_DIR="$(cd "$(dirname "$0")/data" && pwd)"
MODEL_DIR="$(cd "$(dirname "$0")/models" && pwd)"

echo "=========================================="
echo "  CodeBERT CodeSearchNet 微调训练"
echo "  模式: $MODE"
echo "=========================================="

# 检查依赖
echo ""
echo "[1/4] 检查依赖..."
python -c "import sentence_transformers" 2>/dev/null || {
    echo "安装训练依赖..."
    pip install -r "$(dirname "$0")/requirements.txt"
}

# 准备数据
echo ""
echo "[2/4] 准备数据..."
if [ "$MODE" = "demo" ]; then
    python "$SCRIPT_DIR/prepare_data.py" \
        --source demo \
        --output_dir "$DATA_DIR" \
        --max_samples 500
else
    python "$SCRIPT_DIR/prepare_data.py" \
        --source huggingface \
        --languages python java \
        --output_dir "$DATA_DIR" \
        --max_samples 100000
fi

# 训练
echo ""
echo "[3/4] 开始训练..."
EPOCHS=5
BATCH=32
if [ "$MODE" = "demo" ]; then
    EPOCHS=2
    BATCH=16
fi

python "$SCRIPT_DIR/train.py" \
    --train_data "$DATA_DIR/train_pairs.jsonl" \
    --valid_data "$DATA_DIR/valid_pairs.jsonl" \
    --test_data "$DATA_DIR/test_pairs.jsonl" \
    --output_dir "$MODEL_DIR/finetuned_codebert" \
    --epochs $EPOCHS \
    --batch_size $BATCH

# 验证
echo ""
echo "[4/4] 最终评估..."
python "$SCRIPT_DIR/train.py" \
    --evaluate_only \
    --model_path "$MODEL_DIR/finetuned_codebert" \
    --test_data "$DATA_DIR/test_pairs.jsonl"

echo ""
echo "=========================================="
echo "  训练完成!"
echo "  模型路径: $MODEL_DIR/finetuned_codebert"
echo ""
echo "  在 M4 中使用:"
echo "  DefectDetectionService("
echo "      use_codebert=True,"
echo "      finetuned_model_path=\"$MODEL_DIR/finetuned_codebert\""
echo "  )"
echo "=========================================="
