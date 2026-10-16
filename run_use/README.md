# run_use — Coding 评测一键入口

固定模式 **swe_20filter**（SWE-bench Verified representative 20 题）：起 offload adapter → mini-extra + harness → 结果进 `output/<RUN_ID>/`。

## 布局

```
run_use/
  run_sh/run_swe_20filter.sh   # CLI
  html/                        # 网页版（FastAPI）
  output/<RUN_ID>/             # 每次 run 的产物
    status.json
    logs/
    swe_20filter/{runs,verified}/
```

## CLI

编辑 `run_sh/run_swe_20filter.sh` 顶部配置块（或 export 同名环境变量），然后：

```bash
cd /path/to/PyroDash
# 本地 SLM 权重
MODEL_PATH=/path/to/hf_ckpt \
LLM_BASE_URL=https://.../v1 LLM_API_KEY=... LLM_MODEL=... \
ROUTER_MODE=tag \
  bash run_use/run_sh/run_swe_20filter.sh

# 或远程 SLM
SLM_BASE_URL=http://host:8000/v1 SLM_MODEL=my-slm \
LLM_BASE_URL=https://.../v1 LLM_API_KEY=... LLM_MODEL=... \
  bash run_use/run_sh/run_swe_20filter.sh
```

进度写在 `output/<RUN_ID>/status.json`（`starting_adapter` → `evaluating` → `done` / `failed`）。

## 网页版

依赖：`fastapi`、`uvicorn`（若未安装：`pip install fastapi uvicorn`）。

```bash
cd run_use/html
python server.py
# 默认 http://0.0.0.0:8787/
# RUN_USE_HOST / RUN_USE_PORT 可改绑定
```

浏览器打开后：填 SLM/LLM/端口 →「开始评测」→ 轮询进度与日志 →「历史结果」看摘要与文件。

## 说明

- `evaluation/evaluation_code/swe-bench/eval.sh` 支持 `EVAL_OUTPUT_DIR`、`INSTANCE_FILTER`；本脚本会注入 20filter 正则。
- Adapter 来自 `offload/offload_code/{tag|entropy}/api.sh`。
- 评测脚本本身仍只在 `evaluation/`；产物一律进 `run_use/output/`。
