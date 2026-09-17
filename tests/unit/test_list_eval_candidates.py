import asyncio
import csv

from scripts.list_eval_candidates import fetch_candidates, write_candidates_csv
from src.services.result_storage_service import save_result_record


def _make_record(*, item_id, is_recommended, analysis_source, task_name="MacBook"):
    return {
        "爬取时间": "2026-01-01T10:00:00",
        "搜索关键字": "macbook",
        "任务名称": task_name,
        "商品信息": {
            "商品ID": item_id,
            "商品标题": f"商品 {item_id}",
            "商品链接": f"https://www.goofish.com/item.htm?id={item_id}",
            "当前售价": "¥9999",
        },
        "ai_analysis": {
            "is_recommended": is_recommended,
            "analysis_source": analysis_source,
            "reason": "test",
        },
    }


def test_fetch_candidates_includes_keyword_recommended_items_not_just_ai(tmp_path, monkeypatch):
    # 关键场景：大部分商品是关键词推荐（从未经过 AI 判断），候选池不应该把它们排除在外——
    # 评测脚本本来就是要重新用 AI 分析一遍，不要求原始记录必须是 analysis_source='ai'。
    monkeypatch.chdir(tmp_path)
    assert asyncio.run(
        save_result_record(
            _make_record(item_id="1", is_recommended=True, analysis_source="keyword"), "macbook"
        )
    ) is True
    assert asyncio.run(
        save_result_record(
            _make_record(item_id="2", is_recommended=True, analysis_source="ai"), "macbook"
        )
    ) is True

    candidates = fetch_candidates(task_name=None, per_bucket=10)

    item_ids = {c["item_id"] for c in candidates}
    assert item_ids == {"1", "2"}
    sources = {c["item_id"]: c["analysis_source"] for c in candidates}
    assert sources == {"1": "keyword", "2": "ai"}


def test_fetch_candidates_filters_by_task_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert asyncio.run(
        save_result_record(
            _make_record(item_id="1", is_recommended=True, analysis_source="keyword", task_name="A"),
            "macbook-a",
        )
    ) is True
    assert asyncio.run(
        save_result_record(
            _make_record(item_id="2", is_recommended=True, analysis_source="keyword", task_name="B"),
            "macbook-b",
        )
    ) is True

    candidates = fetch_candidates(task_name="A", per_bucket=10)

    assert {c["item_id"] for c in candidates} == {"1"}


def test_write_candidates_csv_leaves_expected_recommend_blank_for_manual_labeling(tmp_path):
    out_path = tmp_path / "labels.csv"
    candidates = [
        {
            "item_id": "1", "task_name": "MacBook", "title": "t", "price_display": "¥1",
            "is_recommended": 1, "analysis_source": "keyword", "status": "active",
            "link": "https://example.com/1",
        }
    ]

    write_candidates_csv(candidates, out_path)

    content = out_path.read_text(encoding="utf-8-sig")
    assert "expected_recommend" in content.splitlines()[0]
    assert content.splitlines()[1].endswith(",,")  # expected_recommend,note 都留空


def test_write_candidates_csv_prefixes_item_id_to_defeat_excel_scientific_notation(tmp_path):
    # 长数字 item_id 被 Excel 打开时会自动转成科学计数法（1234567890123 -> 1.23E+12），
    # 精度一丢就再也找不回来。前导单引号是 Excel 识别"强制按文本"的标准写法。
    out_path = tmp_path / "labels.csv"
    candidates = [
        {
            "item_id": "1234567890123", "task_name": "MacBook", "title": "t", "price_display": "¥1",
            "is_recommended": 1, "analysis_source": "keyword", "status": "active",
            "link": "https://example.com/1",
        }
    ]

    write_candidates_csv(candidates, out_path)

    rows = list(csv.DictReader(out_path.open(encoding="utf-8-sig", newline="")))
    assert rows[0]["item_id"] == "'1234567890123"
