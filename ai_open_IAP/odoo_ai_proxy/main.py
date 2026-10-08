import json
import logging
import os
import hashlib
import hmac
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse


_logger = logging.getLogger(__name__)

app = FastAPI(title="Odoo AI endpoint proxy")

LOG_DIR = Path(__file__).resolve().parents[1] / "logging"
OPEN_IAP_CONNECTION_PARAM = "ai.open_iap.connection_id"
# Used when the selected connection has no URL; other kinds keep the env default.
DEFAULT_BASE_URLS = {
    "claude": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}
# Embeddings always go to Gemini, whatever chat connection is selected. Odoo's
# own IAP uses the same model, and ai.embedding stores vector(1536).
EMBEDDING_MODEL = os.getenv("ODOO_AI_PROXY_EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = 100
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"
EMBEDDING_TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}
# Media types Anthropic accepts as image blocks.
ANTHROPIC_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _config() -> dict[str, Any]:
    model = os.getenv("ODOO_AI_PROXY_MODEL", "llama3.1")
    config = {
        "kind": os.getenv("ODOO_AI_PROXY_KIND", "openai_compatible"),
        "base_url": os.getenv("ODOO_AI_PROXY_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        "api_key": os.getenv("ODOO_AI_PROXY_API_KEY", ""),
        "model": model,
        "timeout": float(os.getenv("ODOO_AI_PROXY_TIMEOUT", "120")),
    }
    selected_config = _selected_connection_config()
    if selected_config:
        config.update(selected_config)
    return config


def _selected_connection_config() -> dict[str, Any] | None:
    dbname = os.getenv("ODOO_AI_PROXY_ODOO_DB", "plane_20")
    if not dbname:
        return None
    try:
        with psycopg2.connect(dbname=dbname) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    select
                        ai_connection.kind,
                        ai_connection.url,
                        ai_connection.model,
                        ai_connection.api_key,
                        ai_connection.temperature,
                        -- jsonb keeps this working before the column exists.
                        (to_jsonb(ai_connection) ->> 'supports_images')::boolean
                            as supports_images
                    from ir_config_parameter
                    join ai_connection
                        on ai_connection.id = nullif(ir_config_parameter.value, '')::integer
                    where ir_config_parameter.key = %s
                        and ai_connection.active
                    limit 1
                    """,
                    [OPEN_IAP_CONNECTION_PARAM],
                )
                row = cursor.fetchone()
    except Exception as e:  # noqa: BLE001
        _log_event("config_error", {"message": str(e)})
        return None
    if not row:
        return None
    config = {
        "kind": row["kind"],
        "model": row["model"] or os.getenv("ODOO_AI_PROXY_MODEL", "llama3.1"),
        "api_key": row["api_key"] or "",
        "temperature": row["temperature"],
        "supports_images": bool(row["supports_images"]),
    }
    base_url = row["url"] or DEFAULT_BASE_URLS.get(row["kind"])
    if base_url:
        config["base_url"] = base_url.rstrip("/")
    return config


def _log_event(kind: str, payload: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    event = {
        "timestamp": now.isoformat(),
        "kind": kind,
        "payload": payload,
    }
    log_path = LOG_DIR / f"{now.date().isoformat()}.jsonl"
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _jsonrpc_result(rpc_id: Any, result: Any, log_result: Any = None) -> JSONResponse:
    """Wrap a JSON-RPC result; log_result replaces bulky results in the log."""
    payload = {"jsonrpc": "2.0", "id": rpc_id, "result": result}
    _log_event(
        "odoo_response",
        payload if log_result is None else {**payload, "result": log_result},
    )
    return JSONResponse(payload)


def _jsonrpc_error(rpc_id: Any, code: int, message: str, data: Any = None) -> JSONResponse:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    payload = {"jsonrpc": "2.0", "id": rpc_id, "error": error}
    _log_event("odoo_response", payload)
    return JSONResponse(payload)


async def _jsonrpc_payload(request: Request) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    payload = await request.json()
    _log_event(
        "odoo_request",
        {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": payload,
        },
    )
    return payload.get("id"), payload.get("params") or {}, payload


def _post_provider(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = _config()
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"
    request = urllib.request.Request(
        f"{config['base_url']}{path}",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        _log_event("provider_request", {"path": path, "body": payload})
        with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
            result = json.loads(response.read().decode())
            _log_event(
                "provider_response",
                {"path": path, "status": response.status, "body": result},
            )
            return result
    except urllib.error.HTTPError as e:
        details = e.read().decode(errors="replace")
        _log_event(
            "provider_response",
            {"path": path, "status": e.code, "body": details},
        )
        raise RuntimeError(f"Provider returned HTTP {e.code}: {details}") from e


def _post_anthropic(payload: dict[str, Any]) -> dict[str, Any]:
    config = _config()
    if not config["api_key"]:
        raise RuntimeError("The selected Claude connection has no API key.")
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{config.get('base_url') or 'https://api.anthropic.com'}/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        _log_event("provider_request", {"path": "/v1/messages", "body": payload})
        with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
            result = json.loads(response.read().decode())
            _log_event(
                "provider_response",
                {"path": "/v1/messages", "status": response.status, "body": result},
            )
            return result
    except urllib.error.HTTPError as e:
        details = e.read().decode(errors="replace")
        _log_event(
            "provider_response",
            {"path": "/v1/messages", "status": e.code, "body": details},
        )
        raise RuntimeError(f"Provider returned HTTP {e.code}: {details}") from e


def _part_text(part: dict[str, Any]) -> str:
    if part.get("type") == "text":
        return part.get("text") or ""
    if part.get("type") == "tool_result":
        return json.dumps(part, ensure_ascii=False)
    if part.get("type") == "inline_data":
        return (
            f"[The user attached a file ({part.get('mimetype', 'unknown')}) "
            "that this model cannot view.]"
        )
    return json.dumps(part, ensure_ascii=False)


def _is_image(part: dict[str, Any]) -> bool:
    return part.get("type") == "inline_data" and (part.get("mimetype") or "").startswith(
        "image/"
    )


def _openai_content(parts: list[dict[str, Any]], with_images: bool) -> str | list:
    """Plain text, or OpenAI content parts when images can be forwarded."""
    if not (with_images and any(_is_image(part) for part in parts)):
        return "\n".join(filter(None, (_part_text(part) for part in parts)))
    content = []
    for part in parts:
        if _is_image(part):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{part['mimetype']};base64,{part['data']}"},
                }
            )
        elif text := _part_text(part):
            content.append({"type": "text", "text": text})
    return content


def _anthropic_content(parts: list[dict[str, Any]], with_images: bool) -> str | list:
    """Plain text, or Anthropic content blocks when images/PDFs can be forwarded."""
    def forwardable(part):
        mimetype = part.get("mimetype") or ""
        return part.get("type") == "inline_data" and (
            mimetype in ANTHROPIC_IMAGE_TYPES or mimetype == "application/pdf"
        )

    if not (with_images and any(forwardable(part) for part in parts)):
        return "\n".join(filter(None, (_part_text(part) for part in parts)))
    content = []
    for part in parts:
        if forwardable(part):
            content.append(
                {
                    "type": "document" if part["mimetype"] == "application/pdf" else "image",
                    "source": {
                        "type": "base64",
                        "media_type": part["mimetype"],
                        "data": part["data"],
                    },
                }
            )
        elif text := _part_text(part):
            content.append({"type": "text", "text": text})
    return content


def _odoo_messages_to_openai(
    messages: list[dict[str, Any]], instructions: str | None, with_images: bool = False
) -> list[dict[str, Any]]:
    openai_messages: list[dict[str, Any]] = []
    if instructions:
        openai_messages.append({"role": "system", "content": instructions})
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content") or []
        # Only user messages may carry images in the OpenAI format.
        openai_messages.append(
            {"role": role, "content": _openai_content(content, with_images and role == "user")}
        )
    return openai_messages


def _odoo_tools_to_openai(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    openai_tools = []
    for tool in tools or []:
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("instructions") or "",
                    "parameters": tool.get("schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return openai_tools


def _tool_call_args(arguments: Any) -> Any:
    if isinstance(arguments, str):
        try:
            return json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {"_raw": arguments}
    return arguments or {}


def _openai_message_to_odoo(provider_response: dict[str, Any]) -> dict[str, Any]:
    choice = (provider_response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = []
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        content.append(
            {
                "type": "tool_call",
                "name": function.get("name"),
                "args": _tool_call_args(function.get("arguments")),
                "call_id": tool_call.get("id"),
                "provider_data": tool_call,
            }
        )
    if text := message.get("content"):
        content.append({"type": "text", "text": text})
    if not content:
        content.append({"type": "text", "text": ""})
    return {
        "role": "assistant",
        "content": content,
        "provider_metadata": {
            "model": provider_response.get("model"),
            "usage": provider_response.get("usage", {}),
        },
    }


def _completion_provider_payload(params: dict[str, Any]) -> dict[str, Any]:
    config = _config()
    provider_payload: dict[str, Any] = {
        "model": params.get("model") or config["model"],
        "messages": _odoo_messages_to_openai(
            params.get("messages") or [],
            params.get("instructions"),
            with_images=config.get("supports_images", False),
        ),
    }
    temperature = params.get("temperature", config.get("temperature"))
    if temperature is not None:
        provider_payload["temperature"] = temperature
    if tools := _odoo_tools_to_openai(params.get("tools")):
        provider_payload["tools"] = tools
        provider_payload["tool_choice"] = "auto"
    if schema := params.get("schema"):
        provider_payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "odoo_response", "schema": schema},
        }
    return provider_payload


def _anthropic_provider_payload(params: dict[str, Any]) -> dict[str, Any]:
    config = _config()
    system_parts = [params.get("instructions") or ""]
    messages = []
    for message in params.get("messages") or []:
        role = message.get("role")
        parts = message.get("content") or []
        if role == "system":
            system_parts.append(_anthropic_content(parts, with_images=False))
        elif role == "assistant":
            messages.append(
                {"role": "assistant", "content": _anthropic_content(parts, with_images=False)}
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": _anthropic_content(
                        parts, with_images=config.get("supports_images", False)
                    ),
                }
            )
    payload = {
        "model": params.get("model") or config["model"],
        "max_tokens": int(os.getenv("ODOO_AI_PROXY_MAX_TOKENS", "4096")),
        "messages": messages,
    }
    if system := "\n\n".join(filter(None, system_parts)):
        payload["system"] = system
    if tools := params.get("tools"):
        payload["tools"] = [
            {
                "name": tool["name"],
                "description": tool.get("instructions") or "",
                "input_schema": tool.get("schema") or {"type": "object", "properties": {}},
            }
            for tool in tools
        ]
    return payload


def _anthropic_message_to_odoo(provider_response: dict[str, Any]) -> dict[str, Any]:
    content = []
    for block in provider_response.get("content") or []:
        if block.get("type") == "tool_use":
            content.append(
                {
                    "type": "tool_call",
                    "name": block.get("name"),
                    "args": block.get("input") or {},
                    "call_id": block.get("id"),
                    "provider_data": block,
                }
            )
        elif block.get("type") == "text":
            content.append({"type": "text", "text": block.get("text") or ""})
    if not content:
        content.append({"type": "text", "text": ""})
    usage = provider_response.get("usage") or {}
    return {
        "role": "assistant",
        "content": content,
        "provider_metadata": {
            "model": provider_response.get("model"),
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
        },
    }


def _get_completion(params: dict[str, Any]) -> dict[str, Any]:
    config = _config()
    if config["kind"] == "claude":
        response = _post_anthropic(_anthropic_provider_payload(params))
        return {"result": _anthropic_message_to_odoo(response)}
    response = _post_provider("/chat/completions", _completion_provider_payload(params))
    return {"result": _openai_message_to_odoo(response)}


def _odoo_hmac(secret: str, message: tuple[Any, ...]) -> str:
    return hmac.new(
        secret.encode(),
        repr(("odoo_ai-webhook", message)).encode(),
        hashlib.sha256,
    ).hexdigest()


def _post_callback(params: dict[str, Any], llm_result: Any, llm_error: Any) -> None:
    webhook_url = params["webhook_url"]
    request_uuid = params["request_uuid"]
    body = {
        "request_uuid": request_uuid,
        "llm_result": llm_result,
        "llm_error": llm_error,
        "signature": _odoo_hmac(
            params["webhook_secret"],
            (request_uuid, llm_result, llm_error),
        ),
    }
    headers = {"Content-Type": "application/json"}
    if dbname := params.get("webhook_dbname"):
        headers["X-Odoo-Database"] = dbname
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    _log_event("callback_request", {"url": webhook_url, "headers": headers, "body": body})
    try:
        with urllib.request.urlopen(request, timeout=_config()["timeout"]) as response:
            response_body = response.read().decode()
            _log_event(
                "callback_response",
                {"url": webhook_url, "status": response.status, "body": response_body},
            )
    except urllib.error.HTTPError as e:
        response_body = e.read().decode(errors="replace")
        _log_event(
            "callback_response",
            {"url": webhook_url, "status": e.code, "body": response_body},
        )
        raise


def _run_async_completion(params: dict[str, Any]) -> None:
    try:
        llm_result = _get_completion(params)
        llm_error = False
    except Exception as e:  # noqa: BLE001
        _logger.exception("Provider async completion request failed")
        llm_result = False
        llm_error = {"code": "provider_request_failed", "message": str(e)}
    try:
        _post_callback(params, llm_result, llm_error)
    except Exception:  # noqa: BLE001
        _logger.exception("Odoo AI callback failed")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/odoo_ai/1/get_completions_sync")
async def get_completions_sync(request: Request) -> JSONResponse:
    rpc_id, params, _payload = await _jsonrpc_payload(request)
    try:
        result = _get_completion(params)
    except Exception as e:  # noqa: BLE001
        _logger.exception("Provider completion request failed")
        return _jsonrpc_error(rpc_id, 200, "provider_request_failed", {"message": str(e)})
    return _jsonrpc_result(rpc_id, result)


@app.post("/api/odoo_ai/1/get_completions")
async def get_completions(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    rpc_id, params, _payload = await _jsonrpc_payload(request)
    params.setdefault("request_uuid", uuid.uuid4().hex)
    missing = [
        key for key in ("webhook_url", "webhook_secret")
        if not params.get(key)
    ]
    if missing:
        return _jsonrpc_error(
            rpc_id,
            200,
            "missing_async_callback_configuration",
            {"missing": missing},
        )
    background_tasks.add_task(_run_async_completion, params)
    return _jsonrpc_result(rpc_id, None)


def _gemini_api_key() -> str:
    if api_key := os.getenv("ODOO_AI_PROXY_GEMINI_API_KEY"):
        return api_key
    dbname = os.getenv("ODOO_AI_PROXY_ODOO_DB", "plane_20")
    with psycopg2.connect(dbname=dbname) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select api_key from ai_connection
            where kind = 'gemini' and active and coalesce(api_key, '') <> ''
            order by id
            limit 1
            """
        )
        row = cursor.fetchone()
    if not row:
        raise RuntimeError("Embeddings need an active Gemini AI connection with an API key.")
    return row[0]


