# SWE-bench (Verified)

Eval client only. Start an [offload_code](../../../offload/offload_code) adapter first, then pass its port here.

## Usage

```bash
# Terminal 1 — start offload API (fill MODEL_PATH / LLM_* in api.sh)
ADAPTER_PORT=18027 bash ../../../offload/offload_code/tag/api.sh

# Terminal 2 — run SWE-bench against that port
bash eval.sh --port 18027
# remote machine:
bash eval.sh --host 10.0.0.1 --port 18027
```

## What it does

1. `GET /health` on the adapter
2. Writes `output/runs/model.<host>.<port>.yaml` with OpenAI `api_base=http://host:port/v1` (`openai/pyrodash_code` → `/v1/chat/completions`)
3. `mini-extra swebench`（叠加 `config/env_testbed_path.yaml`：`bash -lc` + testbed conda PATH，与 `swe_run_offload` 对齐）→ `output/runs/preds.json`
4. Official harness via `run_harness.py` (Docker API timeout 300s) → `output/verified/`

`CLUSTER=us`（默认）走系统 `mini-extra` 和 Docker Hub 镜像。`CLUSTER=shanghai` 改写为阿里云镜像、`DOCKER_HOST=unix:///tmp/docker-rt.sock`，并在 harness 上加 namespace / GitHub raw 缓存。

Token / offload stats stay on the adapter: `GET http://<host>:<port>/stats` and its `logs/.../adapter_stats/`.

## Options

| Flag / env | Default | Meaning |
|------------|---------|---------|
| `--host` / `ADAPTER_HOST` | `127.0.0.1` | Adapter host |
| `--port` / `ADAPTER_PORT` | (required) | Adapter port |
| `SUBSET` | `verified` | mini-extra subset |
| `SPLIT` | `test` | mini-extra split |
| `WORKERS` | `4` | mini-extra parallelism |
| `STEP_LIMIT` | `150` | agent step limit |
| `HARNESS_WORKERS` | `8` | harness parallelism |
| `DATASET_NAME` | `princeton-nlp/SWE-bench_Verified` | harness dataset |
| `RUN_ID` | `swebench_offload_pred` | harness run id |
| `HARNESS_PYTHON` | `/workspace/.conda/bin/python` | Python with `swebench` + `docker` (base conda; **not** gui-360 / project `.venv`) |

Harness reports land under `verified/` (or `EVAL_OUTPUT_DIR/verified/` when used from `run_use`).

```bash
WORKERS=2 STEP_LIMIT=100 bash eval.sh --port 18027
# optional override:
HARNESS_PYTHON=/workspace/.conda/bin/python bash eval.sh --port 18027
```
