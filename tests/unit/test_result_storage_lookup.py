import asyncio

from src.services.result_storage_service import (
    find_result_records_by_item_id,
    save_result_record,
)


def _make_record(*, item_id, task_name, keyword="sony a7m4", title="Sony A7M4 单机"):
    return {
        "爬取时间": "2026-01-01T10:00:00",
        "搜索关键字": keyword,
        "任务名称": task_name,
        "商品信息": {
            "商品ID": item_id,
            "商品标题": title,
            "商品链接": f"https://www.goofish.com/item.htm?id={item_id}",
            "当前售价": "¥10000",
        },
        "ai_analysis": {
            "is_recommended": True,
            "analysis_source": "ai",
            "reason": "符合要求",
        },
    }


def test_find_result_records_by_item_id_returns_empty_when_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    records = asyncio.run(find_result_records_by_item_id("does-not-exist"))

    assert records == []


def test_find_result_records_by_item_id_returns_stored_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    record = _make_record(item_id="2001", task_name="Sony 监控")
    assert asyncio.run(save_result_record(record, "sony a7m4")) is True

    records = asyncio.run(find_result_records_by_item_id("2001"))

    assert len(records) == 1
    assert records[0]["商品信息"]["商品ID"] == "2001"
    assert records[0]["任务名称"] == "Sony 监控"


def test_find_result_records_by_item_id_returns_all_matches_across_tasks(tmp_path, monkeypatch):
    # 同一个商品ID理论上可能在不同关键词/任务下各自入库一份（result_filename 不同），
    # 查询应该把所有命中都返回，由调用方按 task_name 自行消歧。
    monkeypatch.chdir(tmp_path)
    record_a = _make_record(item_id="3001", task_name="任务A", keyword="keyword-a")
    record_b = _make_record(item_id="3001", task_name="任务B", keyword="keyword-b")
    assert asyncio.run(save_result_record(record_a, "keyword-a")) is True
    assert asyncio.run(save_result_record(record_b, "keyword-b")) is True

    records = asyncio.run(find_result_records_by_item_id("3001"))

    task_names = {r["任务名称"] for r in records}
    assert task_names == {"任务A", "任务B"}
