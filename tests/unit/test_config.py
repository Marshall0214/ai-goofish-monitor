import importlib


def _reload_config(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    import src.config as config_module

    return importlib.reload(config_module)


def test_ai_max_output_tokens_defaults_to_8000(monkeypatch):
    config = _reload_config(monkeypatch, AI_MAX_OUTPUT_TOKENS=None)

    assert config.AI_MAX_OUTPUT_TOKENS == 8000


def test_ai_max_output_tokens_reads_env_override(monkeypatch):
    config = _reload_config(monkeypatch, AI_MAX_OUTPUT_TOKENS="12000")

    assert config.AI_MAX_OUTPUT_TOKENS == 12000


def test_ai_max_output_tokens_falls_back_to_default_on_invalid_value(monkeypatch):
    # 之前 prompts/宝可梦goplus_criteria.txt 被污染，根因之一就是响应在 JSON
    # 写完前被截断；这个上限是防止同类截断复发的关键配置，不能因为 .env 里
    # 填了个非法值（比如手滑打错）就让程序直接崩溃退出。
    config = _reload_config(monkeypatch, AI_MAX_OUTPUT_TOKENS="not-a-number")

    assert config.AI_MAX_OUTPUT_TOKENS == 8000
