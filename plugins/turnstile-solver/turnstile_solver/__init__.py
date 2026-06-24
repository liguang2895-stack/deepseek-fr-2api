"""Turnstile Solver — standalone Cloudflare Turnstile token solver with cookie caching.

Works with any site that uses Cloudflare Turnstile + WordPress AIPKit ajax verification.
This plugin is self-contained: it only needs httpx and asyncio.
"""

from __future__ import annotations

__version__ = "1.0.0"

from .solver import TurnstileSolver, TurnstileConfig, TurnstileError

__all__ = ["TurnstileSolver", "TurnstileConfig", "TurnstileError"]
