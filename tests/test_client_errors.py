import json

import pytest

from deepseek_all_in_one.client import DeepSeekClient, QuotaExhaustedError, SessionVerificationError
from deepseek_all_in_one.config import load_config


def test_quota_notice_triggers_cookie_refresh_path():
    client = DeepSeekClient(load_config("config.toml"))
    payload = {
        "error": "Dein heutiges Guthaben von 10.000 Token (V4-Pro) ist aufgebraucht.",
        "quota_notice": {
            "type": "quota_notice",
            "message": "Dein heutiges Guthaben von 10.000 Token (V4-Pro) ist aufgebraucht.",
            "actions": [],
        },
    }
    with pytest.raises(QuotaExhaustedError):
        client._translate_event("error", [json.dumps(payload)])


def test_session_error_triggers_cookie_refresh_path():
    client = DeepSeekClient(load_config("config.toml"))
    with pytest.raises(SessionVerificationError):
        client._translate_event("error", [json.dumps({"error": "deepseek_ts_required"})])


def test_plain_sse_error_does_not_force_cookie_refresh_path():
    client = DeepSeekClient(load_config("config.toml"))
    with pytest.raises(Exception) as exc:
        client._translate_event("error", [json.dumps({"error": "temporary upstream failure"})])
    assert not isinstance(exc.value, (QuotaExhaustedError, SessionVerificationError))
