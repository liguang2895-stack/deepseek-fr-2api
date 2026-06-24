from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from .client import DeepSeekClient, UpstreamError
from .config import Config
from .openai_models import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceDelta,
    ChoiceMessage,
    ModelInfo,
    ResponsesRequest,
    StreamChoice,
    Usage,
    build_prompt,
    responses_to_messages,
    try_parse_tool_calls,
)

logger = logging.getLogger(__name__)


def create_app(config: Config) -> FastAPI:
    client = DeepSeekClient(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("server starting host=%s port=%s models=%s", config.host, config.port, len(config.models))
        yield
        await client.close()
        logger.info("server stopped")

    app = FastAPI(
        title="DeepSeek all-in-one OpenAI proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    auth = Depends(_auth_dependency(config))

    @app.get("/")
    async def root():
        return {"status": "ok", "service": "deepseek-all-in-one"}

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "models": len(config.models),
            "sites": sorted(config.sites),
            "turnstile": config.turnstile.enabled,
        }

    @app.get("/v1/models")
    async def list_models(_=auth):
        now = int(time.time())
        return {
            "object": "list",
            "data": [
                ModelInfo(id=model.id, created=now, owned_by=f"deepseek-{model.site}").model_dump()
                for model in config.models.values()
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(body: ChatCompletionRequest, _=auth):
        if body.model not in config.models:
            raise HTTPException(status_code=404, detail=f"model not found: {body.model}")
        if not body.messages:
            raise HTTPException(status_code=400, detail="messages is required")
        prompt = build_prompt(body.messages, body.tools, body.tool_choice)
        if body.stream:
            return StreamingResponse(
                _stream_chat(client, config, body.model, prompt),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return await _complete_chat(client, config, body.model, prompt)

    @app.post("/v1/responses")
    async def responses(body: ResponsesRequest, _=auth):
        messages = responses_to_messages(body)
        prompt = build_prompt(messages)
        if body.model not in config.models:
            raise HTTPException(status_code=404, detail=f"model not found: {body.model}")
        if body.stream:
            return StreamingResponse(
                _stream_response(client, config, body.model, prompt),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        chat = await _complete_chat(client, config, body.model, prompt)
        payload = json.loads(chat.body)
        text = payload["choices"][0]["message"]["content"]
        response_id = "resp_" + uuid.uuid4().hex[:16]
        return JSONResponse(
            {
                "id": response_id,
                "object": "response",
                "created_at": payload["created"],
                "status": "completed",
                "model": body.model,
                "output": [
                    {
                        "id": "msg_" + uuid.uuid4().hex[:16],
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": text, "annotations": []}],
                    }
                ],
                "output_text": text,
                "usage": payload.get("usage", {}),
            }
        )

    return app


def _auth_dependency(config: Config):
    async def verify(authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)):
        if not config.api_keys:
            return None
        token = x_api_key
        if authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() == "bearer":
                token = value
        if token not in config.api_keys:
            raise HTTPException(status_code=401, detail="unauthorized")
        return None

    return verify


async def _complete_chat(client: DeepSeekClient, config: Config, model_id: str, prompt: str) -> JSONResponse:
    text = ""
    model = config.models[model_id]
    try:
        async for kind, value in client.chat(model, prompt):
            if kind == "delta" and value:
                text += value
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 空响应检测：上游偶发限流/故障会返回空流
    if not text.strip():
        raise HTTPException(
            status_code=502,
            detail=(
                "upstream returned empty response — "
                "the server may be rate-limiting, overloaded, or the "
                "session/nonce expired. Retry in a few seconds."
            ),
        )

    # 尝试解析 tool_calls
    remaining, tool_calls = try_parse_tool_calls(text)
    message = ChoiceMessage(
        content=remaining or "",
        tool_calls=tool_calls,
    )
    created = int(time.time())
    response = ChatCompletionResponse(
        id="chatcmpl-" + uuid.uuid4().hex[:16],
        created=created,
        model=model_id,
        choices=[Choice(message=message)],
        usage=_usage(prompt, text),
    )
    return JSONResponse(response.model_dump(exclude_none=True))


async def _stream_chat(client: DeepSeekClient, config: Config, model_id: str, prompt: str) -> AsyncIterator[str]:
    completion_id = "chatcmpl-" + uuid.uuid4().hex[:16]
    created = int(time.time())
    model = config.models[model_id]
    all_chunks: list[dict[str, Any]] = []
    full_text = ""

    yield _sse(ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model_id,
        choices=[StreamChoice(delta=ChoiceDelta(role="assistant"))],
    ).model_dump(exclude_none=True))
    try:
        async for kind, value in client.chat(model, prompt):
            if kind == "delta" and value:
                full_text += value
                chunk = ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=model_id,
                    choices=[StreamChoice(delta=ChoiceDelta(content=value))],
                ).model_dump(exclude_none=True)
                all_chunks.append(chunk)
                yield _sse(chunk)
    except Exception as exc:
        logger.warning("stream error model=%s error=%s", model_id, exc)
        yield _sse({"error": {"message": str(exc), "type": "upstream_error"}})
        yield "data: [DONE]\n\n"
        return

    # 空响应检测
    if not full_text.strip():
        error_payload = {
            "error": {
                "message": (
                    "upstream returned empty response — "
                    "the server may be rate-limiting, overloaded, or the "
                    "session/nonce expired. Retry in a few seconds."
                ),
                "type": "upstream_empty_response",
            }
        }
        yield _sse(error_payload)
        yield "data: [DONE]\n\n"
        return

    # 后处理：检测 tool_calls JSON
    remaining, tool_calls = try_parse_tool_calls(full_text)
    if tool_calls and all_chunks:
        # 追加包含 tool_calls 的修正 chunk
        fix_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_id,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": remaining,
                    "tool_calls": tool_calls,
                },
                "finish_reason": "stop",
            }],
        }
        yield _sse(fix_chunk)
    else:
        yield _sse(ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model_id,
            choices=[StreamChoice(delta=ChoiceDelta(), finish_reason="stop")],
        ).model_dump(exclude_none=True))
    yield "data: [DONE]\n\n"


async def _stream_response(client: DeepSeekClient, config: Config, model_id: str, prompt: str) -> AsyncIterator[str]:
    response_id = "resp_" + uuid.uuid4().hex[:16]
    yield _sse({"type": "response.created", "response": {"id": response_id, "model": model_id, "status": "in_progress"}})
    async for chunk in _stream_chat(client, config, model_id, prompt):
        if chunk == "data: [DONE]\n\n":
            break
        raw = chunk.removeprefix("data: ").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        choices = data.get("choices") or []
        if choices:
            delta = choices[0].get("delta", {}).get("content")
            if delta:
                yield _sse({"type": "response.output_text.delta", "delta": delta})
    yield _sse({"type": "response.completed", "response": {"id": response_id, "model": model_id, "status": "completed"}})
    yield "data: [DONE]\n\n"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _usage(prompt: str, text: str) -> Usage:
    prompt_tokens = max(1, len(prompt) // 4) if prompt else 0
    completion_tokens = max(1, len(text) // 4) if text else 0
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )

