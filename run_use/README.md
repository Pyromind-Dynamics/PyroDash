# run_use — Coding 评测一键入口

统一入口 **`run_sh/run_coding.sh`**，支持：

| MODE | 含义 |
|------|------|
| `swe` | SWE-bench Verified 全量 |
| `swe_20filter` | representative 20 题（特例） |
| `deepswe` | DeepSWE 1.1（Pier） |
| `terminal` | Terminal-Bench（Harbor） |

流程：起 offload adapter → 跑对应 `evaluation_code/*/eval.sh` → 结果进 `output/<RUN_ID>/<MODE>/`。

ROUTER：`tag` / `entropy`（需 LLM）或 **`slm_only`**（仅小模型，不注入 offload 提示词）。

本地小模型引擎：`SLM_BACKEND=vllm|sglang`（默认 vllm）。网页「本地权重」可选引擎并改 port / GPU / parser 等高级参数；远程 API 不启本地引擎。

**Resume（断点续跑）**：显式开启。Web 勾选 `resume` 并填已有 `RUN_ID`；CLI 设 `RUN_ID=... RESUME=1`。同名且未勾选 resume 仍 409。SWE / `swe_20filter` 靠 `preds.json` 跳过已完成实例；旧进程仍在跑则拒绝。

历史结果页：左右分栏预览文件；`.traj.json` 渲染为对话（保留 `<|llm_offload|>` 标记）。

## CLI

```bash
cd /path/to/PyroDash

# 20filter（或 bash run_use/run_sh/run_swe_20filter.sh）
MODE=swe_20filter MODEL_PATH=/path/to/ckpt \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# 全量 SWE
MODE=swe MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# DeepSWE
MODE=deepswe DEEPSWE_TASKS=/workspace/work/mjy/eval/deep-swe/tasks \
MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Terminal-Bench
MODE=terminal N_TASKS=1 MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Resume 同名 run（SWE 跳过 preds.json 已有题）
MODE=swe_20filter RUN_ID=my_run RESUME=1 MODEL_PATH=... \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# 本地用 SGLang 起小模型（需已安装 sglang）
MODE=swe_20filter SLM_BACKEND=sglang SLM_PORT=8007 MODEL_PATH=... \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh
```

脚本会自动 `source /workspace/work/mjy/.venv`（可用 `VENV_DIR` 覆盖）。

## 网页版

```bash
cd run_use/html
python server.py   # http://0.0.0.0:8787/
```

页面 MODE 下拉可选四种；`deepswe` / `terminal` 会显示各自参数（tasks 路径、dataset、N_TASKS 等）。进度默认 **live** 日志（含 `slm_serve`）。`RUN_ID` 空=新建；续跑需填已有 id 并勾选 **resume**。本地权重可选 **vllm / sglang**。

## 布局

```
run_use/
  run_sh/run_coding.sh
  run_sh/run_swe_20filter.sh   # → MODE=swe_20filter
  html/
  output/<RUN_ID>/{logs,status.json,<MODE>/}
```
