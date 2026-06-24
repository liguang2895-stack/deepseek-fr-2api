import asyncio

from deepseek_all_in_one.config import load_config
from deepseek_all_in_one.turnstile import TurnstileSolver
from turnstile_solver.solver import _CookieState


class DummyCookies(dict):
    def set(self, key, value):
        self[key] = value


class DummyClient:
    def __init__(self):
        self.cookies = DummyCookies()


def test_apply_valid_cookies_coalesces_concurrent_refreshes():
    asyncio.run(_run_concurrency_check())


async def _run_concurrency_check():
    cfg = load_config("config.toml")
    site = cfg.sites["de"]
    solver = TurnstileSolver(cfg)
    calls = 0
    base = solver._base

    async def _fake_refresh(client, *args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        client.cookies.set("dsts", "ok")
        base._cache[site.code] = _CookieState({"dsts": "ok"}, 9999999999)

    base._refresh = _fake_refresh
    clients = [DummyClient() for _ in range(5)]

    await asyncio.gather(*(solver.apply_valid_cookies(client, site) for client in clients))

    assert calls == 1
    assert all(client.cookies["dsts"] == "ok" for client in clients)
