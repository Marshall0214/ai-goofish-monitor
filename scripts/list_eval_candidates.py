"""从本地 SQLite 库里挑一批历史商品，生成待人工标注的 CSV 模板。

配合 scripts/eval_ai_recommendation.py 使用：
    1. python scripts/list_eval_candidates.py --limit 40
    2. 打开 eval/labels.csv，逐条核对 link，在 expected_recommend 列填 true/false
    3. python scripts/eval_ai_recommendation.py eval/labels.csv

候选商品不要求当初是被 AI 分析过的——评测脚本会用今天的 prompt 重新跑一遍分析，
所以关键词推荐（未经 AI 判断）的商品同样能用来测"如果当初让 AI 来判，会判成什么"。
默认按原始 is_recommended 字段各挑一半，仅用于让候选样本更多样，不代表任何结论。

重要：expected_recommend 请你回看当时保存的标题/价格/卖家信息，重新做一次真实判断。
不要用商品当前是否已下架、已卖出、或被你事后加进黑名单屏蔽来代替判断——这些是商品
后续的状态变化或屏蔽规则命中，跟"这条商品信息本身值不值得推荐"是两回事（比如已卖出
反而可能说明当初的推荐是对的）。current_ai_verdict / analysis_source / status 这几列
只是给你参考上下文，不是标签来源。

注意：item_id 是十几位的长数字，如果用 Excel 打开这份 CSV 编辑，Excel 会把它当成
数字自动转成科学计数法（比如 1234567890123 显示成 1.23E+12），精度一截断就再也
找不回来了，评测脚本会因为查不到这个 ID 而把整条跳过。为此 item_id 这一列写入时
会带一个前导单引号（Excel 识别"强制按文本处理"的标准写法），eval_ai_recommendation.py
读取时会自动去掉这个引号——正常情况下不用你手动处理，只是如果你用的不是 Excel、
而是别的工具打开这份 CSV，看到 item_id 前面多了个 ' 不用奇怪。

必须在真实积累了抓取数据的部署环境下运行——一个刚初始化的空数据库挑不出候选商品。
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage  # noqa: E402
from src.infrastructure.persistence.sqlite_connection import sqlite_connection  # noqa: E402


FIELDNAMES = [
    "item_id", "task_name", "title", "price_display",
    "current_ai_verdict", "analysis_source", "status",
    "link", "expected_recommend", "note",
]


def fetch_candidates(task_name: str | None, per_bucket: int) -> list[dict]:
    """挑候选商品，不限定当初的判断方式（关键词/AI）或当前状态（在架/下架/已屏蔽）。

    按 is_recommended 各挑一半只是为了让候选样本更多样（不全是清一色"推荐"），
    不代表这个字段本身就是可信的评测依据。
    """
    bootstrap_sqlite_storage()
    where = "1 = 1"
    params: list = []
    if task_name:
        where += " AND task_name = ?"
        params.append(task_name)

    rows: list[dict] = []
    with sqlite_connection() as conn:
        for verdict in (1, 0):
            query = (
                "SELECT item_id, task_name, title, price_display, link, "
                "is_recommended, analysis_source, status "
                f"FROM result_items WHERE {where} AND is_recommended = ? "
                "ORDER BY crawl_time DESC LIMIT ?"
            )
            for row in conn.execute(query, (*params, verdict, per_bucket)).fetchall():
                rows.append(dict(row))
    return rows


def write_candidates_csv(candidates: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in candidates:
            writer.writerow(
                {
                    # 前导单引号：让 Excel 把这一列强制当文本处理，避免长数字 ID
                    # 被自动转成科学计数法而精度丢失（eval_ai_recommendation.py
                    # 读取时会把这个引号去掉）。
                    "item_id": f"'{row['item_id']}",
                    "task_name": row["task_name"],
                    "title": row["title"],
                    "price_display": row["price_display"],
                    "current_ai_verdict": "推荐" if row["is_recommended"] else "不推荐",
                    "analysis_source": row["analysis_source"] or "keyword",
                    "status": row["status"],
                    "link": row["link"],
                    "expected_recommend": "",
                    "note": "",
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成待人工标注的 AI 评测候选商品 CSV。")
    parser.add_argument("--limit", type=int, default=40, help="候选商品总数上限，默认 40")
    parser.add_argument("--task-name", default=None, help="只从指定任务里挑，默认不限任务")
    parser.add_argument("--out", type=Path, default=Path("eval/labels.csv"), help="输出 CSV 路径")
    args = parser.parse_args()

    per_bucket = max(1, args.limit // 2)
    candidates = fetch_candidates(args.task_name, per_bucket)
    if not candidates:
        raise SystemExit(
            "没有查到任何商品记录——确认这是你真实积累了抓取数据的部署环境，"
            "而不是一个刚初始化的空数据库。"
        )

    write_candidates_csv(candidates, args.out)
    keyword_count = sum(1 for c in candidates if (c["analysis_source"] or "keyword") == "keyword")
    print(f"已生成 {len(candidates)} 条候选到 {args.out}（其中 {keyword_count} 条原本是关键词推荐，未经 AI 判断）。")
    print(
        "请逐条打开 link，回看标题/价格/卖家信息，在 expected_recommend 列填 true/false"
        "（依据商品本身值不值得买，不要参考当前是否下架/已售/被屏蔽），再运行 eval_ai_recommendation.py。"
    )


if __name__ == "__main__":
    main()
