# PyroDash Collaborate Engine

改 `run.sh` 顶部参数，然后启动：

```bash
cd collaborate_engine
pip install -r requirements.txt
chmod +x run.sh
./run.sh
```

`run.sh` 里需要改的参数：

| 变量 | 含义 |
|------|------|
| `SLM_BASE_URL` | 小模型 API 地址 |
| `SLM_API_KEY` | 小模型 key（没有就填 `EMPTY`） |
| `SLM_MODEL` | 小模型名 |
| `LLM_BASE_URL` | 大模型 API 地址 |
| `LLM_API_KEY` | 大模型 key |
| `LLM_MODEL` | 大模型名 |
| `EXPOSED_MODEL_NAME` | 对外模型名（默认 `pyrodash`） |
| `EXPOSED_API_KEY` | 对外接口 key（调用时必带） |
| `HOST` / `PORT` | 监听地址和端口（默认 `8100`） |

启动后接口：`http://127.0.0.1:8100/v1/chat/completions`

调用时带上 key：

```bash
curl http://127.0.0.1:8100/v1/chat/completions \
  -H "Authorization: Bearer sk-pyrodash" \
  -H "Content-Type: application/json" \
  -d '{"model":"pyrodash","messages":[{"role":"user","content":"hi"}]}'
```