def _post_gemini_embeddings(requests: list[dict[str, Any]]) -> list[list[float]]:
    request = urllib.request.Request(
        f"{GEMINI_API_URL}/models/{EMBEDDING_MODEL}:batchEmbedContents",
        data=json.dumps({"requests": requests}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": _gemini_api_key()},
        method="POST",
    )
    # Log sizes only: the inputs are document chunks and the outputs long vectors.
    _log_event("provider_request", {"path": "embeddings", "count": len(requests)})
    try:
        with urllib.request.urlopen(request, timeout=_config()["timeout"]) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        details = e.read().decode(errors="replace")
        _log_event("provider_response", {"path": "embeddings", "status": e.code, "body": details})
        raise RuntimeError(f"Gemini returned HTTP {e.code}: {details}") from e
    _log_event("provider_response", {"path": "embeddings", "status": response.status})
    return [embedding["values"] for embedding in result.get("embeddings", [])]


def _embedding_request(item: Any, task_type: str) -> dict[str, Any]:
    text = item.get("content", "") if isinstance(item, dict) else str(item)
    request = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {"parts": [{"text": text or " "}]},
        "taskType": task_type,
        "outputDimensionality": EMBEDDING_DIMENSIONS,
    }
    # Gemini only accepts a title for document embeddings.
    title = item.get("title") if isinstance(item, dict) else None
    if title and task_type == "RETRIEVAL_DOCUMENT":
        request["title"] = title
    return request


