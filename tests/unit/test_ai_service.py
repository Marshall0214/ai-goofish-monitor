from src.services.ai_service import AIAnalysisService


def _full_result(**overrides):
    base = {
        "prompt_version": "EagleEye-V6.4",
        "is_recommended": True,
        "reason": "符合要求",
        "risk_tags": [],
        "criteria_analysis": {"seller_type": {"status": "PASS"}},
    }
    base.update(overrides)
    return base


def _service() -> AIAnalysisService:
    # _validate_result 是纯逻辑方法，不依赖 ai_client 的具体实现，传 None 即可。
    return AIAnalysisService(ai_client=None)


def test_validate_result_accepts_response_missing_prompt_version():
    # 同 src/ai_handler.py 里的修复：prompt_version 只是装饰性版本号，没有任何
    # 地方真正读取它，模型没回显它不该导致一份内容完整的分析结果被判定失败。
    result = _full_result()
    del result["prompt_version"]

    assert _service()._validate_result(result) is True


def test_validate_result_still_rejects_missing_functional_fields():
    for missing in ("is_recommended", "reason", "risk_tags", "criteria_analysis"):
        result = _full_result()
        del result[missing]
        assert _service()._validate_result(result) is False, missing


def test_validate_result_rejects_wrong_types():
    assert _service()._validate_result(_full_result(is_recommended="yes")) is False
    assert _service()._validate_result(_full_result(risk_tags="none")) is False
    assert _service()._validate_result(_full_result(criteria_analysis={})) is False
