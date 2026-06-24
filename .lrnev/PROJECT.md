---
title: 'ds-piracy-all-in-one'
created: '2026-06-24'
---

# ds-piracy-all-in-one

## L0 摘要

OpenAI 兼容的反向代理，聚合 deepseek.de / deepseek.es / deepseek.fr 三个 WordPress/AIPKit 站点的 V4-Flash 和 V4-Pro 模型，提供统一的 `/v1/chat/completions` 和 `/v1/responses` API。

## L1 概览

### 项目目标

将深寻欧洲三站（德国、西班牙、法国）的 DeepSeek V4 模型包装成标准 OpenAI 兼容 API，支持流式和非流式调用，自动处理 Cloudflare Turnstile 验证和会话维持，让下游客户端无需关心 WordPress 站点细节。

### 核心用户

- 需要免费调用 DeepSeek V4 模型的开发者
- 已使用 OpenAI SDK 的应用（改 base_url 即可切换）

### 当前阶段

v0.1.0 — 核心链路可用：6 个模型、Chat Completions、Responses、SSE 流、Turnstile 自动刷新、重试。

## L2 详情

### 背景

deepseek.de/es/fr 三个 WordPress 站点通过 AIPKit 插件嵌入了 DeepSeek V4 聊天机器人，每个站点提供 V4-Flash 和 V4-Pro 两个模型。站点受 Cloudflare Turnstile 保护，需要解决验证后才能调用聊天 API。

### 范围

**包含**：
- OpenAI 兼容的 `/v1/models`、`/v1/chat/completions`、`/v1/responses`
- 流式 SSE 输出
- Cloudflare Turnstile 自动求解与 cookie 管理
- 失败自动重试与 session 刷新
- TOML 配置文件驱动的多站点/多模型映射

**不包含**：
- 用量计费系统
- 多租户
- Web UI / 管理后台
- embeddings / audio / images 端点

### 关键约束

- 上游站点使用 curl_cffi 模拟 Chrome 浏览器指纹
- 必须通过第三方 Turnstile 求解服务获取 token
- 配置文件是唯一配置源
