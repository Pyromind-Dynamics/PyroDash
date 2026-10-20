# SWE-bench (Verified)

Eval client only. Start an [offload_code](../../../offload/offload_code) adapter first, then pass its port here.  
仅评测客户端。先起 [offload_code](../../../offload/offload_code) adapter，再把端口传进来。

## Dependencies / 依赖

```bash
# Repo root + this folder (enough for SWE harness / mini-extra env)
# 仓库根 + 本目录（足够 SWE harness / mini-extra 环境）
pip install -r ../../../requirements.txt -r requirements.txt
```

Preferred via `run_use` (two envs) / 推荐经 `run_use`（两套环境）：

| Env | Install / 安装 |
|-----|----------------|
| `VLLM_ENV` (vLLM / adapter) | root `requirements.txt` + `offload/offload_code/requirements.txt` |
| `HARNESS_PYTHON` (swebench) | this folder’s `requirements.txt` (`swebench`, `mini-swe-agent`, `docker`) |

## Usage / 用法

```bash
# Terminal 1 — start offload API (fill MODEL_PATH / LLM_* in api.sh)
# 终端 1 — 起 offload API
ADAPTER_PORT=18027 bash ../../../offload/offload_code/tag/api.sh

# Terminal 2 — run SWE-bench against that port
# 终端 2 — 对该端口跑 SWE-bench
bash eval.sh --port 18027
# remote machine / 远程机器:
bash eval.sh --host 10.0.0.1 --port 18027
```

## What it does / 流程

1. `GET /health` on the adapter / 探活 adapter  
2. Writes `output/runs/model.<host>.<port>.yaml` with OpenAI `api_base=http://host:port/v1` (`openai/pyrodash_code` → `/v1/chat/completions`)  
3. `mini-extra swebench`（叠加 `config/env_testbed_path.yaml`：`bash -lc` + testbed conda PATH，与 `swe_run_offload` 对齐）→ `output/runs/preds.json`  
4. Official harness via `run_harness.py` (Docker API timeout 300s) → `output/verified/`  

`CLUSTER=us` (default) uses system `mini-extra` and Docker Hub images. `CLUSTER=shanghai` rewrites to Aliyun images, `DOCKER_HOST=unix:///tmp/docker-rt.sock`, and adds namespace / GitHub raw cache on the harness.  
`CLUSTER=us`（默认）走系统 `mini-extra` 和 Docker Hub 镜像。`CLUSTER=shanghai` 改写为阿里云镜像、`DOCKER_HOST=unix:///tmp/docker-rt.sock`，并在 harness 上加 namespace / GitHub raw 缓存。

Token / offload stats stay on the adapter: `GET http://<host>:<port>/stats` and its `logs/.../adapter_stats/`.  
Token / offload 统计仍在 adapter：`GET /stats` 及其 `logs/.../adapter_stats/`。

## Options / 选项

| Flag / env | Default | Meaning / 含义 |
|------------|---------|----------------|
| `--host` / `ADAPTER_HOST` | `127.0.0.1` | Adapter host |
| `--port` / `ADAPTER_PORT` | (required) | Adapter port |
| `MINI_EXTRA_ARGS` | (unset) | mini-extra args, one per line. When set, replaces the four below; `--filter` / `--slice` also replace `INSTANCE_FILTER` · 一行一个；设置后取代下面四项 |
| `SUBSET` | `verified` | mini-extra subset（when `MINI_EXTRA_ARGS` empty） |
| `SPLIT` | `test` | mini-extra split |
| `WORKERS` | `4` | mini-extra parallelism |
| `STEP_LIMIT` | `150` | agent step limit |
| `HARNESS_WORKERS` | `8` | harness parallelism |
| `DATASET_NAME` | `princeton-nlp/SWE-bench_Verified` | harness dataset |
| `RUN_ID` | `swebench_offload_pred` | harness run id |
| `HARNESS_PYTHON` | (required) | Python with `swebench` + `docker` — set by `run_use` / web UI |

Harness reports land under `verified/` (or `EVAL_OUTPUT_DIR/verified/` from `run_use`). Prefer launching via `run_use`; standalone:  
Harness 报告在 `verified/`（或 `run_use` 的 `EVAL_OUTPUT_DIR/verified/`）。优先用 `run_use`；独立跑：

```bash
HARNESS_PYTHON=/path/to/swe_env/bin/python WORKERS=2 STEP_LIMIT=100 bash eval.sh --port 18027
```
