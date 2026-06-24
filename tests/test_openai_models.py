from deepseek_all_in_one.openai_models import (
    ChatMessage,
    ResponsesRequest,
    build_prompt,
    responses_to_messages,
    try_parse_tool_calls,
)


def test_build_prompt_keeps_roles_and_text_parts():
    prompt = build_prompt([
        ChatMessage(role="system", content="Rules"),
        ChatMessage(role="user", content=[{"type": "text", "text": "Hello"}]),
    ])
    assert "[System]" in prompt
    assert "Rules" in prompt
    assert "[User]" in prompt
    assert "Hello" in prompt


def test_responses_request_to_messages():
    req = ResponsesRequest(model="deepseek-v4-flash-de", instructions="Be terse", input="Hi")
    messages = responses_to_messages(req)
    assert [m.role for m in messages] == ["system", "user"]


def test_try_parse_tool_calls_plain_json():
    """Plain JSON object with tool_calls is parsed correctly."""
    text = '{"tool_calls":[{"id":"call_001","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":\\"Beijing\\"}"}}]}'
    remaining, tool_calls = try_parse_tool_calls(text)
    assert remaining == ""
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"


def test_try_parse_tool_calls_markdown_json_block():
    """Tool call inside ```json block is extracted."""
    text = 'Sure, here you go:\n```json\n{"tool_calls":[{"id":"c1","type":"function","function":{"name":"search","arguments":"{\\"q\\":\\"hello\\"}"}}]}\n```\nDone.'
    remaining, tool_calls = try_parse_tool_calls(text)
    assert "Sure" in remaining
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "search"


def test_try_parse_tool_calls_no_tool_call():
    """Plain text returns None for tool_calls."""
    text = "The weather in Beijing is sunny."
    remaining, tool_calls = try_parse_tool_calls(text)
    assert remaining == text
    assert tool_calls is None


def test_build_prompt_with_tools():
    """build_prompt appends tool instructions when tools are supplied."""
    prompt = build_prompt(
        [ChatMessage(role="user", content="Hi")],
        tools=[{"function": {"name": "search", "description": "Search the web"}}],
    )
    assert "=== TOOL INSTRUCTIONS ===" in prompt
    assert "search" in prompt

