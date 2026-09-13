import asyncio

from src.services.result_storage_service import (
    apply_price_drop_check,
    save_result_blacklist_keywords,
    save_result_record,
    update_item_status,
)


KEYWORD = "sony a7m4"
LINK = "https://www.goofish.com/item.htm?id=1001"
UNIQUE_KEY = "https://www.goofish.com/item.htm?id=1001"


def _make_record(*, price="¥10000", is_recommended=True, title="Sony A7M4 单机"):
    return {
        "爬取时间": "2026-01-01T10:00:00",
        "搜索关键字": KEYWORD,
        "任务名称": "Sony A7M4 监控",
        "商品信息": {
            "商品ID": "1001",
            "商品标题": title,
            "商品链接": LINK,
            "当前售价": price,
        },
        "ai_analysis": {
            "is_recommended": is_recommended,
            "analysis_source": "ai",
            "reason": "符合要求",
        },
    }


def _save(record):
    assert asyncio.run(save_result_record(record, KEYWORD)) is True


def test_apply_price_drop_check_notifies_once_when_price_drops_below_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save(_make_record(price="¥10000"))

    result = apply_price_drop_check(
        KEYWORD,
        UNIQUE_KEY,
        current_price="¥8888",
        current_price_display="¥8888",
        target_price="9000",
    )

    assert result is not None
    assert result["item_data"]["当前售价"] == "¥8888"
    assert "8888" in result["reason"]


def test_apply_price_drop_check_does_not_renotify_while_still_below_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save(_make_record(price="¥10000"))

    first = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥8888", current_price_display="¥8888", target_price="9000"
    )
    assert first is not None

    second = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥8800", current_price_display="¥8800", target_price="9000"
    )
    assert second is None


def test_apply_price_drop_check_renotifies_after_price_recovers_and_drops_again(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save(_make_record(price="¥10000"))

    first = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥8888", current_price_display="¥8888", target_price="9000"
    )
    assert first is not None

    recovered = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥9500", current_price_display="¥9500", target_price="9000"
    )
    assert recovered is None

    dropped_again = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥8700", current_price_display="¥8700", target_price="9000"
    )
    assert dropped_again is not None


def test_apply_price_drop_check_skips_non_recommended_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save(_make_record(price="¥10000", is_recommended=False))

    result = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥8888", current_price_display="¥8888", target_price="9000"
    )
    assert result is None


def test_apply_price_drop_check_skips_manually_hidden_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save(_make_record(price="¥10000"))
    assert asyncio.run(update_item_status(_build_filename(), "1001", "hidden")) is True

    result = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥8888", current_price_display="¥8888", target_price="9000"
    )
    assert result is None


def test_apply_price_drop_check_skips_blacklisted_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save(_make_record(price="¥10000", title="Sony A7M4 水货"))
    asyncio.run(save_result_blacklist_keywords(_build_filename(), ["水货"]))

    result = apply_price_drop_check(
        KEYWORD, UNIQUE_KEY, current_price="¥8888", current_price_display="¥8888", target_price="9000"
    )
    assert result is None


def test_apply_price_drop_check_ignores_unknown_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = apply_price_drop_check(
        KEYWORD, "unknown-key", current_price="¥8888", current_price_display="¥8888", target_price="9000"
    )
    assert result is None


def _build_filename() -> str:
    from src.infrastructure.persistence.storage_names import build_result_filename

    return build_result_filename(KEYWORD)
