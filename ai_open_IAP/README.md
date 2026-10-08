# Odoo AI endpoint proxy

This directory contains a small replacement endpoint for Odoo 20 Enterprise AI
calls. It is intentionally not a full IAP replacement. The Enterprise `ai`
module reads the `ai.endpoint` system parameter and calls routes below
`/api/odoo_ai/...`, so the first useful target is an Odoo AI-compatible proxy.

## Supported routes

- `/api/odoo_ai/1/get_completions_sync`
- `/api/odoo_ai/1/get_supported_embedding_models`
- `/api/odoo_ai/1/get_default_embedding_model`
- `/api/odoo_ai/1/get_embeddings`

The completions route forwards to an OpenAI-compatible chat completions API.
That includes LiteLLM, vLLM, Ollama's OpenAI compatibility layer, and many
self-hosted gateways.

## Run locally

```bash
cd /home/weinni2000/doodba20/odoo/custom/src/ai/ai_open_IAP
python -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"

export ODOO_AI_PROXY_BASE_URL="http://localhost:11434/v1"
export ODOO_AI_PROXY_MODEL="llama3.1"
export ODOO_AI_PROXY_API_KEY=""

uvicorn odoo_ai_proxy.main:app --host 0.0.0.0 --port 8019
```

Then set this Odoo system parameter:

```text
ai.endpoint = http://localhost:8019
```

For Docker-to-host networking, use the URL that is reachable from the Odoo
container, for example `http://host.docker.internal:8019` where supported.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ODOO_AI_PROXY_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible base URL |
| `ODOO_AI_PROXY_API_KEY` | empty | Bearer token sent to the provider |
| `ODOO_AI_PROXY_MODEL` | `llama3.1` | Chat model |
| `ODOO_AI_PROXY_EMBEDDING_MODEL` | same as chat model | Embedding model |
| `ODOO_AI_PROXY_TIMEOUT` | `120` | Provider timeout in seconds |

## Smoke request

```bash
curl -s http://localhost:8019/api/odoo_ai/1/get_completions_sync \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "method": "call",
    "id": "demo",
    "params": {
      "instructions": "Answer briefly.",
      "messages": [
        {"role": "user", "content": [{"type": "text", "text": "Say hello"}]}
      ],
      "tools": []
    }
  }'
```

