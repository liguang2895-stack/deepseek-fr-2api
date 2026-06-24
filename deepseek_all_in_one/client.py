from __future__ import annotations

import html
import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
from curl_cffi import requests as curl_requests

from .config import Config, ModelConfig, SiteConfig
from .turnstile import TurnstileSolver

logger = logging.getLogger(__name__)


class UpstreamError(RuntimeError):
    pass


class QuotaExhaustedError(UpstreamError):
    pass


class SessionVerificationError(UpstreamError):
    pass


@dataclass
class ChatConfig:
    bot_id: int
    post_id: int
    nonce: str
    ajax_url: str
    fetched_at: float


class DeepSeekClient:
    def __init__(self, config: Config):
        self.config = config
        self.turnstile = TurnstileSolver(config)
        self._chat_config_cache: dict[str, ChatConfig] = {}
        self._site_locks: dict[str, asyncio.Lock] = {}
        self._model_config_locks: dict[str, asyncio.Lock] = {}

    async def close(self) -> None:
        return None

    async def chat(self, model: ModelConfig, prompt: str) -> AsyncIterator[tuple[str, str | None]]:
        site = self._site(model)
        last_error: Exception | None = None
        for attempt in range(self.config.refresh_retries + 1):
            try:
                async for item in self._chat_once(site, model, prompt):
                    yield item
                return
            except Exception as exc:
                last_error = exc
                logger.warning("upstream error model=%s attempt=%s error=%s", model.id, attempt + 1, exc)
                if not self.config.auto_refresh or attempt >= self.config.refresh_retries:
                    break
                await asyncio.sleep(self.config.retry_backoff_seconds * (attempt + 1))
                try:
                    force_cookie_refresh = isinstance(exc, (QuotaExhaustedError, SessionVerificationError))
                    await self.refresh_session(site, model, invalidate_cookies=force_cookie_refresh)
                except Exception as refresh_exc:
                    logger.warning("session refresh failed model=%s error=%s", model.id, refresh_exc)
        raise UpstreamError(str(last_error or "upstream failed"))

    async def refresh_session(self, site: SiteConfig, model: ModelConfig, invalidate_cookies: bool = False) -> None:
        self._chat_config_cache.pop(model.id, None)
        if not invalidate_cookies:
            return
        async with self._site_lock(site):
            logger.info("invalidate verified cookie cache site=%s", site.code)
            self.turnstile.invalidate(site)
            client = await self._new_client(site)
            try:
                await self.turnstile.refresh(client, site)
            finally:
                await client.close()

    async def _chat_once(self, site: SiteConfig, model: ModelConfig, prompt: str) -> AsyncIterator[tuple[str, str | None]]:
        client = await self._new_client(site)
        try:
            await self.turnstile.apply_valid_cookies(client, site)
            cfg = await self._get_chat_config(client, site, model)
            referer = f"{site.base_url}{model.page_path}"
            session_id = str(uuid.uuid4())
            conversation_uuid = str(uuid.uuid4())
            client_msg_id = f"aipkit-client-msg-{cfg.bot_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"

            init_resp = await client.post(
                cfg.ajax_url,
                data={
                    "action": "aipkit_cache_sse_message",
                    "message": prompt,
                    "_ajax_nonce": cfg.nonce,
                    "bot_id": str(cfg.bot_id),
                    "session_id": session_id,
                    "conversation_uuid": conversation_uuid,
                    "user_client_message_id": client_msg_id,
                },
                headers=self._ajax_headers(site, referer),
            )
            logger.info("cache message response model=%s status=%s", model.id, init_resp.status_code)
            init_resp.raise_for_status()
            init_data = init_resp.json()
            logger.debug("cache message payload model=%s data=%s", model.id, init_data)
            if not init_data.get("success"):
                code = init_data.get("data", {}).get("code") if isinstance(init_data.get("data"), dict) else None
                if code and "nonce" in code:
                    self._chat_config_cache.pop(model.id, None)
                if self._is_session_error(init_data):
                    raise SessionVerificationError(f"cache message session failed: {init_data}")
                raise UpstreamError(f"cache message failed: {init_data}")
            cache_key = init_data["data"]["cache_key"]

            params = {
                "action": "aipkit_frontend_chat_stream",
                "cache_key": cache_key,
                "bot_id": str(cfg.bot_id),
                "session_id": session_id,
                "conversation_uuid": conversation_uuid,
                "post_id": str(cfg.post_id),
                "_ts": str(int(time.time() * 1000)),
                "_ajax_nonce": cfg.nonce,
            }
            async with client.stream(
                "GET",
                cfg.ajax_url,
                params=params,
                headers={**self._ajax_headers(site, referer), "Accept": "text/event-stream"},
                timeout=self.config.stream_timeout,
            ) as stream:
                stream.raise_for_status()
                logger.info("stream opened model=%s status=%s", model.id, stream.status_code)
                async for item in self._read_sse(stream):
                    yield item
        finally:
            await client.close()

    async def _read_sse(self, stream) -> AsyncIterator[tuple[str, str | None]]:
        event_type = "message"
        data_lines: list[str] = []
        async for raw in stream.aiter_lines():
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            line = raw.strip()
            if not line or line == "\r":
                if data_lines:
                    for item in self._translate_event(event_type, data_lines):
                        yield item
                    data_lines.clear()
                    event_type = "message"
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            for item in self._translate_event(event_type, data_lines):
                yield item

    def _translate_event(self, event_type: str, data_lines: list[str]) -> list[tuple[str, str | None]]:
        payload: dict = {}
        for line in data_lines:
            if line == "[DONE]":
                return [("done", None)]
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
        if event_type == "message_start":
            return [("start", payload.get("message_id"))]
        if event_type in {"done", "complete"}:
            return [("done", None)]
        if event_type == "error" or "error" in payload:
            if self._is_quota_error(payload):
                raise QuotaExhaustedError(f"sse quota exhausted: {payload}")
            if self._is_session_error(payload):
                raise SessionVerificationError(f"sse session failed: {payload}")
            raise UpstreamError(f"sse error: {payload}")
        delta = payload.get("delta") or payload.get("message") or payload.get("content")
        return [("delta", str(delta))] if delta else []

    def _is_quota_error(self, payload: dict) -> bool:
        text = " ".join(
            str(value)
            for value in (
                payload.get("error"),
                payload.get("message"),
                payload.get("quota_notice", {}).get("message") if isinstance(payload.get("quota_notice"), dict) else None,
            )
            if value
        ).lower()
        return bool(payload.get("quota_notice")) or "guthaben" in text or "quota" in text or "token" in text and "aufgebraucht" in text

    def _is_session_error(self, payload: dict) -> bool:
        text = json.dumps(payload, ensure_ascii=False).lower()
        markers = (
            "deepseek_ts_required",
            "ts_required",
            "nonce_failure",
            "nonce",
            "forbidden",
            "unauthorized",
            "403",
        )
        return any(marker in text for marker in markers)

    async def _get_chat_config(self, client: curl_requests.AsyncSession, site: SiteConfig, model: ModelConfig) -> ChatConfig:
        cached = self._chat_config_cache.get(model.id)
        if cached and time.time() - cached.fetched_at < self.config.config_ttl_seconds:
            return cached
        async with self._model_config_lock(model):
            cached = self._chat_config_cache.get(model.id)
            if cached and time.time() - cached.fetched_at < self.config.config_ttl_seconds:
                return cached
            page_url = f"{site.base_url}{model.page_path}"
            resp = await client.get(page_url, headers=self._browser_headers(site))
            resp.raise_for_status()
            parsed = await self._parse_chat_config(client, resp.text, site, model)
            self._chat_config_cache[model.id] = parsed
            logger.info("loaded chat config model=%s bot_id=%s post_id=%s", model.id, parsed.bot_id, parsed.post_id)
            return parsed

    async def _parse_chat_config(self, client: curl_requests.AsyncSession, text: str, site: SiteConfig, model: ModelConfig) -> ChatConfig:
        matches = re.findall(r'id="aipkit_chat_container_(\d+)"[^>]*data-config=\'([^\']+)\'', text)
        for bot_id, raw in matches:
            cfg = json.loads(html.unescape(raw))
            if model.bot_id is None or int(bot_id) == int(model.bot_id):
                return ChatConfig(
                    bot_id=int(cfg.get("botId", bot_id)),
                    post_id=int(cfg.get("postId", model.post_id or 0)),
                    nonce=str(cfg["nonce"]),
                    ajax_url=str(cfg.get("ajaxUrl", site.ajax_url)).replace("\\/", "/"),
                    fetched_at=time.time(),
                )
        if not model.bot_id or not model.post_id:
            raise UpstreamError(f"no chat data-config found for {model.id}")
        nonce = await self._fetch_nonce(client, site, model)
        return ChatConfig(
            bot_id=int(model.bot_id),
            post_id=int(model.post_id),
            nonce=nonce,
            ajax_url=site.ajax_url,
            fetched_at=time.time(),
        )

    async def _fetch_nonce(self, client: curl_requests.AsyncSession, site: SiteConfig, model: ModelConfig) -> str:
        resp = await client.post(
            site.ajax_url,
            data={"action": "aipkit_get_frontend_chat_nonce", "bot_id": str(model.bot_id)},
            headers=self._ajax_headers(site, f"{site.base_url}{model.page_path}"),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise UpstreamError(f"nonce fetch failed for {model.id}: {data}")
        return str(data["data"]["nonce"])

    async def _new_client(self, site: SiteConfig) -> curl_requests.AsyncSession:
        proxies = None
        if self.config.proxy_url:
            proxies = {"http": self.config.proxy_url, "https": self.config.proxy_url}
        return curl_requests.AsyncSession(
            impersonate="chrome120",
            proxies=proxies,
            timeout=self.config.timeout,
            allow_redirects=True,
            headers=self._browser_headers(site),
        )

    def _site(self, model: ModelConfig) -> SiteConfig:
        try:
            return self.config.sites[model.site]
        except KeyError as exc:
            raise UpstreamError(f"unknown site {model.site}") from exc

    def _site_lock(self, site: SiteConfig) -> asyncio.Lock:
        lock = self._site_locks.get(site.code)
        if lock is None:
            lock = asyncio.Lock()
            self._site_locks[site.code] = lock
        return lock

    def _model_config_lock(self, model: ModelConfig) -> asyncio.Lock:
        lock = self._model_config_locks.get(model.id)
        if lock is None:
            lock = asyncio.Lock()
            self._model_config_locks[model.id] = lock
        return lock

    def _browser_headers(self, site: SiteConfig) -> dict[str, str]:
        return {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": site.language,
            "Origin": site.base_url,
            "Referer": site.base_url + "/",
        }

    def _ajax_headers(self, site: SiteConfig, referer: str) -> dict[str, str]:
        return {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": site.language,
            "X-Requested-With": "XMLHttpRequest",
            "Origin": site.base_url,
            "Referer": referer,
        }
