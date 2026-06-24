# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] — 2026-06-24

### Added

- **Vercel / Docker 部署**: 保留旧仓库的 `vercel.json`, `api/index.py`, `Dockerfile`, `docker-compose.yml`，适配新模块化结构。
- **部署文档**: 合并旧仓库的完整部署教程（Vercel 一键部署、Docker、直接运行）。
- **Tool Calling 后处理**: 新增 `try_parse_tool_calls()` 函数，可从模型回复中自动解析 OpenAI 兼容的 `tool_calls` JSON（支持纯 JSON、\`\`\`json 代码块、\`\`\` 代码块三种格式），非流式和流式端点均已集成。
- **增强的 tools prompt**: `_tools_prompt()` 现在输出详细的参数 schema（类型、required 标记），并与 `build_prompt()` 深度集成。
- **空响应检测**: 非流式和流式端点均检测上游返回空流的情况（限流/故障），返回结构化错误消息，支持客户端自动重试。
- **独立 Turnstile 插件**: 将 Cloudflare Turnstile 求解器提取为 `plugins/turnstile-solver` 独立包，可被其他项目直接引用 (`pip install ./plugins/turnstile-solver`)，主项目通过薄包装器适配。
- **lrnev 项目治理**: 初始化 `.lrnev/` 工作区，补全 `PROJECT.md` 和 `ARCHITECTURE.md`。
- **测试**: 新增 4 个测试（plain JSON tool call、markdown JSON block、no tool call、tools prompt），总测试数 10→14。

### Changed

- **Prompt 格式改进**: `build_prompt()` 使用 `[System]`/`[User]`/`[Assistant]`/`[Tool Result]` 格式，更显式地区分角色和对话轮次，与上游 WordPress AIPKit 预期格式一致。
- **API 响应增强**: `_complete_chat()` 非流式响应现在包含 `tool_calls` 字段；`_stream_chat()` 流式响应在检测到 tool_calls 时追加包含 tool_calls 的修正 chunk。
- **Turnstile 重构**: `deepseek_all_in_one/turnstile.py` 重构为薄包装器，实际逻辑委托给 `turnstile-solver` 插件。
- **pyproject.toml**: 添加 `turnstile-solver` 本地依赖 + `[tool.uv.sources]`。

### Dependency changes

- 新增: `turnstile-solver==1.0.0` (local plugin, depends on `httpx>=0.28.0`)
- 移除: 主项目不再直接依赖 httpx（现由 turnstile-solver 依赖传递）

## [0.1.0] — initial

- 6 模型 OpenAI 兼容代理 (deepseek.de/es/fr)
- Chat Completions + Responses 端点
- SSE 流式输出
- Cloudflare Turnstile 自动求解
- CURL_CFFI 浏览器指纹模拟
- 失败自动重试 + session 刷新
- TOML 配置文件驱动
