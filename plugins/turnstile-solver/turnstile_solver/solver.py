"""Standalone Cloudflare Turnstile solver with verified cookie caching.

Zero-dependency beyond httpx + asyncio. Works with any HTTP client
(curl_cffi, httpx, etc.) that supports .cookies and .get/.post.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TurnstileError(RuntimeError):
    """Turnstile solve or verification failure."""
    pass


@dataclass
class TurnstileConfig:
    """Solver configuration."""
    enabled: bool = True
    api_url: str = "https://cfs.071129.xyz/turnstile/sync"
    api_key: str = ""
    sitekey: str = "0x4AAAAAADlLZ3ljqZP6cQwq"
    action: str = "chat"
    timeout_seconds: int = 90
    cookie_ttl_seconds: int = 10800
    retries: int = 5
    retry_backoff_seconds: float = 1.5
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    )
    proxy_url: str | None = None


@dataclass
class _CookieState:
    cookies: dict[str, str]
    expires_at: float


class TurnstileSolver:
    """Token solver + per-site verified cookie cache.

    Usage::

        cfg = TurnstileConfig(api_key="key", sitekey="0x4AAAAAA...")
        solver = TurnstileSolver(cfg)

        import curl_cffi.requests as curl_requests
        async with curl_requests.AsyncSession(impersonate="chrome120") as client:
            await solver.apply_valid_cookies(
                client, "https://deepseek.de",
                "https://deepseek.de/wp-admin/admin-ajax.php",
                "de",
            )
            # client.cookies now has verified Turnstile cookies
    """

    def __init__(self, config: TurnstileConfig):
        self.config = config
        self._cache: dict[str, _CookieState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ── Public API ─────────────────────────────────────────────

    def invalidate(self, site_code: str) -> None:
        """Drop cached verified cookies for *site_code*."""
        self._cache.pop(site_code, None)

    async def apply_valid_cookies(
        self,
        client: Any,
        base_url: str,
        ajax_url: str,
        site_code: str,
        *,
        verify_action: str = "deepseek_ts_verify",
        sitekey: str | None = None,
        language: str = "en-US,en;q=0.9",
    ) -> None:
        """Ensure *client* has fresh verified cookies for *site_code*.

        If cached cookies are still valid they are applied inline
        (no network).  Otherwise a full solve → verify cycle runs under
        a per-site lock so concurrent callers coalesce.
        """
        if not self.config.enabled:
            return
        cached = self._cache.get(site_code)
        if cached and cached.expires_at > time.time():
            self._apply_cookies(client, cached.cookies)
            return
        async with self._lock(site_code):
            cached = self._cache.get(site_code)
            if cached and cached.expires_at > time.time():
                self._apply_cookies(client, cached.cookies)
                return
            await self._refresh(
                client, base_url, ajax_url, site_code,
                verify_action=verify_action,
                sitekey=sitekey,
                language=language,
            )

    async def refresh(
        self,
        client: Any,
        base_url: str,
        ajax_url: str,
        site_code: str,
        *,
        verify_action: str = "deepseek_ts_verify",
        sitekey: str | None = None,
        language: str = "en-US,en;q=0.9",
    ) -> None:
        """Force a fresh solve → verify cycle regardless of cache."""
        if not self.config.enabled:
            return
        async with self._lock(site_code):
            await self._refresh(
                client, base_url, ajax_url, site_code,
                verify_action=verify_action,
                sitekey=sitekey,
                language=language,
            )

    # ── Internal ───────────────────────────────────────────────

    async def _refresh(
        self,
        client: Any,
        base_url: str,
        ajax_url: str,
        site_code: str,
        *,
        verify_action: str,
        sitekey: str | None,
        language: str,
    ) -> None:
        logger.info("turnstile refresh site=%s", site_code)
        _sitekey = sitekey or self.config.sitekey
        token = await self._solve_token(base_url, _sitekey)
        await client.get(
            base_url + "/",
            headers=self._browser_headers(base_url, language),
        )
        await self._verify_token(
            client, base_url, ajax_url, site_code, token,
            verify_action=verify_action, language=language,
        )
        self._cache[site_code] = _CookieState(
            cookies=dict(client.cookies),
            expires_at=time.time() + self.config.cookie_ttl_seconds,
        )

    async def _verify_token(
        self,
        client: Any,
        base_url: str,
        ajax_url: str,
        site_code: str,
        token: str,
        *,
        verify_action: str,
        language: str,
    ) -> dict:
        last_error: Exception | None = None
        headers = {
            **self._ajax_headers(base_url, language),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        for attempt in range(self.config.retries):
            try:
                resp = await client.post(
                    ajax_url,
                    data={"action": verify_action, "token": token},
                    headers=headers,
                )
                logger.info(
                    "turnstile verify site=%s status=%s",
                    site_code, resp.status_code,
                )
                data = resp.json()
                if data.get("ok"):
                    return data
                last_error = TurnstileError(
                    f"turnstile verify failed for {site_code}: {data}"
                )
            except Exception as exc:
                last_error = exc
            logger.warning(
                "turnstile verify retry site=%s attempt=%s error=%s",
                site_code, attempt + 1, last_error,
            )
            await asyncio.sleep(
                self.config.retry_backoff_seconds * (attempt + 1)
            )
        raise TurnstileError(
            f"turnstile verify unavailable for {site_code}: {last_error}"
        )

    async def _solve_token(self, base_url: str, sitekey: str) -> str:
        payload = {
            "url": base_url,
            "sitekey": sitekey,
            "action": self.config.action,
            "cdata": "",
            "timeoutSeconds": self.config.timeout_seconds,
        }
        timeout = self.config.timeout_seconds + 30
        last_error: Exception | None = None
        for attempt in range(self.config.retries):
            try:
                async with httpx.AsyncClient(
                    proxy=self.config.proxy_url,
                    timeout=timeout,
                    trust_env=False,
                ) as c:
                    resp = await c.post(
                        self.config.api_url,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {self.config.api_key}",
                        },
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                if data.get("errorId", 0) != 0 or data.get("status") not in {None, "ready"}:
                    last_error = TurnstileError(
                        f"turnstile solver failed for {base_url}: {data}"
                    )
                    logger.warning(
                        "turnstile solver error site=%s attempt=%s data=%s",
                        base_url, attempt + 1, data,
                    )
                    await asyncio.sleep(
                        self.config.retry_backoff_seconds * (attempt + 1)
                    )
                    continue
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "turnstile solver request failed site=%s attempt=%s error=%s",
                    base_url, attempt + 1, exc,
                )
                await asyncio.sleep(
                    self.config.retry_backoff_seconds * (attempt + 1)
                )
        else:
            raise TurnstileError(
                f"turnstile solver unavailable for {base_url}: {last_error}"
            )
        token = data.get("solution", {}).get("token")
        if not token:
            raise TurnstileError(
                f"turnstile solver returned no token for {base_url}"
            )
        logger.info(
            "turnstile solved site=%s elapsed=%s",
            base_url, data.get("elapsedTime"),
        )
        return token

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _apply_cookies(client: Any, cookies: dict[str, str]) -> None:
        for key, value in cookies.items():
            client.cookies.set(key, value)

    def _lock(self, site_code: str) -> asyncio.Lock:
        lock = self._locks.get(site_code)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[site_code] = lock
        return lock

    def _browser_headers(self, base_url: str, language: str) -> dict[str, str]:
        return {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": language,
            "Origin": base_url,
            "Referer": base_url + "/",
        }

    def _ajax_headers(self, base_url: str, language: str) -> dict[str, str]:
        return {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": language,
            "X-Requested-With": "XMLHttpRequest",
            "Origin": base_url,
            "Referer": base_url + "/",
        }
