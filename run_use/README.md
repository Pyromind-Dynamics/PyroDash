# run_use — Coding 评测一键入口

统一入口 **`run_sh/run_coding.sh`**，支持：

| MODE | 含义 |
|------|------|
| `swe` | SWE-bench Verified 全量 |
| `swe_20filter` | representative 20 题（特例） |
| `deepswe` | DeepSWE 1.1（Pier） |
| `terminal` | Terminal-Bench（Harbor） |

集群：`CLUSTER=us`（默认，美区镜像与本机 Docker）或 `CLUSTER=shanghai`（阿里云 SWE-bench 镜像、docker-rt、离线 HF / GitHub raw 镜像）。页面上的「集群」下拉传同一个变量。LLM 地址、端口、上下文长度不跟集群绑定。

流程：起 offload adapter → 跑对应 `evaluation_code/*/eval.sh` → 结果进 `output/<RUN_ID>/<MODE>/`。

ROUTER：`tag` / `entropy`（需 LLM）或 **`slm_only`**（仅小模型，不注入 offload 提示词）。

本地小模型引擎：`SLM_BACKEND=vllm|sglang`（默认 vllm）。网页「本地权重」可选引擎并改 port / GPU / parser 等高级参数；远程 API 不启本地引擎。

**Resume（断点续跑）**：显式开启。Web 勾选 `resume` 并填已有 `RUN_ID`；CLI 设 `RUN_ID=... RESUME=1`。同名且未勾选 resume 仍 409。SWE / `swe_20filter` 靠 `preds.json` 跳过已完成实例；旧进程仍在跑则拒绝。

历史结果页：左右分栏预览文件；`.traj.json` 渲染为对话（保留 `<|llm_offload|>` 标记）。

## CLI

```bash
cd /path/to/PyroDash

# 必填：VLLM_ENV（vLLM 环境）+ HARNESS_PYTHON（SWE harness；deepswe/terminal 可省略）
# 20filter（或 bash run_use/run_sh/run_swe_20filter.sh）
VLLM_ENV=/path/to/vllm_env HARNESS_PYTHON=/path/to/swe_env \
MODE=swe_20filter MODEL_PATH=/path/to/ckpt \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# 上海集群（美区默认不用加）
VLLM_ENV=... HARNESS_PYTHON=... CLUSTER=shanghai MODE=swe_20filter MODEL_PATH=/path/to/ckpt \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# 全量 SWE
VLLM_ENV=... HARNESS_PYTHON=... MODE=swe MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# DeepSWE
VLLM_ENV=... MODE=deepswe DEEPSWE_TASKS=/path/to/deep-swe/tasks \
MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Terminal-Bench
VLLM_ENV=... MODE=terminal N_TASKS=1 MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Resume 同名 run（SWE 跳过 preds.json 已有题）
VLLM_ENV=... HARNESS_PYTHON=... MODE=swe_20filter RUN_ID=my_run RESUME=1 MODEL_PATH=... \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# 本地用 SGLang 起小模型（需已安装 sglang）
VLLM_ENV=... HARNESS_PYTHON=... MODE=swe_20filter SLM_BACKEND=sglang SLM_PORT=8007 MODEL_PATH=... \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh
```

### Python 环境（网页指定，无机器硬编码）

| 用途 | 覆盖变量 |
|------|----------|
| vLLM / adapter / pipeline | `VLLM_ENV`（网页「vLLM 环境」） |
| SWE harness + mini-extra | `HARNESS_PYTHON`（网页「SWE harness 环境」） |

逻辑在 [`env_paths.sh`](env_paths.sh)；`offload/` / `evaluation/` 只消费已导出的 `PYTHON_BIN` / `VLLM_BIN` / `HARNESS_PYTHON`，不自行选环境。

## 网页版

```bash
cd run_use/html
python server.py   # http://0.0.0.0:8787/
```

页面 MODE 下拉可选四种；**Python 环境**填 SLM/vLLM 与 SWE harness 两套路径（支持 conda env 目录或 `.../bin/python`，下拉可从本机扫描建议）。SWE 的 `MINI_EXTRA_ARGS`、vLLM / SGLang 引擎参数都是一行一个 `--flag`，只跑一题时改 `--filter` 和 `-w`。`deepswe` / `terminal` 会显示各自参数。每次运行放在独立 tmux 会话 `pyrodash_<RUN_ID>` 里，网页或终端断开不会把它杀掉；跑完或失败后会话自动关闭。进度条和左侧运行列表可以 **停止本次运行**。进度默认 **live** 日志。`RUN_ID` 空=新建；续跑需填已有 id 并勾选 **resume**。

## 布局

```
run_use/
  run_sh/run_coding.sh
  run_sh/run_swe_20filter.sh   # → MODE=swe_20filter
  html/
  output/<RUN_ID>/{logs,status.json,<MODE>/}
```
