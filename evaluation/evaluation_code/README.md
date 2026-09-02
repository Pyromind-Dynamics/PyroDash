# evaluation_code

SWE-bench Verified 评测（SLM + LLM offload）。流程分两步：先起服务，再跑评测。

## 用法

```bash
# 终端 1：启动本地 SLM（vLLM）+ offload adapter，保持运行
bash serve/serve_adapter.sh

# 终端 2：等 adapter ready 后跑评测
bash code_eval.sh
```

输出：

- 轨迹 / 预测：`output/runs/`（含 `preds.json`）
- harness 报告：`output/verified/`
- adapter 日志与 token 统计：`output/miniswe_offload_verified/`

运行前请编辑：

- `serve/serve_adapter.sh`：填好 `MODEL` 与 `--llm-*`
- `serve/config_yaml/slm.yaml` / `serve/config_yaml/llm.yaml`：SLM / LLM 采样参数（任意 chat.completions 字段）
- `serve/config_yaml/model_offload.yaml`：mini-extra 指向 adapter 的模型配置

---

## `serve/config_yaml/`

与 `swe-bench/run_yaml` 类似：YAML 集中放在这里，启动 / 评测时按路径传入。

| 文件 | 作用 |
|------|------|
| `serve/config_yaml/slm.yaml` | SLM 采样（任意 chat.completions 字段；嵌套 `extra_body` 会展平） |
| `serve/config_yaml/llm.yaml` | LLM 采样（同上） |
| `serve/config_yaml/model_offload.yaml` | mini-extra 模型配置（`api_base` / `api_key`、agent 步数/时限） |

换一套采样：复制 yaml 改参数，启动时改 `--slm-config` / `--llm-config` 路径即可。

---

## `serve/serve_adapter.sh`

启动本地小模型（vLLM）和 offload adapter。adapter 对外提供 Anthropic 兼容接口（默认 `http://127.0.0.1:18022`），供 `mini-extra` 调用；SLM 遇 offload 时转发给远程 LLM。

| 参数 | 作用 |
|------|------|
| `MODEL` | 本地 SLM 权重路径 |
| `CUDA_VISIBLE_DEVICES` | 使用哪张 GPU |
| vLLM `--port 8001` / `--served-model-name` | SLM HTTP 服务地址与模型名 |
| `--slm-base-url` / `--slm-api-key` / `--slm-model` | adapter 连本地 vLLM 的地址、key、模型名 |
| `--llm-base-url` / `--llm-api-key` / `--llm-model` | 远程大模型 OpenAI 兼容端点 |
| `--use-llm` | 是否启用 LLM offload（`true`/`false`） |
| `--max-new-tokens` | 单轮 SLM+LLM 合计 completion 预算；LLM 分到 `预算 - SLM 已生成`；`nolimit` 表示不设共享上限 |
| `--slm-config` / `--llm-config` | SLM / LLM 采样 YAML（默认 `serve/config_yaml/slm.yaml`、`llm.yaml`） |
| `--stats-dir` | 在线统计目录（`summary.json`、按 session 的 token 用量） |
| `--host` / `--port` | adapter 监听地址（默认 `0.0.0.0:18022`） |

`Ctrl-C` 会同时停掉 adapter 和 vLLM。

---

## `code_eval.sh`

假定 adapter 已在 `http://127.0.0.1:18022` 就绪。先用 `mini-extra swebench` 生成预测，再跑官方 harness 打分。

| 参数 / 配置 | 作用 |
|-------------|------|
| `serve/config_yaml/model_offload.yaml` | 指向本地 adapter（`api_base`、`api_key`）及 agent 步数/时限 |
| `serve/registry.json` | LiteLLM 模型注册表 |
| `--subset verified` / `--split test` | SWE-bench Verified 测试集 |
| `-w` | mini-extra 并行 worker 数 |
| `-o` | 输出目录（默认 `output/runs`） |
| `agent.step_limit` | 每个 instance 最大 agent 步数 |
| `environment.pull_timeout` | 拉镜像超时（秒） |
| `run_swebench_eval.py --predictions_path` | harness 输入的 `preds.json` |
| `--max_workers` | harness 并行评测数 |
| `--run_id` / `--report_dir` | harness 运行 ID 与报告目录 |
| `--cache_level` / `--clean` | Docker 缓存级别与是否清理 |

端口需与 `serve_adapter.sh` / `model_offload.yaml` 一致（默认 adapter `18022`）。