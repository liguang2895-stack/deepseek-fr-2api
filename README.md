# DeepSeek de/es/fr All-in-One Proxy

> 逆向 **deepseek.de / deepseek.es / deepseek.fr** 三个站点的 V4-Flash 与 V4-Pro 模型，提供 **OpenAI API 格式完全兼容** 的中转服务。支持三站点聚合、流式/非流式、Tool Calling、Turnstile 自动突破。

> ⚠️ 这些站点并非 DeepSeek 官方网站，请谨慎使用。

---

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/import?s=https://github.com/t479842598/deepseek-fr-2api)

---

## 目录

- [模型映射](#模型映射)
- [部署方式](#部署方式)
  - [方式一：Vercel 一键部署（推荐）](#方式一vercel-一键部署推荐)
  - [方式二：Docker 部署](#方式二docker-部署)
  - [方式三：直接运行](#方式三直接运行)
- [API 文档](#api-文档)
- [客户端接入](#客户端接入)
- [架构说明](#架构说明)
- [Turnstile 插件](#turnstile-插件)
- [常见问题](#常见问题)
- [免责声明](#免责声明)

---

## 模型映射

共 **6 个模型**，分布在三个欧洲站点：

| 模型 ID | 站点 | 对应模型 | bot_id | post_id |
|---------|------|---------|--------|---------|
| `deepseek-v4-flash-de` | deepseek.de | V4-Flash | 27487 | 106 |
| `deepseek-v4-pro-de` | deepseek.de | V4-Pro | 27533 | 27177 |
| `deepseek-v4-flash-es` | deepseek.es | V4-Flash | 27623 | 27568 |
| `deepseek-v4-pro-es` | deepseek.es | V4-Pro | 27637 | 27615 |
| `deepseek-v4-flash-fr` | deepseek.fr | V4-Flash | 27645 | 27569 |
| `deepseek-v4-pro-fr` | deepseek.fr | V4-Pro | 27647 | 27616 |

> 三个站点各自有独立配额，聚合后每日可用 token 翻 3 倍。

---

## 部署方式

### 方式一：Vercel 一键部署（推荐）

免费、无需服务器、自动 HTTPS、全球 CDN。**已锁定美国区域（iad1）** 以确保能正常访问上游站点。

#### 1. Fork / 克隆仓库

```bash
git clone https://github.com/t479842598/deepseek-fr-2api.git
cd deepseek-fr-2api
```

#### 2. 部署到 Vercel

**方法 A：Vercel CLI（推荐）**

```bash
npm i -g vercel
vercel login
vercel --prod
```

**方法 B：Vercel 网页端**

1. 打开 [vercel.com/new](https://vercel.com/new)
2. Import 你的 GitHub 仓库
3. Framework 选择 **Other**
4. Root Directory 留空，直接点 **Deploy**
5. 部署完成后在 Settings → Functions 里确认 Region 为 **Washington, D.C., USA (iad1)**

> `vercel.json` 已配置 `"regions": ["iad1"]`。上游站点只允许美国 IP 访问。

#### 3. 设置环境变量（可选）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PROXY_URL` | HTTP 代理地址 | — |
| `TURNSTILE_API_KEY` | Turnstile API Key | 内置默认值 |
| `API_KEYS` | 下游鉴权 key，逗号分隔 | —（不鉴权） |

#### 4. 使用

部署完成后你会得到 `https://your-project.vercel.app`：

```bash
curl https://your-project.vercel.app/health
# → {"status":"ok","models":6,"sites":["de","es","fr"]}
```

> **Vercel 注意：** Serverless 函数有 10 秒超时（Pro 版 60 秒）。流式响应可正常工作。

---

### 方式二：Docker 部署

适合有 VPS 的用户，无超时限制。

```bash
git clone https://github.com/t479842598/deepseek-fr-2api.git
cd deepseek-fr-2api
docker compose up -d --build
docker compose logs -f
```

服务默认监听 `127.0.0.1:9000` → 容器内 `8080`。

**自定义端口 / 代理：**

修改 `docker-compose.yml`：

```yaml
ports:
  - "0.0.0.0:8080:8080"
environment:
  - PORT=8080
  - HOST=0.0.0.0
  - PROXY_URL=http://your-proxy:7890
```

---

### 方式三：直接运行

```bash
# 前置：Python 3.13+、uv
git clone https://github.com/t479842598/deepseek-fr-2api.git
cd deepseek-fr-2api

# 安装依赖
uv sync

# 启动（默认端口 8000）
uv run python main.py --config config.toml

# 指定端口
uv run python main.py --host 0.0.0.0 --port 9000
```

---

## API 文档

### `GET /v1/models`

```json
{
  "object": "list",
  "data": [
    {"id": "deepseek-v4-flash-de", "object": "model", "owned_by": "deepseek-de"},
    {"id": "deepseek-v4-pro-de", "object": "model", "owned_by": "deepseek-de"},
    ...
  ]
}
```

### `POST /v1/chat/completions`

OpenAI 格式完全兼容。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | ✅ | 模型 ID |
| `messages` | array | ✅ | 消息列表，支持 system/user/assistant/tool |
| `stream` | boolean | — | `true` 开启 SSE 流式，默认 `false` |
| `tools` | array | — | 工具定义（prompt 注入模拟） |
| `tool_choice` | object | — | 强制指定工具 |

**非流式响应：**

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "deepseek-v4-flash-fr",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello!"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
}
```

**Tool Calling 响应：**

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "",
      "tool_calls": [{
        "id": "call_xxx",
        "type": "function",
        "function": {"name": "get_weather", "arguments": "{\"city\":\"Beijing\"}"}
      }]
    },
    "finish_reason": "stop"
  }]
}
```

**流式响应（SSE）：**

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

### `POST /v1/responses`

OpenAI Responses API 兼容端点（beta）：

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "Authorization: Bearer sk-dsfr-local-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-pro-fr","input":"Bonjour"}'
```

### `GET /health`

```json
{"status":"ok","models":6,"sites":["de","es","fr"],"turnstile":true}
```

---

## 客户端接入

### Python（OpenAI SDK）

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-any",
    base_url="https://your-project.vercel.app/v1"
)

# 非流式
response = client.chat.completions.create(
    model="deepseek-v4-flash-fr",
    messages=[{"role": "user", "content": "Hello!"}]
)

# 流式
for chunk in client.chat.completions.create(
    model="deepseek-v4-pro-de",
    messages=[{"role": "user", "content": "说个笑话"}],
    stream=True
):
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# Tool Calling
response = client.chat.completions.create(
    model="deepseek-v4-flash-es",
    messages=[{"role": "user", "content": "北京天气怎么样？"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            }
        }
    }]
)
```

### 接入各类 LLM 客户端

| 客户端 | 配置方式 |
|--------|---------|
| **Open WebUI** | Settings → Connections → OpenAI API → 填入 `https://你的域名/v1` |
| **LobeChat** | 添加 OpenAI 兼容服务商 |
| **ChatBox** | 设置 → OpenAI 兼容 |
| **One API / New API** | 渠道 → OpenAI 兼容 |
| **Cherry Studio** | 添加提供商 → OpenAI 兼容 |

---

## 架构说明

```
客户端 (任意)
    │  POST /v1/chat/completions
    ▼
本代理 (FastAPI)
    │  1. 鉴权 → 构建 prompt（含 tools/tool_choice）
    │  2. Turnstile 求解 + cookie 验证
    │  3. 抓取页面 data-config nonce
    │  4. POST aipkit_cache_sse_message  → cache_key
    │  5. GET  aipkit_frontend_chat_stream (SSE) → 增量文本
    │  6. 格式转换 → OpenAI chunk / completion
    │  7. 后处理 → try_parse_tool_calls + 空响应检测
    ▼
deepseek.de / .es / .fr  (WordPress + AIPKit)
```

**逆向核心端点：**

| # | 方法 | Action | 说明 |
|---|------|--------|------|
| 1 | POST | `aipkit_get_frontend_chat_nonce` | 获取会话 nonce |
| 2 | POST | `aipkit_cache_sse_message` | 缓存用户消息 |
| 3 | GET | `aipkit_frontend_chat_stream` | SSE 流式响应 |

---

## Turnstile 插件

Turnstile 求解器已提取为独立插件 `plugins/turnstile-solver`，可单独安装：

```bash
pip install ./plugins/turnstile-solver
```

```python
from turnstile_solver import TurnstileSolver, TurnstileConfig

cfg = TurnstileConfig(api_key="your-key")
solver = TurnstileSolver(cfg)
```

---

## 常见问题

### Q: 为什么必须部署在美国？
上游站点会检查 IP 地理位置，非美国 IP 会被拒绝。Vercel `vercel.json` 中 `"regions": ["iad1"]` 确保函数运行在美东。

### Q: Vercel 免费版够用吗？
够用。免费版每月 100GB 带宽、100 万次函数调用。但函数超时 10 秒，长回复可能被截断。建议升级 Pro（60 秒超时）或 Docker。

### Q: 支持 Tool Calling 吗？
**支持。** 本代理通过 prompt 注入 + `try_parse_tool_calls()` 后处理来模拟。如果模型回复包含 `{"tool_calls": [...]}` JSON，自动解析为 OpenAI 标准格式。

### Q: 需要 API Key 吗？
默认 `config.toml` 中配置了 `api_keys`。可以设为空数组 `[]` 关闭鉴权。

### Q: 支持多轮对话吗？
支持。传入完整 `messages` 历史即可。

### Q: "empty response" 是什么？
表示上游站点返回了空响应（限流/故障），代理已内置检测并返回结构化错误。等几秒重试即可。

---

## 免责声明

本项目仅供学习研究和本地开发调试使用。请遵守各站点服务条款。

---

## License

MIT
