# evaluation_code

Benchmark **clients** for a running PyroDash offload adapter ([`offload/offload_code`](../../offload/offload_code)).  
面向已启动的 PyroDash offload adapter 的评测**客户端**。

Start the adapter once, then point each benchmark script at its host/port.  
先起 adapter，再把各评测脚本指到其 host/port。

| Benchmark | Path | Runner |
|-----------|------|--------|
| SWE-bench Verified | [`swe-bench/`](swe-bench/) | mini-extra + harness |
| DeepSWE 1.1 | [`deepswe1.1/`](deepswe1.1/) | Pier |
| Terminal-Bench | [`terminal-sh/`](terminal-sh/) | Harbor |

```bash
# 1) start offload (listen 0.0.0.0 so Docker agents can reach it)
# 1) 起 offload（监听 0.0.0.0，方便 Docker agent 访问）
ADAPTER_PORT=18027 bash offload/offload_code/tag/api.sh

# 2) evaluate (host auto-detected for Pier/Harbor; override with --host if needed)
# 2) 评测（Pier/Harbor 会自动探测 host；必要时用 --host 覆盖）
bash evaluation/evaluation_code/swe-bench/eval.sh --port 18027
DEEPSWE_TASKS=/path/to/deep-swe/tasks \
  bash evaluation/evaluation_code/deepswe1.1/eval.sh --port 18027
bash evaluation/evaluation_code/terminal-sh/eval.sh --port 18027
```

Pier / Harbor agents run in containers — prefer a LAN host IP, not `127.0.0.1`.  
Pier / Harbor agent 跑在容器里 —— 请用局域网 host IP，不要用 `127.0.0.1`。

### Python envs / Python 环境

Configured only in [`run_use`](../../run_use) (web UI or `run_sh/run_coding.sh`). These scripts receive already-resolved:  
仅在 [`run_use`](../../run_use) 配置。这些脚本接收已解析好的：

- `PYTHON_BIN` / `VLLM_BIN` — SLM / adapter
- `HARNESS_PYTHON` — swebench + docker (+ `mini-extra` on `PATH`)

### Per-task pip deps / 按任务安装依赖

Install **repo root** `requirements.txt` plus the task folder’s own file:  
安装**仓库根** `requirements.txt` 加上任务目录自己的文件：

| Task | Extra requirements |
|------|--------------------|
| SWE-bench | [`swe-bench/requirements.txt`](swe-bench/requirements.txt) |
| DeepSWE | [`deepswe1.1/requirements.txt`](deepswe1.1/requirements.txt) |
| Terminal-Bench | [`terminal-sh/requirements.txt`](terminal-sh/requirements.txt) |
