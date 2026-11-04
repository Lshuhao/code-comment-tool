@echo off
REM CodeBERT 微调一键训练脚本 (Windows)
REM 用法: run_train.bat [demo|full]

setlocal enabledelayedexpansion

set MODE=%1
if "%MODE%"=="" set MODE=demo

echo ==========================================
echo   CodeBERT CodeSearchNet 微调训练
echo   模式: %MODE%
echo ==========================================

set SCRIPT_DIR=%~dp0scripts
set DATA_DIR=%~dp0data
set MODEL_DIR=%~dp0models

REM 检查依赖
echo.
echo [1/4] 检查依赖...
python -c "import sentence_transformers" 2>nul
if errorlevel 1 (
    echo 安装训练依赖...
    pip install -r "%~dp0requirements.txt"
)

REM 准备数据
echo.
echo [2/4] 准备数据...
if "%MODE%"=="demo" (
    python "%SCRIPT_DIR%\prepare_data.py" --source demo --output_dir "%DATA_DIR%" --max_samples 500
) else (
    python "%SCRIPT_DIR%\prepare_data.py" --source huggingface --languages python java --output_dir "%DATA_DIR%" --max_samples 100000
)

REM 训练
echo.
echo [3/4] 开始训练...
set EPOCHS=5
set BATCH=32
if "%MODE%"=="demo" (
    set EPOCHS=2
    set BATCH=16
)

python "%SCRIPT_DIR%\train.py" --train_data "%DATA_DIR%\train_pairs.jsonl" --valid_data "%DATA_DIR%\valid_pairs.jsonl" --test_data "%DATA_DIR%\test_pairs.jsonl" --output_dir "%MODEL_DIR%\finetuned_codebert" --epochs %EPOCHS% --batch_size %BATCH%

REM 验证
echo.
echo [4/4] 最终评估...
python "%SCRIPT_DIR%\train.py" --evaluate_only --model_path "%MODEL_DIR%\finetuned_codebert" --test_data "%DATA_DIR%\test_pairs.jsonl"

echo.
echo ==========================================
echo   训练完成!
echo   模型路径: %MODEL_DIR%\finetuned_codebert
echo ==========================================
