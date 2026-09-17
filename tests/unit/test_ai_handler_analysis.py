import asyncio
import json
from types import SimpleNamespace

import pytest

import src.ai_handler as ai_handler
import src.config as app_config


def _build_fake_client(responses_create_impl, chat_create_impl=None):
    responses = SimpleNamespace(create=responses_create_impl)
    chat = SimpleNamespace(
        completions=SimpleNamespace(create=chat_create_impl or responses_create_impl)
    )
    return SimpleNamespace(responses=responses, chat=chat)


def test_get_ai_analysis_stops_after_internal_retries_when_content_is_none(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    call_count = {"value": 0}

    async def fake_create(**_kwargs):
        call_count["value"] += 1
        return SimpleNamespace(output_text="")

    monkeypatch.setattr(ai_handler, "client", _build_fake_client(fake_create))
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)

    with pytest.raises(ValueError, match="AI响应内容为空"):
        asyncio.run(
            ai_handler.get_ai_analysis(
                {"商品信息": {"商品ID": "1", "商品标题": "测试商品"}},
                image_paths=[],
                prompt_text="请输出 JSON",
            )
        )

    assert call_count["value"] == 4


def test_get_ai_analysis_returns_parsed_json(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    call_count = {"value": 0}

    async def fake_create(**_kwargs):
        call_count["value"] += 1
        return SimpleNamespace(
            output_text=(
                '{"prompt_version":"v1","is_recommended":true,'
                '"reason":"ok","risk_tags":[],"criteria_analysis":{"seller_type":"个人"}}'
            )
        )

    monkeypatch.setattr(ai_handler, "client", _build_fake_client(fake_create))
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)

    result = asyncio.run(
        ai_handler.get_ai_analysis(
            {"商品信息": {"商品ID": "2", "商品标题": "测试商品2"}},
            image_paths=[],
            prompt_text="请输出 JSON",
        )
    )

    assert result["is_recommended"] is True
    assert call_count["value"] == 1


def test_get_ai_analysis_retries_without_structured_output_when_model_rejects_it(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    request_history = []

    async def fake_create(**kwargs):
        request_history.append(kwargs)
        if len(request_history) == 1:
            raise Exception(
                "Error code: 400 - {'error': {'code': 'InvalidParameter', "
                "'message': 'The parameter `response_format.type` specified in "
                "the request are not valid: `json_object` is not supported by "
                "this model.', 'param': 'response_format.type'}}"
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"prompt_version":"v1","is_recommended":true,'
                            '"reason":"ok","risk_tags":[],"criteria_analysis":{"seller_type":"个人"}}'
                        )
                    )
                )
            ]
        )

    monkeypatch.setattr(ai_handler, "client", _build_fake_client(fake_create))
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)

    result = asyncio.run(
        ai_handler.get_ai_analysis(
            {"商品信息": {"商品ID": "3", "商品标题": "测试商品3"}},
            image_paths=[],
            prompt_text="请输出 JSON",
        )
    )

    assert result["reason"] == "ok"
    assert request_history[0]["messages"][0]["role"] == "user"
    assert request_history[0]["response_format"]["type"] == "json_object"
    assert "response_format" not in request_history[1]
    assert ai_handler.ENABLE_RESPONSE_FORMAT is True


def test_get_ai_analysis_falls_back_to_responses_when_chat_completions_api_is_missing(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    request_history = []

    async def fake_chat_create(**kwargs):
        request_history.append(("chat", kwargs))
        raise Exception("Error code: 404 - page not found")

    async def fake_responses_create(**kwargs):
        request_history.append(("responses", kwargs))
        if len([item for item in request_history if item[0] == "responses"]) == 1:
            raise Exception(
                "Error code: 400 - {'error': {'code': 'InvalidParameter', "
                "'message': 'The parameter `text.format.type` specified in "
                "the request are not valid: `json_object` is not supported by "
                "this model.', 'param': 'text.format.type'}}"
            )
        return SimpleNamespace(
            output_text=(
                '{"prompt_version":"v1","is_recommended":true,'
                '"reason":"ok","risk_tags":[],"criteria_analysis":{"seller_type":"个人"}}'
            )
        )

    monkeypatch.setattr(
        ai_handler,
        "client",
        _build_fake_client(fake_responses_create, fake_chat_create),
    )
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)

    result = asyncio.run(
        ai_handler.get_ai_analysis(
            {"商品信息": {"商品ID": "4", "商品标题": "测试商品4"}},
            image_paths=[],
            prompt_text="请输出 JSON",
        )
    )

    assert result["reason"] == "ok"
    assert request_history[0][0] == "chat"
    assert request_history[0][1]["messages"][0]["role"] == "user"
    assert request_history[1][0] == "responses"
    assert request_history[1][1]["text"]["format"]["type"] == "json_object"
    assert request_history[2][0] == "responses"
    assert "text" not in request_history[2][1]


def test_get_ai_analysis_retries_without_temperature_when_gateway_rejects_it(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    request_history = []

    async def fake_create(**kwargs):
        request_history.append(kwargs)
        if len(request_history) == 1:
            raise Exception("temperature is unsupported for this model")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"prompt_version":"v1","is_recommended":true,'
                            '"reason":"ok","risk_tags":[],"criteria_analysis":{"seller_type":"个人"}}'
                        )
                    )
                )
            ]
        )

    monkeypatch.setattr(ai_handler, "client", _build_fake_client(fake_create))
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)

    result = asyncio.run(
        ai_handler.get_ai_analysis(
            {"商品信息": {"商品ID": "4", "商品标题": "测试商品4"}},
            image_paths=[],
            prompt_text="请输出 JSON",
        )
    )

    assert result["reason"] == "ok"
    assert request_history[0]["temperature"] == 0.1
    assert "temperature" not in request_history[1]


