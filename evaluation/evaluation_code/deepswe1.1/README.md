# DeepSWE 1.1 (Pier)

Eval client only. Start an [offload_code](../../../offload/offload_code) adapter first, then pass its port.  
仅评测客户端。先起 [offload_code](../../../offload/offload_code) adapter，再传入端口。

Pier runs **agent + verifier** in one job (no separate harness).  
Pier 在同一 job 里跑 **agent + verifier**（无单独 harness）。

## Dependencies / 依赖

```bash
pip install -r ../../../requirements.txt -r requirements.txt
uv tool install datacurve-pier   # pier on PATH; need > 0.3.0 for DeepSWE 1.1
```

## Prerequisites / 前置

- `pier` on PATH (see above) / `pier` 在 PATH 上  
- DeepSWE task tree (not vendored here) / DeepSWE 任务树（本仓库未内置）：

```bash
git clone https://github.com/datacurve-ai/deep-swe
export DEEPSWE_TASKS="$PWD/deep-swe/tasks"
# or point at an existing checkout, e.g. eval/deep-swe/tasks
# 或指向已有 checkout
```

## Usage / 用法

```bash
# Terminal 1 — start offload (0.0.0.0 so Docker agents can reach it)
# 终端 1 — 起 offload（0.0.0.0 以便 Docker agent 访问）
ADAPTER_PORT=18027 bash ../../../offload/offload_code/tag/api.sh

# Terminal 2 — evaluate (host auto-detected; override with --host if needed)
# 终端 2 — 评测（自动探测 host；必要时 --host）
DEEPSWE_TASKS=/path/to/deep-swe/tasks bash eval.sh --port 18027

# smoke 1 task / 冒烟 1 题
DEEPSWE_TASKS=/path/to/deep-swe/tasks bash eval.sh --port 18027 --smoke
```

**Do not use `--host 127.0.0.1`** unless the agent container can reach the host loopback; Pier agents run in Docker and need the host LAN IP.  
**不要用 `--host 127.0.0.1`**，除非容器能访问宿主机 loopback；Pier agent 在 Docker 里，需要宿主机局域网 IP。

## What it does / 流程

1. `GET /health` on the adapter / 探活  
2. Sets `OPENAI_BASE_URL=http://<host>:<port>/v1`  
3. `pier run -a mini-swe-agent -m openai/pyrodash_code ...`  
4. Writes jobs under `output/<job-name>/` (`result.json`, per-task `verifier/reward.json`)  

Token / offload stats: `GET http://<host>:<port>/stats` on the adapter.  
Token / offload 统计：adapter 的 `GET /stats`。

## Options / 选项

| Flag / env | Default | Meaning / 含义 |
|------------|---------|----------------|
| `--host` / `HOST_IP` | auto `hostname -I` | Adapter host (Docker-reachable) / 容器可达的 host |
| `--port` / `ADAPTER_PORT` | (required) | Adapter port |
| `TASKS_DIR` / `DEEPSWE_TASKS` | (required) | Path to `deep-swe/tasks` |
| `N_CONCURRENT` / `--n` | `4` | Concurrent trials / 并发 |
| `N_TASKS` / `--n-tasks` | empty = all | Pier `-l` |
| `SAMPLE_SEED` | `0` | With `-l` |
| `JOB_NAME` / `--job-name` | timestamped | Output job dir name / 输出目录名 |
| `MODEL_NAME` | `openai/pyrodash_code` | LiteLLM model id |
| `--smoke` | — | `N_TASKS=1 N_CONCURRENT=1` |
