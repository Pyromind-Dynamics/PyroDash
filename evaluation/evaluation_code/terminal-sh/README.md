# Terminal-Bench (Harbor)

Eval client only. Start an [offload_code](../../../offload/offload_code) adapter first, then pass its port.  
仅评测客户端。先起 [offload_code](../../../offload/offload_code) adapter，再传入端口。

Uses Harbor + `mini-swe-agent` (no local offload proxy — that lives in `offload_code`).  
使用 Harbor + `mini-swe-agent`（本地无 offload 代理 —— 在 `offload_code`）。

## Dependencies / 依赖

```bash
pip install -r ../../../requirements.txt -r requirements.txt
# Install Harbor CLI separately so `harbor` is on PATH
# 需单独安装 Harbor CLI，保证 `harbor` 在 PATH 上
```

## Prerequisites / 前置

- `harbor` on PATH  
- Dataset pullable by Harbor (default `terminal-bench/terminal-bench-2-1`) / Harbor 可拉取的数据集  

## Usage / 用法

```bash
# Terminal 1 / 终端 1
ADAPTER_PORT=18027 bash ../../../offload/offload_code/tag/api.sh

# Terminal 2 (host auto-detected for Docker agents) / 终端 2（自动探测 host）
bash eval.sh --port 18027

# smoke / 冒烟
bash eval.sh --port 18027 --smoke

# Terminal-Bench 2.0
DATASET=terminal-bench@2.0 bash eval.sh --port 18027
```

**Do not use `--host 127.0.0.1`** unless containers can reach host loopback.  
**不要用 `--host 127.0.0.1`**，除非容器能访问宿主机 loopback。

## What it does / 流程

1. Health-check adapter (`/health` or `/v1/models`) / 探活  
2. Sets `OPENAI_BASE_URL=http://<host>:<port>/v1`  
3. `harbor run -d <dataset> -a mini-swe-agent -m openai/pyrodash_code ...`  
4. Writes jobs under `output/<job-name>/` / 结果写入 `output/<job-name>/`  

Token / offload stats: `GET http://<host>:<port>/stats` on the adapter.  
Token / offload 统计：adapter 的 `GET /stats`。

## Options / 选项

| Flag / env | Default | Meaning / 含义 |
|------------|---------|----------------|
| `--host` / `HOST_IP` | auto `hostname -I` | Adapter host (Docker-reachable) / 容器可达的 host |
| `--port` / `ADAPTER_PORT` | (required) | Adapter port |
| `DATASET` | `terminal-bench/terminal-bench-2-1` | Harbor `-d` |
| `N_CONCURRENT` / `--n` | `4` | Concurrent trials / 并发 |
| `N_TASKS` / `--n-tasks` | empty = all | Harbor `-l` |
| `INCLUDE_TASK` / `--include-task` | — | Harbor `-i` |
| `JOB_NAME` / `--job-name` | timestamped | Output job dir name / 输出目录名 |
| `MODEL_NAME` | `openai/pyrodash_code` | LiteLLM model id |
| `--smoke` | — | `N_TASKS=1 N_CONCURRENT=1` |
