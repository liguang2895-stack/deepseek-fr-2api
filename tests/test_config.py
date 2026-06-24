from deepseek_all_in_one.config import load_config


def test_loads_six_models_from_config():
    cfg = load_config("config.toml")
    assert len(cfg.models) == 6
    assert "deepseek-v4-flash-de" in cfg.models
    assert "deepseek-v4-pro-fr" in cfg.models
    assert cfg.sites["de"].sitekey == "0x4AAAAAADlLZ3ljqZP6cQwq"


def test_security_key_configured():
    cfg = load_config("config.toml")
    assert cfg.api_keys == ["sk-dsfr-local-change-me"]

