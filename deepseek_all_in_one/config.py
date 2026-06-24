from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class TurnstileConfig:
    enabled: bool = True
    api_url: str = "https://cfs.071129.xyz/turnstile/sync"
    api_key: str = "4SYIAfKiHo5472342799adsjbhhasvbjbesfuFu7EKfK9RPKpHk"
    sitekey: str = "0x4AAAAAADlLZ3ljqZP6cQwq"
    action: str = "chat"
    timeout_seconds: int = 90
    cookie_ttl_seconds: int = 3 * 3600
    retries: int = 3
    retry_backoff_seconds: float = 1.5


@dataclass(frozen=True)
class SiteConfig:
    code: str
    base_url: str
    ajax_url: str
    sitekey: str
    verify_action: str = "deepseek_ts_verify"
    language: str = "en-US,en;q=0.9"


@dataclass(frozen=True)
class ModelConfig:
    id: str
    site: str
    upstream_id: str
    label: str
    page_path: str
    bot_id: int | None = None
    post_id: int | None = None


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    api_keys: list[str] = field(default_factory=list)
    proxy_url: str | None = None
    timeout: float = 60.0
    stream_timeout: float = 300.0
    config_ttl_seconds: int = 60
    auto_refresh: bool = True
    refresh_retries: int = 2
    retry_backoff_seconds: float = 1.0
    user_agent: str = DEFAULT_USER_AGENT
    turnstile: TurnstileConfig = field(default_factory=TurnstileConfig)
    sites: dict[str, SiteConfig] = field(default_factory=dict)
    models: dict[str, ModelConfig] = field(default_factory=dict)


def _default_sites(sitekey: str) -> dict[str, SiteConfig]:
    return {
        "de": SiteConfig("de", "https://deepseek.de", "https://deepseek.de/wp-admin/admin-ajax.php", sitekey, language="de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"),
        "es": SiteConfig("es", "https://deepseek.es", "https://deepseek.es/wp-admin/admin-ajax.php", sitekey, language="es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7"),
        "fr": SiteConfig("fr", "https://deepseek.fr", "https://deepseek.fr/wp-admin/admin-ajax.php", sitekey, language="fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"),
    }


def _default_models() -> dict[str, ModelConfig]:
    data = [
        ("deepseek-v4-flash-de", "de", "deepseek-v4-flash", "DeepSeek V4-Flash DE", "/", 27487, 106),
        ("deepseek-v4-pro-de", "de", "deepseek-v4-pro", "DeepSeek V4-Pro DE", "/pro/", 27533, 27177),
        ("deepseek-v4-flash-es", "es", "deepseek-v4-flash", "DeepSeek V4-Flash ES", "/", 27623, 27568),
        ("deepseek-v4-pro-es", "es", "deepseek-v4-pro", "DeepSeek V4-Pro ES", "/pro/", 27637, 27615),
        ("deepseek-v4-flash-fr", "fr", "deepseek-v4-flash", "DeepSeek V4-Flash FR", "/", 27645, 27569),
        ("deepseek-v4-pro-fr", "fr", "deepseek-v4-pro", "DeepSeek V4-Pro FR", "/pro/", 27647, 27616),
    ]
    return {item[0]: ModelConfig(*item) for item in data}


def load_config(path: str | None = None) -> Config:
    config_path = Path(path or "config.toml")
    data = tomllib.loads(config_path.read_text("utf-8")) if config_path.exists() else {}

    turnstile_data = data.get("turnstile", {})
    turnstile = TurnstileConfig(
        enabled=bool(turnstile_data.get("enabled", True)),
        api_url=turnstile_data.get("api_url", TurnstileConfig.api_url),
        api_key=turnstile_data.get("api_key") or os.getenv("TURNSTILE_API_KEY") or TurnstileConfig.api_key,
        sitekey=turnstile_data.get("sitekey", TurnstileConfig.sitekey),
        action=turnstile_data.get("action", "chat"),
        timeout_seconds=int(turnstile_data.get("timeout_seconds", 90)),
        cookie_ttl_seconds=int(turnstile_data.get("cookie_ttl_seconds", 3 * 3600)),
        retries=int(turnstile_data.get("retries", 3)),
        retry_backoff_seconds=float(turnstile_data.get("retry_backoff_seconds", 1.5)),
    )

    server = data.get("server", {})
    security = data.get("security", {})
    upstream = data.get("upstream", {})
    proxy = data.get("proxy", {})
    cfg = Config(
        host=server.get("host", "0.0.0.0"),
        port=int(server.get("port", 8000)),
        log_level=server.get("log_level", "INFO"),
        api_keys=[str(v) for v in security.get("api_keys", []) if str(v)],
        proxy_url=proxy.get("url") or os.getenv("PROXY_URL") or None,
        timeout=float(upstream.get("timeout", 60.0)),
        stream_timeout=float(upstream.get("stream_timeout", 300.0)),
        config_ttl_seconds=int(upstream.get("config_ttl_seconds", 60)),
        auto_refresh=bool(upstream.get("auto_refresh", True)),
        refresh_retries=int(upstream.get("refresh_retries", 2)),
        retry_backoff_seconds=float(upstream.get("retry_backoff_seconds", 1.0)),
        user_agent=upstream.get("user_agent", DEFAULT_USER_AGENT),
        turnstile=turnstile,
    )

    cfg.sites = _default_sites(turnstile.sitekey)
    for code, raw in data.get("sites", {}).items():
        base = raw.get("base_url", cfg.sites[code].base_url if code in cfg.sites else "")
        cfg.sites[code] = SiteConfig(
            code=code,
            base_url=base.rstrip("/"),
            ajax_url=raw.get("ajax_url", f"{base.rstrip('/')}/wp-admin/admin-ajax.php"),
            sitekey=raw.get("sitekey", turnstile.sitekey),
            verify_action=raw.get("verify_action", "deepseek_ts_verify"),
            language=raw.get("language", "en-US,en;q=0.9"),
        )

    cfg.models = _default_models()
    for model_id, raw in data.get("models", {}).items():
        cfg.models[model_id] = ModelConfig(
            id=model_id,
            site=raw["site"],
            upstream_id=raw.get("upstream_id", model_id.rsplit("-", 1)[0]),
            label=raw.get("label", model_id),
            page_path=raw.get("page_path", "/"),
            bot_id=raw.get("bot_id"),
            post_id=raw.get("post_id"),
        )
    return cfg
