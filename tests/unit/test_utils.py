import asyncio

from src.services.result_storage_service import load_all_result_records
from src.utils import (
    format_registration_days,
    get_link_unique_key,
    safe_get,
    save_to_jsonl,
)


def test_safe_get_nested_and_default():
    data = {"a": {"b": [{"c": "value"}]}}
    assert asyncio.run(safe_get(data, "a", "b", 0, "c")) == "value"
    assert asyncio.run(safe_get(data, "a", "b", 1, "c", default="missing")) == "missing"


def test_format_registration_days():
    assert format_registration_days(400).startswith("\u6765\u95f2\u9c7c")
    assert format_registration_days(-1) == "\u672a\u77e5"


def test_get_link_unique_key():
    link = "https://www.goofish.com/item?id=123&foo=bar"
    assert get_link_unique_key(link) == "https://www.goofish.com/item?id=123"


def test_save_to_jsonl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    record = {
        "爬取时间": "2026-01-01T10:00:00",
        "搜索关键字": "sony a7m4",
        "任务名称": "Sony A7M4",
        "商品信息": {
            "商品ID": "1",
            "商品标题": "Sony A7M4",
            "商品链接": "https://www.goofish.com/item?id=1",
            "当前售价": "¥10000",
        },
    }

    ok = asyncio.run(save_to_jsonl(record, keyword="sony a7m4"))
    assert ok is True

    records = asyncio.run(
        load_all_result_records(
            "sony_a7m4_full_data.jsonl",
            ai_recommended_only=False,
            keyword_recommended_only=False,
            sort_by="crawl_time",
            sort_order="asc",
        )
    )
    assert len(records) == 1
    result = records[0]

    # 查询时会附加展示用的装饰字段（可见性/黑名单命中情况），不是原始存入的数据，
    # 单独断言这些字段的默认值，而不是要求跟存入的 record 完全相等。
    assert result["_status"] == "active"
    assert result["_matched_blacklist_keywords"] == []
    assert result["_hidden_reason"] is None
    assert result["_effective_hidden"] is False

    # 原始存入的字段应该原样保留。
    for key, value in record.items():
        assert result[key] == value