def test_get_ai_analysis_uses_first_json_object_when_model_returns_multiple_objects(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)

    async def fake_create(**_kwargs):
        return SimpleNamespace(
            output_text="""```json
{"prompt_version":"v1","is_recommended":true,"reason":"first","risk_tags":[],"criteria_analysis":{"seller_type":"个人"}}
{"prompt_version":"v1","is_recommended":false,"reason":"second","risk_tags":[],"criteria_analysis":{"seller_type":"商家"}}
```"""
        )

    monkeypatch.setattr(ai_handler, "client", _build_fake_client(fake_create))
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)

    result = asyncio.run(
        ai_handler.get_ai_analysis(
            {"商品信息": {"商品ID": "5", "商品标题": "测试商品5"}},
            image_paths=[],
            prompt_text="请输出 JSON",
        )
    )

    assert result["is_recommended"] is True
    assert result["reason"] == "first"


# -- validate_ai_response_format --


def _full_response(**overrides):
    base = {
        "prompt_version": "EagleEye-V6.4",
        "is_recommended": True,
        "reason": "符合要求",
        "risk_tags": [],
        "criteria_analysis": {"seller_type": {"status": "PASS"}},
    }
    base.update(overrides)
    return base


def test_validate_ai_response_format_accepts_response_missing_prompt_version():
    # prompt_version 只是 prompt 模板里的装饰性版本号，代码里从没被读取过；
    # 模型没有回显它不该导致一份内容完整的分析结果被判定失败。
    response = _full_response()
    del response["prompt_version"]

    assert ai_handler.validate_ai_response_format(response) is True


def test_validate_ai_response_format_still_rejects_missing_functional_fields():
    for missing in ("is_recommended", "reason", "risk_tags", "criteria_analysis"):
        response = _full_response()
        del response[missing]
        assert ai_handler.validate_ai_response_format(response) is False, missing


def test_validate_ai_response_format_rejects_response_without_seller_type():
    response = _full_response(criteria_analysis={"model_chip": {"status": "PASS"}})

    assert ai_handler.validate_ai_response_format(response) is False


def test_validate_ai_response_format_rejects_wrong_types():
    assert ai_handler.validate_ai_response_format(_full_response(is_recommended="yes")) is False
    assert ai_handler.validate_ai_response_format(_full_response(risk_tags="none")) is False
    assert ai_handler.validate_ai_response_format(_full_response(criteria_analysis={})) is False


def test_get_ai_analysis_succeeds_on_first_attempt_when_model_omits_prompt_version(
    monkeypatch, tmp_path
):
    # 回归测试：修复前，模型只要没回显 prompt_version 就会被强制重试 3-4 次
    # （白白浪费 AI 调用），即便其余字段完全正确。修复后应该第一次就通过。
    monkeypatch.chdir(tmp_path)
    request_history = []

    async def fake_create(**kwargs):
        request_history.append(kwargs)
        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "is_recommended": True,
                    "reason": "符合要求",
                    "risk_tags": [],
                    "criteria_analysis": {"seller_type": {"status": "PASS"}},
                },
                ensure_ascii=False,
            )
        )

    monkeypatch.setattr(ai_handler, "client", _build_fake_client(fake_create))
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)

    result = asyncio.run(
        ai_handler.get_ai_analysis(
            {"商品信息": {"商品ID": "6", "商品标题": "测试商品6"}},
            image_paths=[],
            prompt_text="请输出 JSON",
        )
    )

    assert result["is_recommended"] is True
    assert len(request_history) == 1


def test_get_ai_analysis_uses_configured_max_output_tokens(monkeypatch, tmp_path):
    # 回归测试：之前 max_output_tokens 硬编码成 4000，遇到内容较长的卖家画像
    # 分析时响应会在 JSON 写完之前被截断，引发"JSON解析失败"或更隐蔽的
    # "响应缺少必需字段"（截断后的残片里某个嵌套子对象被误当作顶层响应）。
    # 现在应该改为读取 src.config.AI_MAX_OUTPUT_TOKENS，可通过 .env 调整。
    monkeypatch.chdir(tmp_path)
    request_history = []

    async def fake_create(**kwargs):
        request_history.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "is_recommended": True,
                                "reason": "ok",
                                "risk_tags": [],
                                "criteria_analysis": {"seller_type": {"status": "PASS"}},
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        )

    monkeypatch.setattr(ai_handler, "client", _build_fake_client(fake_create))
    monkeypatch.setattr(ai_handler, "MODEL_NAME", "fake-model")
    monkeypatch.setattr(ai_handler, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(app_config, "ENABLE_RESPONSE_FORMAT", True)
    monkeypatch.setattr(ai_handler, "AI_MAX_OUTPUT_TOKENS", 12345)

    asyncio.run(
        ai_handler.get_ai_analysis(
            {"商品信息": {"商品ID": "7", "商品标题": "测试商品7"}},
            image_paths=[],
            prompt_text="请输出 JSON",
        )
    )

    assert request_history[0]["max_tokens"] == 12345
