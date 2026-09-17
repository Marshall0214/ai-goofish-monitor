"""离线评测：用生产环境同一条 AI 分析函数，对人工标注样本算准确率/精确率/召回率。

背景：`src/ai_handler.get_ai_analysis` 是生产环境实际调用的分析函数（多模态、结构化
JSON 输出、卖家画像分析）。这个脚本不重新实现一套模拟逻辑，而是直接复用这个函数，
对一批你自己判断过"该不该推荐"的历史商品重新跑一遍今天的 prompt/模型，把 AI 的判断
和你的人工标注做对比，算出一个真实、可复现的准确率/精确率/召回率/F1，而不是空泛地说
"AI 分析很准"。

用法：
    1. 先跑 `python scripts/list_eval_candidates.py` 生成候选商品列表；
    2. 打开生成的 CSV，逐条核实商品链接，在 expected_recommend 列填你的真实判断
       （true/false，也支持 1/0、yes/no、是/否）；
    3. `python scripts/eval_ai_recommendation.py eval/labels.csv`

标注 CSV 需要的列：
    item_id             商品ID（对应 result_items.item_id）
    task_name           用哪个任务的 prompt/criteria 跑分析；留空则用数据库里记录的任务名
    expected_recommend  你的真实判断；留空的行会被跳过（方便标一半先跑一半）
    note                可选备注，不参与计算

必须在真实积累了抓取数据、且 .env 配置了可用 AI 接口的部署环境下运行——一个刚初始化
的空数据库跑不出任何有意义的数字。
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import ai_handler  # noqa: E402
from src.infrastructure.persistence.sqlite_task_repository import (  # noqa: E402
    find_task_by_name_sync,
)
from src.services.result_storage_service import (  # noqa: E402
    find_result_records_by_item_id,
)


TRUE_LABELS = {"1", "true", "t", "yes", "y", "是", "推荐"}
FALSE_LABELS = {"0", "false", "f", "no", "n", "否", "不推荐"}


class LabelParseError(ValueError):
    """标注文件里某个布尔值列既不是 true 也不是 false。"""


def parse_bool_label(raw: str, *, row_num: int, column: str) -> bool:
    value = (raw or "").strip().lower()
    if value in TRUE_LABELS:
        return True
    if value in FALSE_LABELS:
        return False
    raise LabelParseError(
        f"第 {row_num} 行 {column} 列的值 {raw!r} 无法识别为 true/false，"
        f"支持的写法：{sorted(TRUE_LABELS | FALSE_LABELS)}"
    )


@dataclass
class LabelRow:
    item_id: str
    task_name: str
    expected_recommend: bool
    note: str = ""


def load_labels(path: Path) -> list[LabelRow]:
    """读取标注 CSV。expected_recommend 留空的行会被跳过（打印提示，不报错），
    方便你标一部分先跑一部分。"""
    rows: list[LabelRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, raw_row in enumerate(reader, start=2):  # 第1行是表头
            # list_eval_candidates.py 生成时会给 item_id 加一个前导单引号，防止
            # Excel 把长数字 ID 转成科学计数法；这里读回来时去掉它。正常情况下
            # 经 Excel 编辑保存后这个引号已经被 Excel 自己吃掉了，这里是双重保险。
            item_id = (raw_row.get("item_id") or "").strip().lstrip("'")
            if not item_id:
                continue
            expected_raw = (raw_row.get("expected_recommend") or "").strip()
            if not expected_raw:
                print(f"[跳过] 第 {i} 行 item_id={item_id} 还没填 expected_recommend。")
                continue
            expected = parse_bool_label(expected_raw, row_num=i, column="expected_recommend")
            rows.append(
                LabelRow(
                    item_id=item_id,
                    task_name=(raw_row.get("task_name") or "").strip(),
                    expected_recommend=expected,
                    note=(raw_row.get("note") or "").strip(),
                )
            )
    return rows


@dataclass
class EvalOutcome:
    item_id: str
    task_name: str
    title: str
    expected: bool
    predicted: Optional[bool]  # None = AI 分析失败/商品找不到，不计入指标
    ai_reason: str = ""
    error: str = ""


def compute_metrics(outcomes: list[EvalOutcome]) -> dict:
    """纯逻辑：只看 expected/predicted，不碰数据库和网络，方便单测。"""
    scored = [o for o in outcomes if o.predicted is not None]
    skipped = len(outcomes) - len(scored)

    tp = sum(1 for o in scored if o.expected and o.predicted)
    tn = sum(1 for o in scored if not o.expected and not o.predicted)
    fp = sum(1 for o in scored if not o.expected and o.predicted)
    fn = sum(1 for o in scored if o.expected and not o.predicted)

    total = len(scored)
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "total_labeled": len(outcomes),
        "scored": total,
        "skipped_ai_failed": skipped,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _compose_prompt_text(task) -> str:
    """复刻 spider_v2.py 里 base_prompt + criteria 的组装逻辑，保证跑的是生产同款 prompt。"""
    base_prompt = Path(task.ai_prompt_base_file).read_text(encoding="utf-8")
    criteria_text = Path(task.ai_prompt_criteria_file).read_text(encoding="utf-8")
    return base_prompt.replace("{{CRITERIA_SECTION}}", criteria_text)


async def _resolve_record_and_task(row: LabelRow):
    records = await find_result_records_by_item_id(row.item_id)
    if not records:
        raise LookupError(f"商品ID {row.item_id} 在本地数据库里找不到（是否在另一个部署环境？）")

    if row.task_name:
        record = next((r for r in records if r.get("任务名称") == row.task_name), None)
        if record is None:
            actual = sorted({r.get("任务名称") for r in records})
            raise LookupError(
                f"商品ID {row.item_id} 存在，但没有任务 {row.task_name!r} 下的记录"
                f"（实际任务名：{actual}）"
            )
    else:
        record = records[0]

    task_name = row.task_name or record.get("任务名称") or ""
    task = find_task_by_name_sync(task_name) if task_name else None
    if task is None:
        raise LookupError(f"找不到任务 {task_name!r} 的配置（prompt/criteria 文件路径），无法组装 prompt。")
    return record, task


async def evaluate_one(row: LabelRow, *, download_images: bool, keep_images: bool) -> EvalOutcome:
    title = ""
    task_name_for_report = row.task_name
    try:
        record, task = await _resolve_record_and_task(row)
        task_name_for_report = task.task_name
        title = (record.get("商品信息", {}) or {}).get("商品标题", "")
        prompt_text = _compose_prompt_text(task)

        image_paths: list[str] = []
        if download_images and task.analyze_images:
            item_data = record.get("商品信息", {}) or {}
            image_urls = item_data.get("商品图片列表", [])
            product_id = item_data.get("商品ID", row.item_id)
            if image_urls:
                image_paths = await ai_handler.download_all_images(
                    product_id, image_urls, task_name=f"eval_{task.task_name}"
                )

        try:
            ai_result = await ai_handler.get_ai_analysis(record, image_paths, prompt_text)
        finally:
            if image_paths and not keep_images:
                for p in image_paths:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass

        if not ai_result:
            return EvalOutcome(
                item_id=row.item_id,
                task_name=task_name_for_report,
                title=title,
                expected=row.expected_recommend,
                predicted=None,
                error="AI analysis returned None after retries.",
            )

        return EvalOutcome(
            item_id=row.item_id,
            task_name=task_name_for_report,
            title=title,
            expected=row.expected_recommend,
            predicted=bool(ai_result.get("is_recommended")),
            ai_reason=str(ai_result.get("reason", "")),
        )
    except LookupError as exc:
        return EvalOutcome(
            item_id=row.item_id, task_name=task_name_for_report, title=title,
            expected=row.expected_recommend, predicted=None, error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - 评测脚本要把任何异常都记成一条失败，不中断整批
        return EvalOutcome(
            item_id=row.item_id, task_name=task_name_for_report, title=title,
            expected=row.expected_recommend, predicted=None,
            error=f"{type(exc).__name__}: {exc}",
        )


async def run_eval(
    labels_path: Path, *, download_images: bool, keep_images: bool, concurrency: int
) -> list[EvalOutcome]:
    if ai_handler.client is None:
        raise SystemExit(
            "AI 客户端未初始化（检查 .env 里 OPENAI_API_KEY / OPENAI_BASE_URL 是否配置），"
            "无法跑真实评测。"
        )

    rows = load_labels(labels_path)
    if not rows:
        raise SystemExit(f"{labels_path} 里没有可用的标注行（检查 item_id / expected_recommend 是否填了）。")

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(row: LabelRow) -> EvalOutcome:
        async with semaphore:
            return await evaluate_one(row, download_images=download_images, keep_images=keep_images)

    return list(await asyncio.gather(*[_guarded(r) for r in rows]))


def _print_report(outcomes: list[EvalOutcome], metrics: dict) -> None:
    print(
        f"\n标注样本共 {metrics['total_labeled']} 条，"
        f"{metrics['skipped_ai_failed']} 条因 AI 分析失败/商品缺失被跳过，"
        f"实际计入指标 {metrics['scored']} 条。\n"
    )
    print(f"准确率 accuracy:  {metrics['accuracy']:.1%}")
    print(f"精确率 precision: {metrics['precision']:.1%}")
    print(f"召回率 recall:    {metrics['recall']:.1%}")
    print(f"F1:              {metrics['f1']:.1%}")
    print(
        f"混淆矩阵: TP={metrics['tp']} FP={metrics['fp']} "
        f"TN={metrics['tn']} FN={metrics['fn']}\n"
    )

    mismatches = [o for o in outcomes if o.predicted is not None and o.predicted != o.expected]
    if mismatches:
        print(f"不一致的 {len(mismatches)} 条（建议优先复核）：")
        for o in mismatches:
            print(
                f"  - [{o.item_id}] {o.title[:40]!r} "
                f"人工={o.expected} AI={o.predicted}  AI理由: {o.ai_reason[:80]}"
            )

    failures = [o for o in outcomes if o.predicted is None]
    if failures:
        print(f"\n跳过的 {len(failures)} 条（AI 分析失败/商品未找到）：")
        for o in failures:
            print(f"  - [{o.item_id}] {o.error}")


def _write_report_json(outcomes: list[EvalOutcome], metrics: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metrics": metrics,
        "results": [
            {
                "item_id": o.item_id,
                "task_name": o.task_name,
                "title": o.title,
                "expected": o.expected,
                "predicted": o.predicted,
                "ai_reason": o.ai_reason,
                "error": o.error,
            }
            for o in outcomes
        ],
    }
    out_path = out_dir / "report.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用生产环境同款 AI 分析函数，对人工标注样本算准确率/精确率/召回率。"
    )
    parser.add_argument("labels", type=Path, help="标注 CSV 文件路径，例如 eval/labels.csv")
    parser.add_argument(
        "--no-images", action="store_true",
        help="不重新下载图片，纯文本评测（更快更省，但会低估开了多模态分析的任务的真实表现）",
    )
    parser.add_argument("--keep-images", action="store_true", help="评测后保留下载的图片，不自动删除")
    parser.add_argument("--concurrency", type=int, default=3, help="并发调用 AI 的数量，默认 3")
    parser.add_argument("--out-dir", type=Path, default=Path("eval"), help="report.json 输出目录，默认 eval/")
    args = parser.parse_args()

    outcomes = asyncio.run(
        run_eval(
            args.labels,
            download_images=not args.no_images,
            keep_images=args.keep_images,
            concurrency=args.concurrency,
        )
    )
    metrics = compute_metrics(outcomes)
    _print_report(outcomes, metrics)
    out_path = _write_report_json(outcomes, metrics, args.out_dir)
    print(f"\n完整结果已写入 {out_path}")


if __name__ == "__main__":
    main()
