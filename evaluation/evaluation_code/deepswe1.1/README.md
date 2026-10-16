# DeepSWE 1.1 (Pier)

Eval client only. Start an [offload_code](../../../offload/offload_code) adapter first, then pass its port.

Pier runs **agent + verifier** in one job (no separate harness).

## Prerequisites

- `pier` on PATH (`uv tool install datacurve-pier`, need > 0.3.0 for DeepSWE 1.1)
- DeepSWE task tree (not vendored here):

```bash
git clone https://github.com/datacurve-ai/deep-swe
export DEEPSWE_TASKS="$PWD/deep-swe/tasks"
# or point at an existing checkout, e.g. eval/deep-swe/tasks
```

## Usage

```bash
# Terminal 1 — start offload (0.0.0.0 so Docker agents can reach it)
ADAPTER_PORT=18027 bash ../../../offload/offload_code/tag/api.sh

# Terminal 2 — evaluate (host auto-detected; override with --host if needed)
DEEPSWE_TASKS=/path/to/deep-swe/tasks bash eval.sh --port 18027

# smoke 1 task
DEEPSWE_TASKS=/path/to/deep-swe/tasks bash eval.sh --port 18027 --smoke
```

**Do not use `--host 127.0.0.1`** unless the agent container can reach the host loopback; Pier agents run in Docker and need the host LAN IP.

## What it does

1. `GET /health` on the adapter
2. Sets `OPENAI_BASE_URL=http://<host>:<port>/v1`
3. `pier run -a mini-swe-agent -m openai/pyrodash_code ...`
4. Writes jobs under `output/<job-name>/` (`result.json`, per-task `verifier/reward.json`)

Token / offload stats: `GET http://<host>:<port>/stats` on the adapter.

## Options

| Flag / env | Default | Meaning |
|------------|---------|---------|
| `--host` / `HOST_IP` | auto `hostname -I` | Adapter host (Docker-reachable) |
| `--port` / `ADAPTER_PORT` | (required) | Adapter port |
| `TASKS_DIR` / `DEEPSWE_TASKS` | (required) | Path to `deep-swe/tasks` |
| `N_CONCURRENT` / `--n` | `4` | Concurrent trials |
| `N_TASKS` / `--n-tasks` | empty = all | Pier `-l` |
| `SAMPLE_SEED` | `0` | With `-l` |
| `JOB_NAME` / `--job-name` | timestamped | Output job dir name |
| `MODEL_NAME` | `openai/pyrodash_code` | LiteLLM model id |
| `--smoke` | — | `N_TASKS=1 N_CONCURRENT=1` |
