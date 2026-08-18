# PyroDash serving skeleton

Install and run:

```bash
pip install -r requirements-serving.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

The service exposes:

```text
GET  /health/live
POST /v1/chat/completions
```

The first version is intentionally non-streaming. It calls SGLang first, calls GLM only when the SLM emits `<|llm_offload|>`, and returns combined output plus separate `slm` and `llm` usage under `pyrodash_usage`.

Example request:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "pyrodash",
    "messages": [{"role": "user", "content": "Solve this problem."}],
    "max_tokens": 1024
  }'
```
