# DeepSeek de/es/fr All-in-One Proxy

OpenAI-compatible reverse proxy for the three WordPress/AIPKit sites:

- `deepseek.de`
- `deepseek.es`
- `deepseek.fr`

It exposes six model IDs:

- `deepseek-v4-flash-de`
- `deepseek-v4-pro-de`
- `deepseek-v4-flash-es`
- `deepseek-v4-pro-es`
- `deepseek-v4-flash-fr`
- `deepseek-v4-pro-fr`

## Run

```powershell
uv sync
uv run python main.py --config config.toml
```

OpenAI Chat Completions:

```powershell
curl http://127.0.0.1:8000/v1/chat/completions `
  -H "Authorization: Bearer sk-dsfr-local-change-me" `
  -H "Content-Type: application/json" `
  -d '{"model":"deepseek-v4-flash-es","messages":[{"role":"user","content":"Say hi"}],"stream":false}'
```

OpenAI Responses:

```powershell
curl http://127.0.0.1:8000/v1/responses `
  -H "Authorization: Bearer sk-dsfr-local-change-me" `
  -H "Content-Type: application/json" `
  -d '{"model":"deepseek-v4-pro-fr","input":"Bonjour"}'
```

## Config Notes

`config.toml` is the single source of truth:

- `[security].api_keys`: downstream client keys. Empty array disables auth.
- `[proxy].url`: request proxy for upstream sites and Turnstile solver.
- `[turnstile]`: Cloudflare Turnstile solver endpoint and shared sitekey.
- `[sites]`: per-domain base URL, ajax URL, language, and sitekey.
- `[models]`: public model ID to site/page/bot/post mapping.

The client first scrapes each model page for `data-config` and uses the live
`nonce`, `ajaxUrl`, `botId`, and `postId`. If the page shape changes, the
configured `bot_id` / `post_id` are used with the nonce endpoint as fallback.

## Runtime Behavior

- The Turnstile token is fetched from `https://cfs.071129.xyz/turnstile/sync`.
- The token is redeemed through each site's `deepseek_ts_verify` ajax action.
- Verified cookies are cached per site for `cookie_ttl_seconds`.
- Upstream failures trigger a session refresh and retry when `auto_refresh=true`.
- Console logs use `[time][level] message` and colored levels on TTY terminals.

## Compatibility

Implemented endpoints:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /health`

Streaming responses use SSE and finish with `data: [DONE]`.

## Tests

```powershell
uv run pytest
uv run python -m compileall deepseek_all_in_one main.py
```
