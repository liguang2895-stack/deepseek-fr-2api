---
title: 'ds-piracy-all-in-one Architecture'
created: '2026-06-24'
---

# ds-piracy-all-in-one 架构

## L0 摘要

FastAPI + uvicorn HTTP 代理服务，curl_cffi 模拟 Chrome 发起上游请求，httpx 调用 Turnstile 求解器，pydantic 做 OpenAI 模型校验与序列化。

## L1 概览

### 技术栈

- **Python 3.13+**，包管理器 uv
- **Web 框架**: FastAPI 0.137+ + uvicorn 0.49+
- **HTTP 客户端**: curl-cffi 0.15+ (上游站点, 模拟 Chrome120), httpx 0.28+ (Turnstile)
- **数据建模**: pydantic 2.12+
- **配置**: TOML (tomllib 标准库)
- **测试**: pytest 9.0+ + pytest-asyncio

### 主要模块

| 模块 | 职责 |
|------|------|
| `main.py` | 入口，argparse 解析参数，启动 uvicorn |
| `deepseek_all_in_one/config.py` | TOML 配置加载、dataclass 定义、默认站点/模型 |
| `deepseek_all_in_one/api.py` | FastAPI 路由、auth 依赖、SSE 流式输出 |
| `deepseek_all_in_one/client.py` | 上游对话客户端：nonce 抓取、SSE 读、错误分类、重试 |
| `deepseek_all_in_one/turnstile.py` | Turnstile token 求解、cookie 缓存/刷新 |
| `deepseek_all_in_one/openai_models.py` | OpenAI API 请求/响应 Pydantic 模型、prompt 拼接 |
| `deepseek_all_in_one/logging.py` | 控制台彩色日志 |

### 数据流

```
下游客户端 (OpenAI SDK)
    │ POST /v1/chat/completions  (Bearer auth)
    ▼
FastAPI (api.py)
    │ 鉴权 → 模型路由 → 拼接 prompt
    ▼
DeepSeekClient (client.py)
    │ turnstile.apply_valid_cookies()
    │ _get_chat_config() → 抓页面 nonce
    │ POST cache_sse → GET chat_stream (SSE)
    ▼
deepseek.de/es/fr (WordPress + AIPKit)
```

## L2 详情

### 目录结构

```
.
├── main.py                   # 启动入口
├── config.toml               # 运行时配置 (敏感: API keys, turnstile key)
├── pyproject.toml            # 项目元数据 + 依赖声明
├── uv.lock                   # 锁定的依赖版本
├── .python-version            # Python 3.13
├── deepseek_all_in_one/      # 核心包
│   ├── __init__.py
│   ├── config.py             # 配置加载与 dataclass
│   ├── api.py                # FastAPI 路由与 SSE
│   ├── client.py             # 上游对话客户端
│   ├── turnstile.py          # Turnstile 求解
│   ├── openai_models.py      # OpenAI 模型定义
│   └── logging.py            # 日志格式
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_client_errors.py
│   ├── test_config.py
│   ├── test_openai_models.py
│   └── test_turnstile_concurrency.py
└── .lrnev/                   # 项目治理
```

### 关键设计约束

- 上游对话使用 curl_cffi 而非 httpx，因为站点有 TLS 指纹检测
- SSE 读取需要手动解析（curl_cffi 不支持 httpx 的 `aiter_sse()`）
- cookie 缓存必须在 Turnstile 验证通过后按 domain 设置
- 并发刷新使用 asyncio.Lock 防止重复请求 Turnstile

### 外部依赖

- **Turnstile 求解服务**: `https://cfs.071129.xyz/turnstile/sync`
- **上游站点**: deepseek.de, deepseek.es, deepseek.fr (WordPress + AIPKit)
- 可选 SOCKS5 代理 (socksio)
