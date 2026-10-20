# run_use — Coding eval one-click entry / Coding 评测一键入口

Unified entry **`run_sh/run_coding.sh`**, supporting:  
统一入口 **`run_sh/run_coding.sh`**，支持：

| MODE | Meaning / 含义 |
|------|----------------|
| `swe` | SWE-bench Verified full / 全量 |
| `swe_20filter` | Representative 20 instances / representative 20 题（特例） |
| `deepswe` | DeepSWE 1.1（Pier） |
| `terminal` | Terminal-Bench（Harbor） |

**Cluster / 集群:** `CLUSTER=us` (default — US images + local Docker) or `CLUSTER=shanghai` (Aliyun SWE-bench images, docker-rt, offline HF / GitHub raw mirror). The web “集群” dropdown sets the same variable. LLM URL, ports, and context length are **not** tied to cluster.  
`CLUSTER=us`（默认，美区镜像与本机 Docker）或 `CLUSTER=shanghai`（阿里云 SWE-bench 镜像、docker-rt、离线 HF / GitHub raw 镜像）。页面「集群」下拉传同一变量。LLM 地址、端口、上下文长度不跟集群绑定。

**Flow / 流程:** start offload adapter → run the matching `evaluation_code/*/eval.sh` → results under `output/<RUN_ID>/<MODE>/`.  
起 offload adapter → 跑对应 `evaluation_code/*/eval.sh` → 结果进 `output/<RUN_ID>/<MODE>/`。

**ROUTER:** `tag` / `entropy` (needs LLM) or **`slm_only`** (SLM only, no offload prompt injection).  
`tag` / `entropy`（需 LLM）或 **`slm_only`**（仅小模型，不注入 offload 提示词）。

**Local SLM engine / 本地小模型引擎:** `SLM_BACKEND=vllm|sglang` (default vllm). Web “本地权重” can pick engine and advanced port / GPU / parser settings; remote API does not start a local engine.  
网页「本地权重」可选引擎并改 port / GPU / parser 等；远程 API 不启本地引擎。

**Resume / 断点续跑:** Explicit opt-in. Web: check `resume` and fill an existing `RUN_ID`. CLI: `RUN_ID=... RESUME=1`. Same name without resume still returns 409. SWE / `swe_20filter` skip finished instances via `preds.json`; refuse if an old process is still running.  
显式开启。Web 勾选 `resume` 并填已有 `RUN_ID`；CLI 设 `RUN_ID=... RESUME=1`。同名且未勾选 resume 仍 409。SWE / `swe_20filter` 靠 `preds.json` 跳过已完成实例；旧进程仍在跑则拒绝。

**History UI / 历史结果页:** Split preview; `.traj.json` rendered as chat (keeps `<|llm_offload|>` markers).  
左右分栏预览；`.traj.json` 渲染为对话（保留 `<|llm_offload|>` 标记）。

## CLI

```bash
cd /path/to/PyroDash

# Required: VLLM_ENV (vLLM env) + HARNESS_PYTHON (SWE harness; optional for deepswe/terminal)
# 必填：VLLM_ENV（vLLM 环境）+ HARNESS_PYTHON（SWE harness；deepswe/terminal 可省略）
# 20filter（或 bash run_use/run_sh/run_swe_20filter.sh）
VLLM_ENV=/path/to/vllm_env HARNESS_PYTHON=/path/to/swe_env \
MODE=swe_20filter MODEL_PATH=/path/to/ckpt \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Shanghai cluster (not needed for US default) / 上海集群（美区默认不用加）
VLLM_ENV=... HARNESS_PYTHON=... CLUSTER=shanghai MODE=swe_20filter MODEL_PATH=/path/to/ckpt \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Full SWE / 全量 SWE
VLLM_ENV=... HARNESS_PYTHON=... MODE=swe MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# DeepSWE
VLLM_ENV=... MODE=deepswe DEEPSWE_TASKS=/path/to/deep-swe/tasks \
MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Terminal-Bench
VLLM_ENV=... MODE=terminal N_TASKS=1 MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Resume same RUN_ID (SWE skips preds.json) / Resume 同名 run
VLLM_ENV=... HARNESS_PYTHON=... MODE=swe_20filter RUN_ID=my_run RESUME=1 MODEL_PATH=... \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh

# Local SLM via SGLang / 本地用 SGLang 起小模型
VLLM_ENV=... HARNESS_PYTHON=... MODE=swe_20filter SLM_BACKEND=sglang SLM_PORT=8007 MODEL_PATH=... \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_coding.sh
```

### Python envs (set from web / CLI; no machine hardcoding) / Python 环境（网页指定，无机器硬编码）

| Purpose / 用途 | Override / 覆盖变量 |
|----------------|---------------------|
| vLLM / adapter / pipeline | `VLLM_ENV`（网页「vLLM 环境」） |
| SWE harness + mini-extra | `HARNESS_PYTHON`（网页「SWE harness 环境」） |

Logic lives in [`env_paths.sh`](env_paths.sh); `offload/` / `evaluation/` only consume exported `PYTHON_BIN` / `VLLM_BIN` / `HARNESS_PYTHON`.  
逻辑在 [`env_paths.sh`](env_paths.sh)；`offload/` / `evaluation/` 只消费已导出的变量，不自行选环境。

## Web UI / 网页版

```bash
cd run_use/html
python server.py   # http://0.0.0.0:8787/
```

MODE dropdown covers all four modes. **Python envs** take SLM/vLLM and SWE harness paths (conda env dir or `.../bin/python`; dropdown can scan suggestions). SWE `MINI_EXTRA_ARGS`, vLLM / SGLang engine args are one `--flag` per line; for a single instance change `--filter` and `-w`. `deepswe` / `terminal` show their own fields. Each run lives in tmux session `pyrodash_<RUN_ID>` so disconnecting the browser/terminal does not kill it; the session closes after finish/fail. Progress and the left run list can **stop the current run**. Progress defaults to **live** logs. Empty `RUN_ID` = new run; resume needs an existing id + **resume** checked.

页面 MODE 下拉可选四种；**Python 环境**填 SLM/vLLM 与 SWE harness 两套路径。SWE 的 `MINI_EXTRA_ARGS`、引擎参数一行一个 `--flag`。每次运行在独立 tmux 会话 `pyrodash_<RUN_ID>`；进度条和左侧列表可 **停止本次运行**。`RUN_ID` 空=新建；续跑需填已有 id 并勾选 **resume**。

## Layout / 布局

```
run_use/
  run_sh/run_coding.sh
  run_sh/run_swe_20filter.sh   # → MODE=swe_20filter
  html/
  output/<RUN_ID>/{logs,status.json,<MODE>/}
```