@app.post("/api/odoo_ai/1/get_supported_embedding_models")
async def get_supported_embedding_models(request: Request) -> JSONResponse:
    rpc_id, _params, _payload = await _jsonrpc_payload(request)
    return _jsonrpc_result(rpc_id, [EMBEDDING_MODEL])


@app.post("/api/odoo_ai/1/get_default_embedding_model")
async def get_default_embedding_model(request: Request) -> JSONResponse:
    rpc_id, _params, _payload = await _jsonrpc_payload(request)
    return _jsonrpc_result(rpc_id, EMBEDDING_MODEL)


@app.post("/api/odoo_ai/1/get_embeddings")
async def get_embeddings(request: Request) -> JSONResponse:
    rpc_id, params, _payload = await _jsonrpc_payload(request)
    task_type = EMBEDDING_TASK_TYPES.get(params.get("mode"), "SEMANTIC_SIMILARITY")
    requests = [_embedding_request(item, task_type) for item in params.get("input") or []]
    embeddings: list[list[float]] = []
    try:
        for start in range(0, len(requests), EMBEDDING_BATCH_SIZE):
            embeddings += _post_gemini_embeddings(
                requests[start : start + EMBEDDING_BATCH_SIZE]
            )
    except Exception as e:  # noqa: BLE001
        _logger.exception("Gemini embedding request failed")
        return _jsonrpc_error(rpc_id, 200, "provider_request_failed", {"message": str(e)})
    return _jsonrpc_result(
        rpc_id,
        {"embeddings": embeddings},
        log_result={"embeddings": f"{len(embeddings)} x {EMBEDDING_DIMENSIONS}"},
    )
