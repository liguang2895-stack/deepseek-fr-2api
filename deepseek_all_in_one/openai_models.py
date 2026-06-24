from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = ""
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    user: str | None = None


class ResponsesInputMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]]


class ResponsesRequest(BaseModel):
    model: str
    input: str | list[ResponsesInputMessage | dict[str, Any]]
    stream: bool = False
    instructions: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str | None = ""
    tool_calls: list[dict[str, Any]] | None = None


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)


class ChoiceDelta(BaseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: ChoiceDelta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]


class ModelInfo(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "deepseek"


def message_content_to_text(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if item.get("type") in {"text", "input_text", "output_text"}:
            parts.append(str(item.get("text", "")))
    return "\n".join(p for p in parts if p)


def build_prompt(messages: list[ChatMessage], tools: list[dict[str, Any]] | None = None, tool_choice: Any = None) -> str:
    """将 messages 列表拼接为单个 prompt 字符串。"""
    parts: list[str] = []
    for msg in messages:
        content = message_content_to_text(msg.content)
        if msg.role == "system":
            parts.append(f"[System]\n{content}")
        elif msg.role == "user":
            parts.append(f"[User]\n{content}")
        elif msg.role == "assistant":
            if msg.tool_calls:
                import json as _json
                tc_text = _json.dumps(msg.tool_calls, ensure_ascii=False)
                parts.append(f"[Assistant]\n{content}\n[Tool Calls]\n{tc_text}")
            else:
                parts.append(f"[Assistant]\n{content}")
        elif msg.role == "tool":
            parts.append(f"[Tool Result (id={msg.tool_call_id})]\n{content}")
        elif msg.role == "developer":
            parts.append(f"[Developer]\n{content}")
        else:
            parts.append(f"[{msg.role.title()}]\n{content}")
    if tools:
        parts.append(_tools_prompt(tools, tool_choice))
    return "\n\n".join(parts)


def responses_to_messages(req: ResponsesRequest) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    if req.instructions:
        messages.append(ChatMessage(role="system", content=req.instructions))
    if isinstance(req.input, str):
        messages.append(ChatMessage(role="user", content=req.input))
        return messages
    for item in req.input:
        if isinstance(item, dict):
            messages.append(ChatMessage(role=item.get("role", "user"), content=item.get("content", "")))
        else:
            messages.append(ChatMessage(role=item.role, content=item.content))
    return messages


def _tools_prompt(tools: list[dict[str, Any]], tool_choice: Any) -> str:
    """将 tools 描述转换为 prompt 文本，含参数 schema。"""
    lines = [
        "",
        "=== TOOL INSTRUCTIONS ===",
        (
            "You have access to the following tools. When you need to use a tool, "
            "you MUST output ONLY a single JSON object in this exact format "
            "(no markdown, no explanations, no extra text before or after the JSON):"
        ),
        "",
        '{"tool_calls": [{"id": "call_xxx", "type": "function", "function": {"name": "tool_name", "arguments": "{\\"param\\": \\"value\\"}"}}]}',
        "",
        "Available tools:",
    ]
    for idx, tool in enumerate(tools):
        fn = tool.get("function", {})
        params_desc = ""
        if fn.get("parameters", {}).get("properties"):
            props = fn["parameters"]["properties"]
            required = fn["parameters"].get("required", [])
            param_lines = []
            for pname, pschema in props.items():
                ptype = pschema.get("type", "any")
                req_mark = " (required)" if pname in required else ""
                param_lines.append(f"    - {pname}: {ptype}{req_mark}")
            params_desc = "\n" + "\n".join(param_lines)
        lines.append(f"{idx + 1}. {fn.get('name', '')}: {fn.get('description', 'No description')}{params_desc}")
    if isinstance(tool_choice, dict):
        name = tool_choice.get("function", {}).get("name")
        if name:
            lines.append("")
            lines.append(
                f"IMPORTANT: You MUST use the tool '{name}' for this request. "
                "Output ONLY the JSON object above, nothing else."
            )
    else:
        lines.append("")
        lines.append(
            "If no tool is needed, reply normally. "
            "If a tool is needed, output ONLY the JSON object above."
        )
    lines.append("=== END TOOL INSTRUCTIONS ===")
    lines.append("")
    return "\n".join(lines)


def try_parse_tool_calls(text: str) -> tuple[str, list[dict[str, Any]] | None]:
    """尝试从模型回复文本中提取 OpenAI 兼容的 tool_calls。

    返回 (剩余文本, tool_calls | None)。
    """
    import json as _json
    import uuid as _uuid

    text = text.strip()
    candidates: list[str] = []
    if text.startswith("{"):
        candidates.append(text)
    if "```json" in text:
        parts = text.split("```json")
        for part in parts[1:]:
            code = part.split("```", 1)[0].strip()
            if code.startswith("{"):
                candidates.append(code)
    if "```" in text and "```json" not in text:
        parts = text.split("```")
        for part in parts[1:]:
            code = part.split("```", 1)[0].strip()
            if code.startswith("{"):
                candidates.append(code)

    for candidate in candidates:
        try:
            parsed = _json.loads(candidate)
            if "tool_calls" in parsed and isinstance(parsed["tool_calls"], list):
                tool_calls = []
                for tc in parsed["tool_calls"]:
                    tc_id = tc.get("id") or f"call_{_uuid.uuid4().hex[:8]}"
                    tc_type = tc.get("type") or "function"
                    func = tc.get("function", {})
                    arguments = func.get("arguments", "{}")
                    if not isinstance(arguments, str):
                        arguments = _json.dumps(arguments, ensure_ascii=False)
                    tool_calls.append({
                        "id": tc_id,
                        "type": tc_type,
                        "function": {
                            "name": func.get("name", ""),
                            "arguments": arguments,
                        },
                    })
                remaining = text.replace(candidate, "").strip()
                remaining = remaining.replace("```json", "").replace("```", "").strip()
                return remaining, tool_calls
        except (_json.JSONDecodeError, KeyError, TypeError):
            continue

    return text, None

