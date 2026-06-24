# Turnstile Solver Plugin

Standalone Cloudflare Turnstile token solver with verified cookie caching.

## What

Solves Cloudflare Turnstile challenges via a third-party API
(`https://cfs.071129.xyz/turnstile/sync`), redeems the token through a
WordPress AIPKit `deepseek_ts_verify` ajax endpoint, and caches verified
cookies per site with a configurable TTL.

## Install

```bash
pip install ./plugins/turnstile-solver
```

Or with uv:

```bash
uv add ./plugins/turnstile-solver
```

## Usage

```python
import asyncio
from turnstile_solver import TurnstileSolver, TurnstileConfig

config = TurnstileConfig(
    api_key="your-api-key",
    sitekey="0x4AAAAAADlLZ3ljqZP6cQwq",
)

async def main():
    solver = TurnstileSolver(config)

    # Define a site
    site = solver.site(
        code="de",
        base_url="https://deepseek.de",
        ajax_url="https://deepseek.de/wp-admin/admin-ajax.php",
    )

    # Get a client with verified cookies applied
    import httpx
    async with httpx.AsyncClient() as client:
        await solver.apply_valid_cookies(client, site)
        # Now use `client` to make requests — Turnstile cookies are set

asyncio.run(main())
```

## API

### `TurnstileSolver`

- `apply_valid_cookies(client, site)` — ensure `client` has fresh verified cookies
- `refresh(client, site)` — force a new Turnstile solve + verify cycle
- `invalidate(site)` — drop cached cookies for a site

### `TurnstileConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable/disable solver |
| `api_url` | `str` | `https://cfs.071129.xyz/turnstile/sync` | Turnstile API endpoint |
| `api_key` | `str` | (required) | API key for the solver |
| `sitekey` | `str` | `"0x4AAAAAADlLZ3ljqZP6cQwq"` | Cloudflare sitekey |
| `action` | `str` | `"chat"` | Turnstile action |
| `timeout_seconds` | `int` | `90` | Solver timeout |
| `cookie_ttl_seconds` | `int` | `10800` (3h) | Cookie cache duration |
| `retries` | `int` | `5` | Retry count |
| `retry_backoff_seconds` | `float` | `1.5` | Backoff multiplier |
| `proxy_url` | `str | None` | `None` | HTTP proxy for API calls |
| `user_agent` | `str` | Chrome | User-Agent header |

## License

MIT
