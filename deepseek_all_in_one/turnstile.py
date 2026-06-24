"""Turnstile adapter for ds-piracy-all-in-one.

Thin wrapper around the standalone turnstile-solver plugin.  Converts the
project's Config / SiteConfig to the plugin's format and delegates all logic.
"""

from __future__ import annotations

import logging
from typing import Any

from turnstile_solver import TurnstileConfig, TurnstileError as _TurnstileError
from turnstile_solver import TurnstileSolver as _BaseSolver

from .config import Config, SiteConfig

logger = logging.getLogger(__name__)

TurnstileError = _TurnstileError


class TurnstileSolver:
    """Adapter that bridges project Config → turnstile-solver plugin."""

    def __init__(self, config: Config):
        tc = config.turnstile
        self._enabled = tc.enabled
        self._base = _BaseSolver(
            TurnstileConfig(
                enabled=tc.enabled,
                api_url=tc.api_url,
                api_key=tc.api_key,
                sitekey=tc.sitekey,
                action=tc.action,
                timeout_seconds=tc.timeout_seconds,
                cookie_ttl_seconds=tc.cookie_ttl_seconds,
                retries=tc.retries,
                retry_backoff_seconds=tc.retry_backoff_seconds,
                proxy_url=config.proxy_url,
                user_agent=config.user_agent,
            )
        )

    def invalidate(self, site: SiteConfig) -> None:
        self._base.invalidate(site.code)

    async def apply_valid_cookies(self, client: Any, site: SiteConfig) -> None:
        if not self._enabled:
            return
        await self._base.apply_valid_cookies(
            client=client,
            base_url=site.base_url,
            ajax_url=site.ajax_url,
            site_code=site.code,
            verify_action=site.verify_action,
            sitekey=site.sitekey,
            language=site.language,
        )

    async def refresh(self, client: Any, site: SiteConfig) -> None:
        if not self._enabled:
            return
        await self._base.refresh(
            client=client,
            base_url=site.base_url,
            ajax_url=site.ajax_url,
            site_code=site.code,
            verify_action=site.verify_action,
            sitekey=site.sitekey,
            language=site.language,
        )
