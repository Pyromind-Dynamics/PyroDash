# Terminal-Bench (Harbor)

Eval client only. Start an [offload_code](../../../offload/offload_code) adapter first, then pass its port.

Uses Harbor + `mini-swe-agent` (no local offload proxy — that lives in `offload_code`).

## Prerequisites

- `harbor` on PATH
- Dataset pullable by Harbor (default `terminal-bench/terminal-bench-2-1`)

## Usage

```bash
# Terminal 1
ADAPTER_PORT=18027 bash ../../../offload/offload_code/tag/api.sh

# Terminal 2 (host auto-detected for Docker agents)
bash eval.sh --port 18027

# smoke
bash eval.sh --port 18027 --smoke

# Terminal-Bench 2.0
DATASET=terminal-bench@2.0 bash eval.sh --port 18027
```

**Do not use `--host 127.0.0.1`** unless containers can reach host loopback.

## What it does

1. Health-check adapter (`/health` or `/v1/models`)
2. Sets `OPENAI_BASE_URL=http://<host>:<port>/v1`
3. `harbor run -d <dataset> -a mini-swe-agent -m openai/pyrodash_code ...`
4. Writes jobs under `output/<job-name>/`

Token / offload stats: `GET http://<host>:<port>/stats` on the adapter.

## Options

| Flag / env | Default | Meaning |
|------------|---------|---------|
| `--host` / `HOST_IP` | auto `hostname -I` | Adapter host (Docker-reachable) |
| `--port` / `ADAPTER_PORT` | (required) | Adapter port |
| `DATASET` | `terminal-bench/terminal-bench-2-1` | Harbor `-d` |
| `N_CONCURRENT` / `--n` | `4` | Concurrent trials |
| `N_TASKS` / `--n-tasks` | empty = all | Harbor `-l` |
| `INCLUDE_TASK` / `--include-task` | — | Harbor `-i` |
| `JOB_NAME` / `--job-name` | timestamped | Output job dir name |
| `MODEL_NAME` | `openai/pyrodash_code` | LiteLLM model id |
| `--smoke` | — | `N_TASKS=1 N_CONCURRENT=1` |
