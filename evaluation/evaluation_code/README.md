# evaluation_code

Benchmark **clients** for a running PyroDash offload adapter ([`offload/offload_code`](../../offload/offload_code)).

Start the adapter once, then point each benchmark script at its host/port.

| Benchmark | Path | Runner |
|-----------|------|--------|
| SWE-bench Verified | [`swe-bench/`](swe-bench/) | mini-extra + harness |
| DeepSWE 1.1 | [`deepswe1.1/`](deepswe1.1/) | Pier |
| Terminal-Bench | [`terminal-sh/`](terminal-sh/) | Harbor |

```bash
# 1) start offload (listen 0.0.0.0 so Docker agents can reach it)
ADAPTER_PORT=18027 bash offload/offload_code/tag/api.sh

# 2) evaluate (host auto-detected for Pier/Harbor; override with --host if needed)
bash evaluation/evaluation_code/swe-bench/eval.sh --port 18027
DEEPSWE_TASKS=/path/to/deep-swe/tasks \
  bash evaluation/evaluation_code/deepswe1.1/eval.sh --port 18027
bash evaluation/evaluation_code/terminal-sh/eval.sh --port 18027
```

Pier / Harbor agents run in containers — prefer a LAN host IP, not `127.0.0.1`.

### Python envs

- **Offload / vLLM**: project `.venv` (`/workspace/work/mjy/.venv`) via [`env_paths.sh`](../../env_paths.sh)
- **SWE harness**: base conda (`/workspace/.conda/bin/python`) — not gui-360
